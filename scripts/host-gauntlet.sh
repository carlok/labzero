#!/usr/bin/env bash
# Generalized, resumable engine-vs-engine gauntlet for the superhuman-band ladder.
#
# Plays ENGINE_A (default: labzero) against ENGINE_B (an opponent) at a fixed
# time control, diversifies games with a built-in set of short opening lines,
# appends every finished game to disk (so a shutdown resumes mid-run), and
# reports W-L-D, score%, and the repo perf estimate.
#
#   export STOCKFISH=/opt/homebrew/bin/stockfish
#   GAMES=32 SF_ELO=2800 ./scripts/host-gauntlet.sh
#   GAMES=32 ENGINE_B=engines/reckless-macos B_NAME=reckless B_NODES=200000 \
#       ANCHOR=3000 ./scripts/host-gauntlet.sh
#
# Opponent strength control (pick one):
#   SF_ELO=<elo>     configure ENGINE_B with UCI_LimitStrength + UCI_Elo (Stockfish)
#   B_NODES=<n>      cap ENGINE_B to n nodes/move (handicap for engines w/o UCI_Elo)
#   B_MOVETIME=<ms>  cap ENGINE_B to fixed movetime/move
#   (none)           ENGINE_B uses the same clock as ENGINE_A (full strength)
#
# Other env:
#   ENGINE_A=target/release/labzero   A_THREADS=4   A_HASH=64
#   ENGINE_B=$STOCKFISH               B_THREADS=1   B_HASH=64   B_NAME=<label>
#   GAMES=32  TC_SEC=3  TC_INC=2
#   ANCHOR=<elo>   Elo anchor for the perf estimate (defaults to SF_ELO if set)
#   OUT_DIR=docs/strength   RUN_ID=<id>   (RUN_ID makes a run resumable by name)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE_A="${ENGINE_A:-${ROOT}/target/release/labzero}"
ENGINE_B="${ENGINE_B:-${STOCKFISH:?Set ENGINE_B or STOCKFISH}}"
A_THREADS="${A_THREADS:-4}"
A_HASH="${A_HASH:-64}"
B_THREADS="${B_THREADS:-1}"
B_HASH="${B_HASH:-64}"
B_NAME="${B_NAME:-$(basename "${ENGINE_B}")}"
GAMES="${GAMES:-32}"
TC_SEC="${TC_SEC:-3}"
TC_INC="${TC_INC:-2}"
SF_ELO="${SF_ELO:-}"
B_NODES="${B_NODES:-}"
B_MOVETIME="${B_MOVETIME:-}"
ANCHOR="${ANCHOR:-${SF_ELO:-}}"
OUT_DIR="${OUT_DIR:-${ROOT}/docs/strength}"

for e in "${ENGINE_A}" "${ENGINE_B}"; do
  if [[ ! -x "${e}" ]]; then
    echo "engine not executable: ${e}" >&2
    exit 1
  fi
done

# Stable run id so repeated invocations with the same parameters resume the
# same artifact instead of starting a fresh file.
if [[ -z "${RUN_ID:-}" ]]; then
  strength="full"
  [[ -n "${SF_ELO}" ]] && strength="elo${SF_ELO}"
  [[ -n "${B_NODES}" ]] && strength="n${B_NODES}"
  [[ -n "${B_MOVETIME}" ]] && strength="mt${B_MOVETIME}"
  RUN_ID="gauntlet_${B_NAME}_${strength}_${TC_SEC}+${TC_INC}_${GAMES}g"
fi

VENV="${ROOT}/.venv-host-test"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
  "${VENV}/bin/pip" install -q python-chess
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/${RUN_ID}.txt"
PGN="${OUT_DIR}/${RUN_ID}.pgn"
STATE="${OUT_DIR}/${RUN_ID}.state.json"

