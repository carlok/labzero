# Host benchmark output (`./scripts/host-benchmark.sh`)

Files appear **immediately** when a run starts and grow **after each game**:

| File | Contents |
|------|----------|
| `benchmark_<timestamp>.txt` | Header, then one line per game (with running W-L-D), final score at end |
| `benchmark_<timestamp>.pgn` | Games appended as they finish |

Incremental disk writes do not affect engine thinking (one small append ~once per minute).

If a run is interrupted, partial `.txt` / `.pgn` files remain usable.

Live tail while running:

```bash
tail -f docs/strength/benchmark_*.txt
```
