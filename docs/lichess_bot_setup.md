# Lichess Bot setup

## Prerequisites

1. Lichess account upgraded to **BOT** account: https://lichess.org/account/oauth/token/create?scopes[]=bot:play
2. API token with `bot:play` scope
3. labzero engine built: `./scripts/podman/build-engine`

## Configuration

```bash
cp lichess_bot/config.example.toml lichess_bot/config.toml
# Edit engine path if needed
export LICHESS_TOKEN="lip_..."
```

Never commit tokens or `config.toml` with secrets.

## Dry run (no network)

```bash
./scripts/podman/bot --dry-run
```

Simulates 20 plies locally — used for CI and preflight checks.

## Live bot

```bash
export LICHESS_TOKEN="your_token"
./scripts/podman/bot
```

Challenge the bot account from another Lichess user, or enable auto-challenge acceptance in Lichess bot settings.

## Sprint 5 gate

Complete **5+ games** on Lichess without illegal moves or crashes. Record in [lab_log.md](lab_log.md):

```
## Lichess bot live test
- Date:
- Games: N
- Illegal moves: 0
- Crashes: 0
```

## Architecture

```
Lichess HTTP API  <-->  lichess_bot/bot.py  <-->  labzero (UCI subprocess)
```

Engine core in `engine/` is unchanged.
