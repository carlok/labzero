# LabZero Strengthening Plan

## Purpose

Improve LabZero's playing strength without weakening the properties that make the experiment useful: original engine code, legal move generation, UCI compatibility, repeatable verification, and honest strength reporting.

Each iteration should be small enough to judge on its own. A change is only worth keeping if it has a clear expected strength mechanism, passes the required legality and protocol gates, and either improves measured behavior or gives useful negative evidence.

## Ground Rules

- Do not copy source, tables, weights, or engine-specific implementations from Stockfish, Leela, Ethereal, Berserk, Crafty, or any other chess engine.
- Public chess-programming concepts are allowed: bitboards, alpha-beta, quiescence search, transposition tables, pruning, move ordering, FEN, UCI, perft, and standard evaluation ideas.
- Use other engines only as opponents, validators, or comparison targets. Stockfish source is not a reference implementation for LabZero.
- Prefer one narrow change per iteration. Each change must record:
  - expected strength mechanism;
  - files likely touched;
  - falsifiable test or benchmark;
  - rollback condition.
- Do not present Stockfish limited-Elo as a universal rating, Lichess rating, CCRL rating, or official Elo.

## Current Baseline

LabZero already has a working Rust UCI engine with legal move generation, FEN support, make/unmake, repetition and fifty-move draw handling, and a verification harness.

The current search already includes iterative deepening, alpha-beta, quiescence search, transposition-table cutoffs, aspiration windows, PV/TT move ordering, null move pruning, late move reduction, killer/history heuristics (including bounded history gravity and quiet malus on beta cutoffs), SEE-based capture ordering, check extensions, and Lazy SMP with a shared transposition table.

The current evaluation already includes material, tapered piece-square tables, bishop pair, pawn-structure terms, rook file bonuses, king-safety terms, **passed-pawn bonuses**, and **piece mobility**. The current UCI path supports `Hash`, `Threads`, `OwnBook`, `go depth`, `go movetime`, and clock-style `wtime/btime/winc/binc` input.

**Package v0.6.0** (magic bitboards + mailbox on `main`). ~~Headline strength **≈2600**~~ **Withdrawn in v0.6.2 retag** — legacy rows used freshclock synthetic gauntlet, not real wtime. See `docs/strength/ladder.md`.

**Next step:** NNUE bet — self-play + `host-nnue-train.py`, gate vs SF@2600 (`host-sprint-nnue.sh` / `host-sprint-gate.sh`).

## Phase 1: Measurement Before Tuning

Goal: establish a clean baseline before changing strength code.

- Build the current host engine and run the gamma ladder rows already listed in `docs/strength/ladder.md`.
- Use the anchor protocol unless intentionally testing a separate scenario: `TC_MODE=movetime TC_SEC=1 THREADS=1`.
- Record W-L-D, score percentage, illegal count, error count, and artifact basenames for every run.
- Confirm at least one informative 32-game row near the 50% score point before making a public strength claim.
- Roll back no code in this phase; instead, update the benchmark plan if the data shows the ladder is too low, too high, or too noisy.

Likely files touched: `docs/strength/ladder.md`, `docs/lab_log.md`, benchmark artifacts under `docs/strength/`.

Falsifiable check: a reader can rerun the documented commands and find matching artifact names and summarized rows.

## Phase 2: Search Stability And Tactical Strength

Goal: improve tactical reliability and search efficiency without touching move legality.

- Add or extend tactical regression positions before changing search behavior. Start with missed captures, hanging queens, simple mates, and qsearch horizon cases visible in ladder PGNs.
- Tune one search mechanism at a time: aspiration behavior, LMR safety, null-move conditions, qsearch move set, TT replacement, or move ordering weights.
- For each change, compare fixed-depth node counts and best moves on the tactical set before running ladder games.
- Keep changes only if they preserve legal play and improve either tactical results, node efficiency, or ladder score without introducing time losses.

Likely files touched: `engine/src/search.rs`, `engine/src/tt.rs`, `engine/src/see.rs`, tactical fixture files under `verifier/positions/` if new positions are added.

Falsifiable check: tactical smoke positions should show the expected best move or score trend, and the host ladder should not regress at the latest confirmed bracket.

