#!/usr/bin/env bash
# Foreground sidecar monitor for online Lichess bot rating statistics.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [[ -n "${PYTHON:-}" ]]; then
  exec "${PYTHON}" "${ROOT}/lichess_bot/bot_radar.py" "$@"
fi

VENV="${ROOT}/lichess_bot/.venv"
if [[ ! -x "${VENV}/bin/python" ]]; then
  python3 -m venv "${VENV}"
fi

if ! "${VENV}/bin/python" - <<'PY' >/dev/null 2>&1
import chess
PY
then
  "${VENV}/bin/python" -m pip install -q -r "${ROOT}/lichess_bot/requirements.txt"
fi

exec "${VENV}/bin/python" "${ROOT}/lichess_bot/bot_radar.py" "$@"
