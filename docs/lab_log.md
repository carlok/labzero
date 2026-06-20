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
