# User manual — play against labzero

## Two build paths

| Use case | Command | Binary |
|----------|---------|--------|
| **UCI GUI on macOS** (Banksia, etc.) | `./scripts/build-host-engine.sh` | `target/release/labzero` |
| **CI, verify, gauntlet** (Podman) | `./scripts/podman/build-engine` | `.cargo-target/release/labzero` (Linux inside container) |

On macOS, **Banksia must use the host binary** in `target/release/labzero`.  
The Podman-built path `.cargo-target/release/labzero` is a **Linux ELF** file and will fail in Banksia with *"This engine doesn't support any protocol!"*

## Build for GUI play (macOS / native host)

Installs Rust via rustup if needed, then builds a native binary:

```bash
./scripts/build-host-engine.sh
```

Engine path for Banksia:

```text
/Users/you/.../labzero/target/release/labzero
```

Quick helper:

```bash
./scripts/play-uci.sh
```

## Build for Podman workflow

Requires [Podman](https://podman.io/). On macOS, start a Podman machine first.

```bash
./scripts/podman/build-image    # once
./scripts/podman/build-engine
./scripts/podman/verify-smoke
./scripts/podman/ci
```

## Play with a UCI GUI (recommended)

labzero speaks **UCI**. Use any UCI-compatible GUI:

| GUI | Platform | Notes |
|-----|----------|-------|
| [Banksia](https://banksia.info/) | Win / Mac / Linux | Use **host** binary on Mac |
| [Cute Chess GUI](https://github.com/cutechess/cutechess/releases) | Cross-platform | Tournament-focused |
| [Lucas Chess](https://lucaschess.blogspot.com/) | Windows | Beginner-friendly |
| [Arena](http://www.playwitharena.de/) | Windows | Classic free GUI |

### Setup steps (Banksia on macOS)

1. Run `./scripts/build-host-engine.sh` once
2. Banksia → Engines → Install / Add UCI engine
3. **Command:** absolute path to `target/release/labzero` (from `./scripts/play-uci.sh`)
4. **Protocol:** UCI
5. Start a new game: Human vs Engine

### Suggested settings

- **Time control:** 5+3 or 10+0 for casual play
- **Engine depth:** GUI may send `go movetime` or `go depth` — labzero handles both
- **Strength:** labzero is weak (~beginner); suitable for learning tests

## Play on Lichess (bot account)

See [lichess_bot_setup.md](lichess_bot_setup.md) — use **lichess-bot** (official) with the host `target/release/labzero` binary.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Banksia: "doesn't support any protocol" | You pointed at `.cargo-target/...` (Linux). Run `./scripts/build-host-engine.sh` and use `target/release/labzero` |
| Engine does not start | Run `./scripts/build-host-engine.sh`; check binary is executable |
| Illegal move error | File a bug with FEN + move; run `./scripts/podman/verify-smoke` |
| Engine hangs on `go` | Send `stop`; report time control used |
| No output in GUI | Ensure UCI mode (not WinBoard/XBoard) |

## Dev CLI (non-UCI)

```bash
target/release/labzero perft 3
target/release/labzero perft 2 "FEN..."
```

Or via Podman (Linux binary):

```bash
./scripts/podman/run .cargo-target/release/labzero perft 3
```
