# Architecture

## Engine (`engine/`)

| Module | Role |
|--------|------|
| `uci.rs` | UCI protocol loop, options (Hash, Threads, OwnBook) |
| `board.rs` | Position state, Zobrist hash, game status |
| `square.rs`, `piece.rs`, `color.rs`, `mov.rs` | Types |
| `zobrist.rs` | Deterministic Zobrist keys (piece, side, castling, en-passant file) |
| `movegen.rs` | Legal move generation |
| `make_unmake.rs` | Apply/revert moves; incremental hash XOR on make |
| `fen.rs` | FEN parse/serialize |
| `perft.rs` | Perft divider |
| `search.rs` | Negamax, α–β, ID, aspiration, qsearch, null move, LMR, killers/history, TT cutoffs |
| `eval.rs` | Tapered mg/eg PSTs, bishop pair, pawn structure, rook files, king safety |
| `tt.rs` | 64-shard transposition table, mate-aware scores (per-shard `Mutex`) |
| `see.rs` | Static exchange eval for capture ordering |
| `time.rs` | Time budget, soft stop, panic reserve |
| `smp.rs` | Lazy SMP helper threads (shared TT; helpers start ID at depths 3/4/5 cycling) |
| `book.rs` | Optional original opening book (off by default) |

Bitboard representation with mailbox king tracking. Default search depth cap 64 (time-limited ID). Single-thread baseline; optional multi-core via Lazy SMP (main thread from depth 1, helpers from staggered depths 3/4/5).

## Verifier (`verifier/`)

Independent oracles in Python (and optional Rust crosschecks) that compare engine behavior against `python-chess` and published perft tables.

## Execution

All builds and tests run in Podman — see [reproducibility.md](reproducibility.md).
