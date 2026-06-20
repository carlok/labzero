# Strength ladder — host benchmark (paper data)

Method: `./scripts/host-benchmark.sh` — 32 games, alternating colors, ~1s/move per side, Stockfish 18 with `UCI_LimitStrength` + `UCI_Elo`.

Performance Elo (approx, when score ≈ 50%): `SF_ELO + 400 * log10(p / (1-p))` where `p = (W + 0.5*D) / N`.

## Alpha v0.2.0

| SF_ELO | Score (W–L–D) | Score % | Perf Elo (approx) | Artifacts |
|--------|---------------|---------|-------------------|-----------|
| 1320 | 27–2–3 | 89.1% | — | `benchmark_20260620T184517Z` |
| 2000 | 2–23–7 | 17.2% | ≈ 1727 | `benchmark_20260620T192641Z` |

**Alpha bracket (1+0):** ≈ **1700–1750** vs SF limited-Elo.

## Beta v0.3.0-beta (B1–B3)

Search: qsearch, TT (move ordering), null move, LMR, killer/history, SEE.  
Eval: tapered mg/eg PSTs, bishop pair.

| SF_ELO | Score (W–L–D) | Score % | Perf Elo (approx) | Artifacts |
|--------|---------------|---------|-------------------|-----------|
| 1320 | **28–0–4** | **93.8%** | — | `benchmark_20260620T214301Z` |
| 1800 | **14–13–5** | **51.6%** | **≈ 1812** | `benchmark_20260620T221648Z` |
| 2000 | **10–20–2** | **34.4%** | **≈ 1888** | `benchmark_20260620T230310Z` |

### Ablation (paper)

| Version | SF 1320 | SF 1800 | SF 2000 |
|---------|---------|---------|---------|
| alpha v0.2.0 | 89.1% | — | 17.2% |
| beta v0.3.0-beta | **93.8%** | **51.6%** | **34.4%** |

**Beta bracket (1+0):** ≈ **1800–1900** on this protocol (+~150–200 vs alpha at SF@2000).

Gauntlet smoke (Podman, beta): **0 illegal** — `gauntlet_20260620T205728Z.log`.
