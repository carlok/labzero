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

- **Bridge:** `lichess_bot/bot.py`, config.example.toml, `./scripts/podman/bot`
- **Dry-run:** PASS — 20 plies, zero illegal moves
- **Live 5+ games:** requires operator `LICHESS_TOKEN` — see lichess_bot_setup.md

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
