#!/usr/bin/env python3
"""Minimal UCI bot that plays random legal moves — gauntlet opponent."""

from __future__ import annotations

import random
import sys

import chess
import chess.engine


def main() -> None:
    random.seed(42)
    board = chess.Board()
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if line == "uci":
            print("id name random_uci_bot")
            print("id author labzero-verifier")
            print("uciok", flush=True)
        elif line == "isready":
            print("readyok", flush=True)
        elif line == "ucinewgame":
            board = chess.Board()
        elif line.startswith("position "):
            parts = line.split()
            if "startpos" in parts:
                board = chess.Board()
                if "moves" in parts:
                    idx = parts.index("moves") + 1
                    for uci in parts[idx:]:
                        board.push(chess.Move.from_uci(uci))
            elif "fen" in parts:
                idx = parts.index("fen") + 1
                fen_parts = []
                while idx < len(parts) and parts[idx] != "moves":
                    fen_parts.append(parts[idx])
                    idx += 1
                board = chess.Board(" ".join(fen_parts))
                if idx < len(parts) and parts[idx] == "moves":
                    idx += 1
                    while idx < len(parts):
                        board.push(chess.Move.from_uci(parts[idx]))
                        idx += 1
        elif line.startswith("go"):
            moves = list(board.legal_moves)
            if not moves:
                print("bestmove 0000", flush=True)
            else:
                mv = random.choice(moves)
                print(f"bestmove {mv.uci()}", flush=True)
        elif line == "stop":
            pass
        elif line == "quit":
            break


if __name__ == "__main__":
    main()
