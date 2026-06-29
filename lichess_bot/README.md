# LabZero Lichess Bot Runner

Small native runner for playing the copied macOS LabZero binary on Lichess.
It runs in the foreground by default so you can see when the bot is playing.

## Local Files

- `bin/labzero-macos-aarch64-0.6.2` - copied engine binary, gitignored.
- `.env` - local Lichess token, gitignored.
- `config.toml` - optional local config override, gitignored.
- `local/` - logs and runtime files, gitignored.

Token file:

```bash
cp lichess_bot/.env.example lichess_bot/.env
```

Then edit `lichess_bot/.env`:

```bash
LICHESS_TOKEN=lip_xxxxx
```

The runner uses the Lichess Bot API, close to the official `lichess-bot`
architecture. The token must include:

- `bot:play`
- `challenge:write`
- `challenge:read`

`board:play` is not required by the Bot API runner, though it is harmless if
your token already has it. A token with `board:play`, `bot:play`,
`challenge:read`, and `challenge:write` is fine.

The dedicated account must also be upgraded to a Lichess BOT account before
live engine play. This is irreversible and should only be done for an account
that has never played human games:

```bash
set -a
source lichess_bot/.env
set +a
curl -X POST -H "Authorization: Bearer ${LICHESS_TOKEN}" \
  https://lichess.org/api/bot/account/upgrade
```

The official API example sends an empty body; this form is equivalent and also
works well:

```bash
curl -X POST -d '' -H "Authorization: Bearer ${LICHESS_TOKEN}" \
  https://lichess.org/api/bot/account/upgrade
```

If live play fails with `This endpoint can only be used with a Bot account`,
the account has not been upgraded yet.

If the binary was downloaded from GitHub on macOS, it may need local permission
approval before it can run:

```bash
xattr -d com.apple.quarantine lichess_bot/bin/labzero-macos-aarch64-0.6.2
chmod +x lichess_bot/bin/labzero-macos-aarch64-0.6.2
```

To rebuild the host engine and refresh the gitignored bot copies in one step:

```bash
./scripts/build-host-and-bot-engine.sh
```

This updates both `lichess_bot/bin/labzero` and the versioned platform binary
used by `config.toml`.

UCI options (set in `config.toml`, applied at engine start):

```toml
threads = 4   # Lazy SMP; matches host benchmark default
hash_mb = 64
```

## Test Locally

This does not contact Lichess. It starts the copied binary and plays 20 plies
against itself through UCI.

```bash
lichess_bot/run-local.sh --dry-run
```

Expected end:

```text
[IDLE] dry-run PASS (20 plies)
```

Unit tests and coverage are configured with pytest. They do not contact Lichess
or start a live game:

```bash
lichess_bot/.venv/bin/python -m pip install -r lichess_bot/requirements-dev.txt
lichess_bot/.venv/bin/python -m pytest
```

The coverage gate starts at 45% in `pyproject.toml`; raise it as new bot
behavior gets tests.

## Ladder Result Stats

Use this to count only completed rated standard 3+2 blitz results. Aborted and
unfinished games are ignored, even if Lichess includes them in broader "played"
counts.

```bash
lichess_bot/.venv/bin/python -m lichess_bot.ladder_stats --games 30 --block 10
```

Example output:

```text
window: 30 games 24W-1D-5L score=24.5/30 (81.7%) avg_opp=2010 games=old..new
round 1: 10 games ...
round 2: 10 games ...
round 3: 10 games ...
```

## Online Bot Rating Radar

Use the radar as a separate sidecar when you want to understand where LabZero
sits among currently online Lichess bots. It polls `GET /api/bot/online?nb=512`;
`nb=512` means "return up to 512 online bots". The script filters those users by
blitz rating, minimum games, and provisional status, then computes min, max,
average, median, quartiles, rating buckets, LabZero's percentile, and the nearest
stronger online bots.

One snapshot:

```bash
lichess_bot/run-radar.sh --once
```

Continuous sidecar, safe default polling every 60 seconds:

```bash
lichess_bot/run-radar.sh
```

