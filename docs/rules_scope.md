# Chess rules scope

Implemented in `engine/`:

- [x] Normal piece moves
- [x] Captures
- [x] Check, double check
- [x] Pins (legal move filtering)
- [x] Castling (including through-check prohibition)
- [x] En passant (including discovered-check cases)
- [x] Promotion and underpromotion
- [x] Checkmate and stalemate detection
- [x] Fifty-move halfmove counter
- [x] Threefold repetition tracking (for game termination)
- [x] FEN parse and generate

Not implemented:

- Opening books, tablebases, NNUE, resignation heuristics

## Perft verification (depth 6, verify-deep)

| Position | depth 6 nodes |
|----------|---------------|
| startpos | 119,060,324 |
| kiwipete | (depth 4: 4,085,603; depth 6 not in default set) |

Full cross-check at depths 1–6 on startpos, kiwipete, and all EPD fixtures in `verifier/positions/` via `./scripts/podman/verify-deep`. Independent Rust oracles: `cozy_crosscheck`, `shakmaty_crosscheck` (depths 1–4 on startpos).

## Known limits

- Weak search (~beginner strength); not tuned for Elo
- No ponder, no multi-PV, no syzygy
- Human-play GUI QA requires manual games (see `docs/human_play_checklist.md`)
