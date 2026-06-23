# Lab log

Chronological record of changes, test runs, failures, and limitations.

## Bootstrap

- Initial repository skeleton with Podman-first workflow.
- Engine: original Rust UCI implementation with full movegen, negamax search, and verifier tooling.
- `./scripts/podman/ci`: **PASS** (fmt, clippy, tests, verify-smoke, tournament-smoke).

## CI run 2026-06-20T08:37:48Z

- **Result:** FAIL
- **Failures:** cargo fmt --check cargo clippy
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-20T08:38:26Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-20T10:25:49Z

- **Result:** FAIL
- **Failures:** cargo fmt --check
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-20T10:26:20Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`

## Sprint 1 — Hard verification (2026-06-20)

- **Result:** PASS
- **Command:** `./scripts/podman/verify-deep`
- Perft depth 1–6 (startpos, kiwipete, all EPD fixtures)
- 200-game random fuzz (seed=42)
- Legality oracle: 26 positions
- cozy_crosscheck + shakmaty_crosscheck depths 1–4 on startpos

## Sprint 2 — Gauntlet (2026-06-20)

- **Smoke:** PASS — `./scripts/podman/gauntlet --smoke` (8 games, 0 illegal moves)
- **Full:** PASS — `./scripts/podman/gauntlet --games 100` — 200 games aggregate (4×50), 0 illegal moves/crashes; log: `docs/gauntlet/gauntlet_20260620T105634Z.log`

## Sprint 3 — Human play (2026-06-20)

- **Docs:** user_manual.md, human_play_checklist.md, play-uci.sh
- **UCI:** `id version 0.2.0` in handshake
- **Automated protocol QA:** PASS (uci_protocol_tester, gauntlet TC)
- **Manual 10-game GUI checklist:** pending operator (see human_play_checklist.md)

## Sprint 4 — Ops / release (2026-06-20)

- **Result:** PASS
- **Command:** `./scripts/podman/release`
- **Version:** 0.2.0
- **SHA256:** `63b8173f183aaf0bfa1080216a8ebd0b5f68b4ed71a217e51665c50849f6167e`
- CHANGELOG.md, submission_package.md, panic logging to stderr

## Sprint 5 — Lichess bot (2026-06-20)

- **Bridge (live):** [lichess-bot](https://github.com/lichess-bot-devs/lichess-bot) + host `target/release/labzero`
- **Dev stub:** `lichess_bot/bot.py`, `./scripts/podman/bot --dry-run`
- **Dry-run:** PASS — 20 plies, zero illegal moves
- **Live 5+ games:** pending — see [lichess_bot_setup.md](lichess_bot_setup.md)

## Sprint 6 — Public candidate (2026-06-20)

- **GHA:** `.github/workflows/ci.yml` — smoke on push/PR; verify-deep + gauntlet-smoke weekly
- **README:** badges, quickstart, links to user manual + submission pack
- **Submission pack:** docs/submission_package.md (reviewer-ready except live Lichess URL)

## Release v0.2.0 2026-06-20T10:57:00Z

- **Binary:** `.cargo-target/release/labzero`
- **SHA256:** `63b8173f183aaf0bfa1080216a8ebd0b5f68b4ed71a217e51665c50849f6167e`
- **Version:** 0.2.0

## Release v0.2.0 2026-06-20T10:56:43Z

- **Binary:** `.cargo-target/release/labzero`
- **SHA256:** `63b8173f183aaf0bfa1080216a8ebd0b5f68b4ed71a217e51665c50849f6167e`
- **Version:** 0.2.0

## CI run 2026-06-20T12:25:21Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`

## Host benchmark round 2 (2026-06-20)

- **SF UCI Elo:** 2000, 1+0, 32 games
- **Score (labzero):** 2–23–7 (17.2%)
- **Performance Elo (approx):** 1727
- **Illegal / errors:** 0
- **Artifacts:** `docs/strength/benchmark_20260620T192641Z.txt`, `.pgn`

## Beta v0.3.0-beta ladder (2026-06-20)

