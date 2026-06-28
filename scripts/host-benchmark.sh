#!/usr/bin/env bash
# Run N games: labzero vs weakened Stockfish (host binaries). Saves results.
#
#   export STOCKFISH="/path/to/stockfish"
#   ./scripts/host-benchmark.sh
#
# Options (env):
#   GAMES=32          number of games (colors alternate)
#   TC_SEC=1 TC_INC=0 time control (seconds + increment)
#   TC_MODE=movetime  movetime | wtime | freshclock
#                    wtime uses a real decreasing clock; freshclock preserves the
#                    old synthetic repeated-clock protocol
#   THREADS=1         labzero UCI Threads (ladder anchor uses 1)
#   SF_ELO=1320       Stockfish UCI_Elo (1320–3190, needs SF_LIMIT=1)
#   SF_SKILL=0        Stockfish Skill Level (0–20)
#   SF_LIMIT=1        UCI_LimitStrength true/false
#   OUT_DIR=docs/strength
#   DEBUG_MOVES=0     when 1, write benchmark_<stamp>.moves.tsv and live ply logs
#   MAX_PLIES=0       when >0, stop each game at that ply (result: truncated)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABZERO="${LABZERO_ENGINE:-${ROOT}/target/release/labzero}"
STOCKFISH="${STOCKFISH:?Set STOCKFISH to your Stockfish binary path}"
GAMES="${GAMES:-32}"
TC_SEC="${TC_SEC:-1}"
TC_INC="${TC_INC:-0}"
TC_MODE="${TC_MODE:-movetime}"
THREADS="${THREADS:-1}"
SF_ELO="${SF_ELO:-1320}"
SF_SKILL="${SF_SKILL:-0}"
SF_LIMIT="${SF_LIMIT:-1}"
OUT_DIR="${OUT_DIR:-${ROOT}/docs/strength}"
DEBUG_MOVES="${DEBUG_MOVES:-0}"
MAX_PLIES="${MAX_PLIES:-0}"

if [[ ! -x "${LABZERO}" ]]; then
  echo "labzero not found. Run: ./scripts/build-host-engine.sh" >&2
  exit 1
fi
if [[ ! -x "${STOCKFISH}" ]]; then
  echo "Stockfish not executable: ${STOCKFISH}" >&2
  exit 1
fi

VENV="${ROOT}/.venv-host-test"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
  "${VENV}/bin/pip" install -q python-chess
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

mkdir -p "${OUT_DIR}"
STAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
LOG="${OUT_DIR}/benchmark_${STAMP}.txt"
PGN="${OUT_DIR}/benchmark_${STAMP}.pgn"
MOVES="${OUT_DIR}/benchmark_${STAMP}.moves.tsv"

python3 - "${LABZERO}" "${STOCKFISH}" "${GAMES}" "${TC_SEC}" "${TC_INC}" "${TC_MODE}" "${THREADS}" "${SF_ELO}" "${SF_SKILL}" "${SF_LIMIT}" "${LOG}" "${PGN}" "${MOVES}" "${DEBUG_MOVES}" "${MAX_PLIES}" <<'PY'
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

(
    labzero_path,
    sf_path,
    games_n,
    tc_sec,
    tc_inc,
    tc_mode,
    threads,
    sf_elo,
    sf_skill,
    sf_limit,
    log_path,
    pgn_path,
    moves_path,
    debug_moves,
    max_plies_s,
) = sys.argv[1:17]
games_n = int(games_n)
tc_sec = float(tc_sec)
tc_inc = float(tc_inc)
tc_mode = tc_mode.lower()
threads = int(threads)
sf_elo = int(sf_elo)
sf_skill = int(sf_skill)
sf_limit = sf_limit.lower() in ("1", "true", "yes")
debug_moves = debug_moves.lower() in ("1", "true", "yes")
max_plies = int(max_plies_s)

wins = losses = draws = truncated = illegal = errors = 0
interrupted = False
games_started = 0
log_file = Path(log_path)
pgn_file = Path(pgn_path)
moves_file = Path(moves_path)


def display_path(path: str) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(Path.cwd()))
    except ValueError:
        return p.name


def time_control_label() -> str:
    if tc_mode == "wtime":
        return f"{int(tc_sec)}+{int(tc_inc)} (wtime real-clock)"
    if tc_mode == "freshclock":
        return f"{int(tc_sec)}+{int(tc_inc)} (freshclock synthetic)"
    if tc_mode == "movetime":
        return f"{int(tc_sec)}+{int(tc_inc)} (movetime)"
    return f"{int(tc_sec)}+{int(tc_inc)} ({tc_mode})"


def play_limit(white_clock: float, black_clock: float):
    if tc_mode == "wtime":
        return chess.engine.Limit(
            white_clock=max(0.0, white_clock),
            black_clock=max(0.0, black_clock),
            white_inc=tc_inc,
            black_inc=tc_inc,
        )
    if tc_mode == "freshclock":
        return chess.engine.Limit(
            white_clock=tc_sec,
            black_clock=tc_sec,
            white_inc=tc_inc,
            black_inc=tc_inc,
        )
    return chess.engine.Limit(time=tc_sec)


