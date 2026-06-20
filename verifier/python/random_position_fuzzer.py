#!/usr/bin/env python3
"""Random legal self-play fuzz test."""

from __future__ import annotations

import argparse
import random
import sys

import chess
import chess.engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--games", type=int, default=5)
    parser.add_argument("--max-plies", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    try:
        with chess.engine.SimpleEngine.popen_uci(args.engine) as eng:
            for game in range(args.games):
                board = chess.Board()
                plies = rng.randint(20, args.max_plies)
                for _ in range(plies):
                    if board.is_game_over():
                        break
                    result = eng.play(board, chess.engine.Limit(depth=1))
                    if result.move is None or result.move not in board.legal_moves:
                        raise RuntimeError(
                            f"game {game} illegal move {result.move} in {board.fen()}"
                        )
                    board.push(result.move)
    except Exception as exc:
        print(f"random_position_fuzzer: FAIL {exc}", file=sys.stderr)
        return 1

    print(f"random_position_fuzzer: PASS ({args.games} games, seed={args.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
