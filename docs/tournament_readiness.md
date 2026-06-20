# Tournament readiness

Checklist for CuteChess / Fastchess runs inside `labzero-dev` image.

- [x] Engine builds release binary via `./scripts/podman/build-engine`
- [x] UCI smoke passes (`./scripts/podman/verify-smoke`)
- [x] Deep verification available (`./scripts/podman/verify-deep`)
- [x] Perft crosscheck smoke passes
- [x] Self-play smoke via Fastchess (`./scripts/podman/tournament-smoke`)
- [x] Gauntlet script (`./scripts/podman/gauntlet`)
- [x] Gauntlet vs random bot (in gauntlet suite)
- [x] Gauntlet vs Stockfish at low depth (in gauntlet suite)
- [x] Opening EPD suite (`verifier/positions/openings.epd`)
- [x] Full 100-game gauntlet logged (run `./scripts/podman/gauntlet`)
- [ ] Human play QA checklist signed off (10 GUI games — operator)

Run tournament smoke:

```bash
./scripts/podman/tournament-smoke
./scripts/podman/gauntlet --smoke
./scripts/podman/gauntlet
```

Failure conditions: illegal move, crash, timeout, invalid `bestmove`, UCI desync, hang on `stop`.