export ENGINE_A ENGINE_B A_THREADS A_HASH B_THREADS B_HASH B_NAME GAMES \
  TC_SEC TC_INC SF_ELO B_NODES B_MOVETIME ANCHOR LOG PGN STATE

python3 - "$@" <<'PY'
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

engine_a = os.environ["ENGINE_A"]
engine_b = os.environ["ENGINE_B"]
a_threads = int(os.environ["A_THREADS"])
a_hash = int(os.environ["A_HASH"])
b_threads = int(os.environ["B_THREADS"])
b_hash = int(os.environ["B_HASH"])
b_name = os.environ["B_NAME"]
games_n = int(os.environ["GAMES"])
tc_sec = float(os.environ["TC_SEC"])
tc_inc = float(os.environ["TC_INC"])
sf_elo = os.environ.get("SF_ELO") or ""
b_nodes = os.environ.get("B_NODES") or ""
b_movetime = os.environ.get("B_MOVETIME") or ""
anchor = os.environ.get("ANCHOR") or ""
log_path = Path(os.environ["LOG"])
pgn_path = Path(os.environ["PGN"])
state_path = Path(os.environ["STATE"])

A_LABEL = "labzero" if engine_a.endswith("labzero") else Path(engine_a).name

# Short, public opening lines (SAN) to diversify games between deterministic
# engines. Each line is played from both colors across the pairing.
OPENINGS = [
    [], ["e4", "e5"], ["e4", "c5"], ["e4", "e6"], ["e4", "c6"],
    ["d4", "d5"], ["d4", "Nf6"], ["d4", "f5"], ["c4", "e5"], ["Nf3", "d5"],
    ["e4", "e5", "Nf3", "Nc6", "Bb5"], ["e4", "e5", "Nf3", "Nc6", "Bc4"],
    ["d4", "Nf6", "c4", "g6"], ["d4", "d5", "c4", "e6"],
    ["e4", "c5", "Nf3", "d6"], ["e4", "e5", "Nf3", "Nc6", "d4"],
]


def opening_board(idx: int) -> chess.Board:
    board = chess.Board()
    for san in OPENINGS[idx % len(OPENINGS)]:
        board.push_san(san)
    return board


def b_options():
    opts = {"Threads": b_threads, "Hash": b_hash}
    if sf_elo:
        opts["UCI_LimitStrength"] = True
        opts["UCI_Elo"] = int(sf_elo)
    return opts


def b_limit(board: chess.Board):
    if b_nodes:
        return chess.engine.Limit(nodes=int(b_nodes))
    if b_movetime:
        return chess.engine.Limit(time=float(b_movetime) / 1000.0)
    return clock_limit()


def clock_limit():
    return chess.engine.Limit(
        white_clock=tc_sec, black_clock=tc_sec, white_inc=tc_inc, black_inc=tc_inc
    )


def load_state():
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except json.JSONDecodeError:
            pass
    return {"completed": 0, "w": 0, "l": 0, "d": 0, "illegal": 0, "errors": 0}


def save_state(st):
    state_path.write_text(json.dumps(st), encoding="utf-8")


def write_header():
    header = "\n".join([
        f"labzero gauntlet  {datetime.now(timezone.utc).isoformat()}",
        "status:      in progress",
        f"engine A:    {A_LABEL} ({Path(engine_a).name}) Threads={a_threads}",
        f"engine B:    {b_name} ({Path(engine_b).name}) Threads={b_threads}",
        f"games:       {games_n}",
        f"time control: {int(tc_sec)}+{int(tc_inc)} (wtime)",
        f"B strength:  " + (f"SF UCI_Elo={sf_elo}" if sf_elo else
                            f"nodes={b_nodes}" if b_nodes else
                            f"movetime={b_movetime}ms" if b_movetime else "full"),
        f"anchor Elo:  {anchor or 'n/a'}",
        "",
        "games:",
    ])
    log_path.write_text(header + "\n", encoding="utf-8")


