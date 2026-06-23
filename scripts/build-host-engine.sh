#!/usr/bin/env bash
# Build a native macOS/Linux host binary for UCI GUIs (Banksia, Cute Chess, …).
# Podman builds produce a Linux binary in .cargo-target/ — not usable by macOS GUIs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

ensure_cargo() {
  if command -v cargo >/dev/null 2>&1; then
    return 0
  fi
  if [[ -f "${HOME}/.cargo/env" ]]; then
    # shellcheck disable=SC1091
    source "${HOME}/.cargo/env"
  fi
  command -v cargo >/dev/null 2>&1
}

if ! ensure_cargo; then
  echo "==> Rust not found — installing rustup (stable)"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
  # shellcheck disable=SC1091
  source "${HOME}/.cargo/env"
fi

# Podman CI sets CARGO_TARGET_DIR=.cargo-target (Linux). Host GUI builds must use target/.
unset CARGO_TARGET_DIR

echo "==> cargo fmt"
cargo fmt --manifest-path engine/Cargo.toml

echo "==> cargo clippy"
cargo clippy --manifest-path engine/Cargo.toml -- -D warnings

echo "==> cargo build --release (host native)"
cargo build --release --manifest-path engine/Cargo.toml

ENGINE="${ROOT}/target/release/labzero"
if [[ ! -x "${ENGINE}" ]]; then
  echo "build-host-engine: expected binary missing: ${ENGINE}" >&2
  exit 1
fi

echo ""
echo "Host engine ready for UCI GUIs:"
echo "  ${ENGINE}"
echo ""
file "${ENGINE}"
echo ""
echo "UCI smoke:"
printf 'uci\nisready\nquit\n' | "${ENGINE}" | sed 's/^/  /'
echo ""
echo "Use this path in Banksia (not .cargo-target/release/labzero)."
