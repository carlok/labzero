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
| Date | 2026-06-20 |
| SF_ELO | 2000 |
| SF_SKILL | 0 |
| SF_LIMIT | 1 |
| TC | 1+0 (~1s/move) |
| Games | 32 |
| Score (labzero) | **2 – 23 – 7** |
| Score % | **17.2%** |
| Performance Elo (§formula) | **≈ 1727** |
| Artifacts | `benchmark_20260620T192641Z.txt`, `.pgn` |

**Conclusion:** 2000 far too strong → dichotomy next at **1800**.

## Round 3 — SF UCI Elo 1800

| Field | Value |
|-------|--------|
| SF_ELO | 1800 |
| Status | **pending** |

| Score % | Next SF_ELO |
|---------|-------------|
| > 55% | 1900 |
| 40–55% | **estimate ≈ 1800** (this setup) |
| < 30% | 1700 |

## Dichotomy log

```
1320 → 89.1%  →  next 2000
2000 → 17.2%  →  next 1800  (perf Elo ≈ 1727)
1800 → ?      →  (optional round 3)
```

**Working estimate (1+0 bullet):** labzero ≈ **1700–1750** vs SF limited-Elo on this protocol.
