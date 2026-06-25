# Strength ladder — host benchmark (paper data)

Method: `./scripts/host-benchmark.sh` — 32 games, alternating colors, Stockfish 18 with `UCI_LimitStrength` + `UCI_Elo`.

Performance Elo (approx, when score ≈ 50%): `SF_ELO + 400 * log10(p / (1-p))` where `p = (W + 0.5*D) / N`.

**Headline:** **≈2600** direct — **32-game** 3+2 wtime **T=4** vs SF@2600 (**56.2%**, **13–9–10**, **18/32** W-equiv, perf **≈2644**, `gate_sf2600_idtime_32g`, ID time fix on `codex/id-time-depth`). Prior SF@2500 headline: **67.2%** / **18–7–7** (`baseline_sf2500`). Not Lichess/CCRL/FIDE Elo.

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

Search: aspiration, PV ordering, depth cap 64, qsearch check evasions (all legal moves in check), Lazy SMP; **TT score cutoffs** under timed search (complete-node guard, post-Zobrist re-test).  
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
| `TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=1` | 2000 | **10–11–11** | **48.4%** | `benchmark_20260621T140403Z` | **32-game confirm**; perf **≈ 1989**; 0 illegal |
| `3+2 wtime THREADS=1` (post sharded TT) | 2000 | **5–8–3** | **40.6%** | `benchmark_20260621T151817Z` | 16-game SMP sanity; within noise of confirm |
| `3+2 wtime THREADS=4` (post sharded TT) | 2000 | **2–9–5** | **28.1%** | `benchmark_20260621T154803Z` | perf **≈ 1837**; sharded TT did not fix SMP |
| `3+2 wtime THREADS=1` (post Zobrist) | 2000 | **10–6–0** | **62.5%** | `benchmark_20260621T162932Z` | perf **≈ 2089**; 0 illegal |
| `3+2 wtime THREADS=4` (post Zobrist) | 2000 | **7–7–2** | **50.0%** | `benchmark_20260621T165748Z` | perf **≈ 2000**; SMP helps vs pre-Zobrist |
| `3+2 wtime THREADS=1` (Lazy SMP v2) | 2000 | **3–8–5** | **34.4%** | `benchmark_20260621T181146Z` | 16-game sanity; main unchanged; high variance |
| `3+2 wtime THREADS=4` (Lazy SMP v2) | 2000 | **7–5–4** | **56.2%** | `benchmark_20260621T184359Z` | 16-game spot; perf **≈ 2044** |
| `3+2 wtime THREADS=4` (Lazy SMP v2) | 2000 | **13–12–7** | **51.6%** | `benchmark_20260622T120949Z` | **32-game confirm**; perf **≈ 2011**; 0 illegal |
| `3+2 wtime THREADS=4` (+ null-move EP fix) | 2000 | **15–9–8** | **59.4%** | `benchmark_20260622T144847Z` | 32-game; perf **≈ 2066**; correctness fix |
| `3+2 wtime THREADS=4` (+ timed TT cutoffs) | 2000 | **18–9–5** | **64.1%** | `benchmark_20260622T160120Z` | 32-game; perf **≈ 2100**; **keep** |
| `3+2 wtime THREADS=4` | **2100** | **19–11–2** | **62.5%** | `benchmark_20260622T172332Z` | **32-game headline validation**; perf **≈ 2189** |
| `3+2 wtime THREADS=4` | **2200** | **4–8–4** | **37.5%** | `benchmark_20260622T181751Z` | 16-game probe; perf **≈ 2111** |
| `3+2 wtime THREADS=4` (+ qsearch-in-check) | 2000 | **16–7–9** | **64.1%** | `benchmark_20260622T185217Z` | 32-game; perf **≈ 2100**; **keep** |
| `3+2 wtime THREADS=4` (+ SEE sign fix) | 2000 | **18–9–5** | **64.1%** | `benchmark_20260623T044106Z` | 32-game; perf **≈ 2100**; matches v0.5.3 anchor |
| `3+2 wtime THREADS=4` (+ SEE sign fix) | **2200** | **5–3–8** | **56.2%** | `benchmark_20260623T055140Z` | 16-game probe; perf **≈ 2245** |
| `3+2 wtime THREADS=4` (+ SEE sign fix) | **2200** | **15–14–3** | **51.6%** | `benchmark_20260623T062210Z` | 32-game confirm; perf **≈ 2211** |
| `3+2 wtime THREADS=4` (+ history gravity/malus) | 2000 | **20–6–6** | **71.9%** | `benchmark_20260623T090318Z` | 32-game; perf **≈ 2163**; **23/32** W-equiv |
| `3+2 wtime THREADS=4` (+ history gravity/malus) | **2200** | **7–7–2** | **50.0%** | `benchmark_20260623T100753Z` | 16-game probe |
| `3+2 wtime THREADS=4` (+ history gravity/malus) | **2200** | **12–7–13** | **57.8%** | `benchmark_20260623T104424Z` | 32-game confirm; perf **≈ 2257**; **18.5/32** W-equiv |
| `3+2 wtime THREADS=4` (+ eval v2 passed/mobility) | **2200** | **12–1–3** | **84.4%** | `benchmark_20260623T134940Z` | 16-game keep gate; **13.5/16** W-equiv |
| `3+2 wtime THREADS=4` (+ eval v2 passed/mobility) | **2300** | **8–4–4** | **62.5%** | `benchmark_20260623T131324Z` | 16-game probe; **10/16** W-equiv |
| `3+2 wtime THREADS=4` (+ eval v2 passed/mobility) | **2300** | **19–5–8** | **71.9%** | `benchmark_20260623T150655Z` | **32-game**; **23/32** W-equiv |
| `3+2 wtime THREADS=4` (eval v2, direct bracket) | **2400** | **5–4–7** | **53.1%** | `benchmark_20260623T163900Z` | 16-game probe; **8.5/16** W-equiv |
| `3+2 wtime THREADS=4` (eval v2, direct bracket) | **2500** | **3–3–10** | **50.0%** | `benchmark_20260623T171507Z` | 16-game probe; **8/16** W-equiv |
| `3+2 wtime THREADS=4` (eval v2, direct bracket) | **2400** | **11–9–12** | **53.1%** | `benchmark_20260623T175115Z` | **32-game headline**; **17/32** W-equiv; **≈2400** claim |
| `3+2 wtime THREADS=4` (eval v2, direct bracket) | **2500** | **8–12–12** | **43.8%** | `benchmark_20260624T035947Z` | **32-game**; **14/32** W-equiv; PVS baseline |
| `3+2 wtime THREADS=4` (PVS v1, reverted) | **2400** | **7–7–2** | **50.0%** | `benchmark_20260624T052632Z` | 16-game keep; **8/16** W-equiv |
| `3+2 wtime THREADS=4` (PVS v1, reverted) | **2500** | **11–14–7** | **45.3%** | `benchmark_20260624T055916Z` | 32-game; **14.5/32** W-equiv |
| `3+2 wtime THREADS=4` (**v0.6.0** superhuman-band: magic BB, mailbox) | **2500** | **18–7–7** | **67.2%** | `baseline_sf2500` | **32-game headline**; perf **≈2624**; `host-gauntlet`; 0 illegal |
| `3+2 wtime THREADS=4` (+ SPSA s2 params, **rollback**) | **2500** | **11–10–11** | **51.6%** | `gate_sf2500_32g` | 32-game; perf **≈2511**; keep gate miss vs baseline |
| `3+2 wtime THREADS=8` (Lazy SMP v2) | 2000 | **11–15–6** | **43.8%** | `benchmark_20260622T131945Z` | 32-game diagnostic; perf **≈ 1956**; no gain vs T=4 |
| `TC_SEC=1 THREADS=8` | 2000 | **2–9–5** | **28.1%** | `benchmark_20260621T095930Z` | pre-shard SMP spot @ 1+0; perf **≈ 1837** |

```bash
SF_ELO=2000 GAMES=16 TC_SEC=10 TC_MODE=movetime THREADS=1 ./scripts/host-benchmark.sh
SF_ELO=2000 GAMES=16 TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=1 ./scripts/host-benchmark.sh
SF_ELO=2000 GAMES=16 TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4 ./scripts/host-benchmark.sh
SF_ELO=2000 GAMES=32 TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4 ./scripts/host-benchmark.sh
SF_ELO=2100 GAMES=32 TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4 ./scripts/host-benchmark.sh
SF_ELO=2200 GAMES=16 TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4 ./scripts/host-benchmark.sh
SF_ELO=2000 GAMES=32 TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=8 ./scripts/host-benchmark.sh
```

Gauntlet smoke (Podman): **0 illegal** required after engine changes.
