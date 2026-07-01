#!/usr/bin/env python3
"""Mine LabZero's largest puzzle-position disagreements with Stockfish."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class PuzzleCase:
    category: str
    source: str
    line_no: int
    fen: str


@dataclass
class PuzzleResult:
    category: str
    source: str
    line_no: int
    fen: str
    side: str
    labzero_move: str
    stockfish_move: str
    labzero_cp: int | None
    stockfish_cp: int | None
    loss_cp: int | None
    bucket: str


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


def parse_position_line(line: str) -> str | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if ";" in text:
        board = chess.Board()
        try:
            board.set_epd(text)
            return board.fen()
        except ValueError:
            pass
    parts = text.split()
    if len(parts) >= 6:
        return " ".join(parts[:6])
    return None


def load_cases(puzzles_dir: Path, max_positions: int | None) -> list[PuzzleCase]:
    cases: list[PuzzleCase] = []
    files = sorted(
        path
        for path in puzzles_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".epd", ".fen", ".txt"}
    )
    for path in files:
        rel = path.relative_to(puzzles_dir)
        category = rel.parts[0] if len(rel.parts) > 1 else "uncategorized"
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            fen = parse_position_line(raw)
            if fen is None:
                continue
            cases.append(PuzzleCase(category, str(path), line_no, fen))
            if max_positions is not None and len(cases) >= max_positions:
                return cases
    return cases


def pov_cp(info: dict[str, Any], color: chess.Color) -> int | None:
    score = info.get("score")
    if score is None:
        return None
    return score.pov(color).score(mate_score=100_000)


def score_after_move(engine: chess.engine.SimpleEngine, board: chess.Board, move: chess.Move, nodes: int) -> int | None:
    child = board.copy(stack=False)
    mover = board.turn
    child.push(move)
    info = engine.analyse(child, chess.engine.Limit(nodes=nodes))
    score = pov_cp(info, not mover)
    return None if score is None else -score


def bucket(loss_cp: int | None) -> str:
    if loss_cp is None:
        return "unknown"
    if loss_cp >= 700:
        return "blunder"
    if loss_cp >= 300:
        return "mistake"
    if loss_cp >= 120:
        return "inaccuracy"
    if loss_cp >= 40:
        return "small"
    return "ok"


def labzero_limit(args: argparse.Namespace) -> chess.engine.Limit:
    if args.labzero_movetime_ms is not None:
        return chess.engine.Limit(time=args.labzero_movetime_ms / 1000.0)
    return chess.engine.Limit(depth=args.labzero_depth)


def analyze_case(
    case: PuzzleCase,
    labzero: chess.engine.SimpleEngine,
    stockfish: chess.engine.SimpleEngine,
    args: argparse.Namespace,
) -> PuzzleResult | None:
    board = chess.Board(case.fen)
    if board.is_game_over(claim_draw=False):
        return None

    lab = labzero.play(board, labzero_limit(args))
    if lab.move is None or lab.move not in board.legal_moves:
        return None

    sf_info = stockfish.analyse(
        board,
        chess.engine.Limit(nodes=args.stockfish_nodes),
        multipv=1,
    )
    sf_line = sf_info[0] if isinstance(sf_info, list) else sf_info
    sf_pv = sf_line.get("pv") or []
    if not sf_pv:
        return None
    sf_move = sf_pv[0]
    sf_cp = pov_cp(sf_line, board.turn)
    lab_cp = score_after_move(stockfish, board, lab.move, args.stockfish_nodes)
    loss = None if sf_cp is None or lab_cp is None else max(0, sf_cp - lab_cp)

    return PuzzleResult(
        category=case.category,
        source=case.source,
        line_no=case.line_no,
        fen=case.fen,
        side="white" if board.turn == chess.WHITE else "black",
        labzero_move=lab.move.uci(),
        stockfish_move=sf_move.uci(),
        labzero_cp=lab_cp,
        stockfish_cp=sf_cp,
        loss_cp=loss,
        bucket=bucket(loss),
    )


def write_jsonl(path: Path, results: list[PuzzleResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(asdict(result), sort_keys=True) + "\n")


def write_report(path: Path, results: list[PuzzleResult], args: argparse.Namespace) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ranked = sorted(
        results,
        key=lambda r: (-1 if r.loss_cp is None else r.loss_cp),
        reverse=True,
    )
    counts: dict[str, int] = {}
    for result in results:
        counts[result.bucket] = counts.get(result.bucket, 0) + 1

    lines = [
        "# LabZero Puzzle Oracle Report",
        "",
        f"- generated: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        f"- positions: {len(results)}",
        f"- labzero: `{args.labzero}`",
        f"- stockfish: `{args.stockfish}`",
        f"- labzero limit: depth {args.labzero_depth}" if args.labzero_movetime_ms is None else f"- labzero limit: {args.labzero_movetime_ms} ms",
        f"- stockfish nodes: {args.stockfish_nodes}",
        f"- buckets: `{json.dumps(counts, sort_keys=True)}`",
        "",
        "## Worst Cases",
        "",
        "| loss | bucket | category | side | LabZero | Stockfish | source |",
        "|---:|---|---|---|---|---|---|",
    ]
    for result in ranked[: args.worst_limit]:
        loss = "?" if result.loss_cp is None else str(result.loss_cp)
        source = f"{Path(result.source).name}:{result.line_no}"
        lines.append(
            f"| {loss} | {result.bucket} | {result.category} | {result.side} | "
            f"`{result.labzero_move}` | `{result.stockfish_move}` | `{source}` |"
        )
    lines.extend(["", "## Worst FENs", ""])
    for idx, result in enumerate(ranked[: min(args.worst_limit, 20)], start=1):
        lines.extend(
            [
                f"### {idx}. {result.category} loss={result.loss_cp} bucket={result.bucket}",
                "",
                f"- LabZero: `{result.labzero_move}`",
                f"- Stockfish: `{result.stockfish_move}`",
                f"- source: `{result.source}:{result.line_no}`",
                "",
                "```text",
                result.fen,
                "```",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=str(Path(__file__).with_name("config.example.toml")))
    p.add_argument("--puzzles-dir")
    p.add_argument("--labzero")
    p.add_argument("--stockfish")
    p.add_argument("--out")
    p.add_argument("--report")
    p.add_argument("--labzero-depth", type=int)
    p.add_argument("--labzero-movetime-ms", type=int)
    p.add_argument("--stockfish-nodes", type=int)
    p.add_argument("--max-positions", type=int)
    p.add_argument("--worst-limit", type=int)
    return p


def main() -> int:
    args = parser().parse_args()
    cfg = load_toml(Path(args.config))
    for key in (
        "puzzles_dir",
        "labzero",
        "stockfish",
        "out",
        "report",
        "labzero_depth",
        "labzero_movetime_ms",
        "stockfish_nodes",
        "max_positions",
        "worst_limit",
    ):
        if getattr(args, key, None) is None and key in cfg:
            setattr(args, key, cfg[key])

    args.puzzles_dir = resolve(args.puzzles_dir)
    args.labzero = resolve(args.labzero)
    args.stockfish = resolve(args.stockfish)
    args.out = resolve(args.out)
    args.report = resolve(args.report)
    args.labzero_depth = args.labzero_depth or 8
    args.stockfish_nodes = args.stockfish_nodes or 30_000
    args.max_positions = args.max_positions or 200
    args.worst_limit = args.worst_limit or 50

    if not args.puzzles_dir or not Path(args.puzzles_dir).exists():
        raise SystemExit(f"puzzles directory not found: {args.puzzles_dir}")

    cases = load_cases(Path(args.puzzles_dir), args.max_positions)
    if not cases:
        raise SystemExit(f"no puzzle positions found under {args.puzzles_dir}")

    results: list[PuzzleResult] = []
    with chess.engine.SimpleEngine.popen_uci(args.labzero) as labzero:
        with chess.engine.SimpleEngine.popen_uci(args.stockfish) as stockfish:
            for case in cases:
                result = analyze_case(case, labzero, stockfish, args)
                if result is not None:
                    results.append(result)

    write_jsonl(Path(args.out), results)
    write_report(Path(args.report), results, args)
    print(f"positions={len(results)} out={args.out} report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
