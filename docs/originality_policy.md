# Originality policy

## Engine core (`engine/`)

**Forbidden**

- Copying or closely imitating source from Stockfish, Leela Chess Zero, Ethereal, Komodo, Berserk, Crafty, or other engines
- Engine-derived NNUE weights, evaluation terms, search heuristics as code, or precomputed tables copied from existing engines
- Chess move-generation or evaluation crates in the engine core
- Using Stockfish **source** as a reference implementation

**Allowed**

- General algorithms: bitboards, negamax, alpha-beta, perft, move ordering, PSTs written for this project
- Public specs: chess rules, UCI, FEN, perft result tables (for testing only)

## Verifier and tooling (`verifier/`, `tournaments/`)

**Allowed and encouraged**

- `python-chess`, `cozy-chess`, `shakmaty` for independent cross-checks
- Stockfish **binary** as opponent/oracle (never source)
- CuteChess, Fastchess, fuzzing frameworks

The engine under test must stand alone; verifiers compare behavior, not shared code.