- **Engine:** qsearch, TT, null move, LMR, SEE, tapered eval
- **1320:** 28–0–4 (93.8%) — `benchmark_20260620T214301Z`
- **1800:** 14–13–5 (51.6%) — `benchmark_20260620T221648Z`
- **2000:** 10–20–2 (34.4%) — `benchmark_20260620T230310Z`
- **Gauntlet smoke:** PASS, 0 illegal

## CI run 2026-06-20T20:37:54Z

- **Result:** FAIL
- **Failures:** cargo fmt --check cargo clippy
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-20T20:40:58Z

- **Result:** FAIL
- **Failures:** cargo clippy cargo test build engine verify smoke tournament smoke
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-20T20:41:18Z

- **Result:** FAIL
- **Failures:** cargo clippy cargo test build engine verify smoke tournament smoke
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-20T20:41:47Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-20T21:42:59Z

- **Result:** FAIL
- **Failures:** cargo clippy
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-20T21:43:34Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-21T05:37:09Z

- **Result:** FAIL
- **Failures:** cargo fmt --check cargo clippy
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-21T05:37:40Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`

## Phase C — gamma v0.4.0 (2026-06-21)

- **Search:** depth cap 64, aspiration, PV ordering, root make/unmake, check qsearch evasions; **TT ordering-only under movetime** (score cutoffs reverted after ladder blunders)
- **Time:** soft stop before new ID, panic reserve, wtime/increment allocation
- **UCI:** `info depth score cp nodes nps time`, options `Hash`, `Threads`, `OwnBook`/`BookFile`
- **Eval:** pawn structure, rook files, king safety enabled
- **SMP:** Lazy SMP (Threads 1–8, shared thread-safe TT)
- **Book:** optional opening lines (`OwnBook` off by default)
- **CI:** `./scripts/podman/ci` **PASS** (13 unit tests)
- **Ladder:** anchor rows recorded in `docs/strength/ladder.md` (superseded by v0.5.0 re-measure)

## Phase D — strengthening v0.5.0 (2026-06-21)

- **D1a:** `verifier/positions/tactical.epd` (10 positions); fixed-depth tactical tests in `search.rs`
- **D1b:** TT `complete` flag; score cutoffs enabled for `go depth` only — **movetime remains ordering-only** (complete-guard cutoffs still regressed SF@1320 under 1s)
- **D1c:** LMR reduction `move_idx/10` (was `/8`); aspiration windows from depth 5 (was 4)
- **D2:** UCI protocol matrix; `ucinewgame` clears stop flag; wtime benchmark fix in `host-benchmark.sh`
- **D3:** eval weight tune — doubled pawn penalty 10→8, isolated 8→6, rook file 12→10
- **CI:** `./scripts/podman/ci` **PASS** (16 unit tests); gauntlet smoke **0 illegal**
- **Ladder (1+0 anchor):** SF@1320 **14–0–2 (93.8%)**; SF@2000 **9–17–6 (37.5%, 32-game confirm, ≈1911 perf)** — 0 illegal; see `docs/strength/ladder.md`
- **Spot wtime 3+2 @ SF2000 (8 games, pre-harness-fix):** **0–8–0** — superseded; see below (`benchmark_20260621T063138Z`)

## Host benchmark — gamma anchor (2026-06-21)

Post–TT-fix v0.5.0, `TC_MODE=movetime TC_SEC=1 THREADS=1`, 16 games each:

| SF_ELO | Score | % | Artifact |
|--------|-------|---|----------|
| 1320 | 15–1–0 | 93.8% | `benchmark_20260621T063529Z` |
| 1900 | 5–6–5 | 46.9% | `benchmark_20260621T064836Z` |
| 2000 | 5–8–3 | 40.6% | `benchmark_20260621T071050Z` |
| 2100 | 3–10–3 | 28.1% | `benchmark_20260621T073101Z` |

**Invalidated:** `benchmark_20260621T062854Z` (1–15 @ 1320) — TT score cutoffs under movetime (pre-fix).

## CI run 2026-06-21T06:25:39Z

- **Result:** FAIL
- **Failures:** cargo fmt --check cargo clippy verify smoke
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-21T06:27:18Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`

## CI run 2026-06-21T08:04:32Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`

