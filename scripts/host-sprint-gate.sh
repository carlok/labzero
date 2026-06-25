#!/usr/bin/env bash
# Sprint loop 3 — gauntlet gate + ladder record (run when YOU want a measurement).
#
# Uses current build + optional LABZERO_EVAL_PARAMS / LABZERO_NNUE from env.
# Appends superhuman-band.md + elo_series.csv + timeline charts when complete.
#
#   ./scripts/host-sprint-gate.sh 2600          # 16-game probe @ SF 2600
#   ./scripts/host-sprint-gate.sh 2700 32       # 32-game anchor @ SF 2700
#   RUN_ID=my_row ./scripts/host-sprint-gate.sh 2800 16
#
# Ascending ladder (manual loop):
#   export LABZERO_EVAL_PARAMS=data/tune/spsa_s2.best.params
#   ./scripts/host-sprint-gate.sh 2600 && ./scripts/host-sprint-gate.sh 2700
#   # stop when probe < ~53%; 32g confirm at highest passed rung
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

SF_ELO="${1:?usage: host-sprint-gate.sh <SF_ELO> [GAMES]}"
GAMES="${2:-16}"
TC_SEC="${TC_SEC:-3}"
TC_INC="${TC_INC:-2}"
A_THREADS="${A_THREADS:-4}"
STOCKFISH="${STOCKFISH:?set STOCKFISH=/path/to/stockfish}"

RUN_ID="${RUN_ID:-gate_sf${SF_ELO}_${GAMES}g}"
ENGINE_A="${ENGINE_A:-${ROOT}/target/release/labzero}"

if [[ ! -x "${ENGINE_A}" ]]; then
  echo "missing engine: ${ENGINE_A} — run ./scripts/build-host-engine.sh" >&2
  exit 1
fi
if [[ ! -x "${STOCKFISH}" ]]; then
  echo "STOCKFISH not executable: ${STOCKFISH}" >&2
  exit 1
fi

echo "==> sprint 3/3: gate  SF_ELO=${SF_ELO}  GAMES=${GAMES}  RUN_ID=${RUN_ID}"
[[ -n "${LABZERO_EVAL_PARAMS:-}" ]] && echo "    params: ${LABZERO_EVAL_PARAMS}"
[[ -n "${LABZERO_NNUE:-}" ]] && echo "    nnue:   ${LABZERO_NNUE}"

"${ROOT}/scripts/host-kill-sprint.sh"

export STOCKFISH ENGINE_A
RECORD=1 RUN_ID="${RUN_ID}" GAMES="${GAMES}" SF_ELO="${SF_ELO}" \
  TC_SEC="${TC_SEC}" TC_INC="${TC_INC}" A_THREADS="${A_THREADS}" \
  "${ROOT}/scripts/host-gauntlet.sh"

LOG="${ROOT}/docs/strength/${RUN_ID}.txt"
echo ""
echo "Gate done. Log: ${LOG}"
echo "Ladder: ${ROOT}/docs/strength/superhuman-band.md"
echo "Timeline: ${ROOT}/docs/strength/elo_timeline.md"
echo ""
echo "Next rung (if score % was good — 16g probe before 32g confirm):"
echo "  ./scripts/host-sprint-gate.sh $((SF_ELO + 100)) 16"
