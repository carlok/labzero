# Submission package — labzero public candidate

## Engine identity

| Field | Value |
|-------|-------|
| Name | labzero |
| Version | 0.2.0 (see `engine/Cargo.toml`) |
| Protocol | UCI |
| License | MIT |
| Language | Rust (original core) |

## Originality statement

The chess-playing core in `engine/` is written for this project. It does not copy or derive from Stockfish, Leela Chess Zero, or other engine source code. See [originality_policy.md](originality_policy.md).

Independent verification uses `python-chess`, `cozy-chess`, and `shakmaty` in `verifier/` only — never inside the engine core.

## Reproduce verification

```bash
./scripts/podman/build-image
./scripts/podman/ci              # smoke gate
./scripts/podman/verify-deep     # deep verification
./scripts/podman/gauntlet --smoke  # 8-game tournament smoke
./scripts/podman/gauntlet          # 100+ game tournament
./scripts/podman/bot --dry-run     # dev bridge dry-run (see lichess_bot_setup.md for live)
./scripts/podman/release           # tagged binary + SHA256
```

## Evidence checklist

| Check | Command | Status |
|-------|---------|--------|
| Smoke CI | `./scripts/podman/ci` | PASS (2026-06-20) |
| Deep perft/fuzz | `./scripts/podman/verify-deep` | PASS — depth 6 startpos, 200-game fuzz, cozy/shakmaty |
| Gauntlet smoke | `./scripts/podman/gauntlet --smoke` | PASS — 8 games, 0 illegal moves |
| Gauntlet 100+ | `./scripts/podman/gauntlet` | PASS — 200 games, log `docs/gauntlet/gauntlet_20260620T105634Z.log` |
| Human play QA | [human_play_checklist.md](human_play_checklist.md) | Protocol automated PASS; 10 GUI games pending operator |
| Lichess bot (live) | [lichess-bot](https://github.com/lichess-bot-devs/lichess-bot) + host `target/release/labzero` | Pending — see [lichess_bot_setup.md](lichess_bot_setup.md) |
| Lichess dev dry-run | `./scripts/podman/bot --dry-run` | PASS — 20 plies local |

## Binary integrity

```
Version: 0.2.0
SHA256: 63b8173f183aaf0bfa1080216a8ebd0b5f68b4ed71a217e51665c50849f6167e
Path (Podman/CI): .cargo-target/release/labzero
Path (macOS GUI / lichess-bot): target/release/labzero
```

## Lichess listing (draft)

- **Engine name:** labzero
- **Version:** 0.2.0
- **UCI compliant:** yes — see [uci_supported.md](uci_supported.md)
- **Bot account URL:** _(pending — set after live bot games; e.g. `https://lichess.org/@/YourBotName`)_
- **Contact / maintainer:** [@carlok](https://github.com/carlok) — https://github.com/carlok/labzero

## Contact

- **Repository:** https://github.com/carlok/labzero
- **Maintainer:** https://github.com/carlok
