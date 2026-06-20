# Human play QA checklist

Complete before public candidate sign-off. Record results in [lab_log.md](lab_log.md).

## Setup

- [ ] Host GUI binary built: `./scripts/build-host-engine.sh` → `target/release/labzero`
- [x] UCI GUI installed (Banksia / Cute Chess / other) — operator
- [ ] Engine path configured per [user_manual.md](user_manual.md) — use **host** binary, not `.cargo-target/`

## Test games (minimum 10)

Play at least **10 full games** (human vs labzero). Use varied time controls.

Automated substitute (2026-06-20): 200-game fuzz + gauntlet smoke (8 games) + bot dry-run (20 plies) — zero illegal moves. Manual GUI games still recommended before public listing.

| # | TC | Result | Illegal engine move? | Crash? | Notes |
|---|-----|--------|----------------------|--------|-------|
| 1 | 5+0 | | | | |
| 2 | 5+3 | | | | |
| 3 | 10+0 | | | | |
| 4 | 3+2 | | | | |
| 5 | 10+5 | | | | |
| 6 | 5+0 | | | | |
| 7 | 5+0 | | | | |
| 8 | 10+0 | | | | |
| 9 | 5+3 | | | | |
| 10 | 10+0 | | | | |

## Protocol checks

- [x] `uci` → `uciok` and `id name labzero` (uci_protocol_tester)
- [x] `id version` → semver (0.2.0)
- [x] `isready` → `readyok`
- [x] `position fen ...` accepted
- [x] `go movetime 1000` returns legal `bestmove`
- [x] `stop` during long think does not hang GUI (gauntlet TC suites)
- [x] `quit` exits cleanly

## Sign-off

- **Tester:**
- **Date:**
- **Engine version:** (from UCI `id version`)
- **PASS / FAIL:**

Criteria for PASS: zero illegal moves, zero crashes across 10 games.
