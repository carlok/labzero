#!/usr/bin/env bash
# Gamma v0.4.0 strength bracket — 1s movetime anchor, start high (~2k hypothesis).
#
#   export STOCKFISH=/opt/homebrew/bin/stockfish
#   ./scripts/host-ladder-gamma.sh              # full round (default)
#   ./scripts/host-ladder-gamma.sh --probe-only # 16-game sweep only
#   ./scripts/host-ladder-gamma.sh --confirm 2000 2100  # 32-game confirm at listed Elo
#
# Artifacts: docs/strength/benchmark_<UTC>.txt + .pgn (same as host-benchmark.sh)
# After run: fill docs/strength/ladder.md gamma table from the .txt summaries.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH="${ROOT}/scripts/host-benchmark.sh"
STOCKFISH="${STOCKFISH:?Set STOCKFISH to your Stockfish binary path}"

REGRESSION_ELO="${REGRESSION_ELO:-1320}"
REGRESSION_GAMES="${REGRESSION_GAMES:-16}"
PROBE_GAMES="${PROBE_GAMES:-16}"
CONFIRM_GAMES="${CONFIRM_GAMES:-32}"
# Bracket centred on ~2k perf; extend upward if 2100+ scores stay high
PROBE_ELOS="${PROBE_ELOS:-1900 2000 2100 2200 2300}"
TC_SEC="${TC_SEC:-1}"
TC_MODE="${TC_MODE:-movetime}"
THREADS="${THREADS:-1}"

run_bench() {
  local elo="$1"
  local games="$2"
  echo ""
  echo "========== SF_ELO=${elo}  GAMES=${games} =========="
  SF_ELO="${elo}" GAMES="${games}" TC_SEC="${TC_SEC}" TC_INC=0 \
    TC_MODE="${TC_MODE}" THREADS="${THREADS}" \
    STOCKFISH="${STOCKFISH}" "${BENCH}"
}

"${ROOT}/scripts/build-host-engine.sh"

case "${1:-full}" in
  --probe-only)
    for elo in ${PROBE_ELOS}; do
      run_bench "${elo}" "${PROBE_GAMES}"
    done
    ;;
  --confirm)
    shift
    if [[ $# -eq 0 ]]; then
      echo "Usage: $0 --confirm 2000 [2100 ...]" >&2
      exit 1
    fi
    for elo in "$@"; do
      run_bench "${elo}" "${CONFIRM_GAMES}"
    done
    ;;
  --regression-only)
    run_bench "${REGRESSION_ELO}" "${REGRESSION_GAMES}"
    ;;
  full|*)
    echo "Phase A: regression (SF@${REGRESSION_ELO}, ${REGRESSION_GAMES} games)"
    run_bench "${REGRESSION_ELO}" "${REGRESSION_GAMES}"

    echo ""
    echo "Phase B: bracket sweep (${PROBE_GAMES} games each) — ${PROBE_ELOS}"
    for elo in ${PROBE_ELOS}; do
      run_bench "${elo}" "${PROBE_GAMES}"
    done

    echo ""
    echo "Phase B done. Pick confirm levels where score % is between ~20 and ~80."
    echo "Then run for 32-game paper rows, e.g.:"
    echo "  $0 --confirm 2000 2100"
    echo ""
    echo "Or set CONFIRM_ELOS env and re-run with CONFIRM_AUTO=1 (not default)."
    if [[ "${CONFIRM_AUTO:-0}" == "1" ]]; then
      for elo in ${CONFIRM_ELOS:-2000 2100}; do
        run_bench "${elo}" "${CONFIRM_GAMES}"
      done
    fi
    ;;
esac

echo ""
echo "Done. Update docs/strength/ladder.md from docs/strength/benchmark_*.txt files."
