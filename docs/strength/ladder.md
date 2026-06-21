# Strength ladder — host benchmark (paper data)

Method: `./scripts/host-benchmark.sh` — 32 games, alternating colors, Stockfish 18 with `UCI_LimitStrength` + `UCI_Elo`.

Performance Elo (approx, when score ≈ 50%): `SF_ELO + 400 * log10(p / (1-p))` where `p = (W + 0.5*D) / N`.

**Anchor protocol:** `TC_MODE=movetime TC_SEC=1 THREADS=1` (comparable across alpha/beta/gamma).

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

## Gamma / v0.5.0 (Phase C + D)

Search: aspiration, PV ordering, depth cap 64, check qsearch evasions, Lazy SMP; **TT ordering-only under movetime** (score cutoffs for `go depth` only).  
Eval: pawn structure, rook files, king safety (D3 weight tune).  
Time: soft stop, wtime/increment support.

**Anchor (1+0, v0.5.0):** bracket centre ≈ **SF@1900–2000**; **32-game confirm @ SF@2000 → perf Elo ≈ 1911** (37.5%, CI ≈ 1790–2030).

| SF_ELO | Score (W–L–D) | Score % | Perf Elo (approx) | Artifacts | Notes |
|--------|---------------|---------|-------------------|-----------|-------|
| 1320 | **14–0–2** | **93.8%** | — | `benchmark_20260621T084207Z` | 16-game regression |
| 1900 | **5–6–5** | **46.9%** | **≈ 1878** | `benchmark_20260621T064836Z` | 16-game probe |
| 2000 | **9–17–6** | **37.5%** | **≈ 1911** | `benchmark_20260621T091006Z` | **32-game confirm** |
| 2100 | **3–10–3** | **28.1%** | **≈ 1937** | `benchmark_20260621T073101Z` | 16-game probe |
| 2200 | _pending_ | — | — | — | probe interrupted |
| 2300 | _pending_ | — | — | — | not run |

Legacy compare (beta, same protocol): 1320 **93.8%**, 1800 **51.6%** (≈1812 perf), 2000 **34.4%** (≈1888 perf).

**Invalidated:** `benchmark_20260621T062854Z` (1–15 @ SF@1320) — pre–TT-fix run; do not use.

### Ablation (1+0 anchor, T=1)

| Version | SF 1320 | SF 1800 | SF 2000 |
|---------|---------|---------|---------|
| alpha v0.2.0 | 89.1% | — | 17.2% |
| beta v0.3.0-beta | 93.8% | 51.6% | 34.4% |
| gamma v0.5.0 | **93.8%** | **46.9%** (probe) | **37.5%** (32-game confirm, ≈1911 perf) |

**TC caveat:** Anchor rows use `TC_MODE=movetime TC_SEC=1 THREADS=1`. Performance Elo is project-relative vs Stockfish `UCI_LimitStrength`; not Lichess/CCRL/FIDE Elo. Spot-check rows (below) use different protocols and must not be merged into the ablation table.

### Measurement round (~2k bracket)

Three phases; artifacts land in `docs/strength/benchmark_<UTC>.{txt,pgn}` as usual.

| Phase | SF_Elo | Games | Purpose |
|-------|--------|-------|---------|
| **A — regression** | 1320 | 16 | illegal/smoke; expect ≥ **85%** |
| **B — bracket sweep** | **1900 2000 2100 2200 2300** | 16 each | find where score ≈ 50% (perf Elo) |
| **C — confirm** | levels with 20% < score < 80% | **32** | paper-grade rows (usually 2000 + 2100) |

**Perf Elo** when score ≈ 50% at SF@X: perf ≈ X. Between levels, use  
`SF_ELO + 400 * log10(p / (1-p))` with `p = (W + 0.5*D) / N`.

**One-shot (phases A + B):**

```bash
./scripts/build-host-engine.sh
export STOCKFISH=/opt/homebrew/bin/stockfish
./scripts/host-ladder-gamma.sh
```

**After reading Phase B `.txt` files — confirm at informative levels (32 games):**

```bash
./scripts/host-ladder-gamma.sh --confirm 2000 2100
# extend upward if 2100 still > ~55%:
# ./scripts/host-ladder-gamma.sh --confirm 2200
```

**Manual loop (same as beta protocol, higher ladder):**

```bash
./scripts/build-host-engine.sh
export STOCKFISH=/opt/homebrew/bin/stockfish

# regression
SF_ELO=1320 GAMES=16 TC_SEC=1 TC_MODE=movetime THREADS=1 ./scripts/host-benchmark.sh

# bracket (start high — skip 1800 unless sweep shows gap)
for ELO in 1900 2000 2100 2200 2300; do
  SF_ELO=$ELO GAMES=16 TC_SEC=1 TC_MODE=movetime THREADS=1 ./scripts/host-benchmark.sh
done

# confirm (adjust after Phase B)
for ELO in 2000 2100; do
  SF_ELO=$ELO GAMES=32 TC_SEC=1 TC_MODE=movetime THREADS=1 ./scripts/host-benchmark.sh
done
```

**How to record:** copy W–L–D and `labzero %` from each `benchmark_*.txt` footer into the table above; use basename without extension as Artifacts id. Update ablation row in `docs/paper_alpha.md` when Phase C confirm rows exist.

### Spot checks (other time controls — not anchor)

These rows use a **different protocol** than the 1+0 anchor table above. Do not merge into ablation without a TC label.

| Protocol | SF_ELO | Score (W–L–D) | Score % | Artifacts | Notes |
|----------|--------|---------------|---------|-----------|-------|
| `TC_SEC=10 movetime` | 2000 | _in progress_ | — | `benchmark_20260621T072038Z` | rapid-like depth probe (v0.5.0) |
| `TC_MODE=wtime TC_SEC=3 TC_INC=2` | 2000 | **7–6–3** | **53.1%** | `benchmark_20260621T132942Z` | perf **≈ 2022**; 0 illegal; supersedes pre-fix `063138Z` (0–8–0, 8 games) |
| `TC_SEC=1 THREADS=8` | 2000 | **2–9–5** | **28.1%** | `benchmark_20260621T095930Z` | SMP spot; perf **≈ 1837** (no gain vs T=1) |

```bash
SF_ELO=2000 GAMES=16 TC_SEC=10 TC_MODE=movetime THREADS=1 ./scripts/host-benchmark.sh
SF_ELO=2000 GAMES=16 TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=1 ./scripts/host-benchmark.sh
SF_ELO=2000 GAMES=16 TC_SEC=10 THREADS=4 ./scripts/host-benchmark.sh
```

Gauntlet smoke (Podman): **0 illegal** required after engine changes.
