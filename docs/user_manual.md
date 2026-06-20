# User manual — play against labzero

## Build the engine

Requires [Podman](https://podman.io/).

```bash
./scripts/podman/build-image    # once
./scripts/podman/build-engine
```

Release binary (inside container): `/workspace/.cargo-target/release/labzero`  
On host after build: `.cargo-target/release/labzero`

## Play with a UCI GUI (recommended)

labzero speaks **UCI**. Use any UCI-compatible GUI:

| GUI | Platform | Notes |
|-----|----------|-------|
| [Banksia](https://banksia.info/) | Win / Mac / Linux | Modern, easy engine setup |
| [Cute Chess GUI](https://github.com/cutechess/cutechess/releases) | Cross-platform | Tournament-focused |
| [Lucas Chess](https://lucaschess.blogspot.com/) | Windows | Beginner-friendly |
| [Arena](http://www.playwitharena.de/) | Windows | Classic free GUI |

### Setup steps (generic)

1. Open the GUI → Engines → Install / Add UCI engine
2. **Command:** absolute path to `labzero` binary (see above)
3. **Protocol:** UCI
4. **Working directory:** optional; not required
5. Start a new game: Human vs Engine

### Suggested settings

- **Time control:** 5+3 or 10+0 for casual play
- **Engine depth:** GUI may send `go movetime` or `go depth` — labzero handles both
- **Strength:** labzero is weak (~beginner); suitable for learning tests

### Quick path helper

```bash
./scripts/play-uci.sh
```

Prints the engine path and GUI configuration hints.

## Play on Lichess (bot account)

See [lichess_bot_setup.md](lichess_bot_setup.md) to run labzero as a Lichess bot.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Engine does not start | Run `./scripts/podman/build-engine`; check binary is executable |
| Illegal move error | File a bug with FEN + move; run `./scripts/podman/verify-smoke` |
| Engine hangs on `go` | Send `stop`; report time control used |
| No output in GUI | Ensure UCI mode (not WinBoard/XBoard) |

## Dev CLI (non-UCI)

```bash
labzero perft 3                           # startpos depth 3
labzero perft 2 "FEN..."                  # custom position
```

Run via Podman:

```bash
./scripts/podman/run .cargo-target/release/labzero perft 3
```
