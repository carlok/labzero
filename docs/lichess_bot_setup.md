# Lichess Bot setup

Play labzero on Lichess using the **official** [lichess-bot](https://github.com/lichess-bot-devs/lichess-bot) bridge. Lichess expects this workflow for homemade UCI engines — see [How to create a Lichess bot](https://lichess.org/@/thibault/blog/how-to-create-a-lichess-bot/FuKyvDuB).

The labzero engine in `engine/` stays unchanged; lichess-bot spawns it as a UCI subprocess.

---

## Do not use your personal account

| Account | Use |
|---------|-----|
| **@carlok** (or any account with human games) | You — challenge the bot, blog, normal play |
| **New dedicated account** (e.g. `LabzeroBot`) | Engine only — upgraded to BOT via API |

Rules from the [lichess-bot wiki](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-create-a-Lichess-OAuth-token):

- Register a **new** Lichess account for the bot.
- **Never play a game** on it before upgrading (human or otherwise).
- BOT upgrade is **irreversible**.

There is no special “sign up as bot” page. You create a normal account, then upgrade it with lichess-bot.

---

## 1. Build labzero (host binary)

On macOS, Banksia and lichess-bot need the **native** binary:

```bash
./scripts/build-host-engine.sh
```

Engine path:

```text
/Users/you/.../labzero/target/release/labzero
```

Do **not** use `.cargo-target/release/labzero` — that is a Linux binary from Podman.

---

## 2. Install lichess-bot

```bash
git clone https://github.com/lichess-bot-devs/lichess-bot.git
cd lichess-bot
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp config.yml.default config.yml
```

Docs: [Install](https://github.com/lichess-bot-devs/lichess-bot/wiki/How-to-Install) · [Configure](https://github.com/lichess-bot-devs/lichess-bot/wiki/Configure-lichess-bot)

---

## 3. Create OAuth token

1. Log in to Lichess **as the new bot account** (not @carlok).
2. Create a token with **`bot:play`** scope:  
   https://lichess.org/account/oauth/token/create?scopes[]=bot:play
3. Copy the token — Lichess shows it **once**.

Put it in `config.yml`:

```yaml
token: "lip_xxxxxxxx"
```

Or set `LICHESS_BOT_TOKEN` in the environment.

Never commit tokens or `config.yml` with secrets.

---

## 4. Point lichess-bot at labzero

Edit `config.yml` — set `engine.dir` and `engine.name` to your labzero binary:

```yaml
engine:
  dir: "/Users/carlo/Documents/varie/hacks/games/labzero/target/release"
  name: "labzero"
  protocol: "uci"
  # uci_options:        # optional
  #   Threads: 1
```

See [Setup the engine](https://github.com/lichess-bot-devs/lichess-bot/wiki/Setup-the-engine).

---

## 5. Upgrade to BOT account (first run only)

From the `lichess-bot` directory, with venv active:

```bash
python3 lichess-bot.py -u
```

This calls the Lichess API to mark the account as **BOT**. Irreversible.

If you see errors about the account already having games, create a **fresh** account and start over.

Wiki: [Upgrade to a BOT account](https://github.com/lichess-bot-devs/lichess-bot/wiki/Upgrade-to-a-BOT-account)

---

## 6. Run the bot

```bash
python3 lichess-bot.py
```

- Challenge the bot from **@carlok** (or another account).
- Or enable matchmaking in `config.yml` to play other bots (see below).

---

## Getting a Lichess rating (bot vs bot)

There is no single permanent official bot league, but your bot gets a normal **Glicko-2 rating** from rated games.

| Method | Notes |
|--------|-------|
| **Human challenges** | [Online Bots](https://lichess.org/player/bots) page |
| **Matchmaking** | lichess-bot challenges other bots in a rating band |
| **Bot tournaments** | Arenas with “Bot players allowed” (e.g. [Leaderboard of BOTs](https://lichess.org/team/leaderboard-of-bots), [BOTS & Humans League](https://lichess.org/@/jeffforever/blog/bots--humans-league-every-tuesday-7-830pm-cet-started/M42WjL8g)) |

In `config.yml`, see `challenge`, `matchmaking`, `accept_bot`, `only_bot`. Lichess limits **bot-vs-bot** games to about **100 per day** per account.

Configure via [Configure lichess-bot](https://github.com/lichess-bot-devs/lichess-bot/wiki/Configure-lichess-bot) (matchmaking section).

---

## Sprint 5 gate — log live games

Complete **5+ games** without illegal moves, crashes, or API errors. Record in [lab_log.md](lab_log.md):

```markdown
## Lichess bot live test
- Date:
- Bot account: https://lichess.org/@/YourBotName
- Bridge: lichess-bot (official)
- Games: N
- Illegal moves: 0
- Crashes: 0
```

Update **Bot account URL** in [submission_package.md](submission_package.md).

---

## Architecture (recommended)

```text
Lichess HTTP API  <-->  lichess-bot  <-->  labzero (UCI subprocess)
```

---

## Optional: minimal labzero bridge (dev / CI only)

`lichess_bot/bot.py` is a **thin sprint stub** for local testing. It does **not** upgrade accounts, matchmake, or handle tournaments. Use it for dry-run only:

```bash
./scripts/podman/build-engine
LABZERO_ENGINE=/workspace/.cargo-target/release/labzero ./scripts/podman/bot --dry-run
```

For live Lichess play, use **lichess-bot** above.

| Feature | lichess-bot (official) | `lichess_bot/bot.py` (dev) |
|---------|------------------------|----------------------------|
| BOT upgrade (`-u`) | yes | no |
| Matchmaking / rating | yes | no |
| Tournaments | yes | no |
| Both colors | yes | white only (stub) |
| Dry-run / CI | via test harness | `./scripts/podman/bot --dry-run` |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| “Can't use this account as bot” | Account has played games — create a **new** account |
| Lichess says use lichess-bot | Expected — follow this doc, not a manual bot signup |
| Engine won't start | Use `target/release/labzero` (macOS), not `.cargo-target/` |
| Token invalid | Regenerate while logged in as bot account; scope must be `bot:play` |
| No games incoming | Challenge bot from another account, or enable `matchmaking` |

## References

- [lichess-bot](https://github.com/lichess-bot-devs/lichess-bot)
- [How to create a Lichess bot (Thibault)](https://lichess.org/@/thibault/blog/how-to-create-a-lichess-bot/FuKyvDuB)
- [Lichess Bot API](https://lichess.org/api#tag/Bot)
