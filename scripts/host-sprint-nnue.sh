#!/usr/bin/env bash
# Sprint loop 2 — self-play scale (optional) + NNUE train + parity verify.
#
# Self-play feeds NNUE only (not SPSA). Training is resumable via --ckpt.
# Output: data/nnue/net.nnue
#
#   ./scripts/host-sprint-nnue.sh
#   SELFPLAY_GAMES=50000 HIDDEN=256 EPOCHS=30 ./scripts/host-sprint-nnue.sh
#   SKIP_SELFPLAY=1 ./scripts/host-sprint-nnue.sh   # train on existing sp.txt
#   nohup ./scripts/host-sprint-nnue.sh > data/nnue/run.log 2>&1 &
#
# After:  export LABZERO_NNUE=data/nnue/net.nnue
#         ./scripts/host-sprint-gate.sh 2600
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

ENGINE="${ENGINE:-${ROOT}/target/release/labzero}"
SELFPLAY_OUT="${SELFPLAY_OUT:-data/selfplay/sp.txt}"
SELFPLAY_GAMES="${SELFPLAY_GAMES:-10000}"
SELFPLAY_DEPTH="${SELFPLAY_DEPTH:-4}"
SELFPLAY_SEED="${SELFPLAY_SEED:-1}"
SKIP_SELFPLAY="${SKIP_SELFPLAY:-0}"

HIDDEN="${HIDDEN:-256}"
EPOCHS="${EPOCHS:-30}"
BATCH="${BATCH:-8192}"
LR="${LR:-1e-3}"
OUT_NET="${OUT_NET:-data/nnue/net.nnue}"
CKPT="${CKPT:-data/nnue/train.ckpt}"
PY="${ROOT}/.venv-host-test/bin/python"

if [[ ! -x "${ENGINE}" ]]; then
  echo "missing engine: ${ENGINE} — run ./scripts/build-host-engine.sh" >&2
  exit 1
fi

if [[ ! -x "${PY}" ]]; then
  echo "missing venv python: ${PY}" >&2
  echo "  python3 -m venv .venv-host-test && .venv-host-test/bin/pip install python-chess torch" >&2
  exit 1
fi

echo "==> sprint 2/3: NNUE  games=${SELFPLAY_GAMES}  hidden=${HIDDEN}  epochs=${EPOCHS}"

# Kill gauntlet/SPSA/stale engines; allow a dedicated selfplay if you run parallel
# by setting SKIP_KILL=1 (advanced).
if [[ "${SKIP_KILL:-0}" != "1" ]]; then
  "${ROOT}/scripts/host-kill-sprint.sh"
fi

mkdir -p data/selfplay data/nnue

if [[ "${SKIP_SELFPLAY}" != "1" ]]; then
  echo "==> self-play -> ${SELFPLAY_OUT}  (target ${SELFPLAY_GAMES} games, depth ${SELFPLAY_DEPTH})"
  echo "    (appends if file exists — rm sp.txt sp.games for fresh run)"
  "${ENGINE}" selfplay "${SELFPLAY_OUT}" "${SELFPLAY_GAMES}" "${SELFPLAY_DEPTH}" "${SELFPLAY_SEED}"
  echo "    positions: $(wc -l < "${SELFPLAY_OUT}" | tr -d ' ')"
else
  echo "==> SKIP_SELFPLAY=1 — using existing ${SELFPLAY_OUT}"
  [[ -f "${SELFPLAY_OUT}" ]] || { echo "no ${SELFPLAY_OUT}" >&2; exit 1; }
fi

echo "==> train"
"${PY}" "${ROOT}/scripts/host-nnue-train.py" \
  --data "${SELFPLAY_OUT}" \
  --hidden "${HIDDEN}" \
  --epochs "${EPOCHS}" \
  --batch "${BATCH}" \
  --lr "${LR}" \
  --out "${OUT_NET}" \
  --ckpt "${CKPT}"

echo "==> parity verify"
"${ROOT}/scripts/host-nnue-verify.sh" "${OUT_NET}"

echo ""
echo "NNUE done. Net: ${ROOT}/${OUT_NET}"
echo "Gate (example):"
echo "  export LABZERO_NNUE=${ROOT}/${OUT_NET}"
echo "  ./scripts/host-sprint-gate.sh 2600"
