# UCI supported commands

Engine name: `labzero`

## Commands

| Command | Supported |
|---------|-----------|
| `uci` | yes — responds with `id`, `uciok` |
| `id version` | yes — semver from Cargo.toml (e.g. `0.2.0`) |
| `isready` | yes — responds with `readyok` |
| `ucinewgame` | yes |
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

No configurable UCI options yet (`setoption` ignored).
