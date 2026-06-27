#!/usr/bin/env bash
# Sprint loop — policy data + train + parity verify.
#
# Output: data/policy/policy.lzp
#
#   ./scripts/host-sprint-policy.sh
#   POLICY_GAMES=10000 LABEL_DEPTH=7 EPOCHS=20 ./scripts/host-sprint-policy.sh  # v2 soft retrain
#   POLICY_GAMES=5000 EPOCHS=20 ./scripts/host-sprint-policy.sh
#   SKIP_POLICYDATA=1 ./scripts/host-sprint-policy.sh
#   nohup ./scripts/host-sprint-policy.sh > data/policy/run.log 2>&1 &
#
# After:  export LABZERO_POLICY=data/policy/policy.lzp
#         export LABZERO_POLICY_MODE=soft
#         ./scripts/host-sprint-gate.sh 2600
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

ENGINE="${ENGINE:-${ROOT}/target/release/labzero}"
POLICY_OUT="${POLICY_OUT:-data/policy/pd.txt}"
POLICY_GAMES="${POLICY_GAMES:-2000}"
PLAY_DEPTH="${PLAY_DEPTH:-4}"
LABEL_DEPTH="${LABEL_DEPTH:-6}"
SEED="${SEED:-1}"
SKIP_POLICYDATA="${SKIP_POLICYDATA:-0}"

HIDDEN="${HIDDEN:-64}"
EPOCHS="${EPOCHS:-10}"
BATCH="${BATCH:-256}"
LR="${LR:-1e-3}"
OUT_NET="${OUT_NET:-data/policy/policy.lzp}"
CKPT="${CKPT:-data/policy/train.ckpt}"
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

echo "==> policy sprint  games=${POLICY_GAMES}  play=${PLAY_DEPTH}  label=${LABEL_DEPTH}  hidden=${HIDDEN}  epochs=${EPOCHS}"

if [[ "${SKIP_KILL:-0}" != "1" ]]; then
  "${ROOT}/scripts/host-kill-sprint.sh"
fi

mkdir -p data/policy

if [[ "${SKIP_POLICYDATA}" != "1" ]]; then
  echo "==> policydata -> ${POLICY_OUT}  (target ${POLICY_GAMES} games)"
  "${ENGINE}" policydata "${POLICY_OUT}" "${POLICY_GAMES}" "${PLAY_DEPTH}" "${LABEL_DEPTH}" "${SEED}"
  echo "    positions: $(wc -l < "${POLICY_OUT}" | tr -d ' ')"
else
  echo "==> SKIP_POLICYDATA=1 — using existing ${POLICY_OUT}"
  [[ -f "${POLICY_OUT}" ]] || { echo "no ${POLICY_OUT}" >&2; exit 1; }
fi

echo "==> train"
"${PY}" "${ROOT}/scripts/host-policy-train.py" \
  --data "${POLICY_OUT}" \
  --hidden "${HIDDEN}" \
  --epochs "${EPOCHS}" \
  --batch "${BATCH}" \
  --lr "${LR}" \
  --out "${OUT_NET}" \
  --ckpt "${CKPT}"

echo "==> parity verify"
"${ROOT}/scripts/host-policy-verify.sh" "${OUT_NET}"

echo ""
echo "Policy sprint done. Net: ${ROOT}/${OUT_NET}"
echo "Gate (example):"
echo "  export LABZERO_POLICY=${ROOT}/${OUT_NET}"
echo "  RUN_ID=gate_sf2600_policy_16g ./scripts/host-sprint-gate.sh 2600 16"
