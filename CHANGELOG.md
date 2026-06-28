# Changelog

## Unreleased

(nothing)

## 0.6.2 — 2026-06-28

- **Search:** score 3-fold repetition and 50-move draws as `0` in `negamax`/`qsearch` (before TT cutoff); root rank v3 wired (first-on-tie, draw/repeat/progress at root)
- **UCI:** clear `stop` flag at each `go`
- **Harness:** `TC_MODE=wtime` real-clock vs `freshclock synthetic`; `DEBUG_MOVES`, `MAX_PLIES`, SIGINT footer; `host-benchmark-analyze.py`
- **Measurement honesty:** withdraw public **≈2600 / ≈2400** headline. Legacy gauntlet rows used **freshclock synthetic** (full 3+2 reset each move), not production wtime.
- **Real-clock gates (INVALID):** SF@2500 1–5–3/9; SF@2400 0–4–1/5. Smoke SF@2400 4g 1–0–3 pass.
- **Gate:** classical sprint gate unsets/warns on `LABZERO_NNUE` / `LABZERO_POLICY`
- **lichess_bot:** local run scripts, ladder stats, tests (see `lichess_bot/README.md`)

## 0.6.1 — 2026-06-26

- **Search:** fixed iterative-deepening time accounting so `should_start_depth` receives the previous iteration duration instead of cumulative elapsed time
- **Measurement:** direct 3+2 **T=4** vs SF@2600 **32g → 13–9–10 (56.2%, 18/32 W-equiv, perf ≈2644)** (`gate_sf2600_idtime_32g`); 0 illegal/errors
- **Release:** package/tag **v0.6.1**; README/ladder headline now uses the direct SF2600 row

## 0.6.0 — 2026-06-24

- **Search:** magic bitboards + precomputed leaper tables; O(1) mailbox `piece_at`; clone-once legality in movegen (~3.6× perft 6, ~1.4× depth-12 search vs pre-sprint)
- **Eval:** runtime tunable params via `LABZERO_EVAL_PARAMS` (`engine/src/params.rs`); default weights unchanged
- **NNUE:** original two-perspective net (`engine/src/nnue.rs`), off by default; `LABZERO_NNUE` / `NnueFile`; host train/verify scripts
- **Tooling:** resumable `host-gauntlet`, `host-spsa`, self-play CLI, sprint wrappers (`host-sprint-*`), `host-kill-sprint`, `host-record-gauntlet`; operator guide `docs/operator/superhuman-band-sprint.md`
- **Measurement:** 3+2 **T=4** vs SF@2500 **32g → 18–7–7 (67.2%, perf ≈2624)** (`baseline_sf2500`); 0 illegal/errors
- **Tuning:** SPSA s2 (500 iters) **rollback** — same protocol with `spsa_s2.best.params` **11–10–11 (51.6%)** vs baseline (`gate_sf2500_32g`)
- **Headline:** README/ladder **≈2600** on limited-Stockfish benchmarks (was ≈2400)

## 0.5.4 — 2026-06-23

- **SEE:** fix `see_capture_value` sign semantics for capture move ordering (undefended wins positive; defended losses negative); direct unit tests in `engine/src/see.rs`
- **Search:** bounded history gravity + quiet malus on beta cutoffs (`HISTORY_MAX`, capped `history_bonus`, penalize earlier quiet non-cutoffs)
- **Measurement:** 3+2 blitz **T=4** vs SF@2000 **20–6–6 (71.9%, 23/32 W-equiv)**; SF@2200 **16g 7–7–2**, **32g 12–7–13 (57.8%, perf ≈ 2257)**; 0 illegal/errors
- **Headline:** README/ladder **≈2200** on limited-Stockfish benchmarks (was ≈2100)
- **Note:** qsearch SEE pruning attempted twice and rolled back; not included in this release
- **Docs:** ladder/lab_log sync; benchmark artifacts through `benchmark_20260623T104424Z`

## 0.5.3 — 2026-06-22

- **Search:** null-move EP/hash fix (`NullUndo`); timed TT score cutoffs re-enabled post-Zobrist; **qsearch skips stand-pat in check** (full legal evasions)
- **Measurement:** 3+2 blitz vs SF@2000 **T=4 32g → 16–7–9 (64.1%)**; direct SF@2100 **19–11–2 (62.5%)** validates headline; README **≈2100**
- **Docs:** ladder/lab_log/architecture sync; benchmark artifacts through `benchmark_20260622T185217Z`

## 0.5.2 — 2026-06-21

- **SMP:** Lazy SMP v2 — helpers start iterative deepening at staggered depths 3/4/5; aspiration cold-start fix for helper threads
- **Search:** `search_with_info_from_depth` entrypoint; start-depth clamp when above max
- **Measurement:** 3+2 blitz vs SF@2000 — **T=4 7–5–4 (56.2%, perf ≈ 2044)**; headline **≈2050** on limited-Stockfish benchmarks (later revised to **≈2100** after 32g confirms)
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
