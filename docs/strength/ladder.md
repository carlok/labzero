# Strength ladder — host benchmark (paper data)

Method: `./scripts/host-benchmark.sh` — 32 games, alternating colors, ~1s/move per side, Stockfish 18 with `UCI_LimitStrength` + `UCI_Elo`.

Performance Elo (approx, when score ≈ 50%): `SF_ELO + 400 * log10(p / (1-p))` where `p = (W + 0.5*D) / N`.

## Round 1 — SF UCI Elo 1320

| Field | Value |
|-------|--------|
| Date | 2026-06-20 |
| SF_ELO | 1320 |
| SF_SKILL | 0 |
| SF_LIMIT | 1 |
| TC | 1+0 (~1s/move) |
| Games | 32 |
| Score (labzero) | **27 – 2 – 3** |
| Score % | **89.1%** |
| Artifacts | `benchmark_20260620T184517Z.txt`, `.pgn` |

**Conclusion:** 1320 far too weak → dichotomy next at **2000**.

## Round 2 — SF UCI Elo 2000

| Field | Value |
|-------|--------|
| SF_ELO | 2000 |
| Status | **running** (2026-06-20) |
| Log | `benchmark_*2000*.txt` in this folder |

After round 2:

| Score % | Next SF_ELO |
|---------|-------------|
| > 70% | 2400 |
| 40–60% | **estimate ≈ 2000** (this setup) |
| < 35% | 1800 |

## Dichotomy log

```
1320 → 89%  →  next 2000
2000 → ?     →  (fill after run)
```