def info_value(info: dict, key: str) -> str:
    value = info.get(key)
    return "" if value is None else str(value)


def score_value(info: dict, turn: chess.Color) -> str:
    score = info.get("score")
    if score is None:
        return ""
    try:
        return str(score.pov(turn))
    except AttributeError:
        return str(score)


def write_move_log(
    *,
    utc: str,
    elapsed_ms: int,
    game_no: int,
    ply: int,
    side: str,
    engine_name: str,
    fen: str,
    white_clock_sent: float,
    black_clock_sent: float,
    move: chess.Move,
    move_ms: int,
    white_clock_after: float,
    black_clock_after: float,
    info: dict,
    turn: chess.Color,
) -> None:
    row = [
        utc,
        str(elapsed_ms),
        str(game_no),
        str(ply),
        side,
        engine_name,
        fen,
        f"{white_clock_sent:.3f}",
        f"{black_clock_sent:.3f}",
        f"{tc_inc:.3f}",
        f"{tc_inc:.3f}",
        move.uci(),
        str(move_ms),
        f"{white_clock_after:.3f}",
        f"{black_clock_after:.3f}",
        score_value(info, turn),
        info_value(info, "depth"),
        info_value(info, "nodes"),
    ]
    with moves_file.open("a", encoding="utf-8") as f:
        f.write("\t".join(row) + "\n")


