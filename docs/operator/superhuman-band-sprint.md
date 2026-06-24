# Superhuman-band sprint — operator guide

How to run the `codex/superhuman-band` pipeline yourself: measure Elo, tune eval, train NNUE, gate changes, kill jobs, resume, read logs.

**Branch:** `codex/superhuman-band` (not merged to `main` yet).

**North star:** engine-vs-engine at **3+2** against limited Stockfish and handicapped PlentyChess/Reckless. Claim only the bracket you actually pass (32-game anchors, 16-game probes). See `docs/strength/ladder.md` for the perf formula.

---

## 0. One-time setup

```bash
cd /path/to/labzero
git checkout codex/superhuman-band

# Native release binary -> target/release/labzero (NOT .cargo-target/)
./scripts/build-host-engine.sh

# Opponents (already in repo layout if you followed the plan)
export STOCKFISH=/opt/homebrew/bin/stockfish   # your path
ls engines/reckless-macos engines/PlentyChess-* 2>/dev/null || true

# Python venv (auto-created by scripts on first run)
# SPSA + gauntlet need: python-chess
# NNUE trainer needs: pip install torch  (MPS on Apple Silicon)
.venv-host-test/bin/pip install python-chess torch
```

**Build pitfall:** If `CARGO_TARGET_DIR` is set (Podman CI, some IDE sandboxes), you get a stale/wrong binary. Host scripts expect `target/release/labzero`. Always use `./scripts/build-host-engine.sh` or:

```bash
unset CARGO_TARGET_DIR
cargo build --release --manifest-path engine/Cargo.toml
```

---

## 1. What a “sprint” is

1. **Baseline** — gauntlet row(s) with the current build.
2. **Change** — search speed (already on branch), SPSA eval tune, or NNUE train.
3. **Gate** — gauntlet again with the candidate (tuned params or net). Keep only if score goes up vs baseline at the same TC/opponent/handicap.
4. **Stop** — human checkpoint; unattended jobs can keep running locally between sessions.

Generated artifacts live under `data/` (gitignored) and `docs/strength/` (gauntlet rows you choose to keep).

---

## 2. Measuring strength (gauntlet)

### Stockfish limited Elo (primary gate)

```bash
export STOCKFISH=/opt/homebrew/bin/stockfish

# 32-game anchor @ SF 2800, 3+2, labzero 4 threads
GAMES=32 SF_ELO=2800 TC_SEC=3 TC_INC=2 A_THREADS=4 \
  ./scripts/host-gauntlet.sh
```

Outputs (created immediately, grow per game):

| File | Purpose |
|------|---------|
| `docs/strength/gauntlet_<opponent>_<strength>_3+2_32g.txt` | W-L-D, score %, perf Elo |
| `docs/strength/gauntlet_....pgn` | Games |
| `docs/strength/gauntlet_....state.json` | Resume cursor |

**Live tail:**

```bash
tail -f docs/strength/gauntlet_*.txt
```

**Resume after kill/reboot** — rerun the **same** command (same `RUN_ID` is auto-derived from env; or set `RUN_ID=my_run_2800` explicitly both times).

### Handicapped opponents (no UCI_Elo)

```bash
# Reckless capped to ~200k nodes/move — calibrate B_NODES for your band
GAMES=32 ENGINE_B=engines/reckless-macos B_NAME=reckless B_NODES=200000 \
  ANCHOR=3000 TC_SEC=3 TC_INC=2 ./scripts/host-gauntlet.sh
```

Record `B_NODES` / `B_MOVETIME` / `SF_ELO` on every row you trust.

### Perf Elo (approx)

When score ≈ 50% vs anchor `A`:

`perf ≈ A + 400 * log10(p / (1-p))` where `p = (W + 0.5*D) / N`.

Scripts print this at the end. Not FIDE/CCRL — project-relative only.

### Legacy single-opponent script

`./scripts/host-benchmark.sh` still works (labzero vs SF only). Prefer `host-gauntlet.sh` for the superhuman-band ladder (PlentyChess/Reckless + resume).

---

## 3. Self-play data (feeds SPSA + NNUE)

Fast fixed-depth games; **not** the 3+2 gauntlet TC.

```bash
# 1000 games, depth 4, deterministic seed
target/release/labzero selfplay data/selfplay/sp.txt 1000 4 12345
```

| File | Purpose |
|------|---------|
| `data/selfplay/sp.txt` | Lines: `fen;result;cp` (stm-relative) |
| `data/selfplay/sp.games` | Resume: last completed game index |

**Resume:** run the same command again with a **higher** game count — it appends from `sp.games`, does not restart.

```bash
# Started 1000, want 2000 total:
target/release/labzero selfplay data/selfplay/sp.txt 2000 4 12345
```

**Background + log:**

```bash
nohup target/release/labzero selfplay data/selfplay/sp.txt 50000 4 12345 \
  > data/selfplay/sp.log 2>&1 &
echo $! > data/selfplay/sp.pid
tail -f data/selfplay/sp.log
```

**Kill:**

```bash
kill $(cat data/selfplay/sp.pid)    # or: pkill -f 'labzero selfplay'
```

Safe to kill anytime; resume as above.

---

## 4. SPSA eval tuning (Sprint 2 lever)

Tunes 15 weights in `engine/src/params.rs` via `LABZERO_EVAL_PARAMS`.

```bash
# Default-ish overnight run (fast 40ms/move tuning games)
RUN_ID=spsa_s2 ITERS=300 GAMES_PER_ITER=8 MOVETIME_MS=40 \
  ./scripts/host-spsa.sh
```

| File | Purpose |
|------|---------|
| `data/tune/<RUN_ID>.state.json` | iter, theta, seed — **resume** |
| `data/tune/<RUN_ID>.log` | Human log |
| `data/tune/<RUN_ID>.best.params` | Best vector so far |

