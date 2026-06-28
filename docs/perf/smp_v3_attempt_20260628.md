# SMP v3 Eight-Thread Attempt - 2026-06-28

Branch: `codex/smp-v3-eight-thread-scaling`

Outcome: failed the cheap fixed-depth NPS gate and was rolled back.

## Baseline

Artifact: `docs/perf/nps_20260628T185336Z.tsv`

| Threads | Median time | Median NPS | Best moves |
|---:|---:|---:|---|
| 1 | 898.5 ms | 1,181,323 | `b1c3`, `g8f6`, `e4d5`, `c5c6` |
| 4 | 740.0 ms | 773,034 | `e2e4`, `g8f6`, `e4d5`, `c5c6` |
| 8 | 567.0 ms | 658,008 | `e2e4`, `g8f6`, `e4d5`, `c5c6` |

Baseline `Threads=8` was already faster than `Threads=4` by median fixed-depth time on this small suite, though with lower median NPS because the node counts differ across helper schedules.

## Attempt

Artifact: `docs/perf/nps_20260628T185907Z.tsv`

The attempted change made helper start depths unique up to eight threads and allowed the main search to adopt a helper result only when the helper returned a legal best move at a strictly deeper completed depth with a sane score.

| Threads | Median time | Median NPS | Best moves |
|---:|---:|---:|---|
| 1 | 827.0 ms | 1,226,620 | `b1c3`, `g8f6`, `e4d5`, `c5c6` |
| 4 | 567.0 ms | 899,184 | `e2e4`, `g8f6`, `e4d5`, `c5c6` |
| 8 | 590.5 ms | 749,253 | `g1f3`, `g8f6`, `e4d5`, `c5c6` |

The patch made `Threads=8` slightly slower than `Threads=4` on median time and changed the first fixed FEN best move. It did not justify an SF2200 game probe.

## Decision

The engine code change was reverted. Do not merge this SMP attempt.

Next engine tune should return to a narrower tactical/search change, such as qsearch quiet-check handling, or first improve the SMP measurement protocol before changing helper scheduling again.
