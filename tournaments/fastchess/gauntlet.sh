#!/usr/bin/env bash
# Fastchess gauntlet — self-play, vs random bot, vs Stockfish limited.
set -euo pipefail

ENGINE="${1:?engine path}"
RUNNER="${2:-fastchess}"
shift 2

GAMES="${GAUNTLET_GAMES:-100}"
SMOKE=0
OPENINGS="verifier/positions/openings.epd"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) SMOKE=1; GAMES=10; shift ;;
    --games) GAMES="$2"; shift 2 ;;
    --openings) OPENINGS="$2"; shift 2 ;;
    *) shift ;;
  esac
done
RANDOM_BOT="/workspace/verifier/python/random_uci_bot.py"
STOCKFISH="${STOCKFISH:-/usr/games/stockfish}"
LOG_DIR="docs/gauntlet"
mkdir -p "${LOG_DIR}"
STAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
LOG="${LOG_DIR}/gauntlet_${STAMP}.log"

if [[ "${SMOKE}" == "1" ]]; then
  ROUNDS=1
  REPEAT=()
  OPEN_ARGS=()
else
  ROUNDS=$((GAMES / 4))
  if [[ "${ROUNDS}" -lt 1 ]]; then
    ROUNDS=1
  fi
  REPEAT=(-repeat)
  OPEN_ARGS=()
  if [[ -f "${OPENINGS}" ]]; then
    OPEN_ARGS=(-openings "file=${OPENINGS}" format=epd order=random)
  fi
fi

run_match() {
  local name="$1"
  shift
  echo "==> ${name}" | tee -a "${LOG}"
  "$@" 2>&1 | tee -a "${LOG}"
}

echo "gauntlet config: games=${GAMES} rounds=${ROUNDS} smoke=${SMOKE}" | tee "${LOG}"

# Self-play short TC
run_match "self-play short tc" \
  "${RUNNER}" \
  -engine cmd="${ENGINE}" name=labzero proto=uci \
  -engine cmd="${ENGINE}" name=labzero2 proto=uci \
  -each tc=10+0.1 "${OPEN_ARGS[@]}" -rounds "${ROUNDS}" "${REPEAT[@]}"

# vs random bot
run_match "vs random bot" \
  "${RUNNER}" \
  -engine cmd="${ENGINE}" name=labzero proto=uci \
  -engine cmd="${RANDOM_BOT}" name=random proto=uci \
  -each depth=2 "${OPEN_ARGS[@]}" -rounds "${ROUNDS}" "${REPEAT[@]}"

# vs Stockfish limited depth
run_match "vs stockfish depth=1" \
  "${RUNNER}" \
  -engine cmd="${ENGINE}" name=labzero proto=uci \
  -engine cmd="${STOCKFISH}" name=stockfish proto=uci plies=1 \
  -each tc=10+0.1 \
  "${OPEN_ARGS[@]}" -rounds "${ROUNDS}" "${REPEAT[@]}"

# Normal TC subset
run_match "self-play normal tc" \
  "${RUNNER}" \
  -engine cmd="${ENGINE}" name=labzero proto=uci \
  -engine cmd="${ENGINE}" name=labzero2 proto=uci \
  -each tc=60+0.6 "${OPEN_ARGS[@]}" -rounds "${ROUNDS}" "${REPEAT[@]}"

echo "gauntlet: PASS (${GAMES} games target, ${ROUNDS} rounds/suite) log=${LOG}"
