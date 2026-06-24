#!/usr/bin/env bash
# Verify an NNUE file: the engine's integer inference (engine/src/nnue.rs) must
# match the Python reference forward pass (scripts/nnue_format.py) bit-for-bit
# on a set of probe positions. This is the correctness gate for the format and
# feature extraction; run it on any net before trusting a training run.
#
#   ./scripts/host-nnue-verify.sh data/nnue/net.nnue
#
# Env: ENGINE=target/release/labzero
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NET="${1:?usage: host-nnue-verify.sh <net.nnue>}"
ENGINE="${ENGINE:-${ROOT}/target/release/labzero}"
PY="${ROOT}/.venv-host-test/bin/python"

if [[ ! -x "${ENGINE}" ]]; then
  echo "engine not executable: ${ENGINE}" >&2
  exit 1
fi
if [[ ! -x "${PY}" ]]; then
  PY="python3"
fi

# Probe positions: symmetric start, asymmetric middlegames, an endgame, and
# both side-to-move colours.
FENS=(
  "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
  "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
  "8/8/8/4k3/8/4K3/4P3/8 w - - 0 1"
  "rnbqkb1r/1pp1pp1p/p6n/3p2p1/6P1/P2P1N2/1PP1PP1P/RNBQKB1R w KQkq g6 0 5"
  "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R b KQkq - 0 1"
  "2r3k1/5ppp/8/8/8/8/5PPP/2R3K1 b - - 0 1"
)

fail=0
for f in "${FENS[@]}"; do
  r="$(LABZERO_NNUE="${NET}" "${ENGINE}" eval "${f}" 2>/dev/null)"
  p="$("${PY}" "${ROOT}/scripts/nnue_format.py" forward "${NET}" "${f}")"
  if [[ "${r}" == "${p}" ]]; then
    echo "OK   engine=${r}  ref=${p}"
  else
    echo "MISMATCH engine=${r} ref=${p}  fen=${f}" >&2
    fail=1
  fi
done

if [[ "${fail}" -eq 0 ]]; then
  echo "PARITY OK: engine integer inference matches the Python reference."
else
  echo "PARITY FAILED" >&2
fi
exit "${fail}"
