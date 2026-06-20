#!/usr/bin/env python3
"""UCI protocol smoke tester for labzero engine."""

from __future__ import annotations

import argparse
import sys

import chess
import chess.engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", help="Path to labzero binary")
    args = parser.parse_args()

    try:
        with chess.engine.SimpleEngine.popen_uci(args.engine) as eng:
            if "labzero" not in eng.id.get("name", "").lower():
                print("FAIL: unexpected engine name", eng.id, file=sys.stderr)
                return 1

            board = chess.Board()
            result = eng.play(board, chess.engine.Limit(depth=1))
            if result.move is None:
                print("FAIL: no move returned", file=sys.stderr)
                return 1
            if result.move not in board.legal_moves:
                print("FAIL: illegal move", result.move, file=sys.stderr)
                return 1

            board.push(result.move)
            result2 = eng.play(board, chess.engine.Limit(depth=1))
            if result2.move is None or result2.move not in board.legal_moves:
                print("FAIL: illegal follow-up move", file=sys.stderr)
                return 1

        print("uci_protocol_tester: PASS")
        return 0
    except chess.engine.EngineError as exc:
        print(f"FAIL: engine error {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