Rollback condition: revert any search change that causes illegal moves, protocol failures, obvious tactical regressions, unstable scores in repeated fixed-depth tests, or worse confirmed ladder performance.

## Phase 3: Time Management And UCI Robustness

Goal: make LabZero spend time more predictably under real UCI clocks.

- Test `go movetime`, `go depth`, and clock-style `go wtime btime winc binc` separately.
- Improve time allocation only after recording current behavior at fast bullet settings and at a slower spot-check such as `TC_MODE=wtime TC_SEC=3 TC_INC=2`.
- Preserve panic reserve behavior and avoid starting a new iterative-deepening depth when the previous iteration makes a timeout likely.
- Keep UCI output parseable: `bestmove` must always be emitted for legal non-terminal positions, and `info` lines must remain valid.

Likely files touched: `engine/src/time.rs`, `engine/src/uci.rs`, `engine/src/smp.rs`, UCI verifier scripts if new protocol cases are added.

Falsifiable check: UCI protocol tests and tournament smoke complete without time forfeits, missing `bestmove`, or malformed output.

Rollback condition: revert any time change that increases losses by timeout, hangs on `stop`, fails to emit `bestmove`, or weakens the confirmed ladder row at the same settings.

## Phase 4: Evaluation Improvements

Goal: improve cheap positional judgment while keeping evaluation original, simple, and measurable.

- Tune existing terms before adding many new ones: pawn structure, rook files, king safety, bishop pair, and tapered PST phase.
- Add new eval terms only when a PGN review or tactical/endgame fixture shows a repeated weakness. Candidate areas are mobility, passed pawns, king tropism, simple outposts, and endgame king activity.
- Keep evaluation deterministic and fast. Any new term should be inspectable in a small position and cheap enough not to erase search depth.
- Validate with targeted positions first, then ladder games.

Likely files touched: `engine/src/eval.rs`, eval-focused tests in `engine/src/eval.rs`, optional EPD fixtures if they are used for acceptance.

Falsifiable check: targeted positions should move in the expected score direction, unit tests should cover the term, and ladder score should not regress after confirmation.

Rollback condition: revert any eval term that is hard to explain, slows search enough to lose depth at the anchor protocol, or improves one hand-picked position while worsening the confirmed ladder.

## Phase 5: Benchmark Reporting

Goal: make strength claims easy to audit and hard to overstate.

- Keep `docs/strength/ladder.md` as the main strength ledger.
- Record alpha, beta, and gamma rows separately. Do not merge hypotheses with confirmed results.
- For every row, include opponent setting, game count, time control, threads, W-L-D, score percentage, approximate performance only when appropriate, and artifact basename.
- Add a short caveat near every table: Stockfish limited-Elo is a project-relative benchmark, not Lichess, CCRL, FIDE, or universal Elo.
- Prefer broader opponent coverage after the gamma ladder is confirmed: add a few weak open-source engines as separate comparison rows rather than replacing the Stockfish ladder.

Likely files touched: `docs/strength/ladder.md`, `docs/paper/labzero_lichess_blog_draft.md` only if public wording needs adjustment, benchmark scripts only if reporting gaps require script changes.

Falsifiable check: every public claim points to a specific artifact or is explicitly marked pending.

Rollback condition: remove or downgrade any claim that cannot be traced to logs, PGNs, or a documented command.

## Acceptance Criteria

Use this verification ladder for future implementation work:

- Always run `cargo test --manifest-path engine/Cargo.toml`.
- For docs or scripts only, no engine verification is required beyond relevant command inspection.
- For search, eval, or time changes, also run `./scripts/podman/verify-smoke` and `./scripts/podman/tournament-smoke`.
- For move generation, make/unmake, hashing, repetition, FEN, or legality changes, also run `./scripts/podman/verify-deep`.
- For strength claims, run the host ladder at the smallest useful sample first, then confirm with 32 games at informative Stockfish limited-Elo levels.

An iteration is accepted only when:

- originality constraints are still satisfied;
- required tests pass;
- illegal moves and protocol errors remain at zero in the relevant tournament or ladder run;
- the result is recorded with W-L-D, score percentage, illegal/errors, and artifact names;
- any rating language stays scoped to the exact benchmark protocol.
