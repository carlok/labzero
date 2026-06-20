#!/usr/bin/env bash
# Fastchess self-play smoke test — run inside labzero-dev container.
set -euo pipefail

ENGINE="${1:?engine path}"
RUNNER="${2:-fastchess}"

if [[ "${RUNNER}" == "fastchess" ]]; then
  "${RUNNER}" \
    -engine cmd="${ENGINE}" name=labzero proto=uci \
    -engine cmd="${ENGINE}" name=labzero2 proto=uci \
    -each depth=2 -rounds 2
elif [[ "${RUNNER}" == "cutechess-cli" ]]; then
  "${RUNNER}" \
    -engine name=labzero cmd="${ENGINE}" proto=uci \
    -engine name=labzero2 cmd="${ENGINE}" proto=uci \
    -each tc=0.1+0.01 -rounds 2 -repeat
else
  echo "unknown runner: ${RUNNER}" >&2
  exit 1
fi

echo "tournament smoke: PASS"
