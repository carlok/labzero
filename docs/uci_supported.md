# UCI supported commands

Engine name: `labzero`

## Commands

| Command | Supported |
|---------|-----------|
| `uci` | yes — responds with `id`, options, `uciok` |
| `id version` | yes — semver from Cargo.toml (e.g. `0.4.0`) |
| `isready` | yes — responds with `readyok` |
| `ucinewgame` | yes — clears transposition table |
| `position startpos` | yes |
| `position startpos moves ...` | yes |
| `position fen ...` | yes |
| `position fen ... moves ...` | yes |
| `go` | yes — supports `depth`, `movetime`, `wtime`, `btime`, `winc`, `binc`, `movestogo`, `infinite` |
| `stop` | yes |
| `quit` | yes |

## Dev CLI (non-UCI)

```bash
labzero perft <depth> [fen]
```

Runs perft from optional FEN (default start position).

## Options

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `Hash` | spin (MB) | 64 | Transposition table size (1–1024) |
| `Threads` | spin | 1 | Lazy SMP workers (1–8); strength ladder uses **1** |
| `OwnBook` | check | false | Enable opening book |
| `BookFile` | string | — | Load UCI move lines from file (EPD-derived paths ok) |

Search emits `info depth score cp nodes nps time` after each completed iterative-deepening iteration.

## Protocol matrix (Phase D2)

| `go` mode | Example | Expected |
|-----------|---------|----------|
| movetime | `go movetime 1000` | search ~1s, `bestmove` |
| depth | `go depth 8` | fixed depth, no clock stop |
| wtime/btime | `go wtime 30000 btime 30000 winc 2000 binc 2000` | allocates from clock |
| wtime + inc | `go wtime 10000 btime 10000 winc 500 binc 500` | increment bonus applied |
| infinite | `go infinite` | runs until `stop` |
| stop | `stop` during search | `bestmove` within ~100ms |
| ucinewgame | after `stop` | clears TT, resets stop flag |
| Threads>1 | `setoption name Threads value 4` | Lazy SMP, shared TT |

Smoke: `./scripts/podman/verify-smoke` + gauntlet smoke after search/time changes.

## Strength measurement

Anchor ladder (comparable to beta): `THREADS=1 TC_MODE=movetime TC_SEC=1`.

Spot blitz: `TC_MODE=wtime TC_SEC=3 TC_INC=2`. Spot rapid: `TC_SEC=10 THREADS=4`.
