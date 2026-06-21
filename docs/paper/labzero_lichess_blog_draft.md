# LabZero: can a fast coding LLM build a chess engine from zero in one working day?

**Draft for a possible Lichess blog post.**

I spent a working day trying to build a chess engine from nothing.

Not a wrapper around Stockfish. Not a toy that only knows how the pieces move. A fresh Rust codebase with its own move generator, search, evaluation, UCI loop, tests, tournament scripts, and a written originality policy.

The question was simple:

> Can a fast coding LLM help build a legal, working chess engine from zero in less than one human working day?

The current answer is **LabZero**: a small original UCI chess engine that can play legal games, survive automated tournaments, and run through independent rule checks. It is weak by engine standards, but it is real enough to be tested by other tools.

Repository: <https://github.com/carlok/labzero>

## Why chess?

Chess is a useful target for this kind of experiment because it doesn't let the code bluff.

If the engine castles through check, that is wrong.
If en passant exposes the king and the engine allows it, that is wrong.
If the UCI protocol hangs, crashes, or returns an illegal move, that is wrong.

Many LLM demos are hard to judge because the output is subjective. A chess engine is different. The rules are formal, the protocol is documented, and the behavior can be checked from outside the codebase. That made it a good small laboratory for LLM-assisted programming.

I wasn't trying to make a strong engine in one day. I was trying to make a legal and externally checkable one.

## The constraint

The central rule was originality.

External tools were allowed for validation, tournament running, and comparison. The engine core wasn't allowed to copy Stockfish code, use a chess-engine crate, import existing evaluation tables, or reuse another engine's move generator.

That distinction matters. LabZero uses ordinary public ideas: bitboards, FEN, UCI, perft, alpha-beta, quiescence search, transposition tables, move ordering, and simple evaluation terms. Those are common chess-programming techniques. The constraint wasn't to pretend those ideas are new. The constraint was to implement a fresh engine core for this project and use other engines only as opponents or oracles.

There was another personal constraint. I have almost thirty years of software engineering experience, but I wasn't a Rust programmer when I started. That made Rust a useful choice: fast, safe, and unfamiliar enough that the LLM had to help with a lot of language mechanics while I kept control of the goal, the tests, and the quality bar.

The model used for the initial build wasn't the strongest frontier model I could find. It was Cursor's auto-speed coding model at the time, Composer 2.5. I wanted to know what a fast everyday coding assistant could do inside a normal engineering loop.

## What was built

LabZero is now a small Rust workspace with:

- An original engine core in `engine/`;
- Full legal move generation, including castling, promotion, underpromotion, en passant, check, mate, stalemate, fifty-move rule, and repetition tracking;
- FEN parsing and serialization;
- UCI support, including `uci`, `isready`, `position`, `go`, `stop`, `quit`, and options such as `Hash`, `Threads`, and `OwnBook`;
- Iterative search with alpha-beta, quiescence, a transposition table, null move pruning, late move reductions, killer/history ordering, SEE-based capture ordering, aspiration windows, and a simple Lazy SMP mode;
- A hand-written evaluation with material, tapered piece-square tables, bishop pair, pawn structure, rook file bonuses, and king safety;
- Podman scripts for reproducible build and verification;
- Independent Python and Rust verification tools using `python-chess`, `cozy-chess`, and `shakmaty`;
- Tournament scripts and host-side Stockfish ladder scripts.

That list makes the project sound more polished than it is. It's still a lab engine. The code is compact, the evaluation is basic, the search is young, and the strength numbers need more confirmation. But the engine isn't just a prompt artifact. It compiles, speaks UCI, plays games, and is checked by tools that weren't part of the engine core.

## Verification first

The most important part of the experiment wasn't asking the LLM to write chess code. The important part was making wrong chess code fail.

The repository has several gates:

- Unit tests for engine internals;
- Perft checks against known positions;
- Random-game fuzzing;
- Legality checks through `python-chess`;
- Cross-checks against independent Rust chess libraries;
- UCI protocol smoke tests;
- Tournament smoke and gauntlet scripts;
- Host-side Stockfish ladder runs that save text logs and PGNs.

The deeper verification path includes perft to depth 6, a 200-game random fuzzer, legality oracle checks, and Rust cross-checks. The tournament gauntlets are there for a different reason: to catch crashes, protocol failures, bad time handling, and illegal moves under game conditions.

That was the recurring lesson. The LLM could move quickly, but it needed a cage made of tests. Chess supplied a good cage.

## Strength, carefully stated

LabZero shouldn't be described with a single rating number.

The current strength notes come from a constrained host benchmark against Stockfish 18 with `UCI_LimitStrength` and `UCI_Elo`, usually 32 games per point, alternating colors, with a 1+0-style protocol. That is useful for tracking progress inside this project. But it isn't a Lichess rating, not a CCRL rating, and not a universal Elo claim.

