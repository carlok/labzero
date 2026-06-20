# Reproducibility

All builds, tests, and verifier runs use Podman with the repo bind-mounted at `/workspace`.

## Image

- **Tag:** `labzero-dev`
- **Definition:** [containers/Containerfile.dev](../containers/Containerfile.dev)
- **Base:** `rust:1-bookworm`

### Pinned tooling (in image)

| Tool | Source |
|------|--------|
| Rust stable + clippy + rustfmt | rust:1-bookworm |
| Python 3 + pip deps | `verifier/python/requirements.txt` |
| Stockfish binary | Debian `stockfish` package (oracle/opponent only) |
| Fastchess | Shallow git clone + `make` in image |

Container runs as `--user 0:0` for bind-mount write access on macOS/Linux. Cargo artifacts: `/workspace/.cargo-target`.

## Volume mount

```bash
-v "$REPO_ROOT:/workspace"   # :Z suffix on Linux SELinux
-w /workspace
-e CARGO_TARGET_DIR=/workspace/.cargo-target
```

Named volumes cache Cargo registry/git: `labzero-cargo-registry`, `labzero-cargo-git`.

## macOS

Use Podman Desktop or `podman machine init && podman machine start`. Scripts omit `:Z` on Darwin.

## Commands

| Task | Command |
|------|---------|
| Build image | `./scripts/podman/build-image` |
| Dev shell | `./scripts/podman/shell` |
| Build engine | `./scripts/podman/build-engine` |
| Verifier smoke | `./scripts/podman/verify-smoke` |
| Full CI | `./scripts/podman/ci` |
| Tournament smoke | `./scripts/podman/tournament-smoke` |

Compose alternative: `podman compose -f compose.yaml run --rm dev bash`
