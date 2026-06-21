# LabZero: a chess engine from zero in one working day

In less than one human working day, I built a chess engine from zero.

Not one calendar day of unattended computation. One working day of human time. The engine was written in Rust, a language I did not know when I started. The assistant was not the strongest model available, but Cursor's fast coding model at the time: **Composer 2.5 Fast**. I did not copy Stockfish, use a chess-engine crate, or reuse another engine core.

The result is **LabZero**: an original Rust UCI engine that plays legal chess, survives automated checks, and now tests above **1900** in a bullet-like, limited-Stockfish benchmark. More precisely, in the current 32-game confirm at `TC_MODE=movetime TC_SEC=1 THREADS=1` against Stockfish 18 with `UCI_LimitStrength` and `UCI_Elo=2000`, LabZero scored **9-17-6**, or **37.5%**, with **0 illegal moves** and **0 errors**. That maps to roughly **1910 performance Elo** on this test protocol.

That is not a Lichess rating. It is not CCRL. It is not a universal chess-engine rating. It is a project-relative benchmark against a weakened Stockfish binary.

Still: from zero, in one human day, with a fast coding LLM, without knowing Rust, and without copying an engine core, getting to a legal UCI engine in that range surprised me.

Repository: <https://github.com/carlok/labzero>

## Why I tried this

Chess is a good test for LLM-assisted programming because the code cannot talk its way out of being wrong.

If castling goes through check, it is wrong.
If en passant exposes the king and the engine allows it, it is wrong.
If the UCI loop hangs, the engine is unusable.
If it returns an illegal move, the game is over.

That makes chess different from many small AI coding demos. A web page can look plausible. A script can pass one happy-path example. A chess engine has to obey formal rules under repeated external checks.

So the experiment was not "can an LLM write a lot of Rust?" It was:

> Can a fast coding LLM, used inside a normal engineering loop, help build a fresh, legal, testable chess engine very quickly?

The goal was not to beat Stockfish. The goal was to build something real enough that other tools could judge it.

## The constraint

The main rule was originality.

External tools were allowed for testing, validation, and tournament running. Stockfish could be used as an opponent. Python and Rust chess libraries could be used as independent oracles. But the engine core itself had to stand alone.

The forbidden list was simple:

- no copied Stockfish code;
- no copied move generator;
- no imported chess-engine crate in the core;
- no copied evaluation tables or engine weights;
- no Stockfish source as a reference implementation.

The allowed list was also simple: public rules, public protocols, public perft numbers, and standard chess-programming ideas implemented for this project.

This matters because LabZero is not trying to claim new chess algorithms. It uses familiar ideas: bitboards, FEN, UCI, perft, alpha-beta, quiescence search, transposition tables, move ordering, simple evaluation terms. The point is that the core was built fresh, under a verification loop, in very little human time.

## The human side

I am not a strong chess player. I am a software engineer with almost thirty years of experience.

That combination was useful for the experiment. I could design the workflow, set constraints, read failures, and decide what counted as evidence. But I was not bringing deep chess-engine authorship or Rust fluency to the table.

Rust was deliberate. I know many languages, but I did not know Rust. I wanted a language that was fast enough for an engine and strict enough to punish sloppy code. It also forced the coding assistant to carry more of the language-specific work while I kept control of the engineering loop.

The model choice was deliberate too. I did not use the largest or most careful frontier model I could find. I used Cursor's fast auto model, [Composer 2.5 Fast](https://cursor.com/blog/composer-2-5), because I wanted to know what a quick everyday coding assistant could do when boxed in by tests.

## What LabZero can do

LabZero is now a small Rust workspace with an original engine core in `engine/`.

It supports the basic surface a chess GUI or tournament runner expects:

- legal move generation;
- FEN parsing and generation;
- UCI commands such as `uci`, `isready`, `position`, `go`, `stop`, and `quit`;
- UCI options for hash size, thread count, and an optional opening book;
- a native binary that can be used from chess GUIs or tournament tools.

The rules covered include castling, promotion and underpromotion, en passant, check, double check, pins through legal filtering, mate, stalemate, the fifty-move counter, and repetition tracking.

The current search is no longer just "look a few moves ahead and hope." It has iterative deepening, alpha-beta, quiescence search, aspiration windows, null-move pruning, late move reductions, killer and history move ordering, SEE-based capture ordering, and a transposition table. The evaluation is still simple, but it has material, tapered piece-square tables, bishop pair, pawn structure, rook-file terms, and king-safety terms.

There is also a Lazy SMP mode. It did not help in the latest 1-second spot check, so I would not claim "multi-core strength" yet. That is useful information too.

## Verification came first