The alpha engine was roughly in the 1700-1750 bracket on that specific protocol.

The beta version improved after adding quiescence search, transposition-table ordering, null move pruning, LMR, SEE, and tapered evaluation. In the recorded beta ladder it scored:

- 28-0-4 against Stockfish limited to 1320;
- 14-13-5 against Stockfish limited to 1800;
- 10-20-2 against Stockfish limited to 2000.

That put beta around 1800-1900 on this test. The gamma/v0.5.0 branch adds aspiration, time management, Lazy SMP, tuned structural eval, and a tactical regression suite. **All anchor ladder numbers use:** `TC_MODE=movetime TC_SEC=1 THREADS=1` against Stockfish with `UCI_LimitStrength`. That is project-relative performance Elo, not a Lichess or CCRL rating.

**Paper-grade anchor (2026-06-21):**

- **14–0–2** vs Stockfish limited to 1320 (93.8%, 16-game regression);
- **9–17–6** vs Stockfish limited to 2000 (37.5%, **32-game confirm**, `Threads=1`);
- performance Elo at SF@2000 (**T=1**): **≈ 1911** (95% CI roughly **1790–2030** on this protocol).

**Same opponent, Lazy SMP spot (16 games, not anchor):**

- **2–9–5** vs Stockfish limited to 2000 (`Threads=8`, 1+0 movetime);
- performance Elo **≈ 1837** (95% CI roughly **1660–2020**) — **lower** than the single-thread confirm, not higher. Intervals overlap, so this is a directional negative result, not a firm SMP penalty. Lazy SMP v1 at 1 s/move did not pay off on this run.

16-game bracket probes at SF@1900 (46.9%) and SF@2100 (28.1%) bracket the centre near **SF@1900–2000**. A **wtime 3+2** spot check (0–8, 8 games) stays in a separate table — not merged into the anchor ablation.

The fair version is:

> LabZero is an early, original, legal UCI engine. On the fixed 1-second-per-move anchor (**32 games**, `Threads=1`, vs SF@2000), performance is roughly **1910** vs limited Stockfish — about **+20 Elo** vs beta on the same opponent setting (34.4% → 37.5%), with **0 illegal** moves. Turning on **8 threads** on the same 1+0 protocol did **not** improve that number in a 16-game spot check (28.1%, perf ≈ **1840**).

That is less catchy than "LLM builds 2000 Elo engine in a day", but it is closer to the truth.

## What the LLM was good at

The coding assistant was strongest when the work was framed as small, checkable steps:

- Implement FEN;
- Generate legal moves;
- Add perft;
- Speak a subset of UCI;
- Make `go depth 2` return a legal move;
- Add a benchmark script;
- Make the tournament runner fail on illegal moves;
- Add quiescence, then test that obvious captures stop being missed.

It was weaker when the task was vague, such as "make the engine stronger". That kind of instruction tends to produce broad edits and confidence without enough measurement. The useful pattern was to give it a narrow change, an acceptance test, and a rule that legality mustn't regress.

In other words, the LLM wasn't the chess authority. The tests were.

## What this does not prove

This experiment doesn't prove that LLMs can replace chess-engine authors.

It also doesn't prove that LabZero is strong, novel in its algorithms, or ready for serious competition. Most of the techniques inside it are standard. Strong engines are strong because they combine those techniques with enormous care, tuning, testing, and years of accumulated chess knowledge.

What it does show is narrower and, to me, more interesting:

> A fast coding LLM, used by an experienced developer inside a strict verification loop, can help produce a fresh legal chess engine very quickly.

That is a useful result because it is concrete. The engine can be cloned. The commands can be run. The PGNs can be inspected. The claims can be corrected.

## What comes next

The next step is to make the experiment easier to reproduce and harder to fool.

The useful work now isn't only engine strength. It is measurement:

- Publish a cleaner one-command benchmark path;
- Document the ladder method and its limits;
- Run more games at each point;
- Test more time controls;
- Add a few weak open-source engines as opponents, not only Stockfish limited Elo;
- Separate alpha, beta, and gamma claims more clearly;
- Keep recording illegal moves, crashes, and protocol failures as first-class results;
- Invite independent runs from other machines.

On the engine side, the likely improvements aren't mysterious: better move ordering, more stable time management, stronger endgame behavior, tuned evaluation, cleaner SMP testing, and more tactical test suites. But for a public write-up, I think the honest story is still the workflow, not the rating.

LabZero isn't a finished engine.

It's a lab result.

And as a first answer to the question "can a fast coding LLM help build a fresh legal chess engine from zero in one working day?", it's already interesting.
