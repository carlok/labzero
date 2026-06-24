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

**Live tail** (use your `RUN_ID` if you set one, else the auto name `gauntlet_<opponent>_elo2500_3+2_32g.txt`):

```bash
tail -f docs/strength/baseline_sf2500.txt          # when RUN_ID=baseline_sf2500
# or without custom RUN_ID:
tail -f docs/strength/gauntlet_stockfish_elo2500_3+2_32g.txt
```

**Auto-record perf Elo** (appends row to `docs/strength/superhuman-band.md` + `docs/lab_log.md`):

```bash
RECORD=1 GAMES=32 SF_ELO=2500 TC_SEC=3 TC_INC=2 A_THREADS=4 ./scripts/host-gauntlet.sh
```

Or after the fact:

```bash
./scripts/host-record-gauntlet.sh docs/strength/gauntlet_<...>.txt
./scripts/host-record-gauntlet.sh --latest   # newest complete run in docs/strength/
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

## 6. Kill everything before you start

Stale background jobs steal CPU and can wedge UCI (duplicate engines, wrong binary path). Run this **before** kicking off a new gauntlet / self-play / SPSA / NNUE session.

### One command

```bash
./scripts/host-kill-sprint.sh
```

Stops self-play, gauntlet, SPSA, NNUE train, benchmark, orphaned `target/release/labzero` and `stockfish` children, and any `data/*/*.pid` from `nohup`. Then checks immediately, waits 2s, re-checks; if anything survives, sends `SIGKILL` and reports leftovers.

List only (no signals):

```bash
./scripts/host-kill-sprint.sh --check
```

Killing mid-run is safe — jobs resume from their state files (sections 3–5). **Do not** delete `data/**/**.state.json`, `*.games`, `*.ckpt`, or gauntlet `*.state.json` unless you want a fresh run.

### Manual equivalent

```bash
pkill -f 'labzero selfplay'     2>/dev/null || true
pkill -f 'host-gauntlet'        2>/dev/null || true
pkill -f 'host-spsa'            2>/dev/null || true
pkill -f 'host-nnue-train'      2>/dev/null || true
pkill -f 'host-benchmark'       2>/dev/null || true
pkill -f 'target/release/labzero'  2>/dev/null || true
pkill stockfish 2>/dev/null || true

