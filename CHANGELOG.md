# Changelog

## 0.3.0-beta — 2026-06-20

- **Search:** quiescence, transposition table, null-move pruning, LMR, killer/history ordering, SEE
- **Eval:** tapered mg/eg PSTs, pawn structure, bishop pair, rook files, king safety, mobility
- Strength ladder re-measured vs Stockfish limited-Elo (see `docs/strength/ladder.md`)

## 0.2.0 — 2026-06-20

- Sprint roadmap: deep verification, gauntlet, human-play docs, Lichess bot bridge
- UCI `id version` in handshake
- UCI move replay via legal move resolution (fixes multi-game desync)
- Synchronous search in UCI loop for stability

## 0.1.0 — 2026-06-20

- Initial MVP: original Rust UCI engine, Podman CI, smoke verification
