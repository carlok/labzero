#!/usr/bin/env python3
"""Native Lichess Bot API bridge for LabZero.

This runner is intentionally small and host-local: it spawns a copied UCI binary
from ``lichess_bot/bin/`` and keeps foreground status visible while games run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import signal
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
    fallback_blitz_rating: int
    use_fallback_rating_when_provisional: bool
    max_challenge_attempts_per_cycle: int
    max_bot_challenges_per_day: int
    bot_challenge_quota_margin: int
    challenge_quota_file: str
    challenge_control_file: str
    avoid_bots_file: str
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
            fallback_blitz_rating=int(cfg.get("fallback_blitz_rating", 1500)),
            use_fallback_rating_when_provisional=bool(cfg.get("use_fallback_rating_when_provisional", True)),
            max_challenge_attempts_per_cycle=int(cfg.get("max_challenge_attempts_per_cycle", 8)),
            max_bot_challenges_per_day=int(cfg.get("max_bot_challenges_per_day", 100)),
            bot_challenge_quota_margin=int(cfg.get("bot_challenge_quota_margin", 10)),
            challenge_quota_file=resolve_path(str(cfg.get("challenge_quota_file", "lichess_bot/local/challenge-quota.json"))),
            challenge_control_file=resolve_path(str(cfg.get("challenge_control_file", "lichess_bot/local/challenge-control.json"))),
            avoid_bots_file=resolve_path(str(cfg.get("avoid_bots_file", "lichess_bot/local/avoid-bots.json"))),
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
        )


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


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


@dataclass
class MoveDecision:
    move: chess.Move
    score_cp: int | None = None
    offer_draw: bool = False
    source: str = "engine"


class RuntimeState:
    def __init__(self, games_limit: int | None = None) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, str] = {}
        self._reserved: dict[str, float] = {}
        self._pending_outgoing_bots: set[str] = set()
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

    def end_game(self, game_id: str) -> None:
        limit_reached = False
        completed = 0
        limit = self.games_limit
        with self._lock:
            was_active = game_id in self._active
            self._active.pop(game_id, None)
            if was_active:
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
    if board.is_game_over(claim_draw=True):
        return board.result(claim_draw=True)
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


def piece_count(board: chess.Board) -> int:
    return len(board.piece_map())


def score_for_color(info: dict[str, Any], color: chess.Color) -> int | None:
    score = info.get("score")
    if score is None:
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
    try:
        return score.pov(color).score(mate_score=100000)
    except Exception:
        return None


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
                    dtz = abs(tablebase.probe_dtz(board))
                    scored.append((wdl, -dtz, move))
                except Exception:
                    pass
                finally:
                    board.pop()
    except Exception as exc:
        log("TB", f"tablebase ignored: {describe_error(exc)}", Color.GRAY)
        return None
    return max(scored, default=(0, 0, None))[2]  # type: ignore[return-value]


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
) -> None:
    if not cfg.pgn_directory:
        return
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
    state.update_game(game_id, "starting")
    try:
        for event in bot_game_stream(token, game_id):
            etype = event.get("type")
            if etype == "gameFull":
                game_full = event
                color = bot_color_from_full(event, account_id)
                if color is None:
                    log("API", f"cannot determine bot color for {game_id}", Color.GRAY)
                    return
                side = "white" if color == chess.WHITE else "black"
                state.update_game(game_id, f"color={side}")
                log("START", f"▶️ {game_id} bot={side} {matchup_label(event)}", Color.RED)
                opponent_player = player_obj(event, "black" if color == chess.WHITE else "white")
                if quota is not None and is_bot_user(opponent_player) and state.consume_outgoing_bot_game(opponent_player):
                    quota.record_attempt()
                    quota.log_status()
                game_state = event.get("state", {})
                if not hello_sent:
                    opponent = user_name(opponent_player)
                    maybe_chat(token, game_id, "player", format_chat(cfg.hello, me=account_id, opponent=opponent))
                    hello_sent = True
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

            if board.is_game_over() or terminal_status(game_state) in {"mate", "resign", "draw", "stalemate", "timeout", "outoftime"}:
                result = pgn_result(board, game_state)
                result_text, result_symbol = result_for_bot(result, color)
                matchup = f" {matchup_label(game_full)}" if game_full else ""
                log(
                    "GAME END",
                    f"{result_symbol} {result_text} {game_id} result={result} status={terminal_status(game_state) or board.result()}{matchup}",
                    Color.MAGENTA,
                )
                if game_full and color is not None:
                    opponent = game_player_name(game_full, "black" if color == chess.WHITE else "white")
                    maybe_chat(token, game_id, "player", format_chat(cfg.goodbye, me=account_id, opponent=opponent))
                save_pgn(cfg, game_id, board, game_full, game_state)
                return
            if color is None or board.turn != color or moves == last_handled_moves:
                continue

            decision = choose_move(engine, board, color, cfg, game_state)
            if decision.move not in board.legal_moves:
                log("API", f"illegal {decision.source} move {decision.move} in {game_id}", Color.GRAY)
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
            bot_make_move(token, game_id, decision.move.uci(), decision.offer_draw)
            log("MOVE", f"{game_id} accepted ply={ply + 1} {decision.move.uci()}", Color.BLUE)
            last_handled_moves = f"{moves} {decision.move.uci()}".strip()
    finally:
        state.end_game(game_id)


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
        challenge_action(token, "decline", challenge_id, challenger, "busy")
        return
    ok, reason = is_compatible_challenge(challenge, cfg)
    if ok:
        reservation_key = f"in:{challenge_id}"
        if not state.try_reserve_slot(reservation_key, cfg.max_parallel_games):
            challenge_action(token, "decline", challenge_id, challenger, "busy")
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
            api_request(token, "POST", f"/api/challenge/{urllib.parse.quote(challenge_id)}/decline")
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
        log("API", f"game {game_id} stopped with error: {describe_error(exc)}", Color.GRAY)


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


def bot_chat(token: str, game_id: str, room: str, text: str) -> None:
    api_request(
        token,
        "POST",
        f"/api/bot/game/{urllib.parse.quote(game_id)}/chat",
        {"room": room, "text": text},
    )


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


def choose_candidates(users: list[dict[str, Any]], account_id: str, rating: int, cfg: BotConfig) -> list[dict[str, Any]]:
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
        if lo <= rated <= hi:
            candidates.append((rated, str(username), user))
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


def send_challenge(token: str, username: str, cfg: BotConfig) -> None:
    payload = {
        "rated": "true" if cfg.rated else "false",
        "clock.limit": str(cfg.clock_limit),
        "clock.increment": str(cfg.clock_increment),
        "variant": "standard",
        "color": cfg.challenge_color,
    }
    api_request(token, "POST", f"/api/challenge/{urllib.parse.quote(username)}", payload)
    log("CHALLENGE", f"sent to {username} rated={str(cfg.rated).lower()} tc={cfg.clock_limit // 60}+{cfg.clock_increment}", Color.YELLOW)


def challenge_users(token: str, usernames: list[str], cfg: BotConfig) -> None:
    targets = usernames
    if cfg.max_parallel_games <= 1 and len(usernames) > 1:
        targets = usernames[:1]
        skipped = ", ".join(usernames[1:])
        log("CHALLENGE", f"one-game mode: challenging {usernames[0]} only; skipped {skipped}", Color.YELLOW)
    for username in targets:
        send_challenge(token, username, cfg)


def challenge_loop(token: str, account_id: str, cfg: BotConfig, state: RuntimeState, quota: ChallengeQuota) -> None:
    blocked_until: dict[str, float] = {}
    quota.log_status()
    while not state.stop.is_set():
        if state.active_count() == 0:
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
                now = time.time()
                candidates = choose_candidates(online_bots(token), account_id, rating, cfg)
                attempts = 0
                challenged = False
                for candidate in candidates:
                    username = str(candidate.get("username") or candidate.get("name") or candidate.get("id") or "")
                    if not username:
                        continue
                    wait_until = blocked_until.get(username.lower(), 0)
                    if wait_until > now:
                        continue
                    attempts += 1
                    reservation_key = f"out:{username.lower()}"
                    if not state.try_reserve_slot(reservation_key, cfg.max_parallel_games):
                        break
                    try:
                        send_challenge(token, username, cfg)
                        state.mark_outgoing_bot_challenge(username)
                        challenged = True
                        log("CHALLENGE", f"quota will count if {username} starts a bot game", Color.YELLOW)
                        break
                    except Exception as exc:
                        state.release_reserved_slot(reservation_key)
                        cooldown = challenge_cooldown_seconds(exc)
                        if cooldown is not None:
                            blocked_until[username.lower()] = now + cooldown
                            log("CHALLENGE", f"skipping {username} for {cooldown // 60}m: {describe_error(exc)}", Color.YELLOW)
                        else:
                            log("API", f"challenge to {username} failed: {describe_error(exc)}", Color.GRAY)
                        if attempts >= cfg.max_challenge_attempts_per_cycle:
                            break
                if not challenged:
                    log("IDLE", f"no online bot in blitz range {rating}+{cfg.target_rating_min_delta}..+{cfg.target_rating_max_delta}", Color.GREEN)
            except urllib.error.HTTPError as exc:
                log("API", f"challenge loop HTTP {exc.code}: {exc.reason}", Color.GRAY)
            except Exception as exc:
                log("API", f"challenge loop error: {exc}", Color.GRAY)
        time.sleep(cfg.challenge_interval_sec)


def wait_for_active_games(state: RuntimeState) -> None:
    while state.active_count() > 0:
        time.sleep(0.25)


def run_live(token: str, cfg: BotConfig, mode: str, challenge_names: list[str] | None = None, games_limit: int | None = None) -> None:
    account = api_account(token)
    account_id = str(account.get("id") or account.get("username") or account.get("name") or "").lower()
    state = RuntimeState(games_limit=games_limit)
    signal.signal(signal.SIGINT, state.handle_sigint)
    threading.Thread(target=heartbeat, args=(state, cfg.heartbeat_sec), daemon=True).start()

    games_text = f" games={games_limit}" if games_limit is not None else ""
    log(
        "CONFIG",
        f"mode={mode} rated={str(cfg.rated).lower()} tc={cfg.clock_limit // 60}+{cfg.clock_increment} "
        f"threads={cfg.uci_threads} engine={cfg.engine}{games_text}",
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
            challenge_loop(token, account_id, cfg, state, quota)
        elif mode == "challenge":
            challenge_users(token, challenge_names or [], cfg)
            run_event_loop(token, engine, account_id, cfg, state)
        else:
            run_event_loop(token, engine, account_id, cfg, state)
    if games_limit is not None:
        wait_for_active_games(state)
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
    parser.add_argument("--listen", action="store_true")
    parser.add_argument("--challenge-loop", action="store_true")
    parser.add_argument("--challenge", nargs="+", metavar="USERNAME", help="challenge one or more Lichess users, then listen for the game")
    rated = parser.add_mutually_exclusive_group()
    rated.add_argument("--rated", action="store_true")
    rated.add_argument("--unrated", action="store_true")
    parser.add_argument("--games", type=int, metavar="N", help="stop after N completed games (live modes only)")
    args = parser.parse_args()

    if args.games is not None and args.games < 1:
        parser.error("--games must be at least 1")
    if args.games is not None and args.dry_run:
        parser.error("--games cannot be used with --dry-run")

    selected_modes = [args.dry_run, args.listen, args.challenge_loop, bool(args.challenge)]
    if sum(bool(m) for m in selected_modes) != 1:
        parser.error("choose exactly one of --dry-run, --listen, --challenge-loop, or --challenge")

    load_env(Path(args.env_file))
    cfg = BotConfig.from_dict(load_toml(Path(args.config)), rated_override_from_args(args))

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
        run_live(token, cfg, mode, args.challenge, games_limit=args.games)
        return 0
    except Exception as exc:
        log("API", f"runner stopped: {describe_error(exc)}", Color.GRAY)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