for f in data/selfplay/*.pid data/tune/*.pid data/nnue/*.pid; do
  [[ -f "$f" ]] && kill "$(cat "$f")" 2>/dev/null || true
done

pgrep -fl 'labzero|host-gauntlet|host-spsa|host-nnue' || echo "nothing sprint-related running"
sleep 2
pgrep -fl 'labzero|host-gauntlet|host-spsa|host-nnue' || echo "nothing sprint-related running"
```

If the second `pgrep` still shows processes, use `./scripts/host-kill-sprint.sh` (it escalates to `SIGKILL`) or `pkill -9 -f '<pattern>'` by hand.

### See what's running

```bash
pgrep -fl 'labzero|host-gauntlet|host-spsa|host-nnue|host-benchmark|stockfish|reckless|PlentyChess'
```

### Process cheat sheet

| Job | Find | Kill | Resume |
|-----|------|------|--------|
| Self-play | `pgrep -fl 'labzero selfplay'` | `pkill -f 'labzero selfplay'` | Same out path + higher game count |
| SPSA | `pgrep -fl host-spsa` | `pkill -f host-spsa` | Same `RUN_ID`, same `SEED` |
| Gauntlet | `pgrep -fl host-gauntlet` | `pkill -f host-gauntlet` | Same env / `RUN_ID` |
| NNUE train | `pgrep -fl host-nnue-train` | `pkill -f host-nnue-train` | Same `--ckpt` path |

**CPU budget:** 11 cores on your machine — don’t run 12-thread gauntlet + self-play + SPSA at full blast. Typical: gauntlet `A_THREADS=4`, tuning jobs `THREADS=1`.

---

## 7. First real session (smoke → scale)

Copy-paste friendly. Run from repo root on `codex/superhuman-band`.

```bash
# --- clean slate (always first) ---
./scripts/host-kill-sprint.sh

# --- 1) build native binary -> target/release/labzero ---
./scripts/build-host-engine.sh

export STOCKFISH=/opt/homebrew/bin/stockfish   # fix path

# --- 2) baseline gauntlet (32-game anchor) ---
# RECORD=1 -> auto-append perf to docs/strength/superhuman-band.md
RECORD=1 RUN_ID=baseline_sf2500 \
  GAMES=32 SF_ELO=2500 TC_SEC=3 TC_INC=2 A_THREADS=4 \
  ./scripts/host-gauntlet.sh
# tail while running:
tail -f docs/strength/baseline_sf2500.txt
# read perf at end of .txt footer, or open docs/strength/superhuman-band.md

# --- 3) self-play data: smoke then scale ---
# smoke (~minutes): 500 games, depth 4, seed 1
target/release/labzero selfplay data/selfplay/sp.txt 500 4 1

# scale (same file, same seed — APPENDS from game 501, does not restart):
target/release/labzero selfplay data/selfplay/sp.txt 5000 4 1

# production scale (hours/days, background):
nohup target/release/labzero selfplay data/selfplay/sp.txt 50000 4 1 \
  > data/selfplay/sp.log 2>&1 &
echo $! > data/selfplay/sp.pid
tail -f data/selfplay/sp.log
# kill anytime: ./scripts/host-kill-sprint.sh
# resume: bump total again, e.g. 100000

# --- 4) SPSA: smoke then scale ---
# smoke (~minutes): 20 iters, 4 games/iter, 20ms/move
RUN_ID=spsa_smoke ITERS=20 GAMES_PER_ITER=4 MOVETIME_MS=20 \
  ./scripts/host-spsa.sh
# best weights: data/tune/spsa_smoke.best.params

# scale (NEW run_id for a real tune; or same RUN_ID to continue smoke iters):
RUN_ID=spsa_s2 ITERS=300 GAMES_PER_ITER=8 MOVETIME_MS=40 SEED=1 \
  ./scripts/host-spsa.sh
# resume after kill: same RUN_ID + same SEED, bump ITERS (e.g. 500)
# log:  tail -f data/tune/spsa_s2.log
# background:
#   nohup env RUN_ID=spsa_s2 ITERS=300 GAMES_PER_ITER=8 MOVETIME_MS=40 \
#     ./scripts/host-spsa.sh > data/tune/spsa.out 2>&1 &

# --- 5) gate tuned params (16-game probe, then 32-game confirm) ---
export LABZERO_EVAL_PARAMS=data/tune/spsa_s2.best.params   # or spsa_smoke for smoke

RECORD=1 RUN_ID=gate_sf2500_params \
  GAMES=16 SF_ELO=2500 TC_SEC=3 TC_INC=2 A_THREADS=4 \
  ./scripts/host-gauntlet.sh
# if probe looks good vs baseline (section 2, no params):
RECORD=1 RUN_ID=gate_sf2500_params_32g \
  GAMES=32 SF_ELO=2500 TC_SEC=3 TC_INC=2 A_THREADS=4 \
  ./scripts/host-gauntlet.sh

unset LABZERO_EVAL_PARAMS   # back to classical defaults
```

**Smoke vs scale summary**

| Step | Smoke | Scale |
|------|-------|-------|
| Self-play | `... sp.txt 500 4 1` | same path, higher total: `5000`, `50000`, … |
| SPSA | `RUN_ID=spsa_smoke ITERS=20 ...` | new `RUN_ID=spsa_s2 ITERS=300 ...` or resume same id |
| Gauntlet gate | `GAMES=16` probe | `GAMES=32` anchor before claiming Elo |

**Optional — NNUE after enough self-play** (thousands+ positions):

```bash
.venv-host-test/bin/pip install torch   # once
.venv-host-test/bin/python scripts/host-nnue-train.py \
  --data data/selfplay/sp.txt --hidden 256 --epochs 30 \
  --out data/nnue/net.nnue --ckpt data/nnue/train.ckpt
./scripts/host-nnue-verify.sh data/nnue/net.nnue
export LABZERO_NNUE=data/nnue/net.nnue
RECORD=1 GAMES=32 SF_ELO=2500 TC_SEC=3 TC_INC=2 ./scripts/host-gauntlet.sh
```

Compare rows in `docs/strength/superhuman-band.md`. Keep a change only if perf beats baseline at the same opponent/TC/handicap.

---

## 8. What’s already on the branch (no action needed)

- Magic bitboards + mailbox + faster movegen (~3.6× perft 6, ~1.4× depth-12 search vs pre-branch).
- `scripts/host-gauntlet.sh` — resumable ladder.
- `engine/src/selfplay.rs` — data producer.
- `engine/src/params.rs` + `scripts/host-spsa.sh` — tunable classical eval.
- `engine/src/nnue.rs` + trainer/verify scripts — NNUE path (disabled until you load a net).

**Honest scope:** reaching ≈2800–3200 perf on the gauntlet needs real compute (big self-play dump, long SPSA, NNUE epochs). This guide is how to run that locally; the LLM sprint built the machinery, not the final Elo number.

---

## 9. Three-script sprint loop

Three **independent** wrappers. You choose order and timing. They do **not** chain automatically.

| Script | Role | Needs `sp.txt`? |
|--------|------|-----------------|
| `host-sprint-spsa.sh` | classical eval tune | **No** |
| `host-sprint-nnue.sh` | self-play → train net | **Yes** (creates or appends) |
| `host-sprint-gate.sh` | measure Elo + ladder row | **No** |

### Serial vs parallel

```
SERIAL (safe, one job at a time on 11 cores)
────────────────────────────────────────────
  SPSA ──finishes──► export params ──► GATE ──► read ladder
  NNUE ──finishes──► export nnue   ──► GATE ──► read ladder

PARALLEL (OK on idle cores — never overlap GATE)
────────────────────────────────────────────
  SPSA ─────────────────────────────► done
  NNUE (self-play phase) ───────────► train ──► done
         ▲ SKIP_KILL=1 if SPSA already running

  GATE only when BOTH heavy jobs are stopped:
       ./scripts/host-kill-sprint.sh
       ./scripts/host-sprint-gate.sh 2700
```

| Combination | OK? | Why |
|-------------|-----|-----|
| SPSA then GATE | **serial** | tune → measure |
| NNUE then GATE | **serial** | train → measure |
| SPSA ∥ NNUE | **parallel** | different pipelines; watch CPU (`THREADS=1` on SPSA) |
| GATE ∥ anything | **no** | gate spawns labzero+SF; kills others first |
| SPSA ∥ self-play inside NNUE | **tight** | 11 cores; prefer SPSA alone, then `SKIP_SELFPLAY=1` NNUE train only |

**Rule:** `host-sprint-gate.sh` always kills sprint jobs first. Run gate alone when you want a clean measurement.

---

### CLI / env parameters

#### 1) `host-sprint-spsa.sh` — no positional args (env only)

```bash
RUN_ID=spsa_s2 \
ITERS=300 \
GAMES_PER_ITER=8 \
MOVETIME_MS=40 \
SEED=1 \
THREADS=1 \
ENGINE=target/release/labzero \
  ./scripts/host-sprint-spsa.sh
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `RUN_ID` | `spsa_s2` | names `data/tune/<RUN_ID>.{state.json,log,best.params}` |
| `ITERS` | `500` | SPSA iterations (resume: same `RUN_ID`+`SEED`, higher `ITERS`) |
| `GAMES_PER_ITER` | `8` | paired mini-match games per iteration |
| `MOVETIME_MS` | `40` | ms/move in tuning games (not 3+2) |
| `SEED` | `1` | RNG; keep fixed when resuming |
| `THREADS` | `1` | labzero threads during SPSA |

**After:** `export LABZERO_EVAL_PARAMS=data/tune/<RUN_ID>.best.params`

#### 2) `host-sprint-nnue.sh` — no positional args (env only)

```bash
SELFPLAY_GAMES=10000 \
SELFPLAY_DEPTH=4 \
SELFPLAY_SEED=1 \
SELFPLAY_OUT=data/selfplay/sp.txt \
HIDDEN=256 \
EPOCHS=30 \
SKIP_SELFPLAY=0 \
SKIP_KILL=0 \
  ./scripts/host-sprint-nnue.sh
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `SELFPLAY_GAMES` | `10000` | **total** games in `sp.txt` (appends if resuming) |
| `SELFPLAY_DEPTH` | `4` | search depth per self-play move |
| `SELFPLAY_SEED` | `1` | game RNG seed |
| `SELFPLAY_OUT` | `data/selfplay/sp.txt` | position file (`fen;result;cp`) |
| `SKIP_SELFPLAY` | `0` | `1` = train only on existing `sp.txt` |
| `SKIP_KILL` | `0` | `1` = don't kill other jobs (run ∥ SPSA) |
| `HIDDEN` | `256` | net width |
| `EPOCHS` | `30` | training epochs (resume via `CKPT`) |
| `OUT_NET` | `data/nnue/net.nnue` | exported `LZN1` file |
| `CKPT` | `data/nnue/train.ckpt` | resume checkpoint |

**After:** `export LABZERO_NNUE=data/nnue/net.nnue` (or both params + nnue for gate)

#### 3) `host-sprint-gate.sh` — positional CLI

```bash
./scripts/host-sprint-gate.sh <SF_ELO> [GAMES]
```

| Argument / env | Default | Meaning |
|----------------|---------|---------|
| `$1` **SF_ELO** | *(required)* | Stockfish `UCI_Elo` opponent |
| `$2` **GAMES** | `16` | `16` = probe, `32` = anchor |
| `RUN_ID` | `gate_sf<ELO>_<GAMES>g` | log basename under `docs/strength/` |
| `TC_SEC` / `TC_INC` | `3` / `2` | 3+2 wtime |
| `A_THREADS` | `4` | labzero threads |
| `STOCKFISH` | *(required env)* | path to Stockfish binary |
| `LABZERO_EVAL_PARAMS` | unset | optional tuned params file |
| `LABZERO_NNUE` | unset | optional net file |

Examples:

```bash
./scripts/host-sprint-gate.sh 2600          # 16-game probe @ SF 2600
./scripts/host-sprint-gate.sh 2700 32       # 32-game anchor @ SF 2700
RUN_ID=confirm_2800 ./scripts/host-sprint-gate.sh 2800 32
```

---

### Use case: one weekend, three shells

You are at **perf ≈2624** (baseline @ SF2500). Goal: classical tune toward **2700 band**, start NNUE in background, gate when you sit down at the machine.

**Friday night — start compute, walk away**

```bash
export STOCKFISH=/opt/homebrew/bin/stockfish
./scripts/build-host-engine.sh

# Shell 1: SPSA (background, ~hours)
RUN_ID=spsa_s2 ITERS=300 GAMES_PER_ITER=8 MOVETIME_MS=40 SEED=1 \
  nohup ./scripts/host-sprint-spsa.sh > data/tune/spsa.out 2>&1 &

# Shell 2: NNUE data + train (parallel if cores free; else run after SPSA)
# Option A — parallel (SPSA uses little CPU):
SELFPLAY_GAMES=10000 SKIP_KILL=1 \
  nohup ./scripts/host-sprint-nnue.sh > data/nnue/run.log 2>&1 &

# Option B — serial next morning: skip self-play if 500 games already exist:
# SKIP_SELFPLAY=1 EPOCHS=30 ./scripts/host-sprint-nnue.sh
```

**Saturday — SPSA done, gate classical**

```bash
tail data/tune/spsa_s2.log    # wait for "done: 300 iters"

export LABZERO_EVAL_PARAMS=data/tune/spsa_s2.best.params
unset LABZERO_NNUE            # classical only for this check

# Shell 3: ladder probes (serial — each run kills the previous)
./scripts/host-sprint-gate.sh 2600          # 16g — need ~≥53%
./scripts/host-sprint-gate.sh 2700          # 16g — stop if <~53%
./scripts/host-sprint-gate.sh 2700 32       # 32g confirm if 2700 probe passed

cat docs/strength/superhuman-band.md
```

**Sunday — NNUE done, gate net**

```bash
# host-nnue-verify.sh already ran inside host-sprint-nnue.sh
export LABZERO_NNUE=data/nnue/net.nnue
# keep or drop params — your call:
# export LABZERO_EVAL_PARAMS=data/tune/spsa_s2.best.params

./scripts/host-sprint-gate.sh 2600
./scripts/host-sprint-gate.sh 2700 16

# Keep whichever config wins on ladder; discard the loser.
```

**Loop again next week:** bump `ITERS` / `SELFPLAY_GAMES` / next SF rung. Gate only when you care about the number — not after every code edit.

---

### Quick reference

```bash
# 1 — tune
RUN_ID=spsa_s2 ITERS=300 ./scripts/host-sprint-spsa.sh

# 2 — net
SELFPLAY_GAMES=10000 ./scripts/host-sprint-nnue.sh

# 3 — measure (after kill, with exports set)
export LABZERO_EVAL_PARAMS=data/tune/spsa_s2.best.params
./scripts/host-sprint-gate.sh 2700 16
```

SPSA and NNUE never require each other. Gate is the shared scoreboard.