## Host benchmark — paper confirm (2026-06-21)

Post–TT-fix **v0.5.0**, `TC_MODE=movetime TC_SEC=1 THREADS=1`:

| Phase | SF_ELO | Score | % | Perf Elo | Artifact |
|-------|--------|-------|---|----------|----------|
| Regression | 1320 | 14–0–2 | 93.8% | — | `benchmark_20260621T084207Z` |
| **Confirm** | **2000** | **9–17–6** | **37.5%** | **≈ 1911** (95% CI ≈ 1790–2030) | `benchmark_20260621T091006Z` |

**0 illegal**, **0 errors** on both runs.

Prior 16-game probes (same protocol): SF@1900 **46.9%**, SF@2100 **28.1%** — see `docs/strength/ladder.md`.

**Next:** SMP spot `THREADS=8` @ SF@2000 — **2–9–5 (28.1%, perf ≈ 1837)**; no gain vs T=1 confirm (`benchmark_20260621T095930Z`).

## SMP spot — Threads=8 (2026-06-21)

`TC_MODE=movetime TC_SEC=1 THREADS=8`, 16 games vs SF@2000:

| Score | % | Perf Elo (approx) | vs T=1 confirm | Artifact |
|-------|---|-------------------|----------------|----------|
| 2–9–5 | 28.1% | ≈ 1837 (CI ≈ 1660–2020) | **−9.4 pp** / ≈ **−74 Elo** | `benchmark_20260621T095930Z` |

0 illegal, 0 errors. CIs overlap — treat as negative spot result, not proven SMP regression.

## Spot blitz — wtime 3+2 @ SF@2000 (2026-06-21)

`TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=1`, vs SF@2000:

| Games | Score | % | Perf Elo (approx) | Artifact | Notes |
|-------|-------|---|-------------------|----------|-------|
| 16 (probe) | 7–6–3 | 53.1% | ≈ 2022 | `benchmark_20260621T132942Z` | superseded by 32-game confirm |
| **32 (confirm)** | **10–11–11** | **48.4%** | **≈ 1989** (95% CI ≈ 1860–2115) | `benchmark_20260621T140403Z` | **paper-grade blitz row** |

0 illegal, 0 errors on both runs. Supersedes pre–`host-benchmark.sh` clock fix **0–8–0** (`benchmark_20260621T063138Z`). Not comparable to 1+0 anchor (37.5%, ≈1911).

## Sharded TT + SMP spot — 3+2 (2026-06-21)

**Change:** `engine/src/tt.rs` — global `Mutex<Vec<_>>` replaced with **64-shard** table (per-shard mutex); API unchanged.

`TC_MODE=wtime TC_SEC=3 TC_INC=2`, 16 games vs SF@2000:

| Threads | Score | % | Perf Elo (approx) | vs 32g blitz confirm | Artifact |
|---------|-------|---|-------------------|----------------------|----------|
| 1 | 5–8–3 | 40.6% | ≈ 1934 | −7.8 pp (noise) | `benchmark_20260621T151817Z` |
| 4 | 2–9–5 | 28.1% | ≈ 1837 | **−20.3 pp** | `benchmark_20260621T154803Z` |

0 illegal, 0 errors. **T=1** in line with **48.4%** confirm; **T=4** still regressed (same score band as pre-shard `THREADS=8` @ 1+0). **Conclusion:** lock contention was not the sole bottleneck.

## Zobrist hash + SMP re-measure — 3+2 (2026-06-21)

**Change:** `engine/src/zobrist.rs` — deterministic Zobrist tables; `make_unmake.rs` incremental XOR on make (no full-board recompute); `compute_hash()` kept as oracle.

`TC_MODE=wtime TC_SEC=3 TC_INC=2`, 16 games vs SF@2000:

| Threads | Score | % | Perf Elo (approx) | vs post-shard T=4 | Artifact |
|---------|-------|---|-------------------|-------------------|----------|
| 1 | **10–6–0** | **62.5%** | **≈ 2089** | **+21.9 pp** vs shard T=1 | `benchmark_20260621T162932Z` |
| 4 | **7–7–2** | **50.0%** | **≈ 2000** | **+21.9 pp** vs shard T=4 | `benchmark_20260621T165748Z` |

