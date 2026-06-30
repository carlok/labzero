# LabZero Oracle-First Relative Move Quality Roadmap

## Summary Judgment

This direction is worth pursuing, but only with a narrow first milestone:
**build an offline Stockfish-only oracle labeler and report before training any
model or building an MCTS companion**.

The useful idea is not "add neural magic" or "rewrite LabZero around MCTS". The
useful idea is a reproducible teacher pipeline:

```text
FEN -> legal moves -> teacher-scored move distribution -> relative quality labels
```

Those labels can immediately grade LabZero's decisions, expose repeatable
failure modes, and create regression candidates. Later they can feed a small
NNUE/value model, a policy companion, or a root-level MCTS experiment. The
labels must prove useful first.

## Clarified Architecture

The v1 oracle is an offline tooling layer:

- **Teacher**: Stockfish only, invoked as an external UCI process.
- **Student**: LabZero, or a manually supplied move, graded against teacher-ranked legal moves.
- **Labels**: move rank, utility loss, centipawn loss, mate metadata, bucket, and stability status.
- **Consumers**: human-readable reports first; neural/MCTS consumers later.

For each root position, enumerate legal moves, play each move on a copy of the
board, analyze the child position with Stockfish under a fixed node budget, and
convert the result back to the original side-to-move perspective.

Do not use Stockfish code, weights, tables, tuned parameters, or engine-specific
implementation details. Stockfish is only a teacher/labeler, and every label
record must keep teacher provenance.

## V1 Milestone: Stockfish Oracle Labeler

Create the first implementation branch as:

```text
codex/oracle-labeler-v1
```

The exact first target:

- Python CLI: `scripts/host-oracle-label.py`.
- Stockfish path from `--stockfish` or `STOCKFISH`.
- Inputs: `--fen`, `--fen-file`, or `--pgn`.
- Optional student mode: `--student labzero --engine target/release/labzero`, or `--student-move UCI`.
- Outputs: JSONL plus a Markdown report under `docs/oracle/`.
- No Rust engine behavior changes.
- No Lichess bot binary/config changes.

Recommended smoke:

```bash
STOCKFISH=/opt/homebrew/bin/stockfish \
  scripts/host-oracle-label.py \
  --fen-file verifier/positions/tactical_losses.epd \
  --student labzero \
  --engine target/release/labzero \
  --nodes 20000 \
  --nodes2 80000 \
  --out docs/oracle/oracle_smoke.jsonl \
  --report docs/oracle/oracle_smoke.md
```

Acceptance criteria for v1:

- every record includes teacher metadata;
- LabZero's move is graded for every non-terminal input when `--student labzero` is used;
- mate scores are represented without fake giant centipawns;
- repeated or second-budget runs either preserve ranking or mark volatility;
- the Markdown report makes the worst LabZero disagreements inspectable.

## Label Semantics

Use WDL-like bounded utility as the primary move-quality target, with centipawn
loss and rank as supporting fields.

Raw centipawns are not enough: a 100 cp loss near equality is not the same
practical event as a 100 cp loss when already winning by 900 cp. Use:

```text
cp_clamped = clamp(cp, -1200, 1200)
utility = sigmoid(cp_clamped / scale)
delta_utility = best_utility - move_utility
delta_cp = best_cp - move_cp
rank = 1 + count(moves with higher utility)
percentile = 1 - (rank - 1) / max(legal_count - 1, 1)
```

Start with `scale = 400`. Treat this as a label-policy knob, not a strength knob.

Suggested buckets:

| Bucket | Meaning |
| --- | --- |
| best | rank 1 or indistinguishable from best |
| excellent | tiny utility loss |
| playable | small utility loss |
| inaccuracy | visible but non-decisive loss |
| mistake | large practical loss |
| blunder | decisive utility loss or mate concession |

Mate handling:

- store `mate_in` separately from `cp`;
- map forced mate to near-0 or near-1 utility;
- preserve mate distance for display and tie-breaking;
- do not train directly on huge artificial mate centipawn values.

Search budget policy:

| Budget | Use |
| --- | --- |
| fixed nodes | canonical reproducible labels |
| fixed depth | small golden tests/debugging |
| fixed time | interactive UI only |
| adaptive/two-pass | volatility detection after v1 |

For canonical v1 labels, prefer independent child-position searches over root
MultiPV. MultiPV can be a quick UI/top-k optimization later, but child searches
are clearer and more reproducible for all legal moves.

## Data Contract

Use JSONL schema `labzero.move_quality.v1`, one object per root position:

```json
{
  "schema": "labzero.move_quality.v1",
  "fen": "...",
  "source": {"kind": "pgn|fen|manual|benchmark|lichess", "id": "...", "ply": 0},
  "teacher": {
    "engine": "Stockfish",
    "version": "...",
    "path": "...",
    "uci_options": {"Threads": 1, "Hash": 64},
    "budget": {"mode": "nodes", "nodes": 50000}
  },
  "root": {"side_to_move": "w", "legal_count": 0},
  "student": {"kind": "labzero|manual|none", "move": "e2e4"},
  "moves": [
    {
      "uci": "e2e4",
      "rank": 1,
      "cp": 34,
      "mate_in": null,
      "wdl": null,
      "utility": 0.521,
      "delta_utility": 0.0,
      "delta_cp": 0,
      "bucket": "best"
    }
  ],
  "label_quality": {"status": "stable|volatile|mate|shallow", "notes": ""}
}
```

For small audit runs, store all legal moves. For large future datasets, keep full
audit shards and allow compact top-k training shards.

## Future Tracks

The likely order after v1:

1. **Diagnostics and regression mining**: grade LabZero games and extract the largest stable move losses.
2. **Small value/utility model**: NNUE-like evaluator first, because LabZero already has an alpha-beta-compatible NNUE seam.
3. **Policy/root companion**: use labels as root move priors or move-ordering hints only after NPS and strength gates are clean.
4. **Root-level MCTS companion**: only after cached labels or a distilled policy/value model exists; do not make live oracle calls inside play.
5. **Human-facing web app**: thin reader over stable label records, not a separate analysis system.

LC0/Leela can add value later as a second teacher for strategic or policy/value
disagreement, but it is not needed for v1. Syzygy should later override utility
in 5-7 piece positions once tablebase paths and licensing/storage constraints
are explicit.

## Evaluation Metrics

Offline metrics:

- top-1 and top-k agreement with teacher;
- rank correlation over legal moves;
- average utility loss of LabZero's selected moves;
- bucket distribution;
- stability across node budgets;
- worst stable disagreements by source and motif.

LabZero-facing metrics after any model or search integration:

- tactical-suite pass rate;
- fixed-depth best-move changes on regression packs;
- NPS/depth impact;
- matches against classical-only LabZero;
- project-relative Stockfish gates with full artifact metadata.

No neural or MCTS component should be considered useful until it improves either
diagnostic power or playing strength without hiding behind noisy single runs.

## Explicit Deferrals

Do not do these in v1:

- LC0/Leela ensemble;
- Syzygy integration;
- live MCTS or any MCTS inside the engine;
- GPU training;
- large 100k+ label generation;
- web UI/product work;
- Rust search/eval integration;
- Lichess bot changes.

The guiding rule is:

```text
labels first, reports second, model third, engine integration fourth, MCTS last
```
