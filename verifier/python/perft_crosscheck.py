#!/usr/bin/env python3
"""Cross-check engine perft against python-chess."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import chess

# Known perft suites: (name, fen, depths)
BASE_CASES = [
    (
        "startpos",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        [1, 2, 3, 4, 5, 6],
    ),
    (
        "kiwipete",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        [1, 2, 3, 4],
    ),
]

SMOKE_DEPTHS = {
    "startpos": [1, 2, 3],
    "kiwipete": [1, 2],
    "default": [1, 2],
}


# EPD files used for search/eval regression — not perft reference suites.
SKIP_PERFT_EPD = {"tactical.epd"}


def load_epd_cases(positions_dir: Path, smoke: bool) -> list[tuple[str, str, list[int]]]:
    cases: list[tuple[str, str, list[int]]] = []
    if not positions_dir.exists():
        return cases
    for epd in sorted(positions_dir.glob("*.epd")):
        if epd.name in SKIP_PERFT_EPD:
            continue
        for line in epd.read_text().splitlines():
            fen = line.strip()
            if not fen or fen.startswith("#") or " " not in fen:
                continue
            depths = SMOKE_DEPTHS["default"] if smoke else [1, 2, 3, 4]
            cases.append((f"{epd.stem}:{fen[:20]}", fen, depths))
    return cases


def engine_perft(engine: str, depth: int, fen: str | None = None) -> int:
    cmd = [engine, "perft", str(depth)]
    if fen:
        cmd.append(fen)
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=600)
    return int(out.strip().split()[-1])


def python_perft(board: chess.Board, depth: int) -> int:
    nodes = 0

    def recurse(b: chess.Board, d: int) -> None:
        nonlocal nodes
        if d == 0:
            nodes += 1
            return
        for move in b.legal_moves:
            b.push(move)
            recurse(b, d - 1)
            b.pop()

    recurse(board, depth)
    return nodes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--depth", type=int, default=6, help="Max depth for deep mode")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    cases = list(BASE_CASES)
    positions_dir = Path(__file__).resolve().parents[1] / "positions"
    cases.extend(load_epd_cases(positions_dir, args.smoke))

    for name, fen, depths in cases:
        if args.smoke:
            key = name if name in SMOKE_DEPTHS else "default"
            depths = SMOKE_DEPTHS.get(key, SMOKE_DEPTHS["default"])
        else:
            depths = [d for d in depths if d <= args.depth]

        board = chess.Board(fen)
        for depth in depths:
            want = python_perft(board, depth)
            got = engine_perft(args.engine, depth, fen)
            if got != want:
                print(
                    f"perft_crosscheck FAIL {name} depth={depth} engine={got} python={want}",
                    file=sys.stderr,
                )
                return 1
            print(f"  OK {name} depth={depth} nodes={got}")

    print("perft_crosscheck: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
