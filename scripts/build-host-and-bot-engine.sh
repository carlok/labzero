#!/usr/bin/env bash
# Build the host engine and refresh the gitignored Lichess bot binary copies.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

"${ROOT}/scripts/build-host-engine.sh"

ENGINE="${ROOT}/target/release/labzero"
VERSION="$(grep '^version' "${ROOT}/engine/Cargo.toml" | head -1 | cut -d'"' -f2)"
ARCH="$(uname -m)"
OS="$(uname -s)"

case "${OS}" in
  Darwin) OS_NAME="macos" ;;
  Linux) OS_NAME="linux" ;;
  *) OS_NAME="$(printf "%s" "${OS}" | tr '[:upper:]' '[:lower:]')" ;;
esac

case "${ARCH}" in
  arm64|aarch64) ARCH_NAME="aarch64" ;;
  x86_64|amd64) ARCH_NAME="x86_64" ;;
  *) ARCH_NAME="${ARCH}" ;;
esac

PLATFORM="${OS_NAME}-${ARCH_NAME}"

BOT_BIN_DIR="${ROOT}/lichess_bot/bin"
SHORT_COPY="${BOT_BIN_DIR}/labzero"
VERSIONED_COPY="${BOT_BIN_DIR}/labzero-${PLATFORM}-${VERSION}"
LEGACY_COPY="${BOT_BIN_DIR}/labzero-macos-aarch64-${VERSION}"

mkdir -p "${BOT_BIN_DIR}"
cp "${ENGINE}" "${SHORT_COPY}"
cp "${ENGINE}" "${VERSIONED_COPY}"

if [[ "${PLATFORM}" == "macos-aarch64" ]]; then
  cp "${ENGINE}" "${LEGACY_COPY}"
fi

chmod +x "${SHORT_COPY}" "${VERSIONED_COPY}"
if [[ -f "${LEGACY_COPY}" ]]; then
  chmod +x "${LEGACY_COPY}"
fi

if command -v xattr >/dev/null 2>&1; then
  xattr -d com.apple.quarantine "${SHORT_COPY}" 2>/dev/null || true
  xattr -d com.apple.quarantine "${VERSIONED_COPY}" 2>/dev/null || true
  if [[ -f "${LEGACY_COPY}" ]]; then
    xattr -d com.apple.quarantine "${LEGACY_COPY}" 2>/dev/null || true
  fi
fi

echo ""
echo "Bot engine copies ready:"
echo "  ${SHORT_COPY}"
echo "  ${VERSIONED_COPY}"
if [[ -f "${LEGACY_COPY}" && "${LEGACY_COPY}" != "${VERSIONED_COPY}" ]]; then
  echo "  ${LEGACY_COPY}"
fi
