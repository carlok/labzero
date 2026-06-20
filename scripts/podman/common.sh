#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IMAGE_NAME="${LABZERO_IMAGE:-labzero-dev}"
CONTAINERFILE="${REPO_ROOT}/containers/Containerfile.dev"

# SELinux relabel (:Z) on Linux; skip on macOS
volume_mount() {
  local src="$1"
  local dst="$2"
  if [[ "$(uname -s)" == "Linux" ]]; then
    printf '%s:%s:Z' "${src}" "${dst}"
  else
    printf '%s:%s' "${src}" "${dst}"
  fi
}

podman_run() {
  local repo_vol
  repo_vol="$(volume_mount "${REPO_ROOT}" /workspace)"
  local cmd="$*"
  podman run --rm --user 0:0 \
    -v "${repo_vol}" \
    -v labzero-cargo-registry:/usr/local/cargo/registry \
    -v labzero-cargo-git:/usr/local/cargo/git \
    -w /workspace \
    -e CARGO_TARGET_DIR=/workspace/.cargo-target \
    -e RUST_BACKTRACE=1 \
    "${IMAGE_NAME}" \
    bash -c "export PATH=/usr/local/cargo/bin:\$PATH; ${cmd}"
}

export REPO_ROOT IMAGE_NAME CONTAINERFILE