0 illegal, 0 errors. **Decision:** keep Zobrist hash; **T=4 now even** on 3+2 (was 28.1%). Next SMP work: helper depth offset / split diversification for further gain.

## Lazy SMP v2 — helper start-depth diversification (2026-06-21)

**Change:** `search_with_info_from_depth(start_depth)` in `search.rs` — helpers skip shallow ID plies; aspiration gated on prior completed score (fixes cold-start when helper begins at depth 5). `smp.rs` — helpers cycle start depths **3, 4, 5**; main thread unchanged at depth 1.

`TC_MODE=wtime TC_SEC=3 TC_INC=2`, 16 games vs SF@2000:

| Threads | Score | % | Perf Elo (approx) | vs post-Zobrist | Artifact |
|---------|-------|---|-------------------|-------------------|----------|
| 1 | 3–8–5 | 34.4% | ≈ 1888 | −28.1 pp (noise; main path unchanged) | `benchmark_20260621T181146Z` |
| 4 | **7–5–4** | **56.2%** | **≈ 2044** | **+6.2 pp** vs post-Zobrist T=4 | `benchmark_20260621T184359Z` |

0 illegal, 0 errors. **Decision:** keep Lazy SMP v2 — T=4 **9/16 W-equivalent** (≥ keep threshold); beats post-Zobrist **7–7–2**.

### 32-game confirm — Lazy SMP v2 (2026-06-22)

`TC_MODE=wtime TC_SEC=3 TC_INC=2`, vs SF@2000:

| Threads | Score | % | Perf Elo (approx) | Notes | Artifact |
|---------|-------|---|-------------------|-------|----------|
| **4** | **13–12–7** | **51.6%** | **≈ 2011** | **paper-grade T=4 confirm**; ~even vs SF@2000 | `benchmark_20260622T120949Z` |
| 8 | 11–15–6 | 43.8% | ≈ 1956 | diagnostic; worse than T=4 | `benchmark_20260622T131945Z` |

0 illegal, 0 errors. **Headline:** **≈2010** on this protocol (32g T=4 confirm); 16g T=4 spot **≈ 2044** was high-variance.

## Null-move EP correctness (2026-06-22)

**Change:** `NullUndo` in `board.rs` — null move clears `ep_square` and EP hash XOR; `unnull_move` restores prior EP state. Fixes stale EP rights / wrong Zobrist key in null-move subtrees.

`TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4`, 32 games vs SF@2000:

| Score | % | Perf Elo (approx) | vs SMP v2 anchor | Artifact |
|-------|---|-------------------|------------------|----------|
| **15–9–8** | **59.4%** | **≈ 2066** | **+7.8 pp** vs 13–12–7 | `benchmark_20260622T144847Z` |

0 illegal, 0 errors. **Decision:** keep — correctness fix; tests + smoke pass.

## Timed TT score cutoffs re-enabled (2026-06-22)

**Change:** `search.rs` — remove `is_timed()` gate around `tt_cutoff`; safeguards unchanged (`complete`, depth, mate exclusion, partial-node no-store).

`TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4`, 32 games vs SF@2000:

| Score | % | Perf Elo (approx) | vs SMP v2 anchor (13–12–7) | Artifact |
|-------|---|-------------------|------------------------------|----------|
| **18–9–5** | **64.1%** | **≈ 2100** | **+12.5 pp** | `benchmark_20260622T160120Z` |

0 illegal, 0 errors. **Decision:** keep — **20.5/32** W-equivalent (≥ 16/32 threshold).

## Headline validation — SF@2100 direct (2026-06-22)

**Protocol:** `TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4`, vs limited Stockfish:

| SF_ELO | Games | Score | % | Perf Elo (approx) | Decision | Artifact |
|--------|-------|-------|---|-------------------|----------|----------|
| **2100** | 32 | **19–11–2** | **62.5%** | **≈ 2189** | **Keep headline ≈2100** (>60%) | `benchmark_20260622T172332Z` |
| 2200 | 16 | 4–8–4 | 37.5% | ≈ 2111 | probe (below 50% vs SF@2200) | `benchmark_20260622T181751Z` |

