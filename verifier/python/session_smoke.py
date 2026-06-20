#!/usr/bin/env python3
import chess
import chess.engine
import sys

eng_path = sys.argv[1]
with chess.engine.SimpleEngine.popen_uci(eng_path) as eng:
    board = chess.Board()
    for ply in range(80):
        if board.is_game_over():
            print("game over at ply", ply)
            break
        r = eng.play(board, chess.engine.Limit(depth=1))
        if r.move not in board.legal_moves:
            print("FAIL ply", ply, "move", r.move, "fen", board.fen())
            sys.exit(1)
        board.push(r.move)
    print("done")