**Resume:** same `RUN_ID` (and same `SEED`); bump `ITERS` if you want more:

```bash
RUN_ID=spsa_s2 ITERS=500 GAMES_PER_ITER=8 MOVETIME_MS=40 \
  ./scripts/host-spsa.sh
# log: "resume run=spsa_s2 at iter 300/500"
```

**Background:**

```bash
nohup env RUN_ID=spsa_s2 ITERS=300 ./scripts/host-spsa.sh \
  > data/tune/spsa.out 2>&1 &
tail -f data/tune/spsa_s2.log
```

**Kill:** `pkill -f host-spsa` or kill the `nohup` PID. State saved every iteration.

### Gate a tuned candidate

SPSA only optimizes a fast signal. Confirm on the real gauntlet:

```bash
export LABZERO_EVAL_PARAMS=data/tune/spsa_s2.best.params

GAMES=32 SF_ELO=2600 TC_SEC=3 TC_INC=2 \
  ENGINE_A=target/release/labzero ./scripts/host-gauntlet.sh
```

Compare W-L-D / perf to a baseline row **without** `LABZERO_EVAL_PARAMS`. Keep params only if the anchor row improves (or use your SPRT threshold).

To ship permanently, bake winners into `params.rs` defaults or always export `LABZERO_EVAL_PARAMS` in your gauntlet env.

---

## 5. NNUE train + verify (Sprint 3–4 lever)

**Off by default.** Classical eval unchanged until you load a net.

### Train (PyTorch; MPS on Mac if available)

```bash
python scripts/host-nnue-train.py \
  --data data/selfplay/sp.txt \
  --hidden 256 \
  --epochs 30 \
  --out data/nnue/net.nnue \
  --ckpt data/nnue/train.ckpt
```

| File | Purpose |
|------|---------|
| `data/nnue/train.ckpt` | Resume model+optimizer+epoch |
| `data/nnue/net.nnue` | Quantized `LZN1` file for the engine |

**Resume:** rerun the same command; prints `resumed from ... at epoch N`.

**Background:**

```bash
nohup .venv-host-test/bin/python scripts/host-nnue-train.py \
  --data data/selfplay/sp.txt --hidden 256 --epochs 30 \
  --out data/nnue/net.nnue --ckpt data/nnue/train.ckpt \
  > data/nnue/train.log 2>&1 &
tail -f data/nnue/train.log
```

### Parity gate (must pass before trusting a net)

```bash
./scripts/host-nnue-verify.sh data/nnue/net.nnue
# PARITY OK: engine integer inference matches the Python reference.
```

### Use the net in search

**Env (CLI / scripts):**

```bash
export LABZERO_NNUE=data/nnue/net.nnue
target/release/labzero eval "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
```

**UCI (gauntlet / GUI):**

```
setoption name NnueFile value data/nnue/net.nnue
```

**Gauntlet with NNUE:**

```bash
export LABZERO_NNUE=data/nnue/net.nnue
GAMES=32 SF_ELO=2800 TC_SEC=3 TC_INC=2 ./scripts/host-gauntlet.sh
```

Ship the net only if gauntlet band improves at equal TC vs classical-only baseline.

---

## 6. Process cheat sheet

| Job | Find | Kill | Resume |
|-----|------|------|--------|
| Self-play | `pgrep -fl 'labzero selfplay'` | `pkill -f 'labzero selfplay'` | Same out path + higher game count |
| SPSA | `pgrep -fl host-spsa` | `pkill -f host-spsa` | Same `RUN_ID`, same `SEED` |
| Gauntlet | `pgrep -fl host-gauntlet` | `pkill -f host-gauntlet` | Same env / `RUN_ID` |
| NNUE train | `pgrep -fl host-nnue-train` | kill PID | Same `--ckpt` path |

**CPU budget:** 11 cores on your machine — don’t run 12-thread gauntlet + self-play + SPSA at full blast. Typical: gauntlet `A_THREADS=4`, tuning jobs `THREADS=1`.

---

## 7. Suggested first session (manual)

```bash
# 1) Build
./scripts/build-host-engine.sh

# 2) Baseline row
export STOCKFISH=...
GAMES=32 SF_ELO=2500 TC_SEC=3 TC_INC=2 ./scripts/host-gauntlet.sh

# 3) Generate data (small smoke, then scale)
target/release/labzero selfplay data/selfplay/sp.txt 500 4 1

# 4) Short SPSA smoke
RUN_ID=smoke ITERS=20 GAMES_PER_ITER=4 MOVETIME_MS=20 ./scripts/host-spsa.sh

# 5) Gate candidate (if SPSA moved weights)
export LABZERO_EVAL_PARAMS=data/tune/smoke.best.params
GAMES=16 SF_ELO=2500 TC_SEC=3 TC_INC=2 ./scripts/host-gauntlet.sh
```

16-game probe = quick signal; 32-game before you claim a sprint win.

---

## 8. What’s already on the branch (no action needed)

- Magic bitboards + mailbox + faster movegen (~3.6× perft 6, ~1.4× depth-12 search vs pre-branch).
- `scripts/host-gauntlet.sh` — resumable ladder.
- `engine/src/selfplay.rs` — data producer.
- `engine/src/params.rs` + `scripts/host-spsa.sh` — tunable classical eval.
- `engine/src/nnue.rs` + trainer/verify scripts — NNUE path (disabled until you load a net).

**Honest scope:** reaching ≈2800–3200 perf on the gauntlet needs real compute (big self-play dump, long SPSA, NNUE epochs). This guide is how to run that locally; the LLM sprint built the machinery, not the final Elo number.
