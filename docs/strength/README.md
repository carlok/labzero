# Host benchmark output (`./scripts/host-benchmark.sh`)

Files appear **immediately** when a run starts and grow **after each game**:

| File | Contents |
|------|----------|
| `benchmark_<timestamp>.txt` | Header, one line per game (running W-L-D), final score at end |
| `benchmark_<timestamp>.pgn` | Games appended as they finish |
| `benchmark_<timestamp>.moves.tsv` | Per-move telemetry when `DEBUG_MOVES=1` (gitignored) |

Incremental disk writes do not affect engine thinking (one small append ~once per minute).

If a run is interrupted (Ctrl-C), the footer records `status: interrupted` with current W-L-D, illegal/errors, and artifact paths.

## Time control tracks

| `TC_MODE` | Label in `.txt` | Use |
|-----------|-----------------|-----|
| `wtime` | `wtime real-clock` | **Production gold standard** — clocks decrease per move; Lichess readiness |
| `freshclock` | `freshclock synthetic` | **Legacy comparability** — repeated full clock each move (old harness semantics) |
| `movetime` | `movetime` | Fixed movetime per ply |

Do not compare `wtime` results directly with pre-2026-06-28 rows that used synthetic clock behavior without the `freshclock` label.

**Tracked wtime gate artifacts (v0.6.2):** `benchmark_20260628T080455Z` (smoke), `benchmark_20260628T082156Z` (INVALID candidate), `benchmark_20260628T085820Z` (INVALID confirm). Harness dev smokes are gitignored.

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `GAMES` | 32 | Number of games (colors alternate) |
| `TC_SEC` / `TC_INC` | 1 / 0 | Base seconds + increment |
| `TC_MODE` | movetime | `wtime`, `freshclock`, or `movetime` |
| `THREADS` | 1 | LabZero UCI Threads |
| `SF_ELO` / `SF_SKILL` / `SF_LIMIT` | 1320 / 0 / 1 | Stockfish strength limit |
| `DEBUG_MOVES` | 0 | When 1, write `.moves.tsv` and live ply logs |
| `MAX_PLIES` | 0 | When >0, stop each game at that ply (`truncated` in log) |
| `OUT_DIR` | `docs/strength` | Output directory |

## Analyze artifacts

```bash
python3 scripts/host-benchmark-analyze.py docs/strength/benchmark_20260628T072449Z
```

## Live tail

```bash
tail -f docs/strength/benchmark_*.txt
```