Telegram summaries are optional and reuse the same notification config as live
games:

```bash
lichess_bot/run-radar.sh --notify --notify-interval-min 60
```

Snapshots are JSONL files under `lichess_bot/local/bot-radar/`, one file per UTC
day. This is intentionally separate from `run-local.sh`, so radar polling can
never interfere with move submission during a game.

Radar knobs in `config.toml`:

```toml
radar_interval_sec = 60
radar_min_blitz_games = 20
radar_allow_provisional = false
radar_notify_interval_min = 60
radar_output_dir = "lichess_bot/local/bot-radar"
```

## Open The Bot For Real Games

Use `--games N` to stop automatically after **N completed games** (no manual control file needed):

```bash
lichess_bot/run-local.sh --challenge-loop --unrated --games 4
lichess_bot/run-local.sh --challenge-loop --rated --games 4
```

Works with `--listen`, `--challenge`, and `--challenge-loop`. Not compatible with `--dry-run`.

Use this when you want the bot online and ready to accept compatible 3+2
challenges from humans or bots. Foreground logs show `PLAYING`, `MOVE`, and
`GAME END`.

```bash
lichess_bot/run-local.sh --listen --unrated
```

Rated games must be explicit:

```bash
lichess_bot/run-local.sh --listen --rated
```

While a game is active, do not close the terminal or the computer. The runner
prints a heartbeat while playing and requires a second Ctrl-C to force quit.

Incoming challenge policy is controlled in `config.toml`:

```toml
accept_from = "any"   # any, human, or bot
min_rating = 1200     # optional
max_rating = 2600     # optional
```

The default is `any`, so the bot can accept games from other people as well as
other bots.

## Challenge A Specific Player

Use this to challenge one or more users directly, then keep listening for the
resulting game.

```bash
lichess_bot/run-local.sh --challenge SomeUser --unrated
```

You can challenge humans or bots. Color is controlled by:

```toml
challenge_color = "random" # random, white, or black
```

## Challenge Other Bots

This mode looks at online Lichess bots, filters the blitz bucket, and challenges
one bot at a time. Defaults are conservative:

- standard chess only;
- 3+2 blitz only;
- one game at a time;
- non-provisional blitz rating;
- at least 20 blitz games;
- target rating from LabZero's current blitz rating to +150;
- while LabZero's rating is provisional, use `fallback_blitz_rating`.

Safe first run:

```bash
lichess_bot/run-local.sh --challenge-loop --unrated
```

Rated run:

```bash
lichess_bot/run-local.sh --challenge-loop --rated
```

The rating window is controlled by `config.toml` or `config.example.toml`:

```toml
min_blitz_games = 20
allow_provisional = false
target_rating_min_delta = 0
target_rating_max_delta = 150
fallback_blitz_rating = 1500
use_fallback_rating_when_provisional = true
max_challenge_attempts_per_cycle = 8
max_bot_challenges_per_day = 100
bot_challenge_quota_margin = 10
challenge_quota_file = "lichess_bot/local/challenge-quota.json"
challenge_control_file = "lichess_bot/local/challenge-control.json"
avoid_bots_file = "lichess_bot/local/avoid-bots.json"
challenge_interval_sec = 90
```

The runner uses `perfs.blitz.rating`, `perfs.blitz.games`, and
`perfs.blitz.prov` from the online-bot API. If Lichess rejects a candidate
because it already played too many bot-vs-bot games today, the runner skips
that bot until the server cooldown expires and tries another candidate.

Lichess also enforces bot-vs-bot daily limits on your account. The API does not
provide a "remaining games" endpoint, so the runner keeps a local UTC-day
counter and stops outgoing bot challenges before the known 100/day ceiling. The
local counter is incremented only when an outgoing challenged bot actually starts
a bot game. The default `100` with margin `10` stops at 90 counted bot games for
the UTC day.

To stop `--challenge-loop` cleanly after the current game, create or edit the
control file:

```json
{"stop_after_current_game": true}
```

When this flag is true, the runner keeps any active game going but does not send
a new challenge once idle. Set it back to `false` or remove the file to resume
outgoing challenges.

