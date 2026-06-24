#!/usr/bin/env bash
# Stop all superhuman-band sprint jobs (self-play, gauntlet, SPSA, NNUE, benchmark)
# and any orphaned labzero / Stockfish UCI children.
#
# Safe to run anytime: every job checkpoints (see docs/operator/superhuman-band-sprint.md).
# Does NOT kill host-sprint-* wrappers (orchestrators call this, then start work).
#
#   ./scripts/host-kill-sprint.sh          # kill + verify
#   ./scripts/host-kill-sprint.sh --check  # list only, no signals
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

_SELF="$$"
_PARENT="${PPID:-0}"

# List sprint compute jobs. Avoid bare "labzero" — matches this script's path
# (.../labzero/scripts/...) and makes host-sprint-spsa exit before host-spsa runs.
list_sprint_pids() {
  local sig pid rest
  for sig in \
    'labzero selfplay' \
    'target/release/labzero' \
    'host-gauntlet.sh' \
    'host-spsa.sh' \
    'host-nnue-train' \
    'host-benchmark.sh' \
    'stockfish' \
    'reckless' \
    'PlentyChess' \
  ; do
    while IFS= read -r line; do
      [[ -z "${line}" ]] && continue
      pid="${line%% *}"
      rest="${line#* }"
      [[ "${pid}" == "${_SELF}" || "${pid}" == "${_PARENT}" ]] && continue
      # Skip orchestrator wrappers (they call us, then spawn host-spsa.sh).
      [[ "${rest}" == *host-sprint-* ]] && continue
      echo "${line}"
    done < <(pgrep -fl "${sig}" 2>/dev/null || true)
  done | sort -u
}

kill_sprint_jobs() {
  pkill -f 'labzero selfplay' 2>/dev/null || true
  pkill -f 'host-gauntlet.sh' 2>/dev/null || true
  pkill -f 'host-spsa.sh' 2>/dev/null || true
  pkill -f 'host-nnue-train' 2>/dev/null || true
  pkill -f 'host-benchmark.sh' 2>/dev/null || true

  pkill -f 'target/release/labzero' 2>/dev/null || true
  pkill -f '[/]stockfish' 2>/dev/null || true

  for f in data/selfplay/*.pid data/tune/*.pid data/nnue/*.pid; do
    [[ -f "${f}" ]] || continue
    kill "$(cat "${f}")" 2>/dev/null || true
    rm -f "${f}"
  done
}

if [[ "${1:-}" == "--check" ]]; then
  if out="$(list_sprint_pids)" && [[ -n "${out}" ]]; then
    echo "${out}"
    exit 1
  fi
  echo "nothing sprint-related running"
  exit 0
fi

echo "==> stopping sprint jobs..."
kill_sprint_jobs

echo "==> check (immediate)..."
if out="$(list_sprint_pids)" && [[ -n "${out}" ]]; then
  echo "${out}"
else
  echo "nothing sprint-related running"
fi

echo "==> wait 2s, re-check..."
sleep 2

if out="$(list_sprint_pids)" && [[ -n "${out}" ]]; then
  echo "still running — sending SIGKILL..."
  pkill -9 -f 'labzero selfplay' 2>/dev/null || true
  pkill -9 -f 'host-gauntlet.sh' 2>/dev/null || true
  pkill -9 -f 'host-spsa.sh' 2>/dev/null || true
  pkill -9 -f 'host-nnue-train' 2>/dev/null || true
  pkill -9 -f 'host-benchmark.sh' 2>/dev/null || true
  pkill -9 -f 'target/release/labzero' 2>/dev/null || true
  pkill -9 -f '[/]stockfish' 2>/dev/null || true
  sleep 1
  if out="$(list_sprint_pids)" && [[ -n "${out}" ]]; then
    echo "WARNING: could not stop everything:" >&2
    echo "${out}" >&2
    exit 1
  fi
fi

echo "clean — nothing sprint-related running"
