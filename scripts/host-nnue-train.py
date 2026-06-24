#!/usr/bin/env python3
"""Portable (MPS/CUDA/CPU) trainer for labzero's original self-play NNUE.

Reads labzero self-play data (`fen;result;cp`, side-to-move relative, produced
by `labzero selfplay`), trains the two-perspective 768->H->1 net defined in
`engine/src/nnue.rs`, quantizes it, and exports an `LZN1` file the engine loads
via `LABZERO_NNUE` / the `NnueFile` UCI option. Verify any exported net against
the engine with `scripts/host-nnue-verify.sh` before trusting it.

Originality: trains ONLY on labzero's own self-play games and own search labels;
no external engine games or weights (docs/originality_policy.md).

Resumable: a checkpoint (model + optimizer + epoch) is written every epoch to
`--ckpt`; rerunning with the same `--ckpt` resumes from the last completed
epoch, so a shutdown loses at most one epoch.

Device: picks MPS (Apple Silicon) -> CUDA -> CPU automatically; the same code
runs on all three. Inference in the engine stays CPU-SIMD integer; the GPU is
only for training these weights.

    python scripts/host-nnue-train.py --data data/selfplay/sp.txt \
        --hidden 256 --epochs 30 --out data/nnue/net.nnue
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chess

# Shared feature/format/quantization definitions (single source of truth).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nnue_format as fmt  # noqa: E402

# Pawns->WDL logistic scale used for both the result and the cp label so the
# trained output `y` is in pawn units (the engine's integer path yields
# cp = 100*y). Not a strength knob; just keeps training self-consistent.
SIGMOID_SCALE_PAWNS = 4.0


def pick_device(requested: str):
    import torch

    if requested != "auto":
        return torch.device(requested)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_dataset(paths: list[str]):
    """Parse data lines into (stm_idx, opp_idx, target_wdl) python lists."""
    stm_idx, opp_idx, targets = [], [], []
    bad = 0
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(";")
                if len(parts) != 3:
                    bad += 1
                    continue
                fen, result, cp = parts
                try:
                    board = chess.Board(fen)
                    result = float(result)
                    cp = float(cp)
                except (ValueError, IndexError):
                    bad += 1
                    continue
                stm = board.turn
                opp = not stm
                stm_idx.append(fmt.active_indices(board, stm))
                opp_idx.append(fmt.active_indices(board, opp))
                # Blend game outcome with the search label, both stm-relative.
                import math

                wdl_cp = 1.0 / (1.0 + math.exp(-(cp / 100.0) / SIGMOID_SCALE_PAWNS))
                targets.append((result, wdl_cp))
    if bad:
        print(f"skipped {bad} malformed line(s)", file=sys.stderr)
    return stm_idx, opp_idx, targets


def make_bag(idx_lists, device):
    import torch

    flat = [i for sub in idx_lists for i in sub]
    offsets = [0]
    for sub in idx_lists[:-1]:
        offsets.append(offsets[-1] + len(sub))
    return (
        torch.tensor(flat, dtype=torch.long, device=device),
        torch.tensor(offsets, dtype=torch.long, device=device),
    )


def build_model(hidden: int):
    import torch
    import torch.nn as nn

    class Net(nn.Module):
        def __init__(self, h):
            super().__init__()
            # EmbeddingBag(mode='sum') == sparse W_in^T accumulation; one shared
            # table used for both perspectives, matching the engine.
            self.emb = nn.EmbeddingBag(fmt.NUM_FEATURES, h, mode="sum")
            self.b_in = nn.Parameter(torch.zeros(h))
            self.out = nn.Linear(2 * h, 1)
            self.h = h
            nn.init.uniform_(self.emb.weight, -0.1, 0.1)
            nn.init.uniform_(self.out.weight, -0.1, 0.1)

        def forward(self, stm_flat, stm_off, opp_flat, opp_off):
            a_stm = self.emb(stm_flat, stm_off) + self.b_in
            a_opp = self.emb(opp_flat, opp_off) + self.b_in
            h_stm = torch.clamp(a_stm, 0.0, 1.0)
            h_opp = torch.clamp(a_opp, 0.0, 1.0)
            cat = torch.cat([h_stm, h_opp], dim=1)
            return self.out(cat).squeeze(1)  # y, in pawns

    return Net(hidden)


def quantize_and_export(model, out_path: str):
    """Quantize the float model to integers and write the LZN1 file."""
    import torch

    with torch.no_grad():
        w = model.emb.weight.detach().cpu().tolist()  # [768][H]
        b1 = model.b_in.detach().cpu().tolist()  # [H]
        w2 = model.out.weight.detach().cpu().reshape(-1).tolist()  # [2H]
        b2 = float(model.out.bias.detach().cpu().item())
    h = model.h

    def clampi(x, lo, hi):
        return int(max(lo, min(hi, round(float(x)))))

    # idx-major flatten: w_in[idx*H + j] == w[idx][j]
    w_in = [clampi(w[idx][j] * fmt.QA, -32768, 32767) for idx in range(fmt.NUM_FEATURES) for j in range(h)]
    b_in = [clampi(b1[j] * fmt.QA, -(2**31), 2**31 - 1) for j in range(h)]
    w_out = [clampi(w2[k] * fmt.QW_OUT, -32768, 32767) for k in range(2 * h)]
    b_out = clampi(b2 * fmt.QA * fmt.QW_OUT, -(2**31), 2**31 - 1)
    net = {
        "hidden": h,
        "w_in": w_in,
        "b_in": b_in,
        "w_out": w_out,
        "b_out": b_out,
        "out_div": fmt.OUT_DIV,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(fmt.pack(net))
    print(f"exported quantized net hidden={h} -> {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", nargs="+", required=True, help="self-play data file(s)")
    ap.add_argument("--hidden", type=int, default=256)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=8192)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lambda-result", type=float, default=0.5,
                    help="weight on game result vs search cp label (0..1)")
    ap.add_argument("--out", default="data/nnue/net.nnue")
    ap.add_argument("--ckpt", default="data/nnue/train.ckpt")
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    try:
        import torch
        import torch.nn as nn
    except ImportError:
        print("error: PyTorch not installed. Install with 'pip install torch' "
              "(MPS wheels ship in the default macOS build).", file=sys.stderr)
        return 2

    device = pick_device(args.device)
    print(f"device: {device}")

    stm_idx, opp_idx, targets = load_dataset(args.data)
    n = len(targets)
    if n == 0:
        print("no training positions found", file=sys.stderr)
        return 1
    print(f"loaded {n} positions")

    lam = args.lambda_result
    y_target = torch.tensor(
        [lam * r + (1.0 - lam) * c for (r, c) in targets],
        dtype=torch.float32, device=device,
    )

    model = build_model(args.hidden).to(device)
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

    for epoch in range(start_epoch, args.epochs):
        model.train()
        perm = torch.randperm(n)
        total = 0.0
        for bstart in range(0, n, args.batch):
            sel = perm[bstart:bstart + args.batch].tolist()
            sf, so = make_bag([stm_idx[i] for i in sel], device)
            of, oo = make_bag([opp_idx[i] for i in sel], device)
            pred_y = model(sf, so, of, oo)
            pred_wdl = torch.sigmoid(pred_y / SIGMOID_SCALE_PAWNS)
            loss = nn.functional.mse_loss(pred_wdl, y_target[sel])
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(sel)
        avg = total / n
        print(f"epoch {epoch + 1}/{args.epochs} loss={avg:.5f}")
        torch.save(
            {"model": model.state_dict(), "opt": opt.state_dict(),
             "epoch": epoch + 1, "hidden": args.hidden},
            ckpt_path,
        )

    quantize_and_export(model, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
