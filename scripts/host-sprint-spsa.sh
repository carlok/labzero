#!/usr/bin/env bash
# Sprint loop 1 — SPSA eval tuning (resumable).
#
# Does NOT use self-play data. Plays its own fast paired games each iteration.
# Output: data/tune/<RUN_ID>.best.params
#
#   ./scripts/host-sprint-spsa.sh
#   RUN_ID=spsa_s03 ITERS=500 ./scripts/host-sprint-spsa.sh
#   nohup ./scripts/host-sprint-spsa.sh > data/tune/spsa.out 2>&1 &
#
# Resume: same RUN_ID + SEED, bump ITERS.
# After:  export LABZERO_EVAL_PARAMS=data/tune/<RUN_ID>.best.params
#         ./scripts/host-sprint-gate.sh 2600
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

RUN_ID="${RUN_ID:-spsa_s2}"
ITERS="${ITERS:-500}"
GAMES_PER_ITER="${GAMES_PER_ITER:-8}"
MOVETIME_MS="${MOVETIME_MS:-40}"
SEED="${SEED:-1}"
ENGINE="${ENGINE:-${ROOT}/target/release/labzero}"
THREADS="${THREADS:-1}"

if [[ ! -x "${ENGINE}" ]]; then
  echo "missing engine: ${ENGINE} — run ./scripts/build-host-engine.sh" >&2
  exit 1
fi

echo "==> sprint 1/3: SPSA  RUN_ID=${RUN_ID}  ITERS=${ITERS}"
"${ROOT}/scripts/host-kill-sprint.sh"

export ENGINE THREADS RUN_ID ITERS GAMES_PER_ITER MOVETIME_MS SEED
"${ROOT}/scripts/host-spsa.sh"

BEST="${ROOT}/data/tune/${RUN_ID}.best.params"
echo ""
echo "SPSA done. Best params: ${BEST}"
echo "Gate (example):"
echo "  export LABZERO_EVAL_PARAMS=${BEST}"
echo "  ./scripts/host-sprint-gate.sh 2600"
