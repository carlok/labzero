# labzero: An Original Weak Chess Engine (Alpha Release)

**Draft — v0.2.0 (alpha)** · 2026-06-20  
**Repository:** https://github.com/carlok/labzero · **License:** MIT

---

## Abstract

We present **labzero**, an original Rust chess engine built as a research baseline for LLM-assisted, verifiably independent engine development. The alpha release (v0.2.0) implements full FIDE-legal move generation, negamax search with alpha–beta pruning, and a hand-written material + piece-square evaluation. Strength is intentionally modest: the primary claims are **legality**, **UCI compliance**, **reproducible verification**, and **originality**—not competitive Elo.

Independent oracles (perft, fuzz, cross-engine legality checks) and a 200-game tournament gauntlet show **zero illegal moves**. A host benchmark ladder against strength-limited Stockfish 18 brackets **bullet performance Elo at ≈ 1700–1750** on this protocol (see §5). We document a concrete **beta roadmap** adding classical search and evaluation techniques, each measurable on the same ladder without copying existing engine source.

---

## 1. Introduction

Modern top engines (Stockfish, Leela Chess Zero, and derivatives) dominate computer-chess benchmarks. For research on *how* engines are built—especially workflows where large language models propose patches—a useful baseline is:

1. A **small, readable core** with no copied evaluation or search code.
2. **Independent verification** that behavior matches chess rules, not another engine’s bugs.
3. A **fixed strength ladder** so each future change has a quantifiable effect.

**labzero alpha** satisfies (1)–(3). It is “weak but legal”: suitable for human play, Lichess-bot deployment, and gauntlet survival, while leaving substantial headroom for beta improvements (§7).

### 1.1 Originality constraint

The engine core (`engine/`) must not copy or closely imitate source from Stockfish, Leela, Ethereal, or similar projects. Allowed: public rule specs (FEN, UCI, perft tables), general algorithms (negamax, bitboards, PSTs written for this project), and **Stockfish as a binary opponent only**. See [originality_policy.md](originality_policy.md).

---

## 2. Alpha architecture

~1,700 lines of Rust across 14 modules. Bitboard + mailbox representation; make/unmake with Zobrist hashing (hash computed but **not yet used** for search).

| Module | Role |
|--------|------|
| `movegen.rs` | Legal moves: pins, castling, en passant, promotions |
| `search.rs` | Negamax, α–β, iterative deepening (depth cap ~6 by default) |
| `eval.rs` | Material + **original** piece-square tables (not copied from SF/LC0) |
| `uci.rs` | UCI loop, `go` time/depth handling |
| `time.rs` | Budget: `time / movestogo + increment` |

### 2.1 Search (alpha)

Negamax with α–β window $[\alpha, \beta]$:

$$
\text{negamax}(d, \alpha, \beta) =
\begin{cases}
\text{eval}() & d = 0 \text{ or time exhausted} \\[4pt]
\max\limits_{m \in \text{legal}} \bigl(-\text{negamax}(d-1, -\beta, -\max(\alpha, s))\bigr) & \text{else}
\end{cases}
$$

Mate scores use a large constant $M = 30{,}000$ with ply offset (prefer faster mates).

**Not present in alpha:** quiescence, transposition table, null-move pruning, late-move reduction (LMR), aspiration windows, killer/history heuristics, SEE.

Move ordering: captures and promotions first (MVV-LVA-style priority without explicit victim values).

### 2.2 Evaluation (alpha)

Static score for side to move:

$$
\text{eval}(p) = \sum_{sq \in \text{occupied}} \sigma(sq) \cdot \bigl(\text{MATERIAL}(kind) + \text{PST}_{kind}(sq)\bigr)
$$

where $\sigma = +1$ for white pieces and $-1$ for black. King uses a single middlegame PST (no tapered mg/eg).

---

## 3. Verification methodology

All automated gates run in **Podman** for reproducibility ([reproducibility.md](reproducibility.md)).

| Gate | Command | Alpha result |
|------|---------|--------------|
| Smoke CI | `./scripts/podman/ci` | PASS |
| Deep verify | `./scripts/podman/verify-deep` | Perft d1–6, 200-game random fuzz, cozy/shakmaty cross-check |
| Gauntlet | `./scripts/podman/gauntlet` | 200 games aggregate, **0 illegal moves / crashes** |
| UCI dry-run | `./scripts/podman/bot --dry-run` | 20 plies, legal |

Perft anchor (startpos, depth 6): $N = 119{,}060{,}324$ nodes—matches published tables.

**Human GUI QA** (Banksia / similar) remains operator-driven; see [human_play_checklist.md](human_play_checklist.md).

