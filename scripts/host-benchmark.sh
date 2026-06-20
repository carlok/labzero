#!/usr/bin/env bash
# Run N bullet games: labzero vs weakened Stockfish (host binaries). Saves results.
#
#   export STOCKFISH="/path/to/stockfish"
#   ./scripts/host-benchmark.sh
#
# Options (env):
#   GAMES=32          number of games (colors alternate)
#   TC_SEC=1 TC_INC=0 bullet time control (seconds + increment)
#   SF_ELO=1320       Stockfish UCI_Elo (1320–3190, needs SF_LIMIT=1)
#   SF_SKILL=0        Stockfish Skill Level (0–20)
#   SF_LIMIT=1        UCI_LimitStrength true/false
#   OUT_DIR=docs/strength
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABZERO="${LABZERO_ENGINE:-${ROOT}/target/release/labzero}"
STOCKFISH="${STOCKFISH:?Set STOCKFISH to your Stockfish binary path}"
GAMES="${GAMES:-32}"
TC_SEC="${TC_SEC:-1}"
TC_INC="${TC_INC:-0}"
SF_ELO="${SF_ELO:-1320}"
SF_SKILL="${SF_SKILL:-0}"
SF_LIMIT="${SF_LIMIT:-1}"
OUT_DIR="${OUT_DIR:-${ROOT}/docs/strength}"

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

python3 - "${LABZERO}" "${STOCKFISH}" "${GAMES}" "${TC_SEC}" "${TC_INC}" "${SF_ELO}" "${SF_SKILL}" "${SF_LIMIT}" "${LOG}" "${PGN}" <<'PY'
import sys
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
    sf_elo,
    sf_skill,
    sf_limit,
    log_path,
    pgn_path,
) = sys.argv[1:11]
games_n = int(games_n)
tc_sec = float(tc_sec)
tc_inc = float(tc_inc)
sf_elo = int(sf_elo)
sf_skill = int(sf_skill)
sf_limit = sf_limit.lower() in ("1", "true", "yes")

limit = chess.engine.Limit(time=tc_sec)
wins = losses = draws = illegal = errors = 0
log_file = Path(log_path)
pgn_file = Path(pgn_path)


def display_path(path: str) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(Path.cwd()))
    except ValueError:
        return p.name


header = "\n".join(
    [
        f"labzero host benchmark  {datetime.now(timezone.utc).isoformat()}",
        f"status:      in progress",
        f"labzero:     {display_path(labzero_path)}",
        f"stockfish:   {display_path(sf_path)}",
        f"games:       {games_n}",
        f"time control: {int(tc_sec)}+{int(tc_inc)} bullet",
        f"sf weaken:   Skill={sf_skill} LimitStrength={sf_limit} UCI_Elo={sf_elo if sf_limit else 'n/a'}",
        "",
        "games:",
    ]
)
log_file.write_text(header + "\n", encoding="utf-8")
pgn_file.write_text("", encoding="utf-8")


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

with chess.engine.SimpleEngine.popen_uci(labzero_path) as labzero, chess.engine.SimpleEngine.popen_uci(
    sf_path
) as stockfish:
    stockfish.configure(sf_options())
    for i in range(1, games_n + 1):
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

        try:
            while not board.is_game_over(claim_draw=True):
                eng = white if board.turn == chess.WHITE else black
                result = eng.play(board, limit)
                if result.move is None:
                    raise RuntimeError("engine returned no move")
                if result.move not in board.legal_moves:
                    raise RuntimeError(f"illegal move {result.move.uci()}")
                board.push(result.move)
                node = node.add_variation(result.move)
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

footer = [
    "",
    "---",
    f"status:      complete",
    f"score:       {wins}-{losses}-{draws}  (W-L-D for labzero)",
    f"labzero %:   {100.0 * (wins + 0.5 * draws) / games_n:.1f}",
    f"illegal:     {illegal}",
    f"errors:      {errors}",
    f"pgn:         {display_path(pgn_path)}",
]
with log_file.open("a", encoding="utf-8") as f:
    f.write("\n".join(footer) + "\n")

summary = header.replace("in progress", "complete").split("\n") + footer[2:]
text = "\n".join(summary)
print()
print(text)
if illegal or errors:
    sys.exit(1)
PY

echo ""
echo "Saved: ${LOG}"
echo "PGN:   ${PGN}"