header = "\n".join(
    [
        f"labzero host benchmark  {datetime.now(timezone.utc).isoformat()}",
        f"status:      in progress",
        f"labzero:     {display_path(labzero_path)}",
        f"stockfish:   {display_path(sf_path)}",
        f"games:       {games_n}",
        f"time control: {time_control_label()}",
        f"labzero Threads: {threads}",
        f"sf weaken:   Skill={sf_skill} LimitStrength={sf_limit} UCI_Elo={sf_elo if sf_limit else 'n/a'}",
        f"debug moves: {debug_moves}",
        f"max plies:   {max_plies if max_plies > 0 else 'none'}",
        "",
        "games:",
    ]
)
log_file.write_text(header + "\n", encoding="utf-8")
pgn_file.write_text("", encoding="utf-8")
if debug_moves:
    moves_file.write_text(
        "\t".join(
            [
                "utc",
                "elapsed_ms",
                "game",
                "ply",
                "side",
                "engine",
                "fen",
                "white_clock_sent",
                "black_clock_sent",
                "white_inc",
                "black_inc",
                "move",
                "move_ms",
                "white_clock_after",
                "black_clock_after",
                "score",
                "depth",
                "nodes",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_footer(status: str) -> None:
    finished = wins + losses + draws
    pct = 100.0 * (wins + 0.5 * draws) / finished if finished else 0.0
    footer = [
        "",
        "---",
        f"status:      {status}",
        f"score:       {wins}-{losses}-{draws}  (W-L-D for labzero)",
        f"truncated:   {truncated}",
        f"labzero %:   {pct:.1f}",
        f"illegal:     {illegal}",
        f"errors:      {errors}",
        f"pgn:         {display_path(pgn_path)}",
    ]
    if debug_moves:
        footer.append(f"moves:       {display_path(moves_path)}")
    with log_file.open("a", encoding="utf-8") as f:
        f.write("\n".join(footer) + "\n")
    summary = header.replace("in progress", status).split("\n") + footer[2:]
    print()
    print("\n".join(summary))


def append_game_log(line: str) -> None:
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def append_pgn(game: chess.pgn.Game) -> None:
    with pgn_file.open("a", encoding="utf-8") as f:
        print(game, file=f, end="\n\n")


def sf_options():
    opts = {"Skill Level": sf_skill}
    if sf_limit:
        opts["UCI_LimitStrength"] = True
        opts["UCI_Elo"] = sf_elo
    return opts


footer_written = False


def finish(status: str) -> None:
    global footer_written
    if footer_written:
        return
    footer_written = True
    write_footer(status)


def on_sigint(_signum, _frame):
    global interrupted
    interrupted = True
    finish("interrupted")
    os._exit(130)


signal.signal(signal.SIGINT, on_sigint)


try:
    with chess.engine.SimpleEngine.popen_uci(labzero_path) as labzero, chess.engine.SimpleEngine.popen_uci(
        sf_path
    ) as stockfish:
        labzero.configure({"Threads": threads, "Hash": 64})
        stockfish.configure(sf_options())
        bench_start = time.perf_counter()
        for i in range(1, games_n + 1):
            if interrupted:
                break
            games_started = i
            board = chess.Board()
            labzero_white = i % 2 == 1
            white = labzero if labzero_white else stockfish
            black = stockfish if labzero_white else labzero
            game = chess.pgn.Game()
            game.headers["Event"] = "labzero host benchmark"
            game.headers["Date"] = datetime.now(timezone.utc).strftime("%Y.%m.%d")
            game.headers["Round"] = str(i)
            game.headers["White"] = "labzero" if labzero_white else "Stockfish"
            game.headers["Black"] = "Stockfish" if labzero_white else "labzero"
            game.headers["TimeControl"] = f"{int(tc_sec)}+{int(tc_inc)}"
            node = game
            white_clock = tc_sec
            black_clock = tc_sec

            try:
                while not board.is_game_over(claim_draw=True):
                    if interrupted:
                        game.headers["Result"] = "*"
                        game.headers["Termination"] = "interrupted"
                        append_pgn(game)
                        break
                    if max_plies > 0 and board.ply() >= max_plies:
                        game.headers["Result"] = "*"
                        game.headers["Termination"] = "truncated"
                        append_pgn(game)
                        truncated += 1
                        line = (
                            f"game {i:2d}: truncated ply {board.ply()}  "
                            f"({board.status()})  [{wins}-{losses}-{draws}]"
                        )
                        append_game_log(line)
                        print(line, flush=True)
                        break
                    eng = white if board.turn == chess.WHITE else black
                    engine_name = (
                        "labzero"
                        if (board.turn == chess.WHITE) == labzero_white
                        else "stockfish"
                    )
                    fen_before = board.fen()
                    turn_before = board.turn
                    side = "W" if turn_before == chess.WHITE else "B"
                    white_sent = white_clock
                    black_sent = black_clock
                    limit = play_limit(white_clock, black_clock)
                    start = time.perf_counter()
                    result = eng.play(
                        board,
                        limit,
                        info=chess.engine.INFO_ALL if debug_moves else chess.engine.INFO_NONE,
                    )
                    move_ms = int((time.perf_counter() - start) * 1000)
                    if result.move is None:
                        raise RuntimeError("engine returned no move")
                    if result.move not in board.legal_moves:
                        raise RuntimeError(f"illegal move {result.move.uci()}")
                    if tc_mode == "wtime":
                        elapsed = move_ms / 1000.0
                        if turn_before == chess.WHITE:
                            white_clock = max(0.0, white_clock - elapsed) + tc_inc
                        else:
                            black_clock = max(0.0, black_clock - elapsed) + tc_inc
                    elif tc_mode == "freshclock":
                        white_clock = tc_sec
                        black_clock = tc_sec
                    if debug_moves:
                        ply = board.ply() + 1
                        utc = datetime.now(timezone.utc).isoformat()
                        elapsed_ms = int((time.perf_counter() - bench_start) * 1000)
                        info = result.info if result.info is not None else {}
                        write_move_log(
                            utc=utc,
                            elapsed_ms=elapsed_ms,
                            game_no=i,
                            ply=ply,
                            side=side,
                            engine_name=engine_name,
                            fen=fen_before,
                            white_clock_sent=white_sent,
                            black_clock_sent=black_sent,
                            move=result.move,
                            move_ms=move_ms,
                            white_clock_after=white_clock,
                            black_clock_after=black_clock,
                            info=info,
                            turn=turn_before,
                        )
                        score = score_value(info, turn_before)
                        depth = info_value(info, "depth")
                        nodes = info_value(info, "nodes")
                        print(
                            f"ply {ply:3d} {engine_name:8s} {side} {result.move.uci()} "
                            f"{move_ms:4d}ms wc={white_clock:.3f} bc={black_clock:.3f} "
                            f"score={score} depth={depth} nodes={nodes}",
                            flush=True,
                        )
                    board.push(result.move)
                    node = node.add_variation(result.move)
                if interrupted and game.headers.get("Termination") == "interrupted":
                    break
                if game.headers.get("Termination") == "truncated":
                    continue
                if board.is_game_over(claim_draw=True):
                    outcome = board.outcome(claim_draw=True)
                    assert outcome is not None
                    result_str = outcome.result()
                    game.headers["Result"] = result_str
                    append_pgn(game)

                    if result_str == "1/2-1/2":
                        draws += 1
                        tag = "draw"
                    elif (result_str == "1-0") == labzero_white:
                        wins += 1
                        tag = "win"
                    else:
                        losses += 1
                        tag = "loss"
                    line = f"game {i:2d}: {tag:4s} {result_str}  ({board.status()})  [{wins}-{losses}-{draws}]"
                    append_game_log(line)
                    print(line, flush=True)
            except RuntimeError as exc:
                if "illegal" in str(exc).lower():
                    illegal += 1
                    line = f"game {i:2d}: FAIL illegal — {exc}  [{wins}-{losses}-{draws}]"
                else:
                    errors += 1
                    line = f"game {i:2d}: FAIL {exc}  [{wins}-{losses}-{draws}]"
                append_game_log(line)
                print(line, flush=True)
                game.headers["Result"] = "*"
                append_pgn(game)

except KeyboardInterrupt:
    interrupted = True
    finish("interrupted")
    sys.exit(130)
else:
    finish("interrupted" if interrupted else "complete")

if illegal or errors:
    sys.exit(1)
PY

echo ""
echo "Saved: ${LOG}"
echo "PGN:   ${PGN}"
if [[ "${DEBUG_MOVES}" =~ ^(1|true|yes)$ ]]; then
  echo "Moves: ${MOVES}"
fi