0 illegal, 0 errors on both runs.

## Qsearch-in-check fix (2026-06-22)

**Change:** `search.rs` `qsearch` — compute `in_check` before stand-pat; skip stand-pat in check; search all legal evasions (not noisy-only) until `QSEARCH_MAX`.

`TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4`, 32 games vs SF@2000:

| Score | % | Perf Elo (approx) | vs anchor (18–9–5) | Artifact |
|-------|---|-------------------|---------------------|----------|
| **16–7–9** | **64.1%** | **≈ 2100** | **20.5/32** W-equiv (≥ 18/32) | `benchmark_20260622T185217Z` |

0 illegal, 0 errors. **Decision:** keep.

## SEE capture-ordering sign fix (2026-06-23)

**Change:** `engine/src/see.rs` — `see_capture_value` returns positive for materially favorable captures and negative for losing ones (early return when no recapture; invert defender-stop path). Move-ordering callers unchanged. **No qsearch pruning** in this patch.

`TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4`:

| SF_ELO | Games | Score | % | Perf Elo (approx) | vs anchor | Artifact |
|--------|-------|-------|---|-------------------|-----------|----------|
| 2000 | 32 | **18–9–5** | **64.1%** | **≈ 2100** | **20.5/32** W-equiv (keep) | `benchmark_20260623T044106Z` |
| 2200 | 16 | **5–3–8** | **56.2%** | **≈ 2245** | probe (≥ 7.5/16) | `benchmark_20260623T055140Z` |
| 2200 | 32 | **15–14–3** | **51.6%** | **≈ 2211** | ~even vs SF@2200 | `benchmark_20260623T062210Z` |

0 illegal, 0 errors. **Decision:** keep — SF@2000 gate passed; SF@2200 improved vs pre-fix probe (4–8–4). README headline stays **≈2100**.

**Deferred:** qsearch SEE pruning — prior attempt regressed to **5–22–5** (`benchmark_20260622T205652Z`, rolled back) because pre-fix SEE sign was inverted.

## Qsearch SEE pruning retry (2026-06-23)

**Change (rolled back):** conservative qsearch SEE prune — margin **-250**, skip first qsearch ply (`qs_depth == 0`) and all in-check evasions; promotions/EP always kept.

`TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4`, 32 games vs SF@2000: **15–11–6** (56.2%, **18/32** W-equiv). 0 illegal, 0 errors. **Rollback** — below **19/32** gate (anchor **20.5/32**, `benchmark_20260623T044106Z`). Artifact: `benchmark_20260623T073759Z`.

## History gravity + quiet malus (2026-06-23)

**Change:** `search.rs` — bounded history updates (`HISTORY_MAX=16384`, `history_bonus(depth)` capped at 2048, gravity formula); on quiet beta cutoffs, positive gravity on cutoff move and negative gravity on earlier quiet non-cutoffs in the same ordered list. Killers unchanged.

`TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=4`:

| SF_ELO | Games | Score | % | Perf Elo (approx) | W-equiv | Artifact |
|--------|-------|-------|---|-------------------|---------|----------|
| 2000 | 32 | **20–6–6** | **71.9%** | **≈ 2163** | **23/32** (keep) | `benchmark_20260623T090318Z` |
| 2200 | 16 | **7–7–2** | **50.0%** | **≈ 2200** | **8/16** (probe) | `benchmark_20260623T100753Z` |
| 2200 | 32 | **12–7–13** | **57.8%** | **≈ 2257** | **18.5/32** (strong keep) | `benchmark_20260623T104424Z` |

0 illegal, 0 errors. **Decision:** keep — SF@2000 **+2.5 W-equiv** vs SEE-fix anchor; SF@2200 32g **18.5/32** (≥ 17/32 strong tier). **Headline revised to ≈2200** (README, ladder) from SF@2200 32g perf **≈ 2257**.

## CI run 2026-06-21T17:51:27Z

- **Result:** PASS
- **Command:** `./scripts/podman/ci`
