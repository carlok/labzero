# LabZero Puzzle Oracle Miner

This is an experimental workbench for finding LabZero's worst tactical and practical failures against Stockfish on puzzle-style positions.

The goal is diagnostic, not training: run LabZero and Stockfish on many FEN/EPD positions, rank the largest move losses, then turn repeated motifs into small engine regression packs.

## Layout

```text
experiments/puzzle/
  config.example.toml
  generator.example.toml
  lichess_puzzle_generator.py
  puzzle_oracle_miner.py
  puzzles/
    lichess/  # raw Lichess PGN dumps, ignored
    generated/  # generated EPD puzzle candidates, ignored
    sample/
      sample.epd
  out/       # generated JSONL, ignored
  reports/   # generated Markdown, ignored
```

Put puzzle files under `puzzles/<category>/`. Supported inputs are `.epd`, `.fen`, and `.txt` files with one position per line. Blank lines and `#` comments are ignored.

## Generate Puzzles From Lichess PGNs

Put raw Lichess PGN dumps under `experiments/puzzle/puzzles/lichess/`, for example:

```text
experiments/puzzle/puzzles/lichess/
  2016-03/
    lichess_db_standard_rated_2016-03.pgn
```

The generator streams the files, filters games where both players meet the Elo threshold, samples a small deterministic subset, and asks Stockfish for clear best-move gaps. Raw PGNs and generated puzzle runs are ignored by git.

Tiny reproducible sample:

```bash
lichess_bot/.venv/bin/python experiments/puzzle/lichess_puzzle_generator.py \
  --config experiments/puzzle/generator.example.toml \
  --max-games-scanned 2000 \
  --sample-games 5 \
  --max-puzzles 5 \
  --stockfish-nodes 10000 \
  --seed 1
```

Generated EPDs are written by category under `experiments/puzzle/puzzles/generated/latest/`, with a `candidates.jsonl` and `report.md` in the same run folder.

Feed generated puzzles into the existing LabZero-vs-Stockfish miner:

```bash
lichess_bot/.venv/bin/python experiments/puzzle/puzzle_oracle_miner.py \
  --puzzles-dir experiments/puzzle/puzzles/generated/latest \
  --max-positions 5
```

## Mine Existing Puzzle Folders

```bash
lichess_bot/.venv/bin/python experiments/puzzle/puzzle_oracle_miner.py \
  --config experiments/puzzle/config.example.toml
```

Useful overrides:

```bash
lichess_bot/.venv/bin/python experiments/puzzle/puzzle_oracle_miner.py \
  --puzzles-dir experiments/puzzle/puzzles \
  --labzero target/release/labzero \
  --stockfish /opt/homebrew/bin/stockfish \
  --max-positions 200 \
  --out experiments/puzzle/out/run.jsonl \
  --report experiments/puzzle/reports/run.md
```

## How To Use The Results

1. Sort the report by largest `loss_cp`.
2. Look for repeated motifs, not one-off weird positions.
3. Add 5-20 FENs for the motif to a verifier/regression pack.
4. Make one narrow engine change.
5. Re-run this miner and a small real-clock Stockfish smoke.

Keep large puzzle sets and generated output out of git.
