#!/usr/bin/env python3
"""Legality oracle: engine bestmove must be legal vs python-chess."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chess
import chess.engine

EXTRA_FENS = [
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "4k3/8/8/8/8/8/8/4K3 w - - 0 1",
]


def load_epd_boards(positions_dir: Path) -> list[chess.Board]:
    boards: list[chess.Board] = []
    if not positions_dir.exists():
        return boards
    for epd in sorted(positions_dir.glob("*.epd")):
        for line in epd.read_text().splitlines():
            fen = line.strip()
            if not fen or fen.startswith("#") or " " not in fen:
                continue
            boards.append(chess.Board(fen))
    return boards


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    boards = [
        chess.Board(),
        chess.Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"),
        chess.Board("n1n5/PPPk4/8/8/8/8/4Kppp/5NN1 b - - 0 1"),
    ]
    if not args.smoke:
        boards.extend(chess.Board(fen) for fen in EXTRA_FENS)
        boards.extend(load_epd_boards(Path(__file__).resolve().parents[1] / "positions"))

    with chess.engine.SimpleEngine.popen_uci(args.engine) as eng:
        for board in boards:
            if board.is_game_over():
                continue
            result = eng.play(board, chess.engine.Limit(depth=2))
            if result.move is None or result.move not in board.legal_moves:
                print(
                    f"legality_oracle FAIL illegal {result.move} in {board.fen()}",
                    file=sys.stderr,
                )
                return 1

    print(f"legality_oracle: PASS ({len(boards)} positions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
