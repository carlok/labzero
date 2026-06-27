#!/usr/bin/env bash
# Verify a policy LZP1 file: engine integer inference must match the Python
# reference forward pass bit-for-bit on fixed legal probes.
#
#   ./scripts/host-policy-verify.sh data/policy/policy.lzp
#
# Env: ENGINE=target/release/labzero
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NET="${1:?usage: host-policy-verify.sh <policy.lzp>}"
ENGINE="${ENGINE:-${ROOT}/target/release/labzero}"
PY="${ROOT}/.venv-host-test/bin/python"

if [[ ! -x "${ENGINE}" ]]; then
  echo "engine not executable: ${ENGINE}" >&2
  exit 1
fi
if [[ ! -x "${PY}" ]]; then
  PY="python3"
fi

# fen uci pairs: legal quiet moves on varied positions.
PROBES=(
  "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1|e2e4"
  "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3|f1b5"
  "rnbqkb1r/1pp1pp1p/p6n/3p2p1/6P1/P2P1N2/1PP1PP1P/RNBQKB1R w KQkq g6 0 5|d3d4"
  "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R b KQkq - 0 1|e8g8"
  "2r3k1/5ppp/8/8/8/8/5PPP/2R3K1 b - - 0 1|g8f8"
)

fail=0
for probe in "${PROBES[@]}"; do
  fen="${probe%%|*}"
  uci="${probe##*|}"
  r="$(LABZERO_POLICY="${NET}" "${ENGINE}" policyeval "${fen}" "${uci}" 2>/dev/null)"
  p="$("${PY}" "${ROOT}/scripts/policy_format.py" forward "${NET}" "${fen}" "${uci}")"
  if [[ "${r}" == "${p}" ]]; then
    echo "OK   engine=${r}  ref=${p}  uci=${uci}"
  else
    echo "MISMATCH engine=${r} ref=${p}  fen=${fen} uci=${uci}" >&2
    fail=1
  fi
done

if [[ "${fail}" -eq 0 ]]; then
  echo "PARITY OK: engine integer inference matches the Python reference."
else
  echo "PARITY FAILED" >&2
fi
exit "${fail}"
