# Operator TODO — before public Lichess candidate

## Requires you (cannot be automated)

### Manual GUI play (Sprint 3 gate)

Play **10 full games** in a UCI GUI — see [docs/human_play_checklist.md](docs/human_play_checklist.md) and [docs/user_manual.md](docs/user_manual.md).

- [ ] Install UCI GUI (Banksia, Cute Chess, Lucas Chess, …)
- [ ] Build macOS GUI binary: `./scripts/build-host-engine.sh`
- [ ] Configure Banksia path: `./scripts/play-uci.sh` → `target/release/labzero` (not `.cargo-target/`)
- [ ] Play 10 games, fill checklist table, sign off
- [ ] Add summary to [docs/lab_log.md](docs/lab_log.md)

**Pass criteria:** zero illegal moves, zero crashes.

### Live Lichess bot (Sprint 5 gate)

Needs **your** BOT account and `LICHESS_TOKEN` — see [docs/lichess_bot_setup.md](docs/lichess_bot_setup.md).

- [ ] Create Lichess BOT token (`bot:play` scope)
- [ ] `cp lichess_bot/config.example.toml lichess_bot/config.toml`
- [ ] `export LICHESS_TOKEN="lip_..."` then `./scripts/podman/bot`
- [ ] Play 5+ games; log in [docs/lab_log.md](docs/lab_log.md)
- [ ] Set **Bot account URL** in [docs/submission_package.md](docs/submission_package.md)

### Go public (your call)

- [ ] Flip repo to public: `gh repo edit carlok/labzero --visibility public`
- [ ] Submit Lichess engine listing

### Lichess blog post (journey write-up)

Publish an article on your Lichess blog describing the labzero journey — motivation, original engine, verification gauntlets, bot bridge, lessons learned.

- [ ] Draft post (suggested outline: why labzero → MVP → sprints → perft/gauntlet evidence → play the bot → repo link when public)
- [ ] Publish at [lichess.org/@/carlok/blog](https://lichess.org/@/carlok/blog/)
- [ ] Link the post from [docs/submission_package.md](docs/submission_package.md) or README when repo goes public

---

## Automation can run without you (optional)

These do **not** replace GUI or Lichess gates; re-run before a public release if you want fresh artifacts.

| Task | Command | When |
|------|---------|------|
| Smoke CI | `./scripts/podman/ci` | After engine changes |
| Deep verify | `./scripts/podman/verify-deep` | ~7 min; weekly GHA cron |
| Gauntlet smoke | `./scripts/podman/gauntlet --smoke` | ~6 min |
| Full gauntlet | `./scripts/podman/gauntlet` | ~90 min |
| Release + hash | `./scripts/podman/release` | Before tagging |
| Bot preflight | `./scripts/podman/bot --dry-run` | Before live bot |

Weekly GHA (Sunday 06:00 UTC): `verify-deep` + `gauntlet-smoke` — no operator action.

---

## Quick reference

```bash
./scripts/podman/ci
./scripts/podman/verify-deep
./scripts/podman/gauntlet --smoke
./scripts/podman/bot --dry-run
./scripts/play-uci.sh
```