---

## 4. Strength measurement

### 4.1 Host benchmark protocol

Script: `./scripts/host-benchmark.sh`

- **Opponent:** Stockfish 18 binary, `UCI_LimitStrength=true`, `UCI_Elo = E_{\text{SF}}`, `Skill Level = 0`
- **Time control:** 1+0 bullet (~1 s/move per side via engine time budget)
- **Sample:** $N = 32$ games, colors alternate
- **Artifacts:** incremental `.txt` log + `.pgn` per run ([strength/](strength/))

### 4.2 Performance Elo (heuristic)

Let $W, L, D$ be labzero wins, losses, draws and $p = (W + \tfrac{1}{2}D) / N$. Assuming a logistic Elo model against a fixed opponent:

$$
E \approx E_{\text{SF}} + 400 \log_{10}\!\left(\frac{p}{1-p}\right)
$$

This is **not** a FIDE or CCRL rating—it maps a single opponent’s limited-Elo knob to a score percentage. Use only for **relative** comparisons on the same protocol.

### 4.3 Dichotomy ladder

Binary search on $E_{\text{SF}}$ to bracket 50% score:

```
1320 → 89.1%  →  next 2000
2000 → 17.2%  →  next 1800  (perf Elo ≈ 1727)
```

Reference context: [CCRL 40/15](https://computerchess.org.uk/4040/index.html) lists hobby engines (Micro-Max ~1869, CDrill 1800 ~1795) at **different** time controls; bullet SF-Elo numbers are not directly comparable to CCRL.

---

## 5. Alpha strength results

| Round | $E_{\text{SF}}$ | $N$ | Score (W–L–D) | $p$ | $E$ (approx.) | Status |
|-------|-----------------|-----|---------------|-----|---------------|--------|
| 1 | 1320 | 32 | **27–2–3** | 89.1% | ≈ 1520+ | **complete** |
| 2 | 2000 | 32 | **2–23–7** | 17.2% | ≈ 1727 | alpha |

## 5.1 Beta ablation (v0.3.0-beta)

| $E_{\text{SF}}$ | Alpha $p$ | Beta $p$ | Beta artifacts |
|-----------------|-----------|----------|----------------|
| 1320 | 89.1% | **93.8%** | `benchmark_20260620T214301Z` |
| 1800 | — | **51.6%** (≈1812 perf) | `benchmark_20260620T221648Z` |
| 2000 | 17.2% | **34.4%** (≈1888 perf) | `benchmark_20260620T230310Z` |

**Interpretation:** Beta adds qsearch, TT ordering, null move, LMR, SEE, and tapered eval. Vs SF@2000, score roughly **doubled** (17% → 34%); vs SF@1800 ≈ **50%** → performance Elo ≈ **1800–1900** on this protocol. Gauntlet: 0 illegal.

Detailed logs: [strength/ladder.md](strength/ladder.md).

---

## 6. Discussion

### 6.1 What alpha proves

- An LLM-iterated workflow can produce a **self-contained**, **UCI-compliant** engine that survives automated tournaments.
- Independent verification catches legality bugs before human or Lichess exposure.
- A **strength ladder** turns “it feels stronger” into reproducible numbers.

### 6.2 What alpha does not claim

- Competitive play vs humans or full-strength engines.
- Optimality of evaluation or search.
- Transfer of bullet SF-Elo to CCRL 40/15 or Lichess rating pools.

### 6.3 Gap vs small engines on CCRL

Engines like **Micro-Max** (~137 lines C, CCRL ~1869 at 40/15) implement quiescence and pruning tricks labzero alpha lacks. The gap is **search quality per node**, not movegen correctness. That gap is the beta target.

---

## 7. Future work — Beta roadmap (v0.3+)

Beta keeps the **originality policy**: implement standard *algorithms* from textbooks and papers, not transcribe Stockfish source. Each milestone re-runs `./scripts/host-benchmark.sh` at fixed $E_{\text{SF}} \in \{1320, 1800, 2000\}$ and `./scripts/podman/gauntlet` (illegal-move count must stay **0**).

### Phase B0 — Measurement baseline (before code changes)

- [x] Finish round 2 ($E_{\text{SF}} = 2000$, $N = 32$)
- [x] B1a quiescence — implemented
- [x] B1b transposition table — implemented (ordering; mate-aware store)
- [x] B2a null move + B2b LMR — implemented
- [x] B2c killer/history/SEE — implemented
- [x] B3a tapered mg/eg eval — implemented
- [x] B3b structure helpers — in `eval.rs` (disabled at runtime for bullet NPS; tune in B4)

**Exit:** Bracketed performance Elo ±100 on 1+0 protocol.

---

### Phase B1 — Large gains (search extensions)

#### B1a. Quiescence search

Extend leaf evaluation with capture/promotion/check continuations until quiet:

$$
\text{eval\_leaf} = \max\bigl(\text{stand\_pat},\; \max_{m \in \text{noisy}} -\text{qsearch}(-\beta, -\alpha)\bigr)
$$

**Acceptance:** measurable lift vs SF@1800; fewer blunders in PGN tail positions; gauntlet still 0 illegal.

#### B1b. Transposition table

Use existing Zobrist `board.hash` as key; store `(depth, score, flag, best_move)`.

Replace depth-0 cutoff:

$$
\text{if TT.hit}(key, d) \land \text{score usable} \Rightarrow \text{return cached score}
$$

**Acceptance:** node count drops at same depth; same or better score vs alpha at equal time; memory cap documented (e.g. 64–256 MB).

---

### Phase B2 — Medium gains (pruning & ordering)

#### B2a. Null-move pruning

If not in check and $d \ge R$, try a reduced search after a null move:

$$
\text{if } d \ge 3 \land \neg\text{in\_check} \land \text{has\_non\_pawn\_material}: \quad
\text{null\_score} = -\text{negamax}(d - 1 - R, -\beta, -\beta + 1)
$$

**Acceptance:** depth +1 at same time on benchmark positions; no regression in gauntlet illegal count.

#### B2b. Late move reduction (LMR)

For move index $i > \text{full\_depth\_moves}$ at $d \ge 3$, search with $d' = d - 1 - \text{reduction}(i)$ then re-search full depth if score $> \alpha$.

**Acceptance:** improved nodes/sec; ladder score vs SF@2000 increases.

#### B2c. Move ordering: killers, history, SEE

- **Killer moves:** two slots per ply for quiet moves that caused cutoffs.
- **History heuristic:** bonus `history[side][from][to]` on cutoff.
- **SEE (static exchange eval):** order captures by estimated gain.

Combined ordering key (example):

$$
\text{order}(m) = \text{SEE}(m) + 10^4 \cdot \mathbb{1}_{\text{killer}}(m) + \text{history}(m)
$$

**Acceptance:** fewer nodes to fixed depth on perft-with-search smoke positions.

---

### Phase B3 — Medium gains (evaluation)

#### B3a. Tapered evaluation (mg / eg)

Split PSTs and phase:

$$
\text{eval} = \frac{\text{phase} \cdot \text{eval}_{mg} + (256 - \text{phase}) \cdot \text{eval}_{eg}}{256}
$$

with $\text{phase}$ from material (no queens → endgame).

**Acceptance:** fewer eval-blunders in king-and-pawn endings in self-play PGN review.

#### B3b. Structure and mobility (original weights)

Add **original** terms (tuned on labzero self-play, not SF tables):

- Doubled/isolated/backward pawns
- Bishop pair, rook on open/semi-open file
- King safety (pawn shield, open files near king)
- Mobility (legal move count per piece type, capped)

**Acceptance:** improved $p$ vs SF@1800 without search changes; document tuning method for reproducibility.

---

### Phase B4 — Smaller gains (time & infrastructure)

| Item | Description | Acceptance |
|------|-------------|------------|
| Aspiration windows | $\alpha, \beta$ centered on previous iter score | Fewer re-searches at same depth |
| Iterative deepening polish | PV move first on next depth | Higher depth within time budget |
| Time management | Soft stop, panic margin, optional ponder | Stable 1+0 and 3+2 gauntlet |
| Bitboard movegen speed | Precomputed attacks, less cloning in search | Higher NPS; no rule changes |
| Opening book (optional) | Small original EPD book, UCI `ownbook` | Diversity in gauntlet; off by default for ladder |

---

### Phase B5 — Integration & release (beta)

- [ ] `./scripts/podman/ci` + verify-deep + gauntlet 200 — all PASS
- [ ] Strength ladder: report $\Delta p$ per phase vs alpha baseline
- [ ] Version **0.3.0** (beta), CHANGELOG, updated submission pack
- [ ] Live Lichess bot (lichess-bot + host binary): 5+ rated games logged
- [ ] Paper revision: **beta** draft with ablation table

### Beta success criteria (summary)

| Metric | Alpha | Beta target |
|--------|-------|-------------|
| Illegal moves (gauntlet 200) | 0 | 0 |
| Performance Elo (1+0, bracketed) | ~1600–1800 | **+200–400** (hypothesis) |
| Search depth @ 1 s (midgame) | ~6 | ≥ 8–10 with TT + pruning |
| Originality audit | pass | pass (no SF/LC0 source) |

---

### Phase C — Multi–time-control (gamma v0.4.0)

Implemented in v0.4.0 (original code only):

| Sprint | Items |
|--------|-------|
| C1 | Depth cap 64, aspiration, PV ordering, root make/unmake; TT ordering under movetime |
| C2 | Soft stop, panic reserve, UCI `info`, `Hash`, wtime/increment time model |
| C3 | Pawn structure, rook files, king safety in eval |
| C4 | Check evasions in qsearch, optional `OwnBook`/`BookFile` |
| C6 | Lazy SMP (`Threads` 1–8, shared TT) |

**Measurement:** anchor ladder `TC_SEC=1 THREADS=1`; spot blitz `TC_MODE=wtime 3+2`; spot rapid `TC_SEC=10 THREADS=4`. See [strength/ladder.md](strength/ladder.md).

### Phase D — Strengthening (v0.5.0)

| Sprint | Items |
|--------|-------|
| D1a | Tactical EPD + fixed-depth regression tests |
| D1b | TT `complete` flag; depth-only score cutoffs (movetime ordering-only) |
| D1c | LMR / aspiration single-knob tune |
| D2 | wtime spot benchmark, stop/`ucinewgame` hardening, UCI matrix |
| D3 | Eval weight tune (existing terms) |
| D4 | Ablation table, TC caveats, ladder sync |

**Ablation (1+0 anchor, T=1):**

| Version | SF 1320 | SF 1800 | SF 2000 |
|---------|---------|---------|---------|
| alpha v0.2.0 | 89.1% | — | 17.2% |
| beta v0.3.0-beta | 93.8% | 51.6% | 34.4% |
| gamma v0.5.0 | **93.8%** | **46.9%** (probe) | **37.5%** (32-game confirm, ≈**1911** perf) |

**TC caveat:** All published ladder rows use `TC_MODE=movetime TC_SEC=1 THREADS=1` unless marked otherwise. Performance Elo is project-relative vs Stockfish `UCI_LimitStrength`; not Lichess/CCRL/FIDE Elo.

**SMP spot (not anchor):** `Threads=8`, 16 games @ SF@2000 → **28.1%** (perf ≈ **1837**), vs **37.5%** (≈ **1911**) at `Threads=1` (32-game confirm). Lazy SMP v1 did not help at 1 s/move on this run (`benchmark_20260621T095930Z`).

**Blitz spot (not anchor):** `TC_MODE=wtime 3+2`, 16 games @ SF@2000 → **7–6–3** (**53.1%**, perf ≈ **2022**), 0 illegal (`benchmark_20260621T132942Z`). Supersedes pre-harness-fix **0–8–0** (`benchmark_20260621T063138Z`). Wider think time vs 1+0 movetime; 16-game CI is wide.

---

## 8. Conclusion (alpha)

**labzero v0.2.0** demonstrates that a minimal, original chess engine can be built, verified independently, and measured on a reproducible strength ladder—without claiming competitive Elo. Alpha is the **control experiment**; beta adds well-known search and evaluation machinery under the same originality and verification discipline, with each phase producing a datapoint on the ladder.

---

## References & links

- CCRL 40/15 rating list: https://computerchess.org.uk/4040/index.html
- UCI specification: https://www.chessprogramming.org/UCI
- Perft results: https://www.chessprogramming.org/Perft_Results
- Project docs: [architecture.md](architecture.md), [submission_package.md](submission_package.md), [strength/ladder.md](strength/ladder.md)

---

## Appendix A — Reproduce alpha results

```bash
# Verification (Podman)
./scripts/podman/ci
./scripts/podman/verify-deep
./scripts/podman/gauntlet

# Host strength ladder (macOS; set your Stockfish path)
export STOCKFISH="/path/to/stockfish"
./scripts/build-host-engine.sh
SF_ELO=1320 SF_SKILL=0 SF_LIMIT=1 TC_SEC=1 GAMES=32 ./scripts/host-benchmark.sh
```

## Appendix B — Notation

| Symbol | Meaning |
|--------|---------|
| $E_{\text{SF}}$ | Stockfish `UCI_Elo` when `UCI_LimitStrength=true` |
| $p$ | Score rate $(W + \tfrac{1}{2}D)/N$ |
| $E$ | Performance Elo from §4.2 |
| $d$ | Remaining search depth |
| $\alpha, \beta$ | Alpha–beta window bounds |

---

*Draft status: update §5 round 2 row when benchmark completes; mark beta phases complete in §7 as implemented.*