st = load_state()
resume_from = st["completed"]
if resume_from == 0:
    write_header()
    pgn_path.write_text("", encoding="utf-8")
    print(f"starting {games_n}-game gauntlet vs {b_name}")
else:
    print(f"resuming gauntlet vs {b_name} from game {resume_from + 1}/{games_n}")

wins, losses, draws = st["w"], st["l"], st["d"]
illegal, errors = st["illegal"], st["errors"]


def append(path: Path, text: str):
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


with chess.engine.SimpleEngine.popen_uci(engine_a) as ea, \
        chess.engine.SimpleEngine.popen_uci(engine_b) as eb:
    ea.configure({"Threads": a_threads, "Hash": a_hash})
    eb.configure(b_options())

    for i in range(resume_from + 1, games_n + 1):
        board = opening_board((i - 1) // 2)
        a_white = i % 2 == 1
        game = chess.pgn.Game.from_board(board)
        game.headers["Event"] = "labzero gauntlet"
        game.headers["Date"] = datetime.now(timezone.utc).strftime("%Y.%m.%d")
        game.headers["Round"] = str(i)
        game.headers["White"] = A_LABEL if a_white else b_name
        game.headers["Black"] = b_name if a_white else A_LABEL
        game.headers["TimeControl"] = f"{int(tc_sec)}+{int(tc_inc)}"
        node = game.end()

        try:
            while not board.is_game_over(claim_draw=True):
                a_to_move = (board.turn == chess.WHITE) == a_white
                if a_to_move:
                    res = ea.play(board, clock_limit())
                else:
                    res = eb.play(board, b_limit(board))
                if res.move is None or res.move not in board.legal_moves:
                    raise RuntimeError(f"illegal/none move {res.move}")
                board.push(res.move)
                node = node.add_variation(res.move)

            outcome = board.outcome(claim_draw=True)
            result_str = outcome.result()
            game.headers["Result"] = result_str
            if result_str == "1/2-1/2":
                draws += 1
                tag = "draw"
            elif (result_str == "1-0") == a_white:
                wins += 1
                tag = "win "
            else:
                losses += 1
                tag = "loss"
            line = f"game {i:3d}: {tag} {result_str}  [{wins}-{losses}-{draws}]"
        except RuntimeError as exc:
            game.headers["Result"] = "*"
            if "illegal" in str(exc).lower():
                illegal += 1
                line = f"game {i:3d}: FAIL illegal {exc}  [{wins}-{losses}-{draws}]"
            else:
                errors += 1
                line = f"game {i:3d}: FAIL {exc}  [{wins}-{losses}-{draws}]"

        append(log_path, line + "\n")
        append(pgn_path, str(game) + "\n\n")
        st.update(completed=i, w=wins, l=losses, d=draws, illegal=illegal, errors=errors)
        save_state(st)
        print(line, flush=True)

played = wins + losses + draws
score = (wins + 0.5 * draws) / played if played else 0.0
perf = "n/a"
if anchor and 0.0 < score < 1.0:
    perf = f"{float(anchor) + 400.0 * math.log10(score / (1.0 - score)):.0f}"

footer = "\n".join([
    "",
    "---",
    "status:      complete",
    f"score:       {wins}-{losses}-{draws}  (W-L-D for {A_LABEL})",
    f"{A_LABEL} %:   {100.0 * score:.1f}",
    f"perf est:    {perf}  (anchor {anchor or 'n/a'}; perf = anchor + 400*log10(p/(1-p)))",
    f"illegal:     {illegal}",
    f"errors:      {errors}",
    f"pgn:         {pgn_path.name}",
])
append(log_path, footer + "\n")
# Flip the header status now that the run is complete.
log_path.write_text(log_path.read_text().replace("status:      in progress", "status:      complete", 1))
print(footer)
if illegal or errors:
    sys.exit(1)
PY

echo ""
echo "Saved: ${LOG}"
echo "PGN:   ${PGN}"
echo "State: ${STATE}"
