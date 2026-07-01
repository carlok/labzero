#!/usr/bin/env python3
"""Generate EPD puzzle candidates from large Lichess PGN dumps."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TextIO

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class GameRef:
    path: str
    offset: int
    game_id: str
    white_elo: int
    black_elo: int
    result: str


@dataclass
class PuzzleCandidate:
    category: str
    fen: str
    bm: str
    played: str
    game_id: str
    ply: int
    white_elo: int
    black_elo: int
    gap_cp: int | None
    best_cp: int | None
    second_cp: int | None
    best_mate: int | None
    source: str


def load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
    with path.open("rb") as f:
        return tomllib.load(f)


def resolve(path: str | None) -> str | None:
    if path is None:
        return None
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = ROOT / p
    return str(p)


def int_header(headers: chess.pgn.Headers, key: str) -> int | None:
    try:
        return int(str(headers.get(key, "")).strip())
    except ValueError:
        return None


def game_id_from_site(site: str) -> str:
    match = re.search(r"lichess\.org/([A-Za-z0-9]{8})", site)
    return match.group(1) if match else site.rsplit("/", 1)[-1]


def eligible_headers(headers: chess.pgn.Headers, min_elo: int) -> tuple[bool, str]:
    white = int_header(headers, "WhiteElo")
    black = int_header(headers, "BlackElo")
    if white is None or black is None or white < min_elo or black < min_elo:
        return False, "elo"
    if headers.get("Termination") != "Normal":
        return False, "termination"
    if headers.get("Result") not in {"1-0", "0-1", "1/2-1/2"}:
        return False, "result"
    return True, "ok"


def pgn_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.rglob("*.pgn") if path.is_file())


def sample_game_refs(
    input_dir: Path,
    *,
    min_elo: int,
    sample_games: int,
    max_games_scanned: int,
    rng: random.Random,
) -> tuple[list[GameRef], dict[str, int]]:
    sampled: list[GameRef] = []
    stats = {"scanned": 0, "eligible": 0, "elo": 0, "termination": 0, "result": 0}
    for path in pgn_files(input_dir):
        with path.open("r", encoding="utf-8", errors="replace") as f:
            while stats["scanned"] < max_games_scanned:
                offset = f.tell()
                headers = chess.pgn.read_headers(f)
                if headers is None:
                    break
                stats["scanned"] += 1
                ok, reason = eligible_headers(headers, min_elo)
                if not ok:
                    stats[reason] = stats.get(reason, 0) + 1
                    continue
                stats["eligible"] += 1
                ref = GameRef(
                    path=str(path),
                    offset=offset,
                    game_id=game_id_from_site(headers.get("Site", "")),
                    white_elo=int_header(headers, "WhiteElo") or 0,
                    black_elo=int_header(headers, "BlackElo") or 0,
                    result=headers.get("Result", "*"),
                )
                if len(sampled) < sample_games:
                    sampled.append(ref)
                else:
                    index = rng.randrange(stats["eligible"])
                    if index < sample_games:
                        sampled[index] = ref
            if stats["scanned"] >= max_games_scanned:
                break
    return sampled, stats


def read_game(ref: GameRef) -> chess.pgn.Game | None:
    with Path(ref.path).open("r", encoding="utf-8", errors="replace") as f:
        f.seek(ref.offset)
        return chess.pgn.read_game(f)


def cp_value(score: chess.engine.PovScore, color: chess.Color) -> int | None:
    return score.pov(color).score(mate_score=100_000)


def mate_value(score: chess.engine.PovScore, color: chess.Color) -> int | None:
    pov = score.pov(color)
    return pov.mate() if pov.is_mate() else None


def piece_count(board: chess.Board) -> int:
    return len(board.piece_map())


def gives_check(board: chess.Board, move: chess.Move) -> bool:
    child = board.copy(stack=False)
    child.push(move)
    return child.is_check()


def classify(board: chess.Board, best: chess.Move, best_mate: int | None) -> str:
    if best_mate is not None:
        return "mate"
    if piece_count(board) <= 10:
        return "endgame"
    piece = board.piece_at(best.from_square)
    reaches_back_rank = chess.square_rank(best.to_square) in {0, 7}
    if best.promotion is not None or (
        reaches_back_rank and piece is not None and piece.piece_type == chess.PAWN
    ):
        return "promotion"
    if gives_check(board, best):
        return "king_attack"
    if board.is_capture(best):
        return "material"
    return "tactical"


def epd_line(candidate: PuzzleCandidate) -> str:
    fields = " ".join(candidate.fen.split()[:4])
    ops = [
        f"bm {candidate.bm}",
        f'id "{candidate.game_id}"',
        f'c0 "played={candidate.played} ply={candidate.ply} welo={candidate.white_elo} belo={candidate.black_elo} gap={candidate.gap_cp} source={Path(candidate.source).name}"',
    ]
    return f"{fields} {'; '.join(ops)};"


def analyze_game(
    game: chess.pgn.Game,
    ref: GameRef,
    engine: chess.engine.SimpleEngine,
    args: argparse.Namespace,
) -> list[PuzzleCandidate]:
    board = game.board()
    candidates: list[PuzzleCandidate] = []
    checked = 0
    for ply, move in enumerate(game.mainline_moves(), start=1):
        if ply >= args.min_ply and not board.is_game_over(claim_draw=False):
            checked += 1
            info = engine.analyse(
                board,
                chess.engine.Limit(nodes=args.stockfish_nodes),
                multipv=2,
            )
            lines = info if isinstance(info, list) else [info]
            if len(lines) >= 2 and lines[0].get("pv") and lines[1].get("pv"):
                best_score = lines[0]["score"]
                second_score = lines[1]["score"]
                best_cp = cp_value(best_score, board.turn)
                second_cp = cp_value(second_score, board.turn)
                best_mate = mate_value(best_score, board.turn)
                gap = None if best_cp is None or second_cp is None else best_cp - second_cp
                is_clear = best_mate is not None or (gap is not None and gap >= args.min_gap_cp)
                if is_clear:
                    best = lines[0]["pv"][0]
                    candidate = PuzzleCandidate(
                        category=classify(board, best, best_mate),
                        fen=board.fen(),
                        bm=best.uci(),
                        played=move.uci(),
                        game_id=ref.game_id,
                        ply=ply,
                        white_elo=ref.white_elo,
                        black_elo=ref.black_elo,
                        gap_cp=gap,
                        best_cp=best_cp,
                        second_cp=second_cp,
                        best_mate=best_mate,
                        source=ref.path,
                    )
                    candidates.append(candidate)
                    if len(candidates) >= args.max_puzzles:
                        break
            if checked >= args.max_positions_per_game:
                break
        board.push(move)
    return candidates


def write_outputs(candidates: list[PuzzleCandidate], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    by_category: dict[str, list[PuzzleCandidate]] = {}
    for candidate in candidates:
        by_category.setdefault(candidate.category, []).append(candidate)

    for category, items in by_category.items():
        category_dir = output_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        epd_path = category_dir / f"{category}.epd"
        epd_path.write_text("\n".join(epd_line(item) for item in items) + "\n", encoding="utf-8")

    jsonl_path = output_dir / "candidates.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for candidate in candidates:
            f.write(json.dumps(asdict(candidate), sort_keys=True) + "\n")


def write_report(path: Path, candidates: list[PuzzleCandidate], stats: dict[str, int], args: argparse.Namespace) -> None:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.category] = counts.get(candidate.category, 0) + 1
    ranked = sorted(candidates, key=lambda c: (-999_999 if c.best_mate is not None else -(c.gap_cp or 0)))
    lines = [
        "# Lichess Puzzle Generator Report",
        "",
        f"- generated: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        f"- input: `{args.input_dir}`",
        f"- output: `{args.output_dir}`",
        f"- min elo: {args.min_elo}",
        f"- scanned: {stats.get('scanned', 0)}",
        f"- eligible: {stats.get('eligible', 0)}",
        f"- sampled games: {args.sample_games}",
        f"- puzzles: {len(candidates)}",
        f"- categories: `{json.dumps(counts, sort_keys=True)}`",
        "",
        "| gap | mate | category | game | ply | elos | bm | played |",
        "|---:|---:|---|---|---:|---|---|---|",
    ]
    for candidate in ranked[: min(50, len(ranked))]:
        lines.append(
            f"| {candidate.gap_cp} | {candidate.best_mate} | {candidate.category} | "
            f"{candidate.game_id} | {candidate.ply} | {candidate.white_elo}-{candidate.black_elo} | "
            f"`{candidate.bm}` | `{candidate.played}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=str(Path(__file__).with_name("generator.example.toml")))
    p.add_argument("--input-dir")
    p.add_argument("--output-dir")
    p.add_argument("--stockfish")
    p.add_argument("--min-elo", type=int)
    p.add_argument("--sample-games", type=int)
    p.add_argument("--max-games-scanned", type=int)
    p.add_argument("--max-puzzles", type=int)
    p.add_argument("--max-positions-per-game", type=int)
    p.add_argument("--min-ply", type=int)
    p.add_argument("--stockfish-nodes", type=int)
    p.add_argument("--min-gap-cp", type=int)
    p.add_argument("--seed", type=int)
    return p


def apply_config(args: argparse.Namespace) -> argparse.Namespace:
    cfg = load_toml(Path(args.config))
    for key in (
        "input_dir",
        "output_dir",
        "stockfish",
        "min_elo",
        "sample_games",
        "max_games_scanned",
        "max_puzzles",
        "max_positions_per_game",
        "min_ply",
        "stockfish_nodes",
        "min_gap_cp",
        "seed",
    ):
        if getattr(args, key) is None and key in cfg:
            setattr(args, key, cfg[key])
    args.input_dir = resolve(args.input_dir)
    args.output_dir = resolve(args.output_dir)
    args.stockfish = resolve(args.stockfish)
    args.min_elo = args.min_elo or 2030
    args.sample_games = args.sample_games or 20
    args.max_games_scanned = args.max_games_scanned or 20_000
    args.max_puzzles = args.max_puzzles or 20
    args.max_positions_per_game = args.max_positions_per_game or 8
    args.min_ply = args.min_ply or 12
    args.stockfish_nodes = args.stockfish_nodes or 30_000
    args.min_gap_cp = args.min_gap_cp or 180
    args.seed = 1 if args.seed is None else args.seed
    return args


def main() -> int:
    args = apply_config(build_parser().parse_args())
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    if not input_dir.exists():
        raise SystemExit(f"input directory not found: {input_dir}")

    rng = random.Random(args.seed)
    refs, stats = sample_game_refs(
        input_dir,
        min_elo=args.min_elo,
        sample_games=args.sample_games,
        max_games_scanned=args.max_games_scanned,
        rng=rng,
    )
    if not refs:
        raise SystemExit(f"no eligible games found under {input_dir}")

    candidates: list[PuzzleCandidate] = []
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        for ref in refs:
            game = read_game(ref)
            if game is None:
                continue
            candidates.extend(analyze_game(game, ref, engine, args))
            if len(candidates) >= args.max_puzzles:
                candidates = candidates[: args.max_puzzles]
                break

    output_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(candidates, output_dir)
    write_report(output_dir / "report.md", candidates, stats, args)
    print(
        f"scanned={stats['scanned']} eligible={stats['eligible']} "
        f"sampled={len(refs)} puzzles={len(candidates)} output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
