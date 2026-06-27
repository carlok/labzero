#!/usr/bin/env python3
"""Ladder-oriented Lichess result summaries for LabZeroBot0."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

LICHESS_API = "https://lichess.org"
DECISIVE_OR_DRAW_STATUSES = {
    "mate",
    "resign",
    "outoftime",
    "timeout",
    "draw",
    "stalemate",
}


@dataclass(frozen=True)
class FinishedGame:
    game_id: str
    created_at: int
    result: str
    status: str
    color: str
    opponent: str
    opponent_rating: int | None
    bot_rating: int | None


def user_name(player: dict[str, Any]) -> str:
    user = player.get("user") or {}
    return str(user.get("name") or user.get("username") or user.get("id") or "unknown")


def player_rating(player: dict[str, Any]) -> int | None:
    try:
        return int(player.get("rating"))
    except (TypeError, ValueError):
        return None


def is_target_player(player: dict[str, Any], username: str) -> bool:
    wanted = username.lower()
    user = player.get("user") or {}
    return wanted in {
        str(user.get("id") or "").lower(),
        str(user.get("name") or "").lower(),
        str(user.get("username") or "").lower(),
    }


def is_target_clock(game: dict[str, Any], initial: int, increment: int) -> bool:
    clock = game.get("clock") or {}
    try:
        return int(clock.get("initial")) == initial and int(clock.get("increment")) == increment
    except (TypeError, ValueError):
        return False


def is_full_result_status(status: str, winner: str | None) -> bool:
    if winner in {"white", "black"}:
        return status in DECISIVE_OR_DRAW_STATUSES
    return status in {"draw", "stalemate"}


def parse_finished_game(game: dict[str, Any], username: str, initial: int, increment: int) -> FinishedGame | None:
    if not game.get("rated", False):
        return None
    if game.get("perf") != "blitz":
        return None
    if game.get("variant") != "standard":
        return None
    if not is_target_clock(game, initial, increment):
        return None

    players = game.get("players") or {}
    white = players.get("white") or {}
    black = players.get("black") or {}
    if is_target_player(white, username):
        color = "white"
        bot_player = white
        opponent_player = black
    elif is_target_player(black, username):
        color = "black"
        bot_player = black
        opponent_player = white
    else:
        return None

    status = str(game.get("status") or "")
    winner = game.get("winner")
    if not is_full_result_status(status, winner):
        return None

    if winner is None:
        result = "D"
    elif winner == color:
        result = "W"
    else:
        result = "L"

    return FinishedGame(
        game_id=str(game.get("id") or ""),
        created_at=int(game.get("createdAt") or 0),
        result=result,
        status=status,
        color=color,
        opponent=user_name(opponent_player),
        opponent_rating=player_rating(opponent_player),
        bot_rating=player_rating(bot_player),
    )


def fetch_games(username: str, fetch_max: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "max": str(fetch_max),
            "rated": "true",
            "perfType": "blitz",
            "moves": "false",
            "pgnInJson": "false",
            "opening": "false",
        }
    )
    url = f"{LICHESS_API}/api/games/user/{urllib.parse.quote(username)}?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/x-ndjson"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return [json.loads(line) for raw in resp for line in [raw.decode().strip()] if line]


def summarize(games: list[FinishedGame]) -> dict[str, Any]:
    counts = {"W": 0, "D": 0, "L": 0}
    ratings = []
    for game in games:
        counts[game.result] += 1
        if game.opponent_rating is not None:
            ratings.append(game.opponent_rating)
    avg_opp = round(sum(ratings) / len(ratings)) if ratings else None
    score = counts["W"] + 0.5 * counts["D"]
    return {
        "games": len(games),
        "wins": counts["W"],
        "draws": counts["D"],
        "losses": counts["L"],
        "score": score,
        "score_pct": round(100 * score / len(games), 1) if games else 0.0,
        "avg_opp": avg_opp,
    }


def chunks(games: list[FinishedGame], size: int) -> list[list[FinishedGame]]:
    return [games[i : i + size] for i in range(0, len(games), size)]


def format_summary(label: str, games: list[FinishedGame]) -> str:
    summary = summarize(games)
    avg = "-" if summary["avg_opp"] is None else str(summary["avg_opp"])
    first = games[0].game_id if games else "-"
    last = games[-1].game_id if games else "-"
    return (
        f"{label}: {summary['games']} games "
        f"{summary['wins']}W-{summary['draws']}D-{summary['losses']}L "
        f"score={summary['score']:.1f}/{summary['games']} ({summary['score_pct']}%) "
        f"avg_opp={avg} games={first}..{last}"
    )


def build_report(games: list[FinishedGame], block_size: int) -> str:
    if not games:
        return "No completed rated standard blitz games matched the requested clock."
    lines = [format_summary("window", games)]
    for idx, block in enumerate(chunks(games, block_size), 1):
        lines.append(format_summary(f"round {idx}", block))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize recent completed 3+2 rated blitz W/D/L blocks.")
    parser.add_argument("--user", default="LabZeroBot0")
    parser.add_argument("--games", type=int, default=30, help="number of completed matching games to report")
    parser.add_argument("--fetch", type=int, default=120, help="recent rated blitz games to fetch before filtering")
    parser.add_argument("--block", type=int, default=10, help="round size for ladder reporting")
    parser.add_argument("--clock-limit", type=int, default=180)
    parser.add_argument("--clock-increment", type=int, default=2)
    args = parser.parse_args(argv)

    if args.games <= 0 or args.fetch <= 0 or args.block <= 0:
        parser.error("--games, --fetch, and --block must be positive")

    raw_games = fetch_games(args.user, args.fetch)
    finished = [
        parsed
        for game in raw_games
        if (parsed := parse_finished_game(game, args.user, args.clock_limit, args.clock_increment)) is not None
    ]
    recent = list(reversed(finished[: args.games]))
    print(build_report(recent, args.block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

