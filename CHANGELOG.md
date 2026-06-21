# Changelog

## 0.5.2 — 2026-06-21

- **SMP:** Lazy SMP v2 — helpers start iterative deepening at staggered depths 3/4/5; aspiration cold-start fix for helper threads
- **Search:** `search_with_info_from_depth` entrypoint; start-depth clamp when above max
- **Measurement:** 3+2 blitz vs SF@2000 — **T=4 7–5–4 (56.2%, perf ≈ 2044)**; headline **≈2050** on limited-Stockfish benchmarks (was ≈2000 / noisy 2089 spot)
- **Docs:** ladder/lab_log/architecture sync; benchmark artifacts `benchmark_20260621T181146Z`, `benchmark_20260621T184359Z`

## 0.5.1 — 2026-06-21

- **TT:** 64-shard transposition table (per-shard mutex; reduces SMP lock contention)
- **Hash:** deterministic Zobrist keys + incremental XOR on make/unmake (`engine/src/zobrist.rs`)
- **Measurement:** 3+2 blitz vs SF@2000 — post-Zobrist **T=1 62.5%**, **T=4 50.0%** (16 games); README **≈2000** on limited-Stockfish benchmarks
- **Docs:** ladder/lab_log/paper sync for blitz confirm and SMP spots

## 0.5.0 — 2026-06-21

- **Phase D — search stability:** tactical regression suite (`verifier/positions/tactical.epd`, fixed-depth tests); TT `complete` flag; score cutoffs for `go depth` only (movetime ordering-only); LMR table softened (`move_idx/10`); aspiration from depth 5
- **Phase D — time/UCI:** `ucinewgame` resets stop flag; UCI protocol matrix in docs; `host-benchmark.sh` wtime via `white_clock`/`black_clock`
- **Phase D — eval:** tune pawn structure / isolated pawn / rook-on-open-file weights
- **Measurement:** anchor (1+0): SF@2000 **37.5%** (32-game confirm, ≈1911 perf); blitz (3+2 @ SF2000): **48.4%** (32-game confirm) — see `docs/strength/ladder.md`

## 0.4.0 — 2026-06-20

- **Search (Phase C):** remove depth-6 cap (default 64), aspiration, PV move ordering, root make/unmake; TT move ordering under timed search (score cutoffs disabled after regression)
- **Time:** soft stop before new ID iteration, panic reserve, increment-aware wtime allocation
- **UCI:** `info` lines (depth/score/nodes/nps/time), `Hash`, `Threads`, `OwnBook`/`BookFile`
- **Eval:** enable pawn structure, rook files, king safety (original weights)
- **SMP:** Lazy SMP with shared TT (Threads 1–8, default 1)
- **Book:** optional opening lines (disabled for strength ladder)
- **Benchmark:** `TC_MODE=movetime|wtime`, `THREADS` env in `host-benchmark.sh`

## 0.3.0-beta — 2026-06-20

- **Search:** quiescence, transposition table, null-move pruning, LMR, killer/history ordering, SEE
- **Eval:** tapered mg/eg PSTs, pawn structure, bishop pair, rook files, king safety, mobility
- Strength ladder re-measured vs Stockfish limited-Elo (see `docs/strength/ladder.md`)

## 0.2.0 — 2026-06-20

- Sprint roadmap: deep verification, gauntlet, human-play docs, Lichess bot bridge
- UCI `id version` in handshake
- UCI move replay via legal move resolution (fixes multi-game desync)
- Synchronous search in UCI loop for stability

## 0.1.0 — 2026-06-20

- Initial MVP: original Rust UCI engine, Podman CI, smoke verification
