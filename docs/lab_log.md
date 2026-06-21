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

`TC_MODE=wtime TC_SEC=3 TC_INC=2 THREADS=1`, 16 games vs SF@2000:

| Score | % | Perf Elo (approx) | vs 1+0 confirm | Artifact |
|-------|---|-------------------|----------------|----------|
| **7–6–3** | **53.1%** | **≈ 2022** (CI ≈ 1840–2200) | **+15.6 pp** / ≈ **+110 Elo** | `benchmark_20260621T132942Z` |

0 illegal, 0 errors. Supersedes pre–`host-benchmark.sh` clock fix run **0–8–0** (`benchmark_20260621T063138Z`). Sample is 16 games — treat as spot check, not paper-grade confirm.
