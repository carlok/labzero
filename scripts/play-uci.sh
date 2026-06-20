#!/usr/bin/env bash
# Print engine path and UCI GUI setup hints for human play.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST_ENGINE="${ROOT}/target/release/labzero"
PODMAN_ENGINE="${ROOT}/.cargo-target/release/labzero"

echo "labzero — play against the engine"
echo ""

if [[ -x "${HOST_ENGINE}" ]]; then
  echo "Engine binary (use in Banksia / UCI GUI):"
  echo "  ${HOST_ENGINE}"
elif [[ "$(uname -s)" == "Darwin" ]]; then
  echo "No macOS GUI binary yet. Build one:"
  echo "  ./scripts/build-host-engine.sh"
  echo ""
  echo "Do NOT use .cargo-target/release/labzero in Banksia — that is a Linux"
  echo "binary from Podman and will fail with 'doesn't support any protocol'."
else
  echo "Build host binary: ./scripts/build-host-engine.sh"
fi

if [[ -x "${PODMAN_ENGINE}" ]]; then
  echo ""
  echo "Podman/Linux binary (CI, verify, gauntlet — not for macOS GUI):"
  echo "  ${PODMAN_ENGINE}"
fi

echo ""
echo "UCI GUI setup:"
echo "  1. Add UCI engine → command: path above"
echo "  2. Protocol: UCI"
echo "  3. Suggested TC: 5+3 or 10+0"
echo ""
echo "Full guide: docs/user_manual.md"
