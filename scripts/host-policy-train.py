#!/usr/bin/env python3
"""Trainer for labzero policy nets (768->H->4096 from-to logits).

Reads policy-data lines `fen;best_uci;score;depth` from `labzero policydata`,
trains a sparse-input net, quantizes, and exports `LZP1` for `LABZERO_POLICY`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chess
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy_format as fmt  # noqa: E402


def pick_device(requested: str) -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_dataset(paths: list[str]):
    feats, targets = [], []
    bad = 0
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(";")
                if len(parts) != 4:
                    bad += 1
                    continue
                fen, uci, _score, _depth = parts
                try:
                    board = chess.Board(fen)
                    move = chess.Move.from_uci(uci)
                    if move not in board.legal_moves:
                        bad += 1
                        continue
                except (ValueError, IndexError):
                    bad += 1
                    continue
                idx = fmt.active_indices_stm(board)
                midx = fmt.move_index(move.from_square, move.to_square)
                feats.append(idx)
                targets.append(midx)
    if bad:
        print(f"skipped {bad} bad lines", file=sys.stderr)
    return feats, targets


class PolicyNet(nn.Module):
    def __init__(self, hidden: int):
        super().__init__()
        self.hidden = hidden
        self.w_in = nn.Embedding(fmt.NUM_FEATURES, hidden)
        self.b_in = nn.Parameter(torch.zeros(hidden))
        self.w_out = nn.Linear(hidden, fmt.NUM_MOVES, bias=True)

    def forward(self, feat_idx: list[list[int]]) -> torch.Tensor:
        batch = len(feat_idx)
        h = self.hidden
        acc = self.b_in.unsqueeze(0).expand(batch, h).clone()
        for b, indices in enumerate(feat_idx):
            if indices:
                idx_t = torch.tensor(indices, dtype=torch.long, device=acc.device)
                acc[b] += self.w_in(idx_t).sum(dim=0)
        act = torch.clamp(acc, 0.0, 1.0)
        return self.w_out(act)


def quantize(model: PolicyNet) -> dict:
    h = model.hidden
    w_in = (model.w_in.weight.detach().cpu() * fmt.QA).round().clamp(-32768, 32767).to(torch.int16)
    b_in = (model.b_in.detach().cpu() * fmt.QA).round().clamp(-2**31, 2**31 - 1).to(torch.int32)
    w_out = (model.w_out.weight.detach().cpu() * 64).round().clamp(-32768, 32767).to(torch.int16)
    b_out = (model.w_out.bias.detach().cpu() * 64).round().clamp(-2**31, 2**31 - 1).to(torch.int32)
    flat_w_in = [int(w_in[i, j]) for i in range(fmt.NUM_FEATURES) for j in range(h)]
    # nn.Linear stores weight as (out_features, in_features) = (NUM_MOVES, hidden).
    flat_w_out = [int(w_out[k, j]) for j in range(h) for k in range(fmt.NUM_MOVES)]
    return {
        "hidden": h,
        "w_in": flat_w_in,
        "b_in": [int(x) for x in b_in],
        "w_out": flat_w_out,
        "b_out": [int(x) for x in b_out],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Train labzero policy net")
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default="data/policy/train.ckpt")
    args = ap.parse_args()

    device = pick_device(args.device)
    print(f"device: {device}")

    feats, targets = load_dataset(args.data)
    if not feats:
        print("no training data", file=sys.stderr)
        return 1
    print(f"loaded {len(feats)} positions")

    model = PolicyNet(args.hidden).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    start_epoch = 0

    ckpt_path = Path(args.ckpt)
    if ckpt_path.exists():
        state = torch.load(ckpt_path, map_location=device)
        if state.get("hidden") == args.hidden:
            model.load_state_dict(state["model"])
            opt.load_state_dict(state["opt"])
            start_epoch = state["epoch"]
            print(f"resumed from {ckpt_path} at epoch {start_epoch}")
        else:
            print("checkpoint hidden size differs; starting fresh", file=sys.stderr)

    n = len(feats)
    for epoch in range(start_epoch, args.epochs):
        model.train()
        perm = torch.randperm(n, device=device)
        loss_sum = 0.0
        steps = 0
        for start in range(0, n, args.batch):
            idx = perm[start : start + args.batch].tolist()
            batch_feats = [feats[i] for i in idx]
            batch_t = torch.tensor([targets[i] for i in idx], device=device)
            logits = model(batch_feats)
            loss = F.cross_entropy(logits, batch_t)
            opt.zero_grad()
            loss.backward()
            opt.step()
            loss_sum += float(loss.item())
            steps += 1
        print(f"epoch {epoch + 1}/{args.epochs}  loss={loss_sum / max(steps, 1):.4f}")
        torch.save(
            {
                "model": model.state_dict(),
                "opt": opt.state_dict(),
                "epoch": epoch + 1,
                "hidden": args.hidden,
            },
            ckpt_path,
        )

    net = quantize(model)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(fmt.pack(net))
    print(f"wrote {out_path}  hidden={args.hidden}  samples={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
