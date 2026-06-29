# LabZero Lichess Live Median Note

Date: 2026-06-29

## Median-Band Milestone

LabZero reached the filtered online-bot median band in live rated Lichess blitz.

Telegram radar after a game reported:

- own blitz: **2077**
- filtered online bots: **279**
- percentile: **50.2th**
- above: **139**
- at-or-below LabZero: **140**
- median / average: **2077.0 / 2096.8**
- nearest stronger: AetherBot 2087, hummus-bot 2098, mate1-bot 2101

This is live Lichess bot-blitz evidence only. It is not CCRL, FIDE, universal engine Elo, or a Stockfish limited-Elo claim.

After the completed 8-game block, the public account snapshot was:

- blitz rating: **2072**
- blitz games: **95**
- rating deviation: **45**
- account record: **65W-22D-29L** overall, **102** rated games

## Recent Live Windows

From local PGNs under `lichess_bot/local/pgn/`, excluding exported duplicate PGNs:

| Window | Score | Percent | Avg Opponent | Terminations |
|---|---:|---:|---:|---|
| Last 8 | 4W-1D-3L | 4.5/8, 56.2% | 2088.6 | 7 mate, 1 draw |
| Last 16 | 10W-2D-4L | 11/16, 68.8% | 2072.9 | 13 mate, 2 draw, 1 resign |
| Last 24 | 13W-3D-8L | 14.5/24, 60.4% | 2074.3 | 20 mate, 3 draw, 1 resign |
| Last 32 | 17W-5D-10L | 19.5/32, 60.9% | 2073.6 | 26 mate, 5 draw, 1 resign |

The live signal is now positive and stable enough to study failures, not to chase speculative engine changes.

## Latest Loss/Draw Triage

| Game | Result | Opponent | Plies | Classification | Notes |
|---|---|---:|---:|---|---|
| `7CrGKOLC` | Loss | PlayMarius 2102 | 62 | Tactical blunder / king safety | LabZero accepted a sharp Scandinavian-like king attack. The decisive sequence was around `23. Bf4 Qxf4`, `25...Qxe2+`, and `28...Rxg4+`, ending in mate on `31...Qh3#`. This is a short tactical/king-safety failure, not time/protocol. |
| `kftZR0XO` | Loss | AetherBot 2087 | 122 | Endgame conversion/defense | LabZero reached a long rook/minor-piece endgame where Black's passed a-pawn and activity dominated. After `46...a1=Q 47.Rxa1 Rxa1`, the game became a practical conversion problem and ended in mate. |
| `3FzDGI0y` | Loss | PlayMarius 2096 | 209 | Endgame conversion/defense | Very long game. LabZero survived into a queen/endgame phase but failed to neutralize White's queen and king activity. The late collapse included `100.Qxd1`, then queen checks and mate on `105.Qe7#`. |
| `RG8FAhT9` | Draw | Hyperopic 2083 | 66 | Repetition/draw policy | LabZero had a small material edge, then repeated with rook checks/moves: `30.Rh6+`, `31.Rh5+`, `32.Rh6+`, `33.Rh5`. The exported PGN reports normal draw. This is a possible avoidable-draw case, but only one fresh example in the latest set. |

## Decision

Two of the three latest losses are long endgame conversion/defense failures. The next engine branch should therefore be:

`codex/endgame-practicality-v1`

Do not start with qsearch quiet checks or broad search changes from this evidence. The better first step is to extract one reproducible endgame regression from `kftZR0XO` or `3FzDGI0y`, then test a narrow improvement around practical king activity, passed-pawn handling, and queen/pawn conversion.

The draw in `RG8FAhT9` should be tracked, but it is not yet enough to reopen root draw policy by itself.

## Next Recommended Block

If no engine branch is started immediately, run one more controlled block:

```bash
env LABZERO_ROOT_POLICY=raw ./lichess_bot/run-local.sh --challenge-loop --rated --closest-superior --games 8
```

After that block, compare the loss/draw family counts again before changing engine code.
