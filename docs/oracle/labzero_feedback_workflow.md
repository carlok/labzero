# LabZero Oracle Feedback Workflow

This is the intended loop for improving LabZero from live play without turning
Stockfish into copied engine content.

The short version:

```text
play games -> save PGNs -> label LabZero moves -> inspect worst disagreements
-> create one narrow patch -> gate it -> play again
```

The neural companion is a side tool. It can help rank positions, learn move
quality, and suggest where to look next, but it is not loaded by the engine and
is not part of the original core claim.

## Diagram

Render the Graphviz source:

```bash
dot -Tpng docs/oracle/labzero_feedback_workflow.dot \
  -o docs/oracle/labzero_feedback_workflow.png
```

Or inspect the source directly:

```bash
open docs/oracle/labzero_feedback_workflow.dot
```

## Live Play Loop

The bot plays with a copied binary and writes finished games as PGNs:

```bash
env LABZERO_ROOT_POLICY=raw \
  lichess_bot/run-local.sh --challenge-loop --rated --closest-superior --games 4
```

For live feedback, enable the bounded oracle hook after the block:

```bash
STOCKFISH=/opt/homebrew/bin/stockfish \
env LABZERO_ROOT_POLICY=raw \
  lichess_bot/run-local.sh --challenge-loop --rated --closest-superior --games 4 --oracle-after-block
```

The hook runs after the block, not after every game. It labels only a bounded
number of recent positions, writes JSONL under ignored `data/oracle/`, and
writes compact reports under `docs/oracle/`.

## Manual Oracle Runs

Analyze recent LabZero games:

```bash
STOCKFISH=/opt/homebrew/bin/stockfish \
  scripts/host-oracle-label.py \
  --pgn-dir lichess_bot/local/pgn \
  --limit-games 50 \
  --max-positions 300 \
  --nodes 20000 \
  --nodes2 80000 \
  --out data/oracle/live_recent.jsonl \
  --report docs/oracle/live_recent.md
```

Read the report first. The important output is the repeated pattern in the
worst LabZero disagreements:

- missed tactics;
- exposed king or unsafe queen activity;
- passive endgame defense;
- bad passed-pawn races;
- shuffling, conversion, or draw-policy issues.

Only after the pattern is visible should a code branch start.

## External Lichess Database Side Project

The downloaded monthly Lichess PGNs are useful, but they should not go straight
into the engine. First create a filtered candidate set:

```text
raw monthly PGN -> standard rated only -> both players >= 2000
-> sane time controls -> no junk/very short games -> sampled positions
```

Suggested output:

```text
data/oracle/human_2000_positions.jsonl
```

Use this data mostly for policy breadth: it shows plausible moves from strong
human games. It does not by itself prove objective move quality. For correctness
labels, sample positions from it and run the Stockfish oracle labeler.

## Offline Companion Training

Train a medium experimental companion from oracle labels:

```bash
scripts/host-oracle-train.py \
  --data data/oracle/live_recent.jsonl \
  --hidden 256 \
  --epochs 10 \
  --out data/oracle/oracle_companion.pt \
  --report docs/oracle/oracle_companion.md
```

This checkpoint is tooling-only. It can be used later to rank candidate
positions, estimate move quality, or guide root-ordering experiments, but it is
not loaded by LabZero automatically.

## Patch Selection Rule

Do not patch from one anecdote. Patch from repeated evidence.

1. Label a block or a recent slice.
2. Pick one repeated motif from the worst stable disagreements.
3. Add one regression position.
4. Make one narrow engine or bot change.
5. Run tests and a small real-clock smoke.
6. Only then try a controlled Lichess block.

The oracle report is a compass, not a replacement for gates.

## Originality Boundary

Allowed:

- Stockfish binary as an external teacher.
- JSONL labels with teacher provenance.
- Offline reports and tooling-only experimental models.
- Human PGN data as a source of candidate positions.

Not allowed without a separate policy decision:

- copying Stockfish source, tables, weights, or tuned implementation details;
- silently making a Stockfish-label-trained model part of the original engine
  strength claim;
- live oracle calls during a game;
- automatic neural use in play without separate gates and documentation.

The safe default remains:

```text
labels first, reports second, model third, engine integration fourth, MCTS last
```
