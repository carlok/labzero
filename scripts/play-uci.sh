#!/usr/bin/env bash
# Print engine path and UCI GUI setup hints for human play.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE="${ROOT}/.cargo-target/release/labzero"

echo "labzero — play against the engine"
echo ""
if [[ -x "${ENGINE}" ]]; then
  echo "Engine binary: ${ENGINE}"
else
  echo "Engine not built. Run: ./scripts/podman/build-engine"
  echo "Expected path: ${ENGINE}"
fi
echo ""
echo "UCI GUI setup:"
echo "  1. Add UCI engine with command: ${ENGINE}"
echo "  2. Protocol: UCI"
echo "  3. Suggested TC: 5+3 or 10+0"
echo ""
echo "Full guide: docs/user_manual.md"
echo "Podman build: ./scripts/podman/build-engine"
