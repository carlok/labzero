# External Opinion Brief: LabZero v0.6.2 Post-Lichess Triage

You are reviewing LabZero, an original Rust UCI chess engine. We had a legacy headline strength claim around SF2600 on limited-Stockfish `3+2`, but the clock protocol and a bad Lichess run now make that claim unsafe. We need your opinion on root cause and next steps, not broad chess-engine advice.

## Project Context

LabZero is an original Rust alpha-beta engine: legal move generation, UCI, iterative deepening, qsearch, TT, null move, LMR, killers/history, SEE ordering, Lazy SMP, and a tapered hand-written evaluation. Optional policy and NNUE experiments exist but are off for current gates. The project goal is honest, reproducible measurement of an LLM-built engine. Stockfish limited-Elo is used only as a project-relative opponent, never as Lichess, CCRL, FIDE, or universal Elo.

Current `main` is `58762da` (after lichess_bot + analyzer commits); tagged `v0.6.2`. This tag should be read as a conservative engineering tag: draw/repetition fixes, harness stabilization, and public strength-headline withdrawal. It should not be read as a validated SF2600 real-clock strength milestone.

## Central Puzzle

The strongest historical rows were produced by a legacy gauntlet protocol that effectively gave the engine a fresh clock every move. Those rows are now labeled **freshclock synthetic**. The production target is different: `TC_MODE=wtime` in `scripts/host-benchmark.sh` sends decreasing `white_clock` and `black_clock` each move. **Important:** host gates use `TC_SEC=3` = **3 seconds** per side (+2s increment), not minutes. Lichess bot uses `clock_limit=180` = **3 minutes** (+2s increment) with real server clocks.

This distinction matters:

| Track | Meaning | Evidence |
|---|---|---|
| Legacy freshclock synthetic | each move sees fresh 3s+2s; gauntlet only | `gate_sf2600_idtime_32g`: 13-9-10, 18/32 W-equiv |
| Real-clock wtime (host) | 3s+2s depleting clock; `host-benchmark.sh` | SF2400/SF2500 gates failed (table below) |
| Lichess 3+2 blitz | 3min+2s, real server clocks, T=4 via bot config | 1-5-1 rated run, table below |

The current question is whether the collapse is mostly measurement artifact, time-management weakness, root-rank/draw-policy side effect, tactical/eval weakness, or some combination.

## Recent Real-Clock Stockfish Evidence (host harness)

Classical eval, NNUE/policy cleared. **`TC_SEC=3` = 3 seconds** (+2s inc), `TC_MODE=wtime`, `THREADS=4`. Verified by `scripts/host-benchmark-analyze.py` (partial logs supported).

| Artifact | Opponent | Result | Status |
|---|---:|---|---|
| `benchmark_20260628T080455Z` | SF2400 | 1-0-3 (2.5/4) | smoke pass; complete footer |
| `benchmark_20260628T082156Z` | SF2500 | 1-5-3 (9/16) | INVALID candidate; partial/no footer |
| `benchmark_20260628T085820Z` | SF2400 | 0-4-1 (5/16) | INVALID confirm; partial/no footer |

The analyzer currently reports `benchmark_20260628T085820Z` as five normal PGN games: one draw, four losses, zero threefold hits, zero illegal/errors/timeouts in the TXT.

## Lichess Evidence

Local PGNs under `lichess_bot/local/pgn/` show a bad rated bot run on 2026-06-28. **3+2 blitz = 3 minutes + 2 seconds** on Lichess (not the 3-second host harness). Bot config: `threads=4`, `hash_mb=64`, engine `labzero-macos-aarch64-0.6.2`.

| Game | Opponent | Opp Elo | LabZero color | Result | Termination |
|---|---|---:|---|---|---|
| `CW0Ex1Tr` | tomahawkBOT | 2215 | Black | draw | draw by repetition/check sequence |
| `jybiuBbU` | tomahawkBOT | 2215 | Black | loss | mate |
| `Cbb8o6xM` | Oxybullet | 2172 | Black | win | opponent out of time |
| `udfe5Wg0` | FlounderBot | 2086 | Black | loss | mate |
| `meQTmVYW` | Martuni | 2158 | White | loss | mate |
| `i4kf2gL6` | GarboBot | 1935 | White | loss | mate |
| `5Z9DIIfD` | CosetteBot | 2088 | Black | loss | mate |

**Run score: 1-5-1.** Only win was opponent timeout after 4 opening plies. Rating in headers drifted ~2034 to ~1959. There are repeated long conversion failures, passive or shuffling defense, and tactical collapses into mating attacks. It does not look like illegal move bugs.

## Relevant Engine/Harness Facts

