# Operator TODO — before public Lichess candidate

Automated sprints (S1–S6) are done locally. These steps need a human with a GUI and/or Lichess credentials.

## 1. Manual GUI play (Sprint 3 gate)

Play **10 full games** against labzero in a UCI GUI and fill in [docs/human_play_checklist.md](docs/human_play_checklist.md).

- [ ] Install a UCI GUI (Banksia, Cute Chess GUI, Lucas Chess, or similar)
- [ ] Build engine: `./scripts/podman/build-engine`
- [ ] Get engine path: `./scripts/play-uci.sh` (host path: `.cargo-target/release/labzero`)
- [ ] Configure GUI: UCI engine, absolute path to binary — see [docs/user_manual.md](docs/user_manual.md)
- [ ] Play 10 games with varied time controls (table in checklist)
- [ ] Record result, illegal moves, crashes, notes for each game
- [ ] Sign off in checklist (tester, date, engine version, PASS/FAIL)
- [ ] Add summary to [docs/lab_log.md](docs/lab_log.md)

**Pass criteria:** zero illegal engine moves, zero crashes across 10 games.

Protocol checks are already **automated PASS** (uci_protocol_tester, gauntlet TC suites).

---

## 2. Live Lichess bot (Sprint 5 gate)

Run **5+ rated or unrated games** on Lichess without illegal moves, crashes, or API errors.

- [ ] Upgrade Lichess account to **BOT** and create API token with `bot:play` scope  
      https://lichess.org/account/oauth/token/create?scopes[]=bot:play
- [ ] Copy config: `cp lichess_bot/config.example.toml lichess_bot/config.toml`
- [ ] Set token (never commit): `export LICHESS_TOKEN="lip_..."`
- [ ] Preflight: `./scripts/podman/bot --dry-run`
- [ ] Start bot: `./scripts/podman/bot`
- [ ] Play 5+ games (challenge bot from another account or accept challenges)
- [ ] Log results in [docs/lab_log.md](docs/lab_log.md) under `## Lichess bot live test`

Full steps: [docs/lichess_bot_setup.md](docs/lichess_bot_setup.md)

---

## 3. GitHub & listing polish

- [x] Create private repo: https://github.com/carlok/labzero (pushed `main`, CI badge points here)
- [x] GitHub **About**: description + topics (`chess`, `chess-engine`, `uci`, `rust`, `podman`, `lichess`, `lichess-bot`, `perft`, `fastchess`, `research`)
- [ ] Confirm GitHub Actions **smoke** job is green on first push
- [ ] Fill **Bot account URL** and **Contact / maintainer** in [docs/submission_package.md](docs/submission_package.md)
- [ ] When ready to go public: flip repo visibility, submit Lichess engine listing

---

## 4. Optional before going public

- [ ] Re-run release on tagged commit: `./scripts/podman/release`
- [ ] Re-run full gauntlet on release binary: `./scripts/podman/gauntlet` (~90 min)
- [ ] Weekly GHA jobs: verify-deep + gauntlet-smoke (cron Sunday 06:00 UTC)

---

## Quick reference

| Task | Command |
|------|---------|
| Daily smoke | `./scripts/podman/ci` |
| Deep verify | `./scripts/podman/verify-deep` |
| Gauntlet smoke | `./scripts/podman/gauntlet --smoke` |
| Bot dry-run | `./scripts/podman/bot --dry-run` |
| Release + SHA256 | `./scripts/podman/release` |
