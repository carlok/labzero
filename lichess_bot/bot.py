#!/usr/bin/env python3
"""Lichess Bot API bridge — UCI engine subprocess."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import berserk
import chess
import chess.engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lichess_bot")


def load_config(path: Path) -> dict:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
    with path.open("rb") as f:
        return tomllib.load(f)


def dry_run_test(engine_path: str, depth: int) -> None:
    """Simulate bot game loop locally without Lichess network."""
    log.info("dry_run: starting local UCI session")
    with chess.engine.SimpleEngine.popen_uci(engine_path) as eng:
        board = chess.Board()
        for ply in range(20):
            if board.is_game_over():
                break
            result = eng.play(board, chess.engine.Limit(depth=depth))
            if result.move not in board.legal_moves:
                raise RuntimeError(f"illegal move {result.move}")
            board.push(result.move)
    log.info("dry_run: PASS (20 plies)")


def run_bot(token: str, engine_path: str, depth: int, movetime_ms: int) -> None:
    session = berserk.TokenSession(token)
    client = berserk.Client(session)

    log.info("Bot online — waiting for games (Ctrl+C to stop)")
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        for event in client.board.stream_incoming_events():
            if event["type"] != "gameStart":
                continue
            game_id = event["game"]["id"]
            log.info("gameStart: %s", game_id)
            try:
                for event in client.board.stream_game_state(game_id):
                    if event["type"] != "gameFull" and event["type"] != "gameState":
                        continue
                    state = event.get("state", event)
                    moves = state.get("moves", "")
                    board = chess.Board()
                    if moves:
                        for uci in moves.split():
                            board.push_uci(uci)
                    if board.is_game_over():
                        break
                    if board.turn != chess.WHITE:
                        # Assume bot plays white; extend for black if needed
                        continue
                    limit = chess.engine.Limit(depth=depth, time=movetime_ms / 1000)
                    result = engine.play(board, limit)
                    if result.move is None:
                        log.error("no move for %s", game_id)
                        break
                    client.board.make_move(game_id, result.move.uci())
                    log.info("played %s in %s", result.move.uci(), game_id)
                    time.sleep(0.5)
            except Exception as exc:
                log.exception("game error %s: %s", game_id, exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="labzero Lichess bot bridge")
    parser.add_argument("--config", default="lichess_bot/config.toml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        config_path = Path("lichess_bot/config.example.toml")
    cfg = load_config(config_path)

    engine_path = os.environ.get("LABZERO_ENGINE", cfg.get("engine", "labzero"))
    depth = int(cfg.get("search_depth", 4))
    movetime_ms = int(cfg.get("movetime_ms", 2000))

    if args.dry_run or cfg.get("dry_run"):
        dry_run_test(engine_path, depth)
        return 0

    token = os.environ.get("LICHESS_TOKEN")
    if not token:
        log.error("Set LICHESS_TOKEN environment variable")
        return 1

    run_bot(token, engine_path, depth, movetime_ms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