- `v0.6.2` includes root-rank wiring: first-on-tie root picking, immediate-draw penalty, repeat/progress bonuses only when `root_static >= 150`, and progress limited to quiet passed-pawn pushes.
- `engine/src/time.rs` allocates roughly `remaining_time / 30 + 0.7 * increment`, with reserve logic and no `movestogo` from the harness.
- `scripts/host-benchmark.sh` now supports `freshclock`, real `wtime`, `DEBUG_MOVES`, `MAX_PLIES`, and interrupted footers.
- `scripts/host-benchmark-analyze.py` now parses complete and no-footer partial logs.

## Hypotheses To Rank

Please rank these, with confidence:

1. **Measurement artifact:** legacy freshclock inflated apparent strength; real-clock strength is much lower.
2. **Time manager weakness:** real `3+2` exposes bad allocation, long losing shuffles, or inadequate practical overhead handling.
3. **Root-rank/draw policy side effect:** avoiding immediate draws/repeats changes root choices enough to hurt practical play.
4. **Search/eval tactical weakness:** Lichess opponents expose ordinary tactical and conversion blind spots that Stockfish-limited gates hid.
5. **SMP/TT instability:** `THREADS=4` or Lazy SMP produces unstable choices under real-clock/live conditions.

## Questions For Reviewer

1. What is the top root-cause hypothesis, and what evidence supports it?
2. What single A/B experiment would most decisively separate clock protocol from engine regression?
3. Should root-rank v3 stay enabled for the next diagnostic, or should we compare it against v0.6.2 draw-fix-only behavior?
4. Is the current time allocation reasonable for real `3+2`, or obviously too naive?
5. What is the most defensible public strength statement today?

## Proposed Next Experiment

Do not run SF2600 real-clock. First run a small protocol A/B at SF2200 or SF2400 with the same binary:

```bash
# SF2400 protocol A/B (3 second clock — host harness)
SF_ELO=2400 GAMES=4 TC_MODE=freshclock TC_SEC=3 TC_INC=2 THREADS=4 DEBUG_MOVES=1 MAX_PLIES=160 ./scripts/host-benchmark.sh
SF_ELO=2400 GAMES=4 TC_MODE=wtime      TC_SEC=3 TC_INC=2 THREADS=4 DEBUG_MOVES=1 MAX_PLIES=160 ./scripts/host-benchmark.sh

# Floor probe only if SF2400 wtime still collapses
SF_ELO=2200 GAMES=4 TC_MODE=wtime      TC_SEC=3 TC_INC=2 THREADS=4 DEBUG_MOVES=1 MAX_PLIES=160 ./scripts/host-benchmark.sh
```

Pass condition before stronger tests: no illegal/errors/timeouts, at least 2/4 W-equiv in real-clock at SF2200, and no repeated Lichess-like practical failure.

## Diagnostic A/B Results (2026-06-28)

Protocol A/B at SF2400, 4 games, `TC_SEC=3` (+2s inc), `THREADS=4`, `DEBUG_MOVES=1`, `MAX_PLIES=160`. Classical eval, NNUE/policy cleared. SF2200 floor probe **not run** — wtime did not collapse vs freshclock on this sample.

| Artifact | TC_MODE | Result (W-L-D) | W-equiv (3 completed) | Truncated | Status |
|---|---|---:|---:|---:|---|
| `benchmark_20260628T113901Z` | freshclock | 1-2-0 | 1/3 (33%) | 1 | complete |
| `benchmark_20260628T114956Z` | wtime | 0-1-2 | 1/3 (33%) | 1 | complete |

Both runs: 0 illegal, 0 errors, 0 timeouts. Harness-reported `labzero %` = 33.3 for each (draws count 0.5). Wtime scored **better** than the prior SF2400 confirm gate (`085820Z`: 0-4-1 over 5 games) but still below the 2/4 W-equiv pass bar. Freshclock and wtime split differently (wins vs draws) with similar aggregate score — inconclusive on clock-protocol alone; does not yet justify SF2600 real-clock or rated Lichess.

Move traces: `benchmark_20260628T113901Z.moves.tsv`, `benchmark_20260628T114956Z.moves.tsv`.

## What To Stop Doing

- Stop running rated Lichess until a small real-clock diagnostic looks sane.
- Stop quoting SF2600 as a production real-clock claim.
- Stop adding broad search/eval features until one repeated failure mode is isolated.
- Stop mixing freshclock synthetic, real-clock wtime, and Lichess rows in the same strength statement.

## Defensible Statement Today

LabZero has strong legacy synthetic-clock Stockfish-limited results, but its real-clock and Lichess behavior is currently not validated; v0.6.2 should be treated as an engineering stabilization tag, not a strength milestone.
