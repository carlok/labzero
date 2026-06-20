# Architecture

## Engine (`engine/`)

| Module | Role |
|--------|------|
| `uci.rs` | UCI protocol loop |
| `board.rs` | Position state, game status |
| `square.rs`, `piece.rs`, `color.rs`, `mov.rs` | Types |
| `movegen.rs` | Legal move generation |
| `make_unmake.rs` | Apply/revert moves |
| `fen.rs` | FEN parse/serialize |
| `perft.rs` | Perft divider |
| `search.rs` | Negamax + alpha-beta + iterative deepening |
| `eval.rs` | Material + original piece-square tables |
| `time.rs` | Time budget for `go` |

Bitboard representation with mailbox king tracking. Search uses negamax, alpha-beta pruning, and simple move ordering.

## Verifier (`verifier/`)

Independent oracles in Python (and optional Rust crosschecks) that compare engine behavior against `python-chess` and published perft tables.

## Execution

All builds and tests run in Podman — see [reproducibility.md](reproducibility.md).
