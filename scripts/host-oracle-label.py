#!/usr/bin/env python3
"""Stockfish oracle labels for LabZero decisions.

This is tooling only: Stockfish is an external teacher for reports and datasets,
not engine code or copied weights. The output schema is
`labzero.move_quality.v1`, one JSON object per labelled LabZero move.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import chess
    import chess.engine
    import chess.pgn
except ModuleNotFoundError:
    root = Path(__file__).resolve().parents[1]
    for candidate in (root / "lichess_bot/.venv/bin/python", root / ".venv-host-test/bin/python"):
        if candidate.exists() and Path(sys.executable) != candidate:
            os.execv(str(candidate), [str(candidate), *sys.argv])
    raise

SCHEMA = "labzero.move_quality.v1"
DEFAULT_BOT_NAMES = ("labzerobot0", "labzero")


@dataclass(frozen=True)
class PositionSample:
    board: chess.Board
    move: chess.Move
    game_id: str
    ply: int
    source_path: str
    result: str


def game_id_from_headers_or_path(game: chess.pgn.Game, path: Path) -> str:
    site = game.headers.get("Site", "")
    match = re.search(r"lichess\.org/([A-Za-z0-9]{8})", site)
    if match:
        return match.group(1)
    stem = path.stem
    parts = stem.split("_")
    for part in reversed(parts):
        if re.fullmatch(r"[A-Za-z0-9]{8}", part):
            return part
    return stem


def pgn_sort_key(path: Path) -> tuple[int, float, str]:
    # Prefer full local PGNs over export duplicates, then newer files.
    is_export = 1 if "_export" in path.stem else 0
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (is_export, -mtime, str(path))


def index_pgn_paths(paths: Iterable[Path]) -> list[Path]:
    indexed: dict[str, tuple[tuple[int, float, str], Path]] = {}
    for path in paths:
        if not path.exists() or path.suffix.lower() != ".pgn":
            continue
        try:
            with path.open(encoding="utf-8") as f:
                game = chess.pgn.read_game(f)
        except UnicodeDecodeError:
            with path.open(encoding="latin-1") as f:
                game = chess.pgn.read_game(f)
        if game is None:
            continue
        gid = game_id_from_headers_or_path(game, path)
        key = pgn_sort_key(path)
        current = indexed.get(gid)
        if current is None or key < current[0]:
            indexed[gid] = (key, path)
    return [item[1] for item in sorted(indexed.values(), key=lambda item: item[0])]


def collect_pgn_paths(args: argparse.Namespace) -> list[Path]:
    paths = [Path(p) for p in args.pgn]
    for directory in args.pgn_dir:
        paths.extend(sorted(Path(directory).glob("*.pgn")))
    return index_pgn_paths(paths)


def bot_color(game: chess.pgn.Game, bot_names: tuple[str, ...]) -> chess.Color | None:
    white = game.headers.get("White", "").lower()
    black = game.headers.get("Black", "").lower()
    white_id = game.headers.get("WhiteLichessId", "").lower()
    black_id = game.headers.get("BlackLichessId", "").lower()
    names = {name.lower() for name in bot_names}
    if white in names or white_id in names:
        return chess.WHITE
    if black in names or black_id in names:
        return chess.BLACK
    return None


def extract_labzero_samples(path: Path, bot_names: tuple[str, ...]) -> list[PositionSample]:
    samples: list[PositionSample] = []
    with path.open(encoding="utf-8") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            color = bot_color(game, bot_names)
            if color is None:
                continue
            game_id = game_id_from_headers_or_path(game, path)
            board = game.board()
            for node in game.mainline():
                move = node.move
                if board.turn == color and move in board.legal_moves:
                    samples.append(
                        PositionSample(
                            board=board.copy(stack=False),
                            move=move,
                            game_id=game_id,
                            ply=board.ply(),
                            source_path=str(path),
                            result=game.headers.get("Result", "*"),
                        )
                    )
                board.push(move)
    return samples


def labzero_result_priority(path: Path, bot_names: tuple[str, ...]) -> int:
    try:
        with path.open(encoding="utf-8") as f:
            game = chess.pgn.read_game(f)
    except Exception:
        return 3
    if game is None:
        return 3
    color = bot_color(game, bot_names)
    result = game.headers.get("Result", "*")
    if color is None or result == "*":
        return 3
    if result == "1/2-1/2":
        return 1
    labzero_won = (result == "1-0" and color == chess.WHITE) or (result == "0-1" and color == chess.BLACK)
    return 2 if labzero_won else 0


def pgn_analysis_priority(path: Path, bot_names: tuple[str, ...]) -> tuple[int, float, str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (labzero_result_priority(path, bot_names), -mtime, str(path))


def sigmoid_utility(cp: int, scale: float = 400.0) -> float:
    cp_clamped = max(-1200, min(1200, cp))
    return 1.0 / (1.0 + math.exp(-cp_clamped / scale))


def utility_from_score(cp: int | None, mate_in: int | None) -> float:
    if mate_in is not None:
        if mate_in > 0:
            return 0.995 - min(abs(mate_in), 100) * 0.0005
        return 0.005 + min(abs(mate_in), 100) * 0.0005
    return sigmoid_utility(cp or 0)


def bucket_for_loss(delta_utility: float, delta_cp: int | None, mate_in: int | None) -> str:
    if mate_in is not None and mate_in < 0 and delta_utility >= 0.20:
        return "blunder"
    if delta_utility <= 0.005 or (delta_cp is not None and abs(delta_cp) <= 15):
        return "best"
    if delta_utility <= 0.025:
        return "excellent"
    if delta_utility <= 0.075:
        return "playable"
    if delta_utility <= 0.15:
        return "inaccuracy"
    if delta_utility <= 0.30:
        return "mistake"
    return "blunder"


def score_fields(score: chess.engine.PovScore, root_turn: chess.Color) -> tuple[int | None, int | None]:
    pov = score.pov(root_turn)
    mate = pov.mate()
    if mate is not None:
        return None, int(mate)
    cp = pov.score(mate_score=100000)
    return int(cp or 0), None


def analyze_child(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    move: chess.Move,
    root_turn: chess.Color,
    nodes: int,
) -> tuple[int | None, int | None]:
    child = board.copy(stack=False)
    child.push(move)
    info = engine.analyse(child, chess.engine.Limit(nodes=nodes), info=chess.engine.INFO_SCORE)
    if "score" not in info:
        return 0, None
    return score_fields(info["score"], root_turn)


def label_position(
    engine: chess.engine.SimpleEngine | None,
    sample: PositionSample,
    nodes: int,
    nodes2: int | None = None,
    fake_scores: dict[str, tuple[int | None, int | None]] | None = None,
) -> dict[str, Any]:
    board = sample.board
    scored: list[dict[str, Any]] = []
    for move in board.legal_moves:
        if fake_scores is not None:
            cp, mate_in = fake_scores.get(move.uci(), (0, None))
        else:
            assert engine is not None
            cp, mate_in = analyze_child(engine, board, move, board.turn, nodes)
        scored.append(
            {
                "uci": move.uci(),
                "cp": cp,
                "mate_in": mate_in,
                "utility": utility_from_score(cp, mate_in),
            }
        )
    scored.sort(key=lambda item: (item["utility"], item["cp"] if item["cp"] is not None else 0), reverse=True)
    best = scored[0] if scored else {"utility": 0.5, "cp": 0}
    best_cp = best["cp"]
    second_best_uci = None
    if nodes2 and engine is not None and scored:
        second_scores = []
        for move in board.legal_moves:
            cp2, mate2 = analyze_child(engine, board, move, board.turn, nodes2)
            second_scores.append((utility_from_score(cp2, mate2), move.uci()))
        second_best_uci = max(second_scores)[1]
    moves = []
    for rank, item in enumerate(scored, start=1):
        delta_u = float(best["utility"] - item["utility"])
        delta_cp = None if best_cp is None or item["cp"] is None else int(best_cp - item["cp"])
        moves.append(
            {
                "uci": item["uci"],
                "rank": rank,
                "cp": item["cp"],
                "mate_in": item["mate_in"],
                "wdl": None,
                "utility": round(float(item["utility"]), 6),
                "delta_utility": round(delta_u, 6),
                "delta_cp": delta_cp,
                "bucket": bucket_for_loss(delta_u, delta_cp, item["mate_in"]),
            }
        )
    student_move = sample.move.uci()
    status = "shallow"
    notes = ""
    if second_best_uci is not None:
        status = "stable" if second_best_uci == moves[0]["uci"] else "volatile"
        notes = "" if status == "stable" else f"best changed at second budget to {second_best_uci}"
    elif any(item["mate_in"] is not None for item in moves):
        status = "mate"
    return {
        "schema": SCHEMA,
        "fen": board.fen(),
        "source": {
            "kind": "lichess",
            "id": sample.game_id,
            "ply": sample.ply,
            "path": sample.source_path,
            "result": sample.result,
        },
        "teacher": {
            "engine": "Stockfish",
            "version": None,
            "path": None,
            "uci_options": {"Threads": 1, "Hash": 64},
            "budget": {"mode": "nodes", "nodes": nodes},
        },
        "root": {"side_to_move": "w" if board.turn == chess.WHITE else "b", "legal_count": board.legal_moves.count()},
        "student": {"kind": "labzero", "move": student_move},
        "moves": moves,
        "label_quality": {"status": status, "notes": notes},
    }


def student_move_label(record: dict[str, Any]) -> dict[str, Any] | None:
    move = record.get("student", {}).get("move")
    for item in record.get("moves", []):
        if item.get("uci") == move:
            return item
    return None


def report_lines(records: list[dict[str, Any]]) -> list[str]:
    worst = sorted(
        ((student_move_label(r), r) for r in records),
        key=lambda pair: float((pair[0] or {}).get("delta_utility", -1)),
        reverse=True,
    )
    counts: dict[str, int] = {}
    for label, _record in worst:
        if label:
            counts[str(label.get("bucket", "unknown"))] = counts.get(str(label.get("bucket", "unknown")), 0) + 1
    lines = [
        "# LabZero Oracle Report",
        "",
        f"- Generated: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        f"- Positions: {len(records)}",
        f"- Buckets: {json.dumps(counts, sort_keys=True)}",
        "",
        "## Worst LabZero Move Losses",
        "",
        "| Game | Ply | Move | Rank | Bucket | Δutility | Δcp | Best |",
        "| --- | ---: | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for label, record in worst[:20]:
        if not label:
            continue
        best = record.get("moves", [{}])[0].get("uci", "")
        lines.append(
            f"| {record['source']['id']} | {record['source']['ply']} | {record['student']['move']} | "
            f"{label['rank']} | {label['bucket']} | {label['delta_utility']:.3f} | "
            f"{'' if label['delta_cp'] is None else label['delta_cp']} | {best} |"
        )
    return lines


def write_outputs(records: list[dict[str, Any]], out_path: Path, report_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    report_path.write_text("\n".join(report_lines(records)) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pgn", action="append", default=[], help="PGN file to analyze; may be repeated")
    parser.add_argument("--pgn-dir", action="append", default=[], help="directory containing PGNs")
    parser.add_argument("--limit-games", type=int, default=0, help="limit deduped PGNs after newest-first sorting; 0 = all")
    parser.add_argument("--max-positions", type=int, default=0, help="limit labelled LabZero positions; 0 = all")
    parser.add_argument("--stockfish", default=os.environ.get("STOCKFISH", "stockfish"))
    parser.add_argument("--nodes", type=int, default=20000)
    parser.add_argument("--nodes2", type=int, default=0)
    parser.add_argument("--bot-name", action="append", default=list(DEFAULT_BOT_NAMES))
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    pgn_paths = collect_pgn_paths(args)
    # Losses/draws are most useful for plateau diagnosis; within each bucket use newest first.
    pgn_paths.sort(key=lambda path: pgn_analysis_priority(path, tuple(args.bot_name)))
    if args.limit_games:
        pgn_paths = pgn_paths[: args.limit_games]
    samples: list[PositionSample] = []
    for path in pgn_paths:
        samples.extend(extract_labzero_samples(path, tuple(args.bot_name)))
        if args.max_positions and len(samples) >= args.max_positions:
            samples = samples[: args.max_positions]
            break
    if not samples:
        print("no LabZero positions found", file=sys.stderr)
        return 1
    records: list[dict[str, Any]] = []
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        try:
            engine.configure({"Threads": 1, "Hash": 64})
        except chess.engine.EngineError:
            pass
        try:
            version = str(engine.id.get("name", "Stockfish"))
        except Exception:
            version = "Stockfish"
        for sample in samples:
            record = label_position(engine, sample, args.nodes, args.nodes2 or None)
            record["teacher"]["version"] = version
            record["teacher"]["path"] = args.stockfish
            records.append(record)
    write_outputs(records, Path(args.out), Path(args.report))
    print(f"labelled {len(records)} positions -> {args.out}")
    print(f"report -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
