#!/usr/bin/env python3
"""Sidecar monitor for the online Lichess bot blitz population."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from lichess_bot import bot
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lichess_bot import bot


@dataclass
class RadarConfig:
    interval_sec: int
    min_blitz_games: int
    allow_provisional: bool
    notify_interval_min: int
    output_dir: str

    @classmethod
    def from_dict(cls, cfg: dict[str, Any]) -> "RadarConfig":
        return cls(
            interval_sec=max(10, int(cfg.get("radar_interval_sec", 60))),
            min_blitz_games=int(cfg.get("radar_min_blitz_games", cfg.get("min_blitz_games", 20))),
            allow_provisional=bool(cfg.get("radar_allow_provisional", cfg.get("allow_provisional", False))),
            notify_interval_min=max(0, int(cfg.get("radar_notify_interval_min", 60))),
            output_dir=bot.resolve_path(str(cfg.get("radar_output_dir", "lichess_bot/local/bot-radar"))),
        )


def eligible_blitz_bots(
    users: list[dict[str, Any]], min_games: int, allow_provisional: bool
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for user in users:
        perf = bot.blitz_perf(user)
        try:
            rating = int(perf.get("rating", 0) or 0)
            games = int(perf.get("games", 0) or 0)
        except (TypeError, ValueError):
            continue
        provisional = bool(perf.get("prov", False))
        if rating <= 0 or games < min_games:
            continue
        if provisional and not allow_provisional:
            continue
        rows.append(
            {
                "id": user.get("id"),
                "username": user.get("username") or user.get("name") or user.get("id"),
                "rating": rating,
                "games": games,
                "provisional": provisional,
            }
        )
    return rows


def percentile_for_rating(ratings: list[int], rating: int) -> float | None:
    if not ratings:
        return None
    below_or_equal = sum(1 for value in ratings if value <= rating)
    return round(100.0 * below_or_equal / len(ratings), 1)


def quantile(sorted_values: list[int], fraction: float) -> int | None:
    if not sorted_values:
        return None
    idx = round((len(sorted_values) - 1) * fraction)
    return sorted_values[idx]


def rating_buckets(ratings: list[int], width: int = 100) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for rating in ratings:
        lo = (rating // width) * width
        hi = lo + width - 1
        key = f"{lo}-{hi}"
        buckets[key] = buckets.get(key, 0) + 1
    return dict(sorted(buckets.items(), key=lambda item: int(item[0].split("-", 1)[0])))


def build_snapshot(users: list[dict[str, Any]], own_rating: int, cfg: RadarConfig) -> dict[str, Any]:
    rows = eligible_blitz_bots(users, cfg.min_blitz_games, cfg.allow_provisional)
    ratings = sorted(row["rating"] for row in rows)
    stronger = [row for row in rows if row["rating"] > own_rating]
    stronger.sort(key=lambda row: (row["rating"] - own_rating, str(row["username"]).lower()))
    weaker_or_equal = [row for row in rows if row["rating"] <= own_rating]

    stats = {
        "count": len(ratings),
        "min": ratings[0] if ratings else None,
        "max": ratings[-1] if ratings else None,
        "average": round(statistics.fmean(ratings), 1) if ratings else None,
        "median": round(statistics.median(ratings), 1) if ratings else None,
        "q25": quantile(ratings, 0.25),
        "q75": quantile(ratings, 0.75),
        "percentile": percentile_for_rating(ratings, own_rating),
        "below_or_equal": len(weaker_or_equal),
        "above": len(stronger),
        "buckets": rating_buckets(ratings),
        "nearest_stronger": stronger[:8],
    }
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "own_rating": own_rating,
        "filters": {
            "min_blitz_games": cfg.min_blitz_games,
            "allow_provisional": cfg.allow_provisional,
        },
        "stats": stats,
    }


def snapshot_path(output_dir: str) -> Path:
    now = dt.datetime.now(dt.timezone.utc)
    path = Path(output_dir) / f"{now.date().isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_snapshot(snapshot: dict[str, Any], output_dir: str) -> Path:
    path = snapshot_path(output_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, sort_keys=True) + "\n")
    return path


def format_snapshot(snapshot: dict[str, Any]) -> str:
    stats = snapshot["stats"]
    pct = stats["percentile"]
    pct_text = "n/a" if pct is None else f"{pct:.1f}th"
    nearest = stats["nearest_stronger"][:3]
    nearest_text = ", ".join(f"{row['username']} {row['rating']}" for row in nearest) or "none"
    return "\n".join(
        [
            "🤖 LabZero bot radar",
            f"own blitz: {snapshot['own_rating']}",
            f"online bots: {stats['count']} filtered",
            f"percentile: {pct_text} · above={stats['above']} · <=you={stats['below_or_equal']}",
            f"min/median/avg/max: {stats['min']} / {stats['median']} / {stats['average']} / {stats['max']}",
            f"q25/q75: {stats['q25']} / {stats['q75']}",
            f"nearest stronger: {nearest_text}",
        ]
    )


def run_once(token: str, bot_cfg: bot.BotConfig, radar_cfg: RadarConfig) -> tuple[dict[str, Any], Path]:
    own_rating = bot.own_blitz_rating(token, bot_cfg)
    users = bot.online_bots(token)
    snapshot = build_snapshot(users, own_rating, radar_cfg)
    path = save_snapshot(snapshot, radar_cfg.output_dir)
    return snapshot, path


def main() -> int:
    parser = argparse.ArgumentParser(description="LabZero online-bot blitz rating radar")
    parser.add_argument("--config", default=str(bot.DEFAULT_CONFIG))
    parser.add_argument("--env-file", default=str(bot.DEFAULT_ENV))
    parser.add_argument("--once", action="store_true", help="collect one snapshot and exit")
    parser.add_argument("--interval-sec", type=int, help="poll interval; minimum 10 seconds")
    parser.add_argument("--notify", action="store_true", help="send Telegram summaries if notify_provider=telegram")
    parser.add_argument("--notify-interval-min", type=int, help="minimum minutes between Telegram summaries")
    args = parser.parse_args()

    bot.load_env(Path(args.env_file))
    raw_cfg = bot.load_toml(Path(args.config))
    bot_cfg = bot.BotConfig.from_dict(raw_cfg, rated_override=None)
    radar_cfg = RadarConfig.from_dict(raw_cfg)
    if args.interval_sec is not None:
        radar_cfg.interval_sec = max(10, args.interval_sec)
    if args.notify_interval_min is not None:
        radar_cfg.notify_interval_min = max(0, args.notify_interval_min)

    token = bot.os.environ.get("LICHESS_TOKEN")
    if not token:
        bot.log("API", "Set LICHESS_TOKEN in environment or lichess_bot/.env", bot.Color.GRAY)
        return 1

    bot.log(
        "CONFIG",
        f"bot-radar interval={radar_cfg.interval_sec}s min_games={radar_cfg.min_blitz_games} "
        f"allow_provisional={str(radar_cfg.allow_provisional).lower()} output={radar_cfg.output_dir}",
        bot.Color.GRAY,
    )
    last_notify = 0.0
    while True:
        try:
            snapshot, path = run_once(token, bot_cfg, radar_cfg)
            text = format_snapshot(snapshot)
            bot.log("API", f"{text.replace(chr(10), ' | ')} · saved={path.name}", bot.Color.GRAY)
            now = time.time()
            should_notify = args.notify and (
                radar_cfg.notify_interval_min == 0
                or last_notify == 0.0
                or now - last_notify >= radar_cfg.notify_interval_min * 60
            )
            if should_notify:
                bot.notify(bot_cfg, f"{text}\n📄 {path.name}")
                last_notify = now
        except Exception as exc:
            bot.log("API", f"bot-radar error: {bot.describe_error(exc)}", bot.Color.GRAY)
        if args.once:
            break
        time.sleep(radar_cfg.interval_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