The important part was not trusting the LLM. The important part was making wrong code fail.

LabZero has several checks around it:

- unit tests for engine internals;
- perft checks against known positions;
- random-game fuzzing;
- legality checks through `python-chess`;
- cross-checks against independent Rust chess libraries;
- UCI protocol smoke tests;
- tournament smoke and gauntlet scripts;
- benchmark scripts that save logs and PGNs.

The deeper verification path includes perft to depth 6, a 200-game random fuzzer, legality oracle checks, and independent Rust cross-checks. The tournament checks catch a different class of problem: crashes, time trouble, protocol mistakes, and illegal moves under game conditions.

That loop changed how the LLM was useful. I was not asking it to be right. I was asking it to make small changes that could be compiled, run, checked, and rejected.

## The strength result

The headline number should be read carefully, but it should not be hidden.

The benchmark I would publish is:

- opponent: Stockfish 18 binary;
- Stockfish settings: `UCI_LimitStrength=true`, `UCI_Elo=2000`;
- LabZero settings: `Threads=1`;
- time protocol: fixed `movetime` of 1 second per move;
- games: 32, alternating colors;
- result: **9-17-6** for LabZero;
- score: **37.5%**;
- illegal moves: **0**;
- errors: **0**;
- approximate performance on this protocol: **1911**.

There is also a 16-game regression row against Stockfish limited to 1320: **14-0-2**, again with no illegal moves or errors. Earlier beta data had LabZero at **34.4%** against the same SF@2000 setting. The current confirm row is **37.5%**. That is not a huge jump, but it keeps the engine in the same broad band and supports the claim that the result is not a one-off toy.

The fair sentence is:

> LabZero is an original, legal UCI engine, built in roughly one human working day with a fast coding LLM, that currently measures around 1900 on a bullet-like limited-Stockfish benchmark.

That is the claim I am comfortable making.

## What did not work

Some things did not improve the result.

Turning on eight threads in a 16-game 1-second spot check against the same SF@2000 setting scored **2-9-5**. That is worse than the single-thread confirm. The sample is small and the confidence interval is wide, so I do not treat it as proof that threads hurt. But I do treat it as proof that the current Lazy SMP is not a free strength button.

An early clock-style `3+2` run scored **0-8-0** in eight games before I fixed the benchmark harness (`white_clock` / `black_clock` in `host-benchmark.sh`). After the fix, a **32-game** `3+2` confirm against SF@2000 scored **10-11-11** (**48.4%**), with **0 illegal moves** and **0 errors** (`benchmark_20260621T140403Z`). That is roughly **even** on this protocol (performance Elo ≈ **1990**), not Lichess rating. I still keep the **1+0 movetime** row as the headline anchor (**37.5%**, ≈**1911**), but the blitz result shows the engine uses extra think time and real clocks without falling apart.

These failures are part of the result. They show where the engine is still young.

## What the LLM was good at

The assistant was best when I gave it small, falsifiable tasks:

- parse FEN;
- generate legal moves;
- add perft;
- make `go depth 2` return a legal move;
- add a UCI smoke test;
- add quiescence search;
- add a benchmark script;
- make tournament failures visible.

It was much worse when the instruction was vague, such as "make the engine stronger." That kind of request tends to produce broad edits and confident explanations. Chess punishes that.

The useful pattern was:

1. make a small change;
2. run a test that can fail;
3. compare against the previous benchmark;
4. keep the change only if the evidence improves.

That is ordinary software engineering. The LLM made the loop faster, but the loop mattered more than the model.

## What this proves, and what it does not

This does not prove that LLMs can replace chess-engine authors.

It does not prove that LabZero is strong by engine standards. It does not prove a Lichess rating. It does not prove that the search is elegant or that the evaluation is well tuned.

It does show something narrower:

> With strict constraints and objective tests, a fast coding LLM can help an experienced developer build a fresh, legal, externally checkable chess engine in about one working day.

That is already interesting to me.

Many LLM coding claims are hard to verify. This one is more concrete. The repository is there. The originality policy is there. The commands are there. The PGNs and logs are there. The engine either plays legal moves or it does not.

## What comes next

The next work is not to add neural networks or GPU code. That would make the story bigger, but not cleaner.

The useful work is more boring:

- make the benchmark path easier for other people to repeat;
- run more games at the important points;
- test other weak engines, not only limited Stockfish;
- improve real clock handling;
- make multicore search actually pay off;
- tune evaluation from PGN failures, not from vibes;
- keep recording illegal moves and protocol errors as first-class results.

LabZero is not a finished chess engine.

It is a lab result.

But as a first answer to the question "can a fast coding LLM help build a fresh chess engine from zero in one human working day?", I think the answer is yes.
