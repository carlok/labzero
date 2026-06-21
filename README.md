<p align="center">
  <img src="LabZero-logo.png" alt="LabZero logo" width="220">
</p>

# labzero

≈1900–2000 on limited-Stockfish benchmarks — fully legal, original Rust UCI engine. See [strength ladder](docs/strength/ladder.md).

**[Download prebuilt binaries](https://github.com/carlok/labzero/releases)** — macOS Apple Silicon & Linux x86_64 (UCI; no Rust required).

[![CI](https://github.com/carlok/labzero/actions/workflows/ci.yml/badge.svg)](https://github.com/carlok/labzero/actions/workflows/ci.yml)

Research target: an LLM-iterated engine with no copied engine core, independent perft/legality validation, UCI protocol compliance, and automated tournament survival.

## Downloads (prebuilt UCI binary)

Tagged releases include host binaries (no Rust required):

| Platform | Asset |
|----------|--------|
| **macOS Apple Silicon** | `labzero-macos-aarch64` |
| **Linux x86_64** | `labzero-linux-x86_64` |

Get them from **[GitHub Releases](https://github.com/carlok/labzero/releases)** (latest tag, e.g. `v0.5.0`). Each upload has a `.sha256` sidecar; `SHA256SUMS` lists all files.

**macOS:** release binaries are **not code-signed or notarized**. On first run, Gatekeeper may block the app (“unidentified developer”). Use **Right click → Open**, or verify the `.sha256` checksum and build from source if you prefer. Linux users can verify with `sha256sum -c` against `SHA256SUMS`.

Quick smoke after download:

```bash
chmod +x labzero-macos-aarch64   # or labzero-linux-x86_64
printf 'uci\nisready\nquit\n' | ./labzero-macos-aarch64
```

Point your UCI GUI (Banksia, Cute Chess, etc.) at that path. To build from source instead, see below.

Maintainers: push a semver tag to publish — `git tag v0.5.0 && git push origin v0.5.0` runs [`.github/workflows/release.yml`](.github/workflows/release.yml).

## Quick start (Podman)

Requires [Podman](https://podman.io/). On macOS, start a Podman machine first.

```bash
./scripts/podman/build-image
./scripts/podman/build-engine
./scripts/podman/verify-smoke
./scripts/podman/ci
```

## Play against labzero

**macOS GUI (Banksia):** build a native binary first — Podman output is Linux-only.

```bash
./scripts/build-host-engine.sh
./scripts/play-uci.sh          # prints target/release/labzero for Banksia
```

See **[User manual](docs/user_manual.md)** for full GUI setup.

## Verification levels

| Command | Purpose |
|---------|---------|
| `./scripts/podman/ci` | Daily smoke gate |
| `./scripts/podman/verify-deep` | Deep perft, 200-game fuzz, Rust cross-checks |
| `./scripts/podman/gauntlet --smoke` | 10-game tournament |
| `./scripts/podman/gauntlet` | 100-game tournament gauntlet |
| `./scripts/podman/bot --dry-run` | Lichess bridge dry-run (dev stub) |

## Layout

| Path | Purpose |
|------|---------|
| `engine/` | Original UCI chess engine (Rust) |
| `verifier/` | Independent Python/Rust validation tools |
| `lichess_bot/` | Minimal Lichess bridge stub (dev/CI dry-run); live play uses [lichess-bot](https://github.com/lichess-bot-devs/lichess-bot) |
| `tournaments/` | Fastchess smoke and gauntlet scripts |
| `docs/` | Architecture, user manual, submission pack |
| `containers/` | Podman image definition |
| `scripts/podman/` | Portable build/test/CI wrappers |

## Documentation

- [User manual — play vs engine](docs/user_manual.md)
- [Submission package](docs/submission_package.md)
- [Lichess bot setup](docs/lichess_bot_setup.md)
- [Human play QA checklist](docs/human_play_checklist.md)
- [Originality policy](docs/originality_policy.md)
- [Reproducibility / Podman](docs/reproducibility.md)
- [UCI commands](docs/uci_supported.md)
- [Lab log](docs/lab_log.md)
- [Alpha paper draft](docs/paper_alpha.md)

## License

MIT — see [LICENSE](LICENSE).
