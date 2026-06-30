#!/usr/bin/env python3
"""Native Lichess Bot API bridge for LabZero.

This runner is intentionally small and host-local: it spawns a copied UCI binary
from ``lichess_bot/bin/`` and keeps foreground status visible while games run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import mimetypes
import os
import random
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn
import chess.polyglot
import chess.syzygy

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "lichess_bot"
DEFAULT_CONFIG = BOT_DIR / "config.toml"
DEFAULT_ENV = BOT_DIR / ".env"
LICHESS_API = "https://lichess.org"


class Color:
    RESET = "\033[0m"
    GRAY = "\033[90m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[91m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"


USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def paint(text: str, color: str) -> str:
    if not USE_COLOR:
        return text
    return f"{color}{text}{Color.RESET}"


def log(label: str, msg: str, color: str = Color.GRAY) -> None:
    print(f"{paint(f'[{label}]', color)} {msg}", flush=True)


class ApiError(RuntimeError):
    pass


def describe_error(exc: Exception) -> str:
    detail = str(exc).strip()
    if "This endpoint can only be used with a Bot account" in detail:
        return f"{detail} (upgrade the dedicated account with POST /api/bot/account/upgrade)"
    return detail or exc.__class__.__name__


def load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    if not path.exists():
        path = BOT_DIR / "config.example.toml"
    with path.open("rb") as f:
        return tomllib.load(f)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def resolve_path(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return str(path)


@dataclass
class BotConfig:
    engine: str
    rated: bool
    clock_limit: int
    clock_increment: int
    max_parallel_games: int
    search_depth: int | None
    movetime_ms: int | None
    min_blitz_games: int
    allow_provisional: bool
    target_rating_min_delta: int
    target_rating_max_delta: int
    target_expected_score_min: float | None
    target_expected_score_max: float | None
    fallback_blitz_rating: int
    use_fallback_rating_when_provisional: bool
    max_challenge_attempts_per_cycle: int
    max_bot_challenges_per_day: int
    bot_challenge_quota_margin: int
    challenge_quota_file: str
    challenge_control_file: str
    avoid_bots_file: str
    opponent_cooldown_file: str
    challenge_interval_sec: int
    heartbeat_sec: int
    move_overhead_ms: int
    max_movetime_ms: int | None
    accept_from: str
    min_rating: int | None
    max_rating: int | None
    challenge_color: str
    pgn_directory: str | None
    hello: str
    goodbye: str
    chat_rooms: list[str]
    polyglot_books: list[str]
    polyglot_max_depth: int
    syzygy_paths: list[str]
    syzygy_max_pieces: int
    resign_enabled: bool
    resign_score: int
    resign_moves: int
    offer_draw_enabled: bool
    offer_draw_score: int
    offer_draw_moves: int
    offer_draw_pieces: int
    accept_draw_enabled: bool
    accept_draw_losing_score: int
    accept_draw_equal_score: int
    accept_draw_equal_pieces: int
    accept_draw_min_ply: int
    accept_draw_low_time_sec: int
    accept_draw_low_time_score: int
    uci_threads: int
    uci_hash_mb: int
    notify_provider: str
    notify_busy_human_challenge: bool
    notify_radar_after_game: bool
    notify_radar_after_game_delay_sec: int
    notify_block_summary: bool
    oracle_after_block: bool
    oracle_script: str
    oracle_stockfish: str | None
    oracle_max_positions: int
    oracle_nodes: int
    oracle_out_dir: str
    oracle_report_dir: str
    radar_min_blitz_games: int
    radar_allow_provisional: bool
    cancel_stale_outgoing_challenges: bool
    opponent_cooldown_sec: int

    @classmethod
    def from_dict(cls, cfg: dict[str, Any], rated_override: bool | None) -> "BotConfig":
        rated = bool(cfg.get("rated", False)) if rated_override is None else rated_override
        accept_from = str(cfg.get("accept_from", "any")).lower()
        if accept_from not in {"any", "bot", "human"}:
            raise ValueError("accept_from must be one of: any, bot, human")
        challenge_color = str(cfg.get("challenge_color", "random")).lower()
        if challenge_color not in {"random", "white", "black"}:
            raise ValueError("challenge_color must be one of: random, white, black")
        uci_threads = int(cfg.get("threads", 4))
        uci_hash_mb = int(cfg.get("hash_mb", 64))
        if not 1 <= uci_threads <= 8:
            raise ValueError("threads must be between 1 and 8")
        if not 1 <= uci_hash_mb <= 1024:
            raise ValueError("hash_mb must be between 1 and 1024")
        notify_provider = str(cfg.get("notify_provider", "none")).lower()
        if notify_provider not in {"none", "telegram"}:
            raise ValueError("notify_provider must be one of: none, telegram")
        chat_rooms = normalized_chat_rooms(cfg.get("chat_rooms", ["player"]))
        expected_score_min = optional_float(cfg.get("target_expected_score_min"))
        expected_score_max = optional_float(cfg.get("target_expected_score_max"))
        validate_expected_score_window(expected_score_min, expected_score_max)
        return cls(
            engine=resolve_path(str(cfg.get("engine", "lichess_bot/bin/labzero-macos-aarch64-0.6.2"))),
            rated=rated,
            clock_limit=int(cfg.get("clock_limit", 180)),
            clock_increment=int(cfg.get("clock_increment", 2)),
            max_parallel_games=int(cfg.get("max_parallel_games", 1)),
            search_depth=optional_int(cfg.get("search_depth")),
            movetime_ms=optional_int(cfg.get("movetime_ms")),
            min_blitz_games=int(cfg.get("min_blitz_games", 20)),
            allow_provisional=bool(cfg.get("allow_provisional", False)),
            target_rating_min_delta=int(cfg.get("target_rating_min_delta", 0)),
            target_rating_max_delta=int(cfg.get("target_rating_max_delta", 150)),
            target_expected_score_min=expected_score_min,
            target_expected_score_max=expected_score_max,
            fallback_blitz_rating=int(cfg.get("fallback_blitz_rating", 1500)),
            use_fallback_rating_when_provisional=bool(cfg.get("use_fallback_rating_when_provisional", True)),
            max_challenge_attempts_per_cycle=int(cfg.get("max_challenge_attempts_per_cycle", 8)),
            max_bot_challenges_per_day=int(cfg.get("max_bot_challenges_per_day", 100)),
            bot_challenge_quota_margin=int(cfg.get("bot_challenge_quota_margin", 10)),
            challenge_quota_file=resolve_path(str(cfg.get("challenge_quota_file", "lichess_bot/local/challenge-quota.json"))),
            challenge_control_file=resolve_path(str(cfg.get("challenge_control_file", "lichess_bot/local/challenge-control.json"))),
            avoid_bots_file=resolve_path(str(cfg.get("avoid_bots_file", "lichess_bot/local/avoid-bots.json"))),
            opponent_cooldown_file=resolve_path(str(cfg.get("opponent_cooldown_file", "lichess_bot/local/opponent-cooldown.json"))),
            challenge_interval_sec=int(cfg.get("challenge_interval_sec", 90)),
            heartbeat_sec=int(cfg.get("heartbeat_sec", 25)),
            move_overhead_ms=int(cfg.get("move_overhead_ms", 500)),
            max_movetime_ms=optional_int(cfg.get("max_movetime_ms")),
            accept_from=accept_from,
            min_rating=optional_int(cfg.get("min_rating")),
            max_rating=optional_int(cfg.get("max_rating")),
            challenge_color=challenge_color,
            pgn_directory=optional_resolved_path(cfg.get("pgn_directory", "lichess_bot/local/pgn")),
            hello=str(cfg.get("hello", "Hi! I'm {me}. Good luck!")),
            goodbye=str(cfg.get("goodbye", "Good game!")),
            chat_rooms=chat_rooms,
            polyglot_books=resolved_path_list(cfg.get("polyglot_books", [])),
            polyglot_max_depth=int(cfg.get("polyglot_max_depth", 20)),
            syzygy_paths=resolved_path_list(cfg.get("syzygy_paths", [])),
            syzygy_max_pieces=int(cfg.get("syzygy_max_pieces", 7)),
            resign_enabled=bool(cfg.get("resign_enabled", False)),
            resign_score=int(cfg.get("resign_score", -1000)),
            resign_moves=int(cfg.get("resign_moves", 3)),
            offer_draw_enabled=bool(cfg.get("offer_draw_enabled", False)),
            offer_draw_score=int(cfg.get("offer_draw_score", 20)),
            offer_draw_moves=int(cfg.get("offer_draw_moves", 10)),
            offer_draw_pieces=int(cfg.get("offer_draw_pieces", 10)),
            accept_draw_enabled=bool(cfg.get("accept_draw_enabled", True)),
            accept_draw_losing_score=int(cfg.get("accept_draw_losing_score", -100)),
            accept_draw_equal_score=int(cfg.get("accept_draw_equal_score", 25)),
            accept_draw_equal_pieces=int(cfg.get("accept_draw_equal_pieces", 8)),
            accept_draw_min_ply=int(cfg.get("accept_draw_min_ply", 40)),
            accept_draw_low_time_sec=int(cfg.get("accept_draw_low_time_sec", 10)),
            accept_draw_low_time_score=int(cfg.get("accept_draw_low_time_score", 100)),
            uci_threads=uci_threads,
            uci_hash_mb=uci_hash_mb,
            notify_provider=notify_provider,
            notify_busy_human_challenge=bool(cfg.get("notify_busy_human_challenge", True)),
            notify_radar_after_game=bool(cfg.get("notify_radar_after_game", True)),
            notify_radar_after_game_delay_sec=max(0, int(cfg.get("notify_radar_after_game_delay_sec", 2))),
            notify_block_summary=bool(cfg.get("notify_block_summary", True)),
            oracle_after_block=bool(cfg.get("oracle_after_block", False)),
            oracle_script=resolve_path(str(cfg.get("oracle_script", "scripts/host-oracle-label.py"))),
            oracle_stockfish=optional_resolved_path(cfg.get("oracle_stockfish")),
            oracle_max_positions=max(1, int(cfg.get("oracle_max_positions", 40))),
            oracle_nodes=max(1, int(cfg.get("oracle_nodes", 20000))),
            oracle_out_dir=resolve_path(str(cfg.get("oracle_out_dir", "data/oracle"))),
            oracle_report_dir=resolve_path(str(cfg.get("oracle_report_dir", "docs/oracle"))),
            radar_min_blitz_games=int(cfg.get("radar_min_blitz_games", cfg.get("min_blitz_games", 20))),
            radar_allow_provisional=bool(cfg.get("radar_allow_provisional", cfg.get("allow_provisional", False))),
            cancel_stale_outgoing_challenges=bool(cfg.get("cancel_stale_outgoing_challenges", True)),
            opponent_cooldown_sec=max(0, int(cfg.get("opponent_cooldown_sec", 20 * 60))),
        )


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def validate_expected_score_window(score_min: float | None, score_max: float | None) -> None:
    for label, value in (("target_expected_score_min", score_min), ("target_expected_score_max", score_max)):
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} must be between 0.0 and 1.0")
    if score_min is not None and score_max is not None and score_min > score_max:
        raise ValueError("target_expected_score_min must be <= target_expected_score_max")


def optional_resolved_path(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return resolve_path(str(value))


def resolved_path_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    return [resolve_path(str(item)) for item in items if str(item).strip()]


def normalized_chat_rooms(value: Any) -> list[str]:
    if value is None or value == "":
        return ["player"]
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    rooms = [str(item).strip().lower() for item in items if str(item).strip()]
    if not rooms:
        return ["player"]
    allowed = {"player", "spectator"}
    invalid = [room for room in rooms if room not in allowed]
    if invalid:
        raise ValueError("chat_rooms must contain only: player, spectator")
    return list(dict.fromkeys(rooms))


@dataclass
class MoveDecision:
    move: chess.Move
    score_cp: int | None = None
    offer_draw: bool = False
    source: str = "engine"


@dataclass
class FinishedGameSummary:
    game_id: str
    result_text: str
    result: str
    opponent: str
    opponent_rating: int | None
    status: str


def load_opponent_cooldown(path: str | None) -> dict[str, float]:
    if not path:
        return {}
    cooldown_path = Path(path)
    if not cooldown_path.exists():
        return {}
    try:
        data = json.loads(cooldown_path.read_text())
    except Exception as exc:
        log("CONTROL", f"ignoring unreadable {cooldown_path}: {describe_error(exc)}", Color.GRAY)
        return {}
    if not isinstance(data, dict):
        return {}
    raw_opponents = data.get("opponents", data)
    if not isinstance(raw_opponents, dict):
        return {}
    opponents: dict[str, float] = {}
    for raw_key, raw_value in raw_opponents.items():
        key = str(raw_key).strip().lower()
        if not key:
            continue
        try:
            opponents[key] = float(raw_value)
        except (TypeError, ValueError):
            continue
    return opponents


def save_opponent_cooldown(path: str | None, opponents: dict[str, float]) -> None:
    if not path:
        return
    cooldown_path = Path(path)
    cooldown_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "opponents": dict(sorted(opponents.items())),
    }
    cooldown_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


class RuntimeState:
    def __init__(self, games_limit: int | None = None, opponent_cooldown_file: str | None = None) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, str] = {}
        self._reserved: dict[str, float] = {}
        self._pending_outgoing_bots: set[str] = set()
        self._opponent_cooldown_file = opponent_cooldown_file
        self._opponent_last_played: dict[str, float] = load_opponent_cooldown(opponent_cooldown_file)
        self._finished_games: list[FinishedGameSummary] = []
        self._force_quit = False
        self.stop = threading.Event()
        self.games_limit = games_limit
        self.completed_games = 0

    def _expire_reserved_locked(self) -> None:
        now = time.time()
        expired = [key for key, until in self._reserved.items() if until <= now]
        for key in expired:
            self._reserved.pop(key, None)

    def active_count(self) -> int:
        with self._lock:
            self._expire_reserved_locked()
            return len(self._active) + len(self._reserved)

    def try_reserve_slot(self, key: str, max_games: int, ttl_sec: int = 180) -> bool:
        with self._lock:
            self._expire_reserved_locked()
            if key in self._reserved:
                return True
            if len(self._active) + len(self._reserved) >= max_games:
                return False
            self._reserved[key] = time.time() + ttl_sec
            return True

    def release_reserved_slot(self, key: str) -> None:
        with self._lock:
            self._reserved.pop(key, None)

    def has_pending_outgoing_bot(self, username: str) -> bool:
        key = username.strip().lower()
        if not key:
            return False
        with self._lock:
            return key in self._pending_outgoing_bots

    def clear_pending_outgoing_bot(self, username: str) -> None:
        key = username.strip().lower()
        if not key:
            return
        with self._lock:
            self._pending_outgoing_bots.discard(key)

    def try_begin_game(self, game_id: str, text: str, max_games: int) -> bool:
        with self._lock:
            self._expire_reserved_locked()
            if game_id in self._active:
                return False
            if len(self._active) >= max_games:
                return False
            if len(self._active) + len(self._reserved) >= max_games and self._reserved:
                self._reserved.pop(next(iter(self._reserved)))
            elif len(self._active) + len(self._reserved) >= max_games:
                return False
            self._active[game_id] = text
            return True

    def begin_game(self, game_id: str, text: str) -> None:
        with self._lock:
            self._active[game_id] = text

    def update_game(self, game_id: str, text: str) -> None:
        with self._lock:
            if game_id in self._active:
                self._active[game_id] = text

    def end_game(self, game_id: str, *, finished: bool = False) -> None:
        limit_reached = False
        completed = 0
        limit = self.games_limit
        with self._lock:
            was_active = game_id in self._active
            self._active.pop(game_id, None)
            if was_active and finished:
                self.completed_games += 1
                completed = self.completed_games
                if limit is not None and self.completed_games >= limit:
                    self.stop.set()
                    limit_reached = True
        if limit_reached and limit is not None:
            log("IDLE", f"game limit reached ({completed}/{limit}); no new games", Color.GREEN)

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._active)

    def mark_outgoing_bot_challenge(self, username: str) -> None:
        key = username.strip().lower()
        if not key:
            return
        with self._lock:
            self._pending_outgoing_bots.add(key)

    def consume_outgoing_bot_game(self, player: dict[str, Any]) -> bool:
        keys = {user_id(player), user_name(player).lower()}
        keys.discard("")
        if not keys:
            return False
        with self._lock:
            matched = self._pending_outgoing_bots.intersection(keys)
            if not matched:
                return False
            self._pending_outgoing_bots.difference_update(keys)
            return True

    def record_finished_game(self, summary: FinishedGameSummary, opponent_keys: set[str]) -> None:
        now = time.time()
        with self._lock:
            self._finished_games.append(summary)
            for key in opponent_keys:
                self._opponent_last_played[key] = now
            save_opponent_cooldown(self._opponent_cooldown_file, self._opponent_last_played)

    def opponent_cooldown_remaining(self, username: str, cooldown_sec: int) -> int:
        if cooldown_sec <= 0:
            return 0
        key = username.strip().lower()
        if not key:
            return 0
        with self._lock:
            last = self._opponent_last_played.get(key)
        if last is None:
            return 0
        return max(0, int((last + cooldown_sec) - time.time()))

    def finished_game_summaries(self) -> list[FinishedGameSummary]:
        with self._lock:
            return list(self._finished_games)

    def handle_sigint(self, _signum: int, _frame: object) -> None:
        if self.active_count() == 0:
            log("IDLE", "stopping", Color.GREEN)
            raise SystemExit(0)
        if not self._force_quit:
            self._force_quit = True
            log("PLAYING", "game active; press Ctrl-C again to force quit", Color.RED)
            return
        log("PLAYING", "forced quit requested", Color.RED)
        os._exit(130)


def heartbeat(state: RuntimeState, interval: int) -> None:
    while not state.stop.is_set():
        time.sleep(interval)
        for game_id, text in state.snapshot().items():
            log("PLAYING", f"game={game_id} {text}", Color.RED)


def configure_uci_engine(engine: chess.engine.SimpleEngine, cfg: BotConfig) -> None:
    engine.configure({"Threads": cfg.uci_threads, "Hash": cfg.uci_hash_mb})
    log("CONFIG", f"uci Threads={cfg.uci_threads} Hash={cfg.uci_hash_mb}", Color.GRAY)


def game_url(game_id: str) -> str:
    return f"https://lichess.org/{game_id}"


def notify_basename(path: str | None) -> str | None:
    if not path:
        return None
    return Path(path).name


def parse_pgn_rating_diffs(pgn_text: str) -> dict[str, int | None]:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return {"white": None, "black": None}

    def parse_diff(key: str) -> int | None:
        value = game.headers.get(key)
        if value is None or value == "":
            return None
        try:
            return int(str(value))
        except ValueError:
            return None

    return {
        "white": parse_diff("WhiteRatingDiff"),
        "black": parse_diff("BlackRatingDiff"),
    }


def rating_diffs_for_game(cfg: BotConfig, game_id: str, pgn_path: str | None) -> dict[str, int | None]:
    if cfg.pgn_directory:
        exports = sorted(Path(cfg.pgn_directory).glob(f"*_{game_id}_export.pgn"))
        if exports:
            return parse_pgn_rating_diffs(exports[-1].read_text(encoding="utf-8"))
    if pgn_path:
        path = Path(pgn_path)
        if path.is_file():
            return parse_pgn_rating_diffs(path.read_text(encoding="utf-8"))
    return {"white": None, "black": None}


def format_elo_line(start: int | None, diff: int | None) -> str:
    if start is None:
        return "?"
    if diff is None:
        return str(start)
    end = start + diff
    diff_text = f"+{diff}" if diff > 0 else str(diff)
    return f"{start} ({diff_text}) → {end}"


def notify_player_elo_line(game_full: dict[str, Any], color: str, diffs: dict[str, int | None]) -> str:
    player = player_obj(game_full, color)
    side = "White" if color == "white" else "Black"
    title = str(player.get("title") or "").strip()
    title_part = f"{title} " if title else ""
    name = user_name(player)
    elo = format_elo_line(player_rating(player), diffs.get(color))
    return f"{side}: {title_part}{name} · {elo}"


def notify_message_start(game_id: str, cfg: BotConfig, color: chess.Color, game_full: dict[str, Any]) -> str:
    side = "white" if color == chess.WHITE else "black"
    tc = f"{cfg.clock_limit // 60}+{cfg.clock_increment}"
    rated = "rated" if cfg.rated else "unrated"
    lines = [
        f"▶️ START {game_id}",
        f"{rated} {tc} · bot={side}",
        notify_player_elo_line(game_full, "white", {}),
        notify_player_elo_line(game_full, "black", {}),
        game_url(game_id),
    ]
    return "\n".join(lines)


def notify_message_end(
    game_id: str,
    cfg: BotConfig,
    color: chess.Color | None,
    result: str,
    game_full: dict[str, Any] | None,
    game_state: dict[str, Any],
    pgn_path: str | None,
) -> str:
    result_text, result_symbol = result_for_bot(result, color)
    status = terminal_status(game_state) or "unknown"
    rated = "rated" if cfg.rated else "unrated"
    diffs = rating_diffs_for_game(cfg, game_id, pgn_path) if game_full else {"white": None, "black": None}
    lines = [
        f"{result_symbol} {result_text} {game_id}",
        f"result={result} · status={status} · {rated}",
    ]
    if game_full:
        lines.extend(
            [
                notify_player_elo_line(game_full, "white", diffs),
                notify_player_elo_line(game_full, "black", diffs),
            ]
        )
    lines.append(game_url(game_id))
    pgn_name = notify_basename(pgn_path)
    if pgn_name:
        lines.append(f"📄 {pgn_name}")
    return "\n".join(lines)


def send_telegram_notification(text: str) -> None:
    token = os.environ.get("LABZERO_NOTIFY_TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("LABZERO_NOTIFY_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("LABZERO_NOTIFY_TELEGRAM_TOKEN and LABZERO_NOTIFY_TELEGRAM_CHAT_ID are required")
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{urllib.parse.quote(token)}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()


def telegram_document_request(path: Path, caption: str) -> urllib.request.Request:
    token = os.environ.get("LABZERO_NOTIFY_TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("LABZERO_NOTIFY_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("LABZERO_NOTIFY_TELEGRAM_TOKEN and LABZERO_NOTIFY_TELEGRAM_CHAT_ID are required")
    if not path.is_file():
        raise RuntimeError(f"notification file not found: {path}")

    boundary = f"labzero-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    chunks: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )

    add_field("chat_id", chat_id)
    if caption:
        add_field("caption", caption)
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )

    return urllib.request.Request(
        f"https://api.telegram.org/bot{urllib.parse.quote(token)}/sendDocument",
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )


def send_telegram_document(path: str, caption: str) -> None:
    req = telegram_document_request(Path(path), caption)
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def notify(cfg: BotConfig, text: str) -> None:
    if cfg.notify_provider == "none":
        return
    try:
        if cfg.notify_provider == "telegram":
            send_telegram_notification(text)
        else:
            return
        log("API", "notification sent", Color.GRAY)
    except Exception as exc:
        log("API", f"notification ignored: {describe_error(exc)}", Color.GRAY)


def notify_test(cfg: BotConfig, text: str, file_path: str | None) -> None:
    if cfg.notify_provider != "telegram":
        raise RuntimeError('notify_provider must be "telegram" for --notify-test')
    if file_path:
        send_telegram_document(file_path, text)
    else:
        send_telegram_notification(text)
    log("API", "notification test sent", Color.GRAY)


def bot_radar_rows(users: list[dict[str, Any]], cfg: BotConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for user in users:
        perf = blitz_perf(user)
        try:
            rating = int(perf.get("rating", 0) or 0)
            games = int(perf.get("games", 0) or 0)
        except (TypeError, ValueError):
            continue
        provisional = bool(perf.get("prov", False))
        if rating <= 0 or games < cfg.radar_min_blitz_games:
            continue
        if provisional and not cfg.radar_allow_provisional:
            continue
        rows.append(
            {
                "username": user.get("username") or user.get("name") or user.get("id"),
                "rating": rating,
                "games": games,
                "provisional": provisional,
            }
        )
    return rows


def bot_rating_percentile(ratings: list[int], own_rating: int) -> float | None:
    if not ratings:
        return None
    below_or_equal = sum(1 for rating in ratings if rating <= own_rating)
    return round(100.0 * below_or_equal / len(ratings), 1)


def notify_message_radar_after_game(own_rating: int, rows: list[dict[str, Any]]) -> str:
    ratings = sorted(row["rating"] for row in rows)
    percentile = bot_rating_percentile(ratings, own_rating)
    stronger = sorted(
        (row for row in rows if row["rating"] > own_rating),
        key=lambda row: (row["rating"] - own_rating, str(row["username"]).lower()),
    )
    nearest = ", ".join(f"{row['username']} {row['rating']}" for row in stronger[:3]) or "none"
    pct_text = "n/a" if percentile is None else f"{percentile:.1f}th"
    median = "n/a" if not ratings else f"{statistics.median(ratings):.1f}"
    avg = "n/a" if not ratings else f"{statistics.fmean(ratings):.1f}"
    return "\n".join(
        [
            "🤖 RADAR after game",
            f"own blitz: {own_rating}",
            f"online bots: {len(ratings)} filtered",
            f"percentile: {pct_text} · above={len(stronger)} · <=you={len(ratings) - len(stronger)}",
            f"median/avg: {median} / {avg}",
            f"nearest stronger: {nearest}",
        ]
    )


def notify_radar_after_game(token: str, cfg: BotConfig) -> None:
    if cfg.notify_provider != "telegram" or not cfg.notify_radar_after_game:
        return
    try:
        if cfg.notify_radar_after_game_delay_sec > 0:
            time.sleep(cfg.notify_radar_after_game_delay_sec)
        own_rating = own_blitz_rating(token, cfg)
        rows = bot_radar_rows(online_bots(token), cfg)
        notify(cfg, notify_message_radar_after_game(own_rating, rows))
    except Exception as exc:
        log("API", f"post-game radar ignored: {describe_error(exc)}", Color.GRAY)


def game_summary(
    game_id: str,
    result: str,
    color: chess.Color | None,
    game_full: dict[str, Any] | None,
    game_state: dict[str, Any],
) -> FinishedGameSummary:
    result_text, _ = result_for_bot(result, color)
    opponent_player: dict[str, Any] = {}
    if game_full and color is not None:
        opponent_player = player_obj(game_full, "black" if color == chess.WHITE else "white")
    return FinishedGameSummary(
        game_id=game_id,
        result_text=result_text,
        result=result,
        opponent=user_name(opponent_player),
        opponent_rating=player_rating(opponent_player),
        status=terminal_status(game_state) or "unknown",
    )


def score_for_summary(summary: FinishedGameSummary) -> float:
    if summary.result_text == "WIN":
        return 1.0
    if summary.result_text == "DRAW":
        return 0.5
    return 0.0


def notify_message_block_summary(summaries: list[FinishedGameSummary], games_limit: int | None) -> str:
    wins = sum(1 for item in summaries if item.result_text == "WIN")
    draws = sum(1 for item in summaries if item.result_text == "DRAW")
    losses = sum(1 for item in summaries if item.result_text == "LOSS")
    score = sum(score_for_summary(item) for item in summaries)
    ratings = [item.opponent_rating for item in summaries if item.opponent_rating is not None]
    avg_opp = "n/a" if not ratings else f"{statistics.fmean(ratings):.0f}"
    limit_text = "open block" if games_limit is None else f"{games_limit}-game block"
    last_ids = ", ".join(item.game_id for item in summaries[-4:])
    return "\n".join(
        [
            f"📊 BLOCK summary · {limit_text}",
            f"{wins}W-{draws}D-{losses}L · score={score:g}/{len(summaries)} ({100 * score / max(1, len(summaries)):.1f}%)",
            f"avg opponent: {avg_opp}",
            f"last games: {last_ids}",
        ]
    )


def notify_block_summary(token: str, cfg: BotConfig, state: RuntimeState, games_limit: int | None) -> None:
    if cfg.notify_provider != "telegram" or not cfg.notify_block_summary:
        return
    summaries = state.finished_game_summaries()
    if not summaries:
        return
    try:
        notify(cfg, notify_message_block_summary(summaries, games_limit))
    except Exception as exc:
        log("API", f"block summary ignored: {describe_error(exc)}", Color.GRAY)


def pgn_paths_for_summaries(cfg: BotConfig, summaries: list[FinishedGameSummary]) -> list[str]:
    if not cfg.pgn_directory:
        return []
    pgn_dir = Path(cfg.pgn_directory)
    if not pgn_dir.exists():
        return []
    paths: list[Path] = []
    for summary in summaries:
        paths.extend(pgn_dir.glob(f"*_{summary.game_id}.pgn"))
        paths.extend(pgn_dir.glob(f"*_{summary.game_id}_export.pgn"))
    return [str(path) for path in sorted(set(paths))]


def oracle_output_paths(cfg: BotConfig) -> tuple[str, str]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(cfg.oracle_out_dir) / f"block_{stamp}.jsonl"
    report_path = Path(cfg.oracle_report_dir) / f"block_{stamp}.md"
    return str(out_path), str(report_path)


def build_oracle_after_block_command(
    cfg: BotConfig,
    summaries: list[FinishedGameSummary],
    out_path: str,
    report_path: str,
) -> list[str]:
    command = [
        sys.executable,
        cfg.oracle_script,
        "--max-positions",
        str(cfg.oracle_max_positions),
        "--nodes",
        str(cfg.oracle_nodes),
        "--out",
        out_path,
        "--report",
        report_path,
    ]
    if cfg.oracle_stockfish:
        command.extend(["--stockfish", cfg.oracle_stockfish])
    for path in pgn_paths_for_summaries(cfg, summaries):
        command.extend(["--pgn", path])
    return command


def oracle_worst_labels(out_path: str, limit: int = 3) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    path = Path(out_path)
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            student_move = record.get("student", {}).get("move")
            label = next((item for item in record.get("moves", []) if item.get("uci") == student_move), None)
            if label:
                rows.append((label, record))
    rows.sort(key=lambda item: float(item[0].get("delta_utility", -1)), reverse=True)
    return rows[:limit]


def oracle_block_message(out_path: str, report_path: str) -> str:
    worst = oracle_worst_labels(out_path)
    lines = ["🧪 ORACLE block analysis", f"report: {notify_basename(report_path)}"]
    for label, record in worst:
        lines.append(
            f"{record.get('source', {}).get('id', '?')} ply {record.get('source', {}).get('ply', '?')}: "
            f"{record.get('student', {}).get('move', '?')} → {label.get('bucket')} "
            f"rank={label.get('rank')} Δu={float(label.get('delta_utility', 0.0)):.3f}"
        )
    return "\n".join(lines)


def run_oracle_after_block(cfg: BotConfig, state: RuntimeState, games_limit: int | None) -> None:
    summaries = state.finished_game_summaries()
    if not summaries:
        return
    out_path, report_path = oracle_output_paths(cfg)
    command = build_oracle_after_block_command(cfg, summaries, out_path, report_path)
    if "--pgn" not in command:
        log("API", "oracle-after-block skipped: no saved PGNs for completed block", Color.GRAY)
        return
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        log("API", f"oracle-after-block failed: {describe_error(exc)}", Color.GRAY)
        return
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        log("API", f"oracle-after-block exited {result.returncode}: {detail}", Color.GRAY)
        return
    log("API", f"oracle-after-block wrote {report_path}", Color.GRAY)
    notify(cfg, oracle_block_message(out_path, report_path))


def dry_run_test(engine_path: str, cfg: BotConfig) -> None:
    log("CONFIG", f"dry-run engine={engine_path}", Color.GRAY)
    with chess.engine.SimpleEngine.popen_uci(engine_path, timeout=5.0) as eng:
        configure_uci_engine(eng, cfg)
        board = chess.Board()
        for ply in range(20):
            if board.is_game_over():
                break
            result = eng.play(board, dry_run_limit(cfg))
            if result.move not in board.legal_moves:
                raise RuntimeError(f"illegal move {result.move}")
            board.push(result.move)
            log("MOVE", f"ply={ply + 1} {result.move.uci()}", Color.BLUE)
    log("IDLE", "dry-run PASS (20 plies)", Color.GREEN)


def dry_run_limit(cfg: BotConfig) -> chess.engine.Limit:
    if cfg.search_depth is not None:
        return chess.engine.Limit(depth=cfg.search_depth)
    if cfg.movetime_ms is not None:
        return chess.engine.Limit(time=cfg.movetime_ms / 1000.0)
    return chess.engine.Limit(depth=4)


def clock_seconds(value: Any, default_seconds: int) -> float:
    if value is None:
        return float(default_seconds)
    if isinstance(value, (int, float)):
        raw = float(value)
    else:
        raw = float(str(value))
    # Lichess Bot API clock fields are milliseconds; tolerate seconds in tests.
    return raw / 1000.0 if raw >= 1000 else raw


def clock_seconds_with_overhead(value: Any, default_seconds: int, overhead_ms: int) -> float:
    raw_seconds = clock_seconds(value, default_seconds)
    adjusted_ms = max(1, int(raw_seconds * 1000) - max(0, overhead_ms))
    return adjusted_ms / 1000.0


def engine_limit(cfg: BotConfig, board: chess.Board, state: dict[str, Any] | None = None) -> chess.engine.Limit:
    if state and all(k in state for k in ("wtime", "btime")):
        limit = chess.engine.Limit(
            white_clock=clock_seconds_with_overhead(state.get("wtime"), cfg.clock_limit, cfg.move_overhead_ms),
            black_clock=clock_seconds_with_overhead(state.get("btime"), cfg.clock_limit, cfg.move_overhead_ms),
            white_inc=max(0.0, clock_seconds(state.get("winc"), cfg.clock_increment) - cfg.move_overhead_ms / 1000.0),
            black_inc=max(0.0, clock_seconds(state.get("binc"), cfg.clock_increment) - cfg.move_overhead_ms / 1000.0),
        )
        if cfg.max_movetime_ms is not None:
            limit.time = cfg.max_movetime_ms / 1000.0
        own_clock = limit.white_clock if board.turn == chess.WHITE else limit.black_clock
        panic_cap = low_clock_movetime_cap(own_clock)
        if panic_cap is not None:
            limit.time = min(limit.time, panic_cap) if limit.time is not None else panic_cap
        return limit
    if cfg.search_depth is not None:
        return chess.engine.Limit(depth=cfg.search_depth)
    if cfg.movetime_ms is not None:
        return chess.engine.Limit(time=cfg.movetime_ms / 1000.0)
    return chess.engine.Limit(
        white_clock=cfg.clock_limit,
        black_clock=cfg.clock_limit,
        white_inc=cfg.clock_increment,
        black_inc=cfg.clock_increment,
    )


def low_clock_movetime_cap(own_clock_sec: float | None) -> float | None:
    if own_clock_sec is None:
        return None
    if own_clock_sec <= 8:
        return 0.5
    if own_clock_sec <= 15:
        return 1.0
    return None


def user_id(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    return str(user.get("id") or user.get("name") or user.get("username") or "").lower()


def user_keys(user: dict[str, Any] | None) -> set[str]:
    if not user:
        return set()
    keys = {
        str(user.get("id") or "").lower(),
        str(user.get("name") or "").lower(),
        str(user.get("username") or "").lower(),
    }
    return {key for key in keys if key}


def player_obj(event: dict[str, Any] | None, color: str) -> dict[str, Any]:
    if not event:
        return {}
    direct = event.get(color)
    if isinstance(direct, dict):
        return direct
    player = event.get("players", {}).get(color, {})
    if isinstance(player, dict):
        nested = player.get("user")
        if isinstance(nested, dict):
            merged = dict(nested)
            for key in ("rating", "ratingDiff", "provisional"):
                if key in player and key not in merged:
                    merged[key] = player[key]
            return merged
        return player
    return {}


def player_user_id(event: dict[str, Any], color: str) -> str:
    return user_id(player_obj(event, color))


def user_name(user: dict[str, Any] | None) -> str:
    if not user:
        return "unknown"
    return str(user.get("name") or user.get("username") or user.get("id") or "unknown")


def player_rating(player: dict[str, Any]) -> int | None:
    try:
        return int(player.get("rating"))
    except (TypeError, ValueError):
        return None


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "unknown"


def is_bot_user(user: dict[str, Any] | None) -> bool:
    return str((user or {}).get("title") or "").upper() == "BOT"


def load_avoid_bots(path: str) -> set[str]:
    avoid_path = Path(path)
    if not avoid_path.exists():
        return set()
    try:
        data = json.loads(avoid_path.read_text())
    except Exception as exc:
        log("CONTROL", f"ignoring unreadable avoid list {avoid_path}: {describe_error(exc)}", Color.GRAY)
        return set()
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("bots", [])
    else:
        items = []
    return {str(item).strip().lower() for item in items if str(item).strip()}


def is_avoided_user(user: dict[str, Any] | None, avoid_bots: set[str]) -> bool:
    return bool(user_keys(user).intersection(avoid_bots))


def challenge_rating(challenge: dict[str, Any]) -> int | None:
    challenger = challenge.get("challenger", {}) or {}
    perf = challenge.get("perf", {}) or challenge.get("perfType", {}) or {}
    rating = challenger.get("rating") or perf.get("rating")
    try:
        return int(rating)
    except (TypeError, ValueError):
        return None


def bot_color_from_full(event: dict[str, Any], account_id: str) -> chess.Color | None:
    if player_user_id(event, "white") == account_id:
        return chess.WHITE
    if player_user_id(event, "black") == account_id:
        return chess.BLACK
    return None


def board_from_moves(moves: str) -> chess.Board:
    board = chess.Board()
    for uci in moves.split():
        board.push_uci(uci)
    return board


def terminal_status(state: dict[str, Any]) -> str | None:
    return state.get("status") or state.get("winner")


def game_player_name(event: dict[str, Any], color: str) -> str:
    return user_name(player_obj(event, color))


def pgn_result(board: chess.Board, game_state: dict[str, Any]) -> str:
    winner = game_state.get("winner")
    if winner == "white":
        return "1-0"
    if winner == "black":
        return "0-1"
    status = str(game_state.get("status") or "")
    if status in {"draw", "stalemate"}:
        return "1/2-1/2"
    # Claimable draws (threefold, fifty-move) are not terminal on Lichess until claimed.
    if board.is_game_over(claim_draw=False):
        return board.result(claim_draw=False)
    return "*"


def player_label(player: dict[str, Any]) -> str:
    name = user_name(player)
    rating = player_rating(player)
    title = str(player.get("title") or "").strip()
    title_part = f"{title} " if title else ""
    rating_part = f" ({rating})" if rating is not None else ""
    return f"{title_part}{name}{rating_part}"


def matchup_label(game_full: dict[str, Any]) -> str:
    white = player_label(player_obj(game_full, "white"))
    black = player_label(player_obj(game_full, "black"))
    return f"White: {white} vs Black: {black}"


def result_for_bot(result: str, color: chess.Color | None) -> tuple[str, str]:
    if result == "1/2-1/2":
        return "DRAW", "🤝"
    if result == "*" or color is None:
        return "UNKNOWN", "❔"
    bot_won = (result == "1-0" and color == chess.WHITE) or (result == "0-1" and color == chess.BLACK)
    if bot_won:
        return "WIN", "✅"
    return "LOSS", "❌"


def format_chat(text: str, *, me: str, opponent: str) -> str:
    return text.replace("{me}", me).replace("{opponent}", opponent).strip()


def maybe_chat(token: str, game_id: str, room: str, text: str) -> None:
    if not text:
        return
    try:
        bot_chat(token, game_id, room, text)
    except Exception as exc:
        log("API", f"chat ignored for {game_id}: {describe_error(exc)}", Color.GRAY)


def maybe_chat_rooms(token: str, game_id: str, rooms: list[str], text: str) -> None:
    for room in rooms:
        maybe_chat(token, game_id, room, text)


def can_claim_lichess_draw(board: chess.Board) -> bool:
    return board.can_claim_threefold_repetition() or board.can_claim_fifty_moves()


def should_claim_available_draw(
    cfg: BotConfig,
    board: chess.Board,
    color: chess.Color,
    game_state: dict[str, Any],
) -> bool:
    if board.turn != color or not can_claim_lichess_draw(board):
        return False
    return own_clock_seconds(game_state, color, cfg) <= cfg.accept_draw_low_time_sec


def is_game_already_over_error(exc: Exception) -> bool:
    if not isinstance(exc, ApiError):
        return False
    detail = describe_error(exc).lower()
    return (
        "already over" in detail
        or "not your turn" in detail
        or "not the time to claim draw" in detail
    )


def maybe_claim_draw(token: str, game_id: str, reason: str) -> bool | None:
    """Return True if claimed, False if retry later, None if the game is already over."""
    try:
        bot_claim_draw(token, game_id)
        log("MOVE", f"{game_id} claimed draw ({reason})", Color.BLUE)
        return True
    except Exception as exc:
        log("API", f"claim-draw ignored for {game_id}: {describe_error(exc)}", Color.GRAY)
        if is_game_already_over_error(exc):
            return None
        return False


def piece_count(board: chess.Board) -> int:
    return len(board.piece_map())


def score_for_color(info: dict[str, Any], color: chess.Color) -> int | None:
    score = info.get("score")
    if score is None:
        return None
    try:
        return score.pov(color).score(mate_score=100000)
    except Exception:
        return None


def draw_offer_pending(game_state: dict[str, Any], color: chess.Color) -> bool:
    value = game_state.get("drawOffer", game_state.get("draw_offer", game_state.get("offeringDraw")))
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"white", "black"}:
            return normalized != ("white" if color == chess.WHITE else "black")
    return False


def own_clock_seconds(game_state: dict[str, Any], color: chess.Color, cfg: BotConfig) -> float:
    key = "wtime" if color == chess.WHITE else "btime"
    return clock_seconds(game_state.get(key), cfg.clock_limit)


def should_accept_draw_offer(
    cfg: BotConfig,
    board: chess.Board,
    color: chess.Color,
    score_cp: int | None,
    game_state: dict[str, Any],
) -> bool:
    if not cfg.accept_draw_enabled or score_cp is None:
        return False
    if score_cp <= cfg.accept_draw_losing_score:
        return True
    if (
        board.ply() >= cfg.accept_draw_min_ply
        and piece_count(board) <= cfg.accept_draw_equal_pieces
        and abs(score_cp) <= cfg.accept_draw_equal_score
    ):
        return True
    if own_clock_seconds(game_state, color, cfg) <= cfg.accept_draw_low_time_sec and score_cp <= cfg.accept_draw_low_time_score:
        return True
    return False


TERMINAL_GAME_STATUSES = frozenset(
    {"mate", "resign", "draw", "stalemate", "timeout", "outoftime", "aborted"}
)


def is_game_terminal(board: chess.Board, game_state: dict[str, Any]) -> bool:
    status = terminal_status(game_state)
    if status in TERMINAL_GAME_STATUSES:
        return True
    # Claimable draws (threefold, fifty-move) are not terminal on Lichess until claimed.
    return board.is_game_over(claim_draw=False)


def is_stale_move_error(exc: Exception) -> bool:
    if not isinstance(exc, ApiError):
        return False
    detail = describe_error(exc).lower()
    return "already over" in detail or "not your turn" in detail


def is_transient_network_error(exc: Exception) -> bool:
    if isinstance(exc, ApiError):
        detail = describe_error(exc).lower()
        return any(code in detail for code in ("http 429", "http 500", "http 502", "http 503", "http 504"))
    return isinstance(exc, (TimeoutError, ConnectionError, urllib.error.URLError))


def bot_make_move_with_retry(
    token: str,
    game_id: str,
    move: str,
    offering_draw: bool = False,
    *,
    attempts: int = 3,
) -> None:
    for attempt in range(1, attempts + 1):
        try:
            bot_make_move(token, game_id, move, offering_draw)
            return
        except Exception as exc:
            if is_stale_move_error(exc) or not is_transient_network_error(exc) or attempt >= attempts:
                raise
            delay = min(2.0, 0.5 * attempt)
            log(
                "API",
                f"{game_id} move post retry {attempt + 1}/{attempts} after: {describe_error(exc)}",
                Color.GRAY,
            )
            time.sleep(delay)


def book_move(board: chess.Board, cfg: BotConfig) -> chess.Move | None:
    if not cfg.polyglot_books or board.ply() >= cfg.polyglot_max_depth:
        return None
    for book_path in cfg.polyglot_books:
        path = Path(book_path)
        if not path.exists():
            continue
        try:
            with chess.polyglot.open_reader(path) as reader:
                entries = list(reader.find_all(board))
        except Exception as exc:
            log("BOOK", f"{path.name} ignored: {describe_error(exc)}", Color.GRAY)
            continue
        if not entries:
            continue
        total = sum(max(1, entry.weight) for entry in entries)
        pick = random.randint(1, total)
        upto = 0
        for entry in entries:
            upto += max(1, entry.weight)
            if upto >= pick:
                log(
                    "BOOK",
                    f"ply={board.ply()} move={entry.move.uci()} book={path.name} entries={len(entries)}",
                    Color.BLUE,
                )
                return entry.move
    return None


def syzygy_move(board: chess.Board, cfg: BotConfig) -> chess.Move | None:
    if not cfg.syzygy_paths or piece_count(board) > cfg.syzygy_max_pieces:
        return None
    paths = [path for path in cfg.syzygy_paths if Path(path).exists()]
    if not paths:
        return None
    scored: list[tuple[int, int, chess.Move]] = []
    try:
        with chess.syzygy.open_tablebase(paths[0]) as tablebase:
            for extra_path in paths[1:]:
                tablebase.add_directory(extra_path)
            for move in board.legal_moves:
                board.push(move)
                try:
                    wdl = -tablebase.probe_wdl(board)
                    dtz = tablebase.probe_dtz(board)
                    scored.append((wdl, dtz, move))
                except Exception:
                    pass
                finally:
                    board.pop()
    except Exception as exc:
        log("TB", f"tablebase ignored: {describe_error(exc)}", Color.GRAY)
        return None
    return select_syzygy_move(scored)


def syzygy_dtz_preference(wdl: int, dtz: int) -> int:
    dtz_abs = abs(dtz)
    if wdl > 0:
        return -dtz_abs
    if wdl < 0:
        return dtz_abs
    return -dtz_abs


def select_syzygy_move(scored: list[tuple[int, int, chess.Move]]) -> chess.Move | None:
    if not scored:
        return None
    ranked = [
        (wdl, syzygy_dtz_preference(wdl, dtz), move.uci(), move)
        for wdl, dtz, move in scored
    ]
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return ranked[0][3]


def choose_move(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    color: chess.Color,
    cfg: BotConfig,
    game_state: dict[str, Any],
) -> MoveDecision:
    move = book_move(board, cfg)
    if move is not None:
        return MoveDecision(move=move, source="book")
    move = syzygy_move(board, cfg)
    if move is not None:
        return MoveDecision(move=move, source="tablebase")
    result = engine.play(board, engine_limit(cfg, board, game_state), info=chess.engine.INFO_SCORE)
    if result.move is None:
        raise RuntimeError("no move from engine")
    score_cp = score_for_color(result.info, color)
    return MoveDecision(move=result.move, score_cp=score_cp)


def save_pgn(
    cfg: BotConfig,
    game_id: str,
    board: chess.Board,
    game_full: dict[str, Any] | None,
    game_state: dict[str, Any],
) -> str | None:
    if not cfg.pgn_directory:
        return None
    pgn_dir = Path(cfg.pgn_directory)
    pgn_dir.mkdir(parents=True, exist_ok=True)
    game = chess.pgn.Game.from_board(board)
    now = dt.datetime.now(dt.timezone.utc)
    game.headers["Event"] = "Lichess Bot Game"
    game.headers["Site"] = f"https://lichess.org/{game_id}"
    game.headers["Date"] = now.strftime("%Y.%m.%d")
    game.headers["UTCDate"] = now.strftime("%Y.%m.%d")
    game.headers["UTCTime"] = now.strftime("%H:%M:%S")
    white = player_obj(game_full, "white")
    black = player_obj(game_full, "black")
    if game_full:
        game.headers["White"] = user_name(white)
        game.headers["Black"] = user_name(black)
        for color, player in (("White", white), ("Black", black)):
            rating = player_rating(player)
            if rating is not None:
                game.headers[f"{color}Elo"] = str(rating)
            if player.get("title"):
                game.headers[f"{color}Title"] = str(player["title"])
            if player.get("id"):
                game.headers[f"{color}LichessId"] = str(player["id"])
            if "provisional" in player:
                game.headers[f"{color}RatingProvisional"] = "true" if player.get("provisional") else "false"
    status = terminal_status(game_state) or "unknown"
    game.headers["Termination"] = status
    game.headers["Result"] = pgn_result(board, game_state)
    white_name = safe_filename_part(game.headers.get("White", "unknown"))
    black_name = safe_filename_part(game.headers.get("Black", "unknown"))
    path = pgn_dir / f"{now.strftime('%Y%m%d-%H%M%S')}_{white_name}_vs_{black_name}_{game_id}.pgn"
    with path.open("w", encoding="utf-8") as f:
        print(game, file=f, end="\n\n")
    log("PGN", f"saved {path}", Color.GREEN)
    return str(path)


def save_exported_pgn(cfg: BotConfig, game_id: str, pgn_text: str) -> None:
    if not cfg.pgn_directory or not pgn_text.strip():
        return
    pgn_dir = Path(cfg.pgn_directory)
    pgn_dir.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    path = pgn_dir / f"{now.strftime('%Y%m%d-%H%M%S')}_{game_id}_export.pgn"
    path.write_text(pgn_text.strip() + "\n\n", encoding="utf-8")
    log("PGN", f"saved export {path}", Color.GREEN)


def fetch_game_export_pgn(token: str, game_id: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/x-chess-pgn",
    }
    req = urllib.request.Request(
        f"{LICHESS_API}/game/export/{urllib.parse.quote(game_id)}?moves=1&tags=1&clocks=1",
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode().strip()
    except Exception as exc:
        log("API", f"export ignored for {game_id}: {describe_error(exc)}", Color.GRAY)
        return None
    return text or None


def enrich_state_from_export(
    pgn_text: str,
    board: chess.Board,
    game_state: dict[str, Any],
) -> tuple[chess.Board, dict[str, Any]]:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return board, game_state
    end_board = game.end().board()
    result = game.headers.get("Result", "*")
    enriched = dict(game_state)
    if result == "1/2-1/2":
        enriched["status"] = "draw"
    elif result == "1-0":
        enriched["winner"] = "white"
        enriched.setdefault("status", "mate")
    elif result == "0-1":
        enriched["winner"] = "black"
        enriched.setdefault("status", "mate")
    return end_board, enriched


def finish_game_after_api_over(
    token: str,
    game_id: str,
    account_id: str,
    cfg: BotConfig,
    state: RuntimeState,
    board: chess.Board,
    game_full: dict[str, Any] | None,
    game_state: dict[str, Any],
    color: chess.Color | None,
    *,
    note: str = "",
) -> None:
    export = fetch_game_export_pgn(token, game_id)
    if export:
        save_exported_pgn(cfg, game_id, export)
        board, game_state = enrich_state_from_export(export, board, game_state)
    finish_played_game(token, game_id, account_id, cfg, state, board, game_full, game_state, color, note=note)


def finish_played_game(
    token: str,
    game_id: str,
    account_id: str,
    cfg: BotConfig,
    state: RuntimeState,
    board: chess.Board,
    game_full: dict[str, Any] | None,
    game_state: dict[str, Any],
    color: chess.Color | None,
    *,
    note: str = "",
) -> None:
    result = pgn_result(board, game_state)
    result_text, result_symbol = result_for_bot(result, color)
    matchup = f" {matchup_label(game_full)}" if game_full else ""
    extra = f" {note}" if note else ""
    log(
        "GAME END",
        f"{result_symbol} {result_text} {game_id} result={result} status={terminal_status(game_state) or board.result()}{matchup}{extra}",
        Color.MAGENTA,
    )
    if game_full and color is not None:
        opponent = game_player_name(game_full, "black" if color == chess.WHITE else "white")
        maybe_chat_rooms(token, game_id, cfg.chat_rooms, format_chat(cfg.goodbye, me=account_id, opponent=opponent))
    pgn_path = save_pgn(cfg, game_id, board, game_full, game_state)
    notify(cfg, notify_message_end(game_id, cfg, color, result, game_full, game_state, pgn_path))
    notify_radar_after_game(token, cfg)
    summary = game_summary(game_id, result, color, game_full, game_state)
    opponent_keys: set[str] = set()
    if game_full and color is not None:
        opponent_keys = user_keys(player_obj(game_full, "black" if color == chess.WHITE else "white"))
    state.record_finished_game(summary, opponent_keys)


def resilient_bot_game_stream(token: str, game_id: str, state: RuntimeState) -> Any:
    reconnects = 0
    while not state.stop.is_set():
        try:
            saw_event = False
            for event in bot_game_stream(token, game_id):
                saw_event = True
                reconnects = 0
                yield event
            if saw_event:
                log("API", f"{game_id} game stream ended; reconnecting", Color.GRAY)
            else:
                log("API", f"{game_id} game stream ended without events; reconnecting", Color.GRAY)
        except Exception as exc:
            if not is_transient_network_error(exc):
                raise
            reconnects += 1
            delay = min(10.0, 1.5 * reconnects)
            log(
                "API",
                f"{game_id} game stream reconnect {reconnects} after: {describe_error(exc)}",
                Color.GRAY,
            )
            time.sleep(delay)


def play_game(
    token: str,
    engine: chess.engine.SimpleEngine,
    game_id: str,
    account_id: str,
    cfg: BotConfig,
    state: RuntimeState,
    quota: "ChallengeQuota | None" = None,
) -> None:
    color: chess.Color | None = None
    last_handled_moves: str | None = None
    game_full: dict[str, Any] | None = None
    game_state: dict[str, Any] = {}
    resign_count = 0
    draw_count = 0
    hello_sent = False
    finished = False
    state.update_game(game_id, "starting")
    try:
        for event in resilient_bot_game_stream(token, game_id, state):
            etype = event.get("type")
            if etype == "gameFull":
                first_full = game_full is None
                game_full = event
                color = bot_color_from_full(event, account_id)
                if color is None:
                    log("API", f"cannot determine bot color for {game_id}", Color.GRAY)
                    return
                side = "white" if color == chess.WHITE else "black"
                state.update_game(game_id, f"color={side}")
                if first_full:
                    log("START", f"▶️ {game_id} bot={side} {matchup_label(event)}", Color.RED)
                    notify(cfg, notify_message_start(game_id, cfg, color, event))
                    opponent_player = player_obj(event, "black" if color == chess.WHITE else "white")
                    if quota is not None and is_bot_user(opponent_player) and state.consume_outgoing_bot_game(opponent_player):
                        quota.record_attempt()
                        quota.log_status()
                game_state = event.get("state", {})
            elif etype == "gameState":
                game_state = event
            elif etype == "opponentGone":
                log("PLAYING", f"{game_id} opponentGone={event}", Color.YELLOW)
                continue
            else:
                continue

            moves = str(game_state.get("moves", ""))
            board = board_from_moves(moves)
            ply = board.ply()
            state.update_game(game_id, f"ply={ply} turn={'white' if board.turn else 'black'}")

            # Lichess UI drops player chat posted before the first ply (API still returns 200).
            if not hello_sent and moves.strip() and game_full is not None and color is not None:
                opponent = game_player_name(game_full, "black" if color == chess.WHITE else "white")
                maybe_chat_rooms(token, game_id, cfg.chat_rooms, format_chat(cfg.hello, me=account_id, opponent=opponent))
                hello_sent = True

            if is_game_terminal(board, game_state):
                finish_played_game(token, game_id, account_id, cfg, state, board, game_full, game_state, color)
                finished = True
                return
            if color is None or board.turn != color or moves == last_handled_moves:
                continue

            if should_claim_available_draw(cfg, board, color, game_state):
                claim = maybe_claim_draw(token, game_id, "low time")
                if claim is True:
                    continue
                if claim is None:
                    finish_game_after_api_over(
                        token,
                        game_id,
                        account_id,
                        cfg,
                        state,
                        board,
                        game_full,
                        game_state,
                        color,
                        note="(claim-draw: game already over)",
                    )
                    finished = True
                    return

            decision = choose_move(engine, board, color, cfg, game_state)
            if decision.move not in board.legal_moves:
                log("API", f"illegal {decision.source} move {decision.move} in {game_id}", Color.GRAY)
                return
            if is_game_terminal(board, game_state):
                finish_played_game(
                    token,
                    game_id,
                    account_id,
                    cfg,
                    state,
                    board,
                    game_full,
                    game_state,
                    color,
                    note="(terminal before move post)",
                )
                finished = True
                return
            if decision.score_cp is not None and cfg.resign_enabled and decision.score_cp <= cfg.resign_score:
                resign_count += 1
            else:
                resign_count = 0
            if cfg.resign_enabled and resign_count >= cfg.resign_moves:
                log("MOVE", f"{game_id} resigning score={decision.score_cp}", Color.BLUE)
                bot_resign(token, game_id)
                return
            accepts_draw_offer = draw_offer_pending(game_state, color) and should_accept_draw_offer(cfg, board, color, decision.score_cp, game_state)
            if decision.score_cp is not None and cfg.offer_draw_enabled and abs(decision.score_cp) <= cfg.offer_draw_score and piece_count(board) <= cfg.offer_draw_pieces:
                draw_count += 1
            else:
                draw_count = 0
            decision.offer_draw = accepts_draw_offer or (cfg.offer_draw_enabled and draw_count >= cfg.offer_draw_moves)
            if accepts_draw_offer:
                draw_suffix = " acceptingDraw=true"
            else:
                draw_suffix = " offeringDraw=true" if decision.offer_draw else ""
            score_suffix = f" score={decision.score_cp}" if decision.score_cp is not None else ""
            log("MOVE", f"{game_id} posting ply={ply + 1} {decision.move.uci()} source={decision.source}{score_suffix}{draw_suffix}", Color.BLUE)
            try:
                bot_make_move_with_retry(token, game_id, decision.move.uci(), decision.offer_draw)
            except Exception as exc:
                if is_stale_move_error(exc):
                    finish_game_after_api_over(
                        token,
                        game_id,
                        account_id,
                        cfg,
                        state,
                        board,
                        game_full,
                        game_state,
                        color,
                        note="(stale move)",
                    )
                    finished = True
                    return
                raise
            log("MOVE", f"{game_id} accepted ply={ply + 1} {decision.move.uci()}", Color.BLUE)
            last_handled_moves = f"{moves} {decision.move.uci()}".strip()
    finally:
        state.end_game(game_id, finished=finished)


def is_compatible_challenge(challenge: dict[str, Any], cfg: BotConfig) -> tuple[bool, str]:
    if bool(challenge.get("rated", False)) != cfg.rated:
        return False, "rated mismatch"
    challenger = challenge.get("challenger", {}) or {}
    is_bot = is_bot_user(challenger)
    if is_bot and is_avoided_user(challenger, load_avoid_bots(cfg.avoid_bots_file)):
        return False, "avoided bot"
    if cfg.accept_from == "bot" and not is_bot:
        return False, "human challenger disabled"
    if cfg.accept_from == "human" and is_bot:
        return False, "bot challenger disabled"
    rating = challenge_rating(challenge)
    if cfg.min_rating is not None and rating is not None and rating < cfg.min_rating:
        return False, "rating too low"
    if cfg.max_rating is not None and rating is not None and rating > cfg.max_rating:
        return False, "rating too high"
    variant = challenge.get("variant", {})
    if (variant.get("key") or variant.get("name") or "standard").lower() != "standard":
        return False, "variant mismatch"
    tc = challenge.get("timeControl", {})
    if int(tc.get("limit", 0)) != cfg.clock_limit or int(tc.get("increment", 0)) != cfg.clock_increment:
        return False, "time control mismatch"
    return True, "ok"


def busy_human_challenge_message(challenge: dict[str, Any], cfg: BotConfig, reason: str) -> str:
    challenger = challenge.get("challenger", {}) or {}
    rating = challenge_rating(challenge)
    rating_text = f" · {rating}" if rating is not None else ""
    tc = challenge.get("timeControl", {}) or {}
    limit = int(tc.get("limit", cfg.clock_limit) or cfg.clock_limit)
    inc = int(tc.get("increment", cfg.clock_increment) or cfg.clock_increment)
    rated = "rated" if bool(challenge.get("rated", False)) else "unrated"
    return (
        f"⏸️ Human challenge declined\n"
        f"{user_name(challenger)}{rating_text}\n"
        f"{rated} {limit // 60}+{inc} · reason={reason}"
    )


def notify_busy_human_challenge(challenge: dict[str, Any], cfg: BotConfig, reason: str) -> None:
    if not cfg.notify_busy_human_challenge:
        return
    challenger = challenge.get("challenger", {}) or {}
    if is_bot_user(challenger):
        return
    notify(cfg, busy_human_challenge_message(challenge, cfg, reason))


def decline_busy_challenge(
    token: str,
    challenge: dict[str, Any],
    cfg: BotConfig,
    challenger: str,
    reason: str = "busy",
) -> None:
    challenge_id = challenge.get("id")
    if not challenge_id:
        return
    challenge_action(token, "decline", challenge_id, challenger, reason)
    notify_busy_human_challenge(challenge, cfg, reason)


def accept_or_decline_challenge(token: str, challenge: dict[str, Any], cfg: BotConfig, state: RuntimeState, account_id: str) -> None:
    challenge_id = challenge.get("id")
    challenger_obj = challenge.get("challenger", {}) or {}
    challenger_id = user_id(challenger_obj)
    challenger = user_name(challenger_obj)
    if not challenge_id:
        return
    if challenger_id == account_id:
        log("CHALLENGE", f"ignored own outgoing challenge {challenge_id}", Color.YELLOW)
        return
    if state.active_count() >= cfg.max_parallel_games:
        decline_busy_challenge(token, challenge, cfg, challenger)
        return
    ok, reason = is_compatible_challenge(challenge, cfg)
    if ok:
        reservation_key = f"in:{challenge_id}"
        if not state.try_reserve_slot(reservation_key, cfg.max_parallel_games):
            decline_busy_challenge(token, challenge, cfg, challenger)
            return
        kind = "bot" if is_bot_user(challenger_obj) else "human"
        rating = challenge_rating(challenge)
        rating_text = f" rating={rating}" if rating is not None else ""
        if not challenge_action(token, "accept", challenge_id, challenger, f"{kind} rated={cfg.rated}{rating_text}"):
            state.release_reserved_slot(reservation_key)
    else:
        challenge_action(token, "decline", challenge_id, challenger, reason)


def challenge_action(token: str, action: str, challenge_id: str, challenger: str, reason: str) -> bool:
    try:
        if action == "accept":
            api_request(token, "POST", f"/api/challenge/{urllib.parse.quote(challenge_id)}/accept")
            log("CHALLENGE", f"accepted {challenger} {reason}", Color.YELLOW)
        else:
            payload = {"reason": reason} if reason == "busy" else None
            api_request(token, "POST", f"/api/challenge/{urllib.parse.quote(challenge_id)}/decline", payload)
            log("CHALLENGE", f"declined {challenger}: {reason}", Color.YELLOW)
        return True
    except Exception as exc:
        log("API", f"challenge {action} ignored for {challenger}: {describe_error(exc)}", Color.GRAY)
        return False


def run_event_loop(
    token: str,
    engine: chess.engine.SimpleEngine,
    account_id: str,
    cfg: BotConfig,
    state: RuntimeState,
    quota: "ChallengeQuota | None" = None,
) -> None:
    log("IDLE", "listening for games/challenges", Color.GREEN)
    while not state.stop.is_set():
        try:
            for event in bot_event_stream(token):
                if state.stop.is_set():
                    return
                etype = event.get("type")
                if etype == "challenge":
                    try:
                        accept_or_decline_challenge(token, event.get("challenge", {}), cfg, state, account_id)
                    except Exception as exc:
                        log("API", f"challenge event ignored: {describe_error(exc)}", Color.GRAY)
                elif etype == "gameStart":
                    game_id = event.get("game", {}).get("id")
                    if not game_id:
                        continue
                    if not state.try_begin_game(game_id, "starting", cfg.max_parallel_games):
                        log("CHALLENGE", f"gameStart {game_id} while busy; ignoring", Color.YELLOW)
                        continue
                    log("PLAYING", f"gameStart {game_id}", Color.RED)
                    threading.Thread(
                        target=run_game_worker,
                        args=(token, engine, game_id, account_id, cfg, state, quota),
                        daemon=True,
                    ).start()
        except Exception as exc:
            if not state.stop.is_set():
                log("API", f"event stream reconnecting after: {describe_error(exc)}", Color.GRAY)
                time.sleep(5)


def run_game_worker(
    token: str,
    engine: chess.engine.SimpleEngine,
    game_id: str,
    account_id: str,
    cfg: BotConfig,
    state: RuntimeState,
    quota: "ChallengeQuota | None" = None,
) -> None:
    try:
        play_game(token, engine, game_id, account_id, cfg, state, quota)
    except Exception as exc:
        detail = describe_error(exc)
        log("API", f"game {game_id} stopped with error: {detail}", Color.GRAY)
        notify(cfg, f"⚠️ GAME WORKER STOPPED {game_id}\n{detail}\n{game_url(game_id)}")


def api_request(token: str, method: str, path: str, data: dict[str, Any] | None = None) -> Any:
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(f"{LICHESS_API}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace").strip()
        scopes = exc.headers.get("x-oauth-scopes")
        accepted = exc.headers.get("x-accepted-oauth-scopes")
        extra = []
        if detail:
            extra.append(detail)
        if scopes:
            extra.append(f"scopes={scopes}")
        if accepted:
            extra.append(f"accepted_scopes={accepted}")
        suffix = f": {'; '.join(extra)}" if extra else ""
        raise ApiError(f"HTTP {exc.code} {exc.reason} {method} {path}{suffix}") from exc
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def api_stream(token: str, path: str) -> Any:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/x-ndjson",
    }
    req = urllib.request.Request(f"{LICHESS_API}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            for raw in resp:
                line = raw.decode().strip()
                if line:
                    yield json.loads(line)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace").strip()
        scopes = exc.headers.get("x-oauth-scopes")
        accepted = exc.headers.get("x-accepted-oauth-scopes")
        extra = []
        if detail:
            extra.append(detail)
        if scopes:
            extra.append(f"scopes={scopes}")
        if accepted:
            extra.append(f"accepted_scopes={accepted}")
        suffix = f": {'; '.join(extra)}" if extra else ""
        raise ApiError(f"HTTP {exc.code} {exc.reason} GET {path}{suffix}") from exc


def bot_event_stream(token: str) -> Any:
    return api_stream(token, "/api/stream/event")


def bot_game_stream(token: str, game_id: str) -> Any:
    return api_stream(token, f"/api/bot/game/stream/{urllib.parse.quote(game_id)}")


def bot_make_move(token: str, game_id: str, move: str, offering_draw: bool = False) -> None:
    suffix = "?offeringDraw=true" if offering_draw else ""
    api_request(token, "POST", f"/api/bot/game/{urllib.parse.quote(game_id)}/move/{urllib.parse.quote(move)}{suffix}")


def bot_resign(token: str, game_id: str) -> None:
    api_request(token, "POST", f"/api/bot/game/{urllib.parse.quote(game_id)}/resign")


def bot_abort(token: str, game_id: str) -> None:
    api_request(token, "POST", f"/api/bot/game/{urllib.parse.quote(game_id)}/abort")


def bot_claim_draw(token: str, game_id: str) -> None:
    api_request(token, "POST", f"/api/bot/game/{urllib.parse.quote(game_id)}/claim-draw")


def bot_chat(token: str, game_id: str, room: str, text: str) -> None:
    api_request(
        token,
        "POST",
        f"/api/bot/game/{urllib.parse.quote(game_id)}/chat",
        {"room": room, "text": text},
    )


def cancel_challenge(token: str, challenge_id: str, username: str) -> bool:
    if not challenge_id:
        return False
    try:
        api_request(token, "POST", f"/api/challenge/{urllib.parse.quote(challenge_id, safe='')}/cancel")
        log("CHALLENGE", f"cancelled stale challenge to {username}", Color.YELLOW)
        return True
    except Exception as exc:
        log("API", f"stale challenge cancel ignored for {username}: {describe_error(exc)}", Color.GRAY)
        return False


def online_bots(token: str) -> list[dict[str, Any]]:
    data = api_request(token, "GET", "/api/bot/online?nb=512")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("users"), list):
            return data["users"]
        if isinstance(data.get("online"), list):
            return data["online"]
    return []


def blitz_perf(user: dict[str, Any]) -> dict[str, Any]:
    return dict(user.get("perfs", {}).get("blitz", {}) or {})


def own_blitz_rating(client: Any, cfg: BotConfig) -> int:
    try:
        me = api_account(client)
        blitz = me.get("perfs", {}).get("blitz", {}) or {}
        if cfg.use_fallback_rating_when_provisional and bool(blitz.get("prov", False)):
            return cfg.fallback_blitz_rating
        return int(blitz.get("rating", cfg.fallback_blitz_rating))
    except Exception:
        return cfg.fallback_blitz_rating


def api_account(token: str) -> dict[str, Any]:
    data = api_request(token, "GET", "/api/account")
    return data if isinstance(data, dict) else {}


def elo_expected_score(own_rating: int, opponent_rating: int) -> float:
    return 1.0 / (1.0 + 10.0 ** ((opponent_rating - own_rating) / 400.0))


def expected_score_allowed(own_rating: int, opponent_rating: int, cfg: BotConfig) -> bool:
    expected = elo_expected_score(own_rating, opponent_rating)
    if cfg.target_expected_score_min is not None and expected < cfg.target_expected_score_min:
        return False
    if cfg.target_expected_score_max is not None and expected > cfg.target_expected_score_max:
        return False
    return True


def choose_candidates(
    users: list[dict[str, Any]],
    account_id: str,
    rating: int,
    cfg: BotConfig,
    closest_superior: bool = False,
) -> list[dict[str, Any]]:
    lo = rating + cfg.target_rating_min_delta
    hi = rating + cfg.target_rating_max_delta
    avoid_bots = load_avoid_bots(cfg.avoid_bots_file)
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for user in users:
        username = user.get("username") or user.get("name") or user.get("id")
        if not username or str(username).lower() == account_id:
            continue
        if is_avoided_user(user, avoid_bots):
            continue
        perf = blitz_perf(user)
        games = int(perf.get("games", 0) or 0)
        rated = int(perf.get("rating", 0) or 0)
        provisional = bool(perf.get("prov", False))
        if games < cfg.min_blitz_games:
            continue
        if provisional and not cfg.allow_provisional:
            continue
        if lo <= rated <= hi and expected_score_allowed(rating, rated, cfg):
            candidates.append((rated, str(username), user))
    if closest_superior:
        candidates = [item for item in candidates if item[0] > rating]
        candidates.sort(key=lambda item: (item[0] - rating, item[1].lower()))
    else:
        random.shuffle(candidates)
    return [item[2] for item in candidates]


def challenge_cooldown_seconds(exc: Exception) -> int | None:
    detail = str(exc)
    seconds_match = re.search(r'"seconds"\s*:\s*(\d+)', detail)
    if seconds_match:
        return max(60, int(seconds_match.group(1)))
    if "bot.vsBot.day" in detail or "played 100 games against other bots today" in detail:
        return 60 * 60
    return None


class ChallengeQuota:
    def __init__(self, path: str, daily_limit: int, margin: int) -> None:
        self.path = Path(path)
        self.daily_limit = max(0, daily_limit)
        self.margin = max(0, margin)
        self.day = dt.datetime.now(dt.timezone.utc).date().isoformat()
        self.sent = 0
        self._load()

    @property
    def stop_at(self) -> int:
        if self.daily_limit <= 0:
            return 0
        return max(0, self.daily_limit - self.margin)

    def _rollover(self) -> None:
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        if self.day != today:
            self.day = today
            self.sent = 0
            self.save()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except Exception:
            return
        if data.get("day") == self.day:
            self.sent = int(data.get("sent", 0) or 0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"day": self.day, "sent": self.sent}, indent=2) + "\n")

    def remaining(self) -> int:
        self._rollover()
        if self.daily_limit <= 0:
            return 10**9
        return max(0, self.stop_at - self.sent)

    def can_send(self) -> bool:
        return self.remaining() > 0

    def record_attempt(self) -> None:
        self._rollover()
        self.sent += 1
        self.save()

    def log_status(self) -> None:
        if self.daily_limit <= 0:
            log("CHALLENGE", "local bot-vs-bot daily quota guard disabled", Color.YELLOW)
            return
        log(
            "CHALLENGE",
            f"local bot-vs-bot quota {self.sent}/{self.stop_at} used for {self.day} UTC "
            f"(server limit assumed {self.daily_limit}, margin {self.margin})",
            Color.YELLOW,
        )


def stop_after_current_game(path: str) -> bool:
    control_path = Path(path)
    if not control_path.exists():
        return False
    try:
        data = json.loads(control_path.read_text())
    except Exception as exc:
        log("CONTROL", f"ignoring unreadable {control_path}: {describe_error(exc)}", Color.GRAY)
        return False
    return bool(data.get("stop_after_current_game", False))


def challenge_id_from_response(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    challenge = data.get("challenge")
    if isinstance(challenge, dict) and challenge.get("id"):
        return str(challenge["id"])
    if data.get("id"):
        return str(data["id"])
    return None


def send_challenge(token: str, username: str, cfg: BotConfig) -> str | None:
    payload = {
        "rated": "true" if cfg.rated else "false",
        "clock.limit": str(cfg.clock_limit),
        "clock.increment": str(cfg.clock_increment),
        "variant": "standard",
        "color": cfg.challenge_color,
    }
    data = api_request(token, "POST", f"/api/challenge/{urllib.parse.quote(username)}", payload)
    log("CHALLENGE", f"sent to {username} rated={str(cfg.rated).lower()} tc={cfg.clock_limit // 60}+{cfg.clock_increment}", Color.YELLOW)
    return challenge_id_from_response(data)


def challenge_users(token: str, usernames: list[str], cfg: BotConfig) -> None:
    targets = usernames
    if cfg.max_parallel_games <= 1 and len(usernames) > 1:
        targets = usernames[:1]
        skipped = ", ".join(usernames[1:])
        log("CHALLENGE", f"one-game mode: challenging {usernames[0]} only; skipped {skipped}", Color.YELLOW)
    for username in targets:
        send_challenge(token, username, cfg)


def challenge_loop(
    token: str,
    account_id: str,
    cfg: BotConfig,
    state: RuntimeState,
    quota: ChallengeQuota,
    closest_superior: bool = False,
) -> None:
    blocked_until: dict[str, float] = {}
    pending_challenges: dict[str, dict[str, Any]] = {}
    quota.log_status()
    while not state.stop.is_set():
        if state.active_count() == 0:
            now = time.time()
            for username, pending in list(pending_challenges.items()):
                if float(pending.get("cancel_after", 0)) > now:
                    continue
                if state.has_pending_outgoing_bot(username):
                    challenge_id = str(pending.get("challenge_id") or "")
                    cancelled = False
                    if cfg.cancel_stale_outgoing_challenges and challenge_id:
                        cancelled = cancel_challenge(token, challenge_id, username)
                    if cancelled or not challenge_id or not cfg.cancel_stale_outgoing_challenges:
                        state.clear_pending_outgoing_bot(username)
                    state.release_reserved_slot(str(pending.get("reservation_key") or f"out:{username}"))
                    blocked_until[username] = now + max(180, cfg.challenge_interval_sec * 3)
                pending_challenges.pop(username, None)
            if stop_after_current_game(cfg.challenge_control_file):
                log("IDLE", f"challenge loop paused by {cfg.challenge_control_file}", Color.GREEN)
                time.sleep(cfg.challenge_interval_sec)
                continue
            if not quota.can_send():
                log("IDLE", f"local bot-vs-bot quota exhausted for {quota.day} UTC; waiting", Color.GREEN)
                time.sleep(cfg.challenge_interval_sec)
                continue
            rating = own_blitz_rating(token, cfg)
            try:
                candidates = choose_candidates(online_bots(token), account_id, rating, cfg, closest_superior=closest_superior)
                attempts = 0
                challenged = False
                for candidate in candidates:
                    username = str(candidate.get("username") or candidate.get("name") or candidate.get("id") or "")
                    if not username:
                        continue
                    username_key = username.lower()
                    cooldown_remaining = state.opponent_cooldown_remaining(username, cfg.opponent_cooldown_sec)
                    if cooldown_remaining > 0:
                        continue
                    wait_until = blocked_until.get(username_key, 0)
                    if wait_until > now:
                        continue
                    attempts += 1
                    reservation_key = f"out:{username_key}"
                    reserve_ttl = cfg.challenge_interval_sec if closest_superior else 180
                    if not state.try_reserve_slot(reservation_key, cfg.max_parallel_games, ttl_sec=reserve_ttl):
                        break
                    try:
                        challenge_id = send_challenge(token, username, cfg)
                        state.mark_outgoing_bot_challenge(username)
                        challenged = True
                        log("CHALLENGE", f"quota will count if {username} starts a bot game", Color.YELLOW)
                        if closest_superior:
                            skip_for = max(180, cfg.challenge_interval_sec * 3)
                            blocked_until[username_key] = now + skip_for
                            pending_challenges[username_key] = {
                                "challenge_id": challenge_id,
                                "reservation_key": reservation_key,
                                "cancel_after": now + cfg.challenge_interval_sec,
                            }
                            log(
                                "CHALLENGE",
                                f"waiting one idle cycle for {username}; next miss tries the next closest superior",
                                Color.YELLOW,
                            )
                        break
                    except Exception as exc:
                        state.release_reserved_slot(reservation_key)
                        cooldown = challenge_cooldown_seconds(exc)
                        if cooldown is not None:
                            blocked_until[username_key] = now + cooldown
                            log("CHALLENGE", f"skipping {username} for {cooldown // 60}m: {describe_error(exc)}", Color.YELLOW)
                        else:
                            log("API", f"challenge to {username} failed: {describe_error(exc)}", Color.GRAY)
                        if attempts >= cfg.max_challenge_attempts_per_cycle:
                            break
                if not challenged:
                    mode_text = "closest superior " if closest_superior else ""
                    log("IDLE", f"no online {mode_text}bot in blitz range {rating}+{cfg.target_rating_min_delta}..+{cfg.target_rating_max_delta}", Color.GREEN)
            except urllib.error.HTTPError as exc:
                log("API", f"challenge loop HTTP {exc.code}: {exc.reason}", Color.GRAY)
            except Exception as exc:
                log("API", f"challenge loop error: {exc}", Color.GRAY)
        time.sleep(cfg.challenge_interval_sec)


def wait_for_active_games(state: RuntimeState) -> None:
    while state.active_count() > 0:
        time.sleep(0.25)


def run_live(
    token: str,
    cfg: BotConfig,
    mode: str,
    challenge_names: list[str] | None = None,
    games_limit: int | None = None,
    closest_superior: bool = False,
    oracle_after_block: bool = False,
) -> None:
    account = api_account(token)
    account_id = str(account.get("id") or account.get("username") or account.get("name") or "").lower()
    state = RuntimeState(games_limit=games_limit, opponent_cooldown_file=cfg.opponent_cooldown_file)
    signal.signal(signal.SIGINT, state.handle_sigint)
    threading.Thread(target=heartbeat, args=(state, cfg.heartbeat_sec), daemon=True).start()

    games_text = f" games={games_limit}" if games_limit is not None else ""
    selection_text = " selection=closest-superior" if closest_superior else ""
    log(
        "CONFIG",
        f"mode={mode} rated={str(cfg.rated).lower()} tc={cfg.clock_limit // 60}+{cfg.clock_increment} "
        f"threads={cfg.uci_threads} engine={cfg.engine}{games_text}{selection_text}",
        Color.GRAY,
    )
    with chess.engine.SimpleEngine.popen_uci(cfg.engine, timeout=5.0) as engine:
        configure_uci_engine(engine, cfg)
        if mode == "challenge-loop":
            quota = ChallengeQuota(cfg.challenge_quota_file, cfg.max_bot_challenges_per_day, cfg.bot_challenge_quota_margin)
            threading.Thread(
                target=run_event_loop,
                args=(token, engine, account_id, cfg, state, quota),
                daemon=True,
            ).start()
            challenge_loop(token, account_id, cfg, state, quota, closest_superior=closest_superior)
        elif mode == "challenge":
            challenge_users(token, challenge_names or [], cfg)
            run_event_loop(token, engine, account_id, cfg, state)
        else:
            run_event_loop(token, engine, account_id, cfg, state)
        wait_for_active_games(state)
    if games_limit is not None:
        notify_block_summary(token, cfg, state, games_limit)
    if games_limit is not None and (oracle_after_block or cfg.oracle_after_block):
        run_oracle_after_block(cfg, state, games_limit)
    if games_limit is not None:
        log("IDLE", f"finished {state.completed_games}/{games_limit} game(s); exiting", Color.GREEN)


def rated_override_from_args(args: argparse.Namespace) -> bool | None:
    if args.rated:
        return True
    if args.unrated:
        return False
    return False if args.listen or args.challenge_loop or args.challenge else None


def main() -> int:
    parser = argparse.ArgumentParser(description="LabZero native Lichess bot runner")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--notify-test", action="store_true")
    parser.add_argument("--notify-test-text", default="LabZero notification test")
    parser.add_argument("--notify-test-file", help="optional file to send via Telegram sendDocument")
    parser.add_argument("--listen", action="store_true")
    parser.add_argument("--challenge-loop", action="store_true")
    parser.add_argument("--challenge", nargs="+", metavar="USERNAME", help="challenge one or more Lichess users, then listen for the game")
    parser.add_argument("--closest-superior", action="store_true", help="with --challenge-loop, challenge the closest stronger eligible bot instead of a random eligible bot")
    parser.add_argument("--oracle-after-block", action="store_true", help="after --games N completes, run the bounded Stockfish oracle labeler on the saved block PGNs")
    rated = parser.add_mutually_exclusive_group()
    rated.add_argument("--rated", action="store_true")
    rated.add_argument("--unrated", action="store_true")
    parser.add_argument("--games", type=int, metavar="N", help="stop after N completed games (live modes only)")
    args = parser.parse_args()

    if args.games is not None and args.games < 1:
        parser.error("--games must be at least 1")
    if args.games is not None and (args.dry_run or args.notify_test):
        parser.error("--games cannot be used with --dry-run or --notify-test")
    if args.closest_superior and not args.challenge_loop:
        parser.error("--closest-superior can only be used with --challenge-loop")
    if args.oracle_after_block and args.games is None:
        parser.error("--oracle-after-block requires --games N")

    selected_modes = [args.dry_run, args.notify_test, args.listen, args.challenge_loop, bool(args.challenge)]
    if sum(bool(m) for m in selected_modes) != 1:
        parser.error("choose exactly one of --dry-run, --notify-test, --listen, --challenge-loop, or --challenge")

    load_env(Path(args.env_file))
    cfg = BotConfig.from_dict(load_toml(Path(args.config)), rated_override_from_args(args))

    if args.notify_test:
        try:
            notify_test(cfg, args.notify_test_text, args.notify_test_file)
            return 0
        except Exception as exc:
            log("API", f"notification test failed: {describe_error(exc)}", Color.GRAY)
            return 1

    if args.dry_run:
        try:
            dry_run_test(cfg.engine, cfg)
            return 0
        except Exception as exc:
            log("API", f"dry-run failed: {describe_error(exc)}", Color.GRAY)
            return 1

    token = os.environ.get("LICHESS_TOKEN")
    if not token:
        log("API", "Set LICHESS_TOKEN in environment or lichess_bot/.env", Color.GRAY)
        return 1
    if not Path(cfg.engine).exists():
        log("API", f"engine not found: {cfg.engine}", Color.GRAY)
        return 1

    try:
        if args.challenge_loop:
            mode = "challenge-loop"
        elif args.challenge:
            mode = "challenge"
        else:
            mode = "listen"
        run_live(
            token,
            cfg,
            mode,
            args.challenge,
            games_limit=args.games,
            closest_superior=args.closest_superior,
            oracle_after_block=args.oracle_after_block,
        )
        return 0
    except Exception as exc:
        log("API", f"runner stopped: {describe_error(exc)}", Color.GRAY)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
