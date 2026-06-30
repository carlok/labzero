#!/usr/bin/env python3
"""Train an experimental oracle companion from move-quality JSONL.

This script is tooling only. It trains a medium sparse board model from
Stockfish-oracle labels and writes a PyTorch checkpoint/report. It does not
export an engine-loadable file and is not enabled by LabZero automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import chess
except ModuleNotFoundError:
    root = Path(__file__).resolve().parents[1]
    for candidate in (root / ".venv-host-test/bin/python", root / "lichess_bot/.venv/bin/python"):
        if candidate.exists() and Path(sys.executable) != candidate:
            os.execv(str(candidate), [str(candidate), *sys.argv])
    raise

sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy_format as fmt  # noqa: E402


def pick_device(requested: str):
    import torch

    if requested != "auto":
        return torch.device(requested)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def best_move_label(record: dict) -> dict | None:
    moves = record.get("moves", [])
    if not moves:
        return None
    return min(moves, key=lambda item: int(item.get("rank", 999999)))


def load_dataset(paths: list[str]):
    feats, policy_targets, value_targets = [], [], []
    skipped = 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if record.get("schema") != "labzero.move_quality.v1":
                        skipped += 1
                        continue
                    board = chess.Board(record["fen"])
                    best = best_move_label(record)
                    if best is None:
                        skipped += 1
                        continue
                    move = chess.Move.from_uci(str(best["uci"]))
                    if move not in board.legal_moves:
                        skipped += 1
                        continue
                    feats.append(fmt.active_indices_stm(board))
                    policy_targets.append(fmt.move_index(move.from_square, move.to_square))
                    value_targets.append(float(best.get("utility", 0.5)))
                except (KeyError, ValueError, json.JSONDecodeError):
                    skipped += 1
    if skipped:
        print(f"skipped {skipped} unusable record(s)", file=sys.stderr)
    return feats, policy_targets, value_targets


class OracleCompanion:
    @staticmethod
    def build(hidden: int):
        import torch
        import torch.nn as nn

        class Net(nn.Module):
            def __init__(self, h: int):
                super().__init__()
                self.hidden = h
                self.emb = nn.EmbeddingBag(fmt.NUM_FEATURES, h, mode="sum")
                self.bias = nn.Parameter(torch.zeros(h))
                self.policy = nn.Linear(h, fmt.NUM_MOVES)
                self.value = nn.Linear(h, 1)

            def forward(self, flat, offsets):
                acc = self.emb(flat, offsets) + self.bias
                act = torch.clamp(acc, 0.0, 1.0)
                return self.policy(act), torch.sigmoid(self.value(act)).squeeze(1)

        return Net(hidden)


def make_bag(batch_feats, device):
    import torch

    flat = [idx for feats in batch_feats for idx in feats]
    offsets = [0]
    for feats in batch_feats[:-1]:
        offsets.append(offsets[-1] + len(feats))
    return (
        torch.tensor(flat, dtype=torch.long, device=device),
        torch.tensor(offsets, dtype=torch.long, device=device),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", nargs="+", required=True)
    parser.add_argument("--hidden", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--out", default="data/oracle/oracle_companion.pt")
    parser.add_argument("--report", default="docs/oracle/oracle_companion.md")
    args = parser.parse_args()

    try:
        import torch
        import torch.nn.functional as F
    except ImportError:
        root = Path(__file__).resolve().parents[1]
        candidate = root / ".venv-host-test/bin/python"
        if candidate.exists() and Path(sys.executable) != candidate:
            os.execv(str(candidate), [str(candidate), *sys.argv])
        print("error: PyTorch not installed; install torch to train the oracle companion", file=sys.stderr)
        return 2

    feats, policy_targets, value_targets = load_dataset(args.data)
    if not feats:
        print("no oracle training records found", file=sys.stderr)
        return 1

    device = pick_device(args.device)
    model = OracleCompanion.build(args.hidden).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    n = len(feats)
    policy_t = torch.tensor(policy_targets, dtype=torch.long, device=device)
    value_t = torch.tensor(value_targets, dtype=torch.float32, device=device)
    losses: list[float] = []

    for epoch in range(args.epochs):
        perm = torch.randperm(n)
        total = 0.0
        for start in range(0, n, args.batch):
            sel = perm[start : start + args.batch].tolist()
            flat, offsets = make_bag([feats[i] for i in sel], device)
            logits, value = model(flat, offsets)
            loss_policy = F.cross_entropy(logits, policy_t[sel])
            loss_value = F.mse_loss(value, value_t[sel])
            loss = loss_policy + loss_value
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss.item()) * len(sel)
        avg = total / n
        losses.append(avg)
        print(f"epoch {epoch + 1}/{args.epochs} loss={avg:.5f}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "schema": "labzero.oracle_companion.v1",
            "hidden": args.hidden,
            "samples": n,
            "model": model.state_dict(),
        },
        out_path,
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# Oracle Companion Smoke Report",
                "",
                f"- Samples: {n}",
                f"- Hidden: {args.hidden}",
                f"- Epochs: {args.epochs}",
                f"- Device: {device}",
                f"- Final loss: {losses[-1]:.5f}",
                "",
                "This checkpoint is tooling-only and is not loaded by LabZero.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_path}")
    print(f"report -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
