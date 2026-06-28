#!/usr/bin/env python3
"""Summarize host-benchmark artifacts (.txt, .pgn, optional .moves.tsv)."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

MATE_SENTINEL = 2_147_483_647
BLUNDER_SWING_CP = 200


def resolve_prefix(prefix: str) -> tuple[Path, Path, Path | None]:
    p = Path(prefix)
    if p.suffix:
        stem = p.with_suffix("")
        base = stem.name
        parent = stem.parent
    else:
        base = p.name
        parent = p.parent if p.parent != Path(".") else Path("docs/strength")
    txt = parent / f"{base}.txt"
    pgn = parent / f"{base}.pgn"
    tsv = parent / f"{base}.moves.tsv"
    if not tsv.is_file():
        tsv = None
    return txt, pgn, tsv


def parse_game_lines(text: str) -> list[dict]:
    games: list[dict] = []
    for line in re.findall(r"^game\s+\d+:.+$", text, re.M):
        m = re.match(r"^game\s+(\d+):\s+(\S+)", line)
        if not m:
            continue
        tag = m.group(2).lower()
        bracket = re.search(r"\[(\d+)-(\d+)-(\d+)\]\s*$", line)
        cumulative = tuple(map(int, bracket.groups())) if bracket else None
        games.append({"number": int(m.group(1)), "tag": tag, "cumulative": cumulative})
    return games


def parse_txt(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    has_footer = "---" in text
    footer = text.split("---")[-1] if has_footer else ""
    out: dict = {
        "status": "unknown",
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "truncated": 0,
        "games_completed": 0,
        "games_planned": 0,
        "partial": False,
        "illegal": 0,
        "errors": 0,
        "timeouts": 0,
        "time_control": "",
        "has_footer": has_footer,
    }
    header_status = re.search(r"^status:\s+(.+)$", text, re.M)
    footer_status = re.search(r"^status:\s+(.+)$", footer, re.M) if has_footer else None
    if footer_status:
        out["status"] = footer_status.group(1).strip()
    elif header_status and header_status.group(1).strip() == "in progress":
        out["status"] = "in-progress/no-footer"
    elif header_status:
        out["status"] = header_status.group(1).strip()

    game_lines = parse_game_lines(text)
    game_wins = game_losses = game_draws = game_truncated = 0
    game_illegal = game_errors = 0
    for g in game_lines:
        tag = g["tag"]
        if tag == "win":
            game_wins += 1
        elif tag == "loss":
            game_losses += 1
        elif tag == "draw":
            game_draws += 1
        elif tag == "truncated":
            game_truncated += 1

    for line in re.findall(r"^game\s+\d+:.+$", text, re.M):
        if "FAIL illegal" in line:
            game_illegal += 1
        elif ": FAIL" in line:
            game_errors += 1

    m = re.search(r"^games:\s+(\d+)", text, re.M)
    if m:
        out["games_planned"] = int(m.group(1))

    m = re.search(r"score:\s+(\d+)-(\d+)-(\d+)", footer)
    if m:
        out["wins"], out["losses"], out["draws"] = map(int, m.groups())
    elif game_lines and game_lines[-1]["cumulative"] is not None:
        out["wins"], out["losses"], out["draws"] = game_lines[-1]["cumulative"]
    else:
        out["wins"], out["losses"], out["draws"] = game_wins, game_losses, game_draws

    out["partial"] = not has_footer or out["status"] in {"in-progress/no-footer", "interrupted"}

    m = re.search(r"truncated:\s+(\d+)", footer)
    out["truncated"] = int(m.group(1)) if m else game_truncated

    m = re.search(r"illegal:\s+(\d+)", footer)
    out["illegal"] = int(m.group(1)) if m else game_illegal

    m = re.search(r"errors:\s+(\d+)", footer)
    out["errors"] = int(m.group(1)) if m else game_errors

    out["games_completed"] = out["wins"] + out["losses"] + out["draws"]
    m = re.search(r"time control:\s+(.+)", text)
    if m:
        out["time_control"] = m.group(1).strip()
    out["timeouts"] = len(re.findall(r"\btimeout\b", text, re.I))
    return out


def parse_score_cp(raw: str) -> int | None:
    raw = raw.strip()
    if not raw or raw.startswith("#") or raw.startswith("M") or raw.startswith("-M"):
        return None
    if raw.startswith("+"):
        raw = raw[1:]
    try:
        v = int(raw)
    except ValueError:
        return None
    if abs(v) >= MATE_SENTINEL - 1000:
        return None
    return v


def analyze_pgn(path: Path) -> list[dict]:
    try:
        import chess
        import chess.pgn
        import chess.polyglot
    except ImportError:
        print(
            "python-chess is required for PGN analysis; run with "
            ".venv-host-test/bin/python or install python-chess. "
            "Continuing with TXT/TSV summary only.",
            file=sys.stderr,
        )
        return []

    def position_key(board: chess.Board) -> int:
        return chess.polyglot.zobrist_hash(board)

    games: list[dict] = []
    with path.open(encoding="utf-8") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            board = game.board()
            rep_keys: list[int] = [position_key(board)]
            threefold = 0
            plies = 0
            term = game.headers.get("Termination", "")
            result = game.headers.get("Result", "*")
            for move in game.mainline_moves():
                board.push(move)
                plies += 1
                key = position_key(board)
                if rep_keys.count(key) >= 2:
                    threefold += 1
                rep_keys.append(key)
            games.append(
                {
                    "round": game.headers.get("Round", "?"),
                    "result": result,
                    "termination": term,
                    "plies": plies,
                    "threefold_positions": threefold,
                }
            )
    return games


def analyze_tsv(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if len(lines) < 2:
        return {"mate_flags": [], "blunders": []}

    header = lines[0].split("\t")
    idx = {name: i for i, name in enumerate(header)}
    mate_flags: list[str] = []
    labzero_rows: list[tuple[int, int, str, str, str]] = []

    for line in lines[1:]:
        cols = line.split("\t")
        if len(cols) < len(header):
            continue
        score = cols[idx["score"]] if "score" in idx else ""
        if str(MATE_SENTINEL) in score or str(-MATE_SENTINEL) in score:
            mate_flags.append(
                f"game {cols[idx['game']]} ply {cols[idx['ply']]} "
                f"{cols[idx['engine']]} {cols[idx['move']]} score={score}"
            )
        if cols[idx.get("engine", -1)] == "labzero":
            ply = int(cols[idx["ply"]])
            game = int(cols[idx["game"]])
            fen = cols[idx["fen"]]
            move = cols[idx["move"]]
            cp = parse_score_cp(score)
            if cp is not None:
                labzero_rows.append((game, ply, fen, move, cp))

    blunders: list[str] = []
    by_game: dict[int, list[tuple[int, str, str, int]]] = {}
    for game, ply, fen, move, cp in labzero_rows:
        by_game.setdefault(game, []).append((ply, fen, move, cp))
    for game, rows in sorted(by_game.items()):
        rows.sort(key=lambda r: r[0])
        for j in range(1, len(rows)):
            prev_ply, _, prev_move, prev_cp = rows[j - 1]
            ply, fen, move, cp = rows[j]
            if ply != prev_ply + 2:
                continue
            swing = cp - prev_cp
            if abs(swing) >= BLUNDER_SWING_CP:
                blunders.append(
                    f"game {game} ply {ply}: {move} after {prev_move} "
                    f"swing {swing:+d}cp (fen {fen})"
                )

    return {"mate_flags": mate_flags, "blunders": blunders}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", help="Artifact prefix or path to .txt/.pgn")
    args = parser.parse_args()

    txt, pgn, tsv = resolve_prefix(args.prefix)
    if not txt.is_file():
        print(f"missing: {txt}", file=sys.stderr)
        return 1

    meta = parse_txt(txt)
    print(f"=== {txt.name} ===")
    print(f"status:       {meta['status']}")
    if meta["partial"]:
        planned = meta["games_planned"] or "?"
        print(f"partial:      true  games={meta['games_completed']}/{planned}")
    print(f"time control: {meta['time_control']}")
    print(
        f"score:        {meta['wins']}-{meta['losses']}-{meta['draws']} "
        f"(completed={meta['games_completed']} truncated={meta['truncated']})"
    )
    print(
        f"illegal:      {meta['illegal']}  errors: {meta['errors']}  "
        f"timeouts: {meta['timeouts']}"
    )

    if pgn.is_file():
        games = analyze_pgn(pgn)
        print(f"\n=== PGN ({len(games)} games) ===")
        term_counts = Counter(g.get("termination") or "normal" for g in games)
        print(f"terminations: {dict(term_counts)}")
        for g in games:
            print(
                f"  round {g['round']}: {g['result']} plies={g['plies']} "
                f"threefold_hits={g['threefold_positions']} term={g['termination'] or '-'}"
            )
    else:
        print(f"\n(no PGN: {pgn})")

    if tsv and tsv.is_file():
        tsv_data = analyze_tsv(tsv)
        print(f"\n=== TSV {tsv.name} ===")
        if tsv_data["mate_flags"]:
            print("mate-score flags:")
            for row in tsv_data["mate_flags"][:20]:
                print(f"  {row}")
            if len(tsv_data["mate_flags"]) > 20:
                print(f"  ... +{len(tsv_data['mate_flags']) - 20} more")
        else:
            print("mate-score flags: none")
        if tsv_data["blunders"]:
            print("labzero score swings (>={}cp adjacency):".format(BLUNDER_SWING_CP))
            for row in tsv_data["blunders"][:15]:
                print(f"  {row}")
        else:
            print("labzero blunder swings: none detected")
    elif tsv:
        print(f"\n(no TSV: {tsv})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