To avoid specific bots in both outgoing `--challenge-loop` selection and
incoming challenge accepts, create `lichess_bot/local/avoid-bots.json`:

```json
{
  "bots": ["SomeBot", "AnotherBot"]
}
```

A plain JSON list also works:

```json
["SomeBot", "AnotherBot"]
```

## Game Records, Chat, Draws, Resigns, Books

Finished games are written as PGN files by default:

```toml
pgn_directory = "lichess_bot/local/pgn"
```

PGN files include player names, colors, Lichess ids, titles, Elo ratings when
Lichess sends them, and a filename shaped like
`YYYYMMDD-HHMMSS_White_vs_Black_gameid.pgn`.

Live games use Lichess clock fields with a local move overhead cushion:

```toml
move_overhead_ms = 500
# max_movetime_ms = 5000
```

Basic player-chat greetings can use `{me}` and `{opponent}`:

```toml
hello = "Hi! I'm {me}. Good luck!"
goodbye = "Good game!"
```

Draw offers and resigns are available but disabled by default. Test them in
casual games before enabling them for rated play:

```toml
resign_enabled = false
resign_score = -1000
resign_moves = 3
offer_draw_enabled = false
offer_draw_score = 20
offer_draw_moves = 10
offer_draw_pieces = 10
accept_draw_enabled = true
accept_draw_losing_score = -100
accept_draw_equal_score = 25
accept_draw_equal_pieces = 8
accept_draw_min_ply = 40
accept_draw_low_time_sec = 10
accept_draw_low_time_score = 100
```

Incoming draw offers are accepted only when the policy says the position is
clearly worse, late and simplified enough to be nearly equal, or very low on
time while not clearly winning. Favorable positions play on.

Optional Polyglot books and local Syzygy tablebases can be configured. Empty
lists keep all play engine-only:

```toml
polyglot_books = []
polyglot_max_depth = 20
syzygy_paths = []
syzygy_max_pieces = 7
```

## Notifications

Game-start and game-end notifications are optional and disabled by default. To
send Telegram messages, set this in `lichess_bot/config.toml`:

```toml
notify_provider = "telegram"
```

Then put the secrets in `lichess_bot/.env`:

```bash
LABZERO_NOTIFY_TELEGRAM_TOKEN=123456:abc
LABZERO_NOTIFY_TELEGRAM_CHAT_ID=123456789
```

Notifications are best-effort: failures are logged and never stop a game.

You can test Telegram without starting a Lichess game:

```bash
lichess_bot/run-local.sh --notify-test --notify-test-text "LabZero test"
lichess_bot/run-local.sh --notify-test --notify-test-text "LabZero file test" \
  --notify-test-file docs/perf/README.md
```

If a human challenges the bot while it is already busy, the runner declines with
the Lichess `busy` reason and sends the operator a Telegram notification. Bot
challenges are not notified by default to avoid spam.

When Telegram is enabled, the runner also sends a small online-bot radar summary
shortly after each game ends. It uses the same blitz filters as `run-radar.sh`
and reports LabZero's current percentile among filtered online bots:

```toml
notify_radar_after_game = true
notify_radar_after_game_delay_sec = 2
```

## Game Chat Visibility

By default, greetings and good-game messages are sent to the Lichess `player`
chat room. Spectators/audience do not see that room. To make bot chat visible
while watching the game, configure:

```toml
chat_rooms = ["player", "spectator"]
```

Live games use the Bot API endpoints:

- `/api/stream/event`
- `/api/bot/game/stream/{gameId}`
- `/api/bot/game/{gameId}/move/{move}`
- `/api/bot/game/{gameId}/chat`
- `/api/bot/game/{gameId}/resign`
- `/api/challenge/{username}`
- `/api/challenge/{challengeId}/accept`
- `/api/challenge/{challengeId}/decline`

## Notes

- `--unrated` is the safe default for live use.
- `--rated` is always explicit on the command line.
- Keep `max_parallel_games = 1` unless the runner is deliberately redesigned.
- The copied binary is used to avoid conflicts with development builds in
  `target/release/`.
