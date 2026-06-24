#!/usr/bin/env bash
# Resumable SPSA tuner for labzero's tunable eval parameters (see params.rs).
#
# Each iteration perturbs the whole parameter vector by a single random sign
# vector (Spall's simultaneous-perturbation trick), plays a short paired
# self-play match between the "plus" and "minus" candidates, estimates the
# gradient from the match score, and nudges the parameter vector uphill. State
# is checkpointed after every iteration, so a power-off resumes mid-run.
#
# This is local engine-vs-engine compute (no LLM tokens). The tuned vector is
# written to data/tune/<run>.best.params for the operator to confirm with the
# 3+2 gauntlet at the next human checkpoint -- SPSA optimizes a relative signal
# at fast time control; the gauntlet is the absolute band gate.
#
#   ITERS=300 GAMES_PER_ITER=8 MOVETIME_MS=40 ./scripts/host-spsa.sh
#   RUN_ID=spsa_s2 ITERS=500 ./scripts/host-spsa.sh        # named, resumable
#
# Env:
#   ENGINE=target/release/labzero   THREADS=1   HASH=16
#   ITERS=300            total SPSA iterations (target; resumes toward it)
#   GAMES_PER_ITER=8     games per iteration (even; paired colors)
#   MOVETIME_MS=40       per-move time for the fast tuning games
#   SEED=1               base RNG seed (resume is exact for a given seed)
#   RUN_ID=<id>          names the run so it resumes instead of restarting
#   OUT_DIR=data/tune
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE="${ENGINE:-${ROOT}/target/release/labzero}"
THREADS="${THREADS:-1}"
HASH="${HASH:-16}"
ITERS="${ITERS:-300}"
GAMES_PER_ITER="${GAMES_PER_ITER:-8}"
MOVETIME_MS="${MOVETIME_MS:-40}"
SEED="${SEED:-1}"
OUT_DIR="${OUT_DIR:-${ROOT}/data/tune}"
RUN_ID="${RUN_ID:-spsa_${ITERS}i_${GAMES_PER_ITER}g_mt${MOVETIME_MS}}"

if [[ ! -x "${ENGINE}" ]]; then
  echo "engine not executable: ${ENGINE}" >&2
  exit 1
fi

VENV="${ROOT}/.venv-host-test"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
  "${VENV}/bin/pip" install -q python-chess
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

mkdir -p "${OUT_DIR}"
STATE="${OUT_DIR}/${RUN_ID}.state.json"
LOG="${OUT_DIR}/${RUN_ID}.log"
BEST="${OUT_DIR}/${RUN_ID}.best.params"

export ENGINE THREADS HASH ITERS GAMES_PER_ITER MOVETIME_MS SEED STATE LOG BEST OUT_DIR RUN_ID

python3 - <<'PY'
import json
import math
import os
import random
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine

ENGINE = os.environ["ENGINE"]
THREADS = int(os.environ["THREADS"])
HASH = int(os.environ["HASH"])
ITERS = int(os.environ["ITERS"])
GAMES_PER_ITER = int(os.environ["GAMES_PER_ITER"])
MOVETIME = int(os.environ["MOVETIME_MS"]) / 1000.0
SEED = int(os.environ["SEED"])
STATE = Path(os.environ["STATE"])
LOG = Path(os.environ["LOG"])
BEST = Path(os.environ["BEST"])
OUT_DIR = Path(os.environ["OUT_DIR"])
RUN_ID = os.environ["RUN_ID"]

# name -> (default, lo, hi, c0, a0)
#   c0 = initial perturbation magnitude (param units)
#   a0 = initial learning step       (param units per unit gradient)
# Scales mirror each weight's natural magnitude so one SPSA step is meaningful.
# material.pawn is the eval anchor and is intentionally NOT tuned.
PARAM_SPEC = [
    ("material.knight", 320, 260, 400, 8, 6),
    ("material.bishop", 330, 260, 400, 8, 6),
    ("material.rook", 500, 420, 620, 12, 8),
    ("material.queen", 900, 760, 1100, 20, 12),
    ("mob.knight.mg", 4, 0, 12, 1, 1),
    ("mob.knight.eg", 3, 0, 12, 1, 1),
    ("mob.bishop.mg", 4, 0, 12, 1, 1),
    ("mob.bishop.eg", 4, 0, 12, 1, 1),
    ("mob.rook.mg", 2, 0, 10, 1, 1),
    ("mob.rook.eg", 3, 0, 10, 1, 1),
    ("mob.queen.mg", 1, 0, 8, 1, 1),
    ("mob.queen.eg", 1, 0, 8, 1, 1),
    ("bishop_pair", 25, 0, 60, 3, 2),
    ("rook_open", 15, 0, 40, 2, 2),
    ("rook_semi", 8, 0, 30, 2, 1),
]
NAMES = [s[0] for s in PARAM_SPEC]
DEFAULT = {s[0]: float(s[1]) for s in PARAM_SPEC}
LO = {s[0]: s[2] for s in PARAM_SPEC}
HI = {s[0]: s[3] for s in PARAM_SPEC}
C0 = {s[0]: float(s[4]) for s in PARAM_SPEC}
A0 = {s[0]: float(s[5]) for s in PARAM_SPEC}

# Standard Spall gain-sequence exponents.
ALPHA = 0.602
GAMMA = 0.101
A_STAB = max(10.0, 0.1 * ITERS)  # stabilizes early, large steps

# Short, balanced openings (played from both sides each iteration) so the
# match measures the parameter delta, not a colour or opening bias.
OPENINGS = [
    [],                                   # startpos
    ["e2e4", "e7e5"],
    ["d2d4", "d7d5"],
    ["c2c4", "e7e5"],
    ["e2e4", "c7c5"],
    ["d2d4", "g8f6", "c2c4", "e7e6"],
    ["g1f3", "d7d5", "g2g3"],
    ["e2e4", "e7e6", "d2d4", "d7d5"],
]


def clamp(name, v):
    return max(LO[name], min(HI[name], int(round(v))))


def write_params(theta, path):
    lines = [f"{n} {clamp(n, theta[n])}" for n in NAMES]
    path.write_text("\n".join(lines) + "\n")


def open_engine(params_path):
    eng = chess.engine.SimpleEngine.popen_uci(
        ENGINE, env={**os.environ, "LABZERO_EVAL_PARAMS": str(params_path)}
    )
    try:
        eng.configure({"Threads": THREADS, "Hash": HASH})
    except Exception:
        pass
    return eng


def play_game(white_eng, black_eng, opening):
    board = chess.Board()
    for uci in opening:
        mv = chess.Move.from_uci(uci)
        if mv in board.legal_moves:
            board.push(mv)
        else:
            break
    limit = chess.engine.Limit(time=MOVETIME)
    while not board.is_game_over(claim_draw=True):
        eng = white_eng if board.turn == chess.WHITE else black_eng
        try:
            res = eng.play(board, limit)
        except chess.engine.EngineError:
            return None
        if res.move is None:
            break
        board.push(res.move)
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return 0.5
    if outcome.winner is None:
        return 0.5
    return 1.0 if outcome.winner == chess.WHITE else 0.0


def match(theta_plus, theta_minus, n_games, rng):
    """Return plus-candidate's score fraction in [0,1] over n_games."""
    pp = OUT_DIR / f"{RUN_ID}.plus.params"
    pm = OUT_DIR / f"{RUN_ID}.minus.params"
    write_params(theta_plus, pp)
    write_params(theta_minus, pm)
    eng_plus = open_engine(pp)
    eng_minus = open_engine(pm)
    plus_points = 0.0
    played = 0
    try:
        for g in range(n_games):
            opening = OPENINGS[rng.randrange(len(OPENINGS))]
            plus_is_white = (g % 2 == 0)
            if plus_is_white:
                r = play_game(eng_plus, eng_minus, opening)
                if r is None:
                    continue
                plus_points += r
            else:
                r = play_game(eng_minus, eng_plus, opening)
                if r is None:
                    continue
                plus_points += (1.0 - r)
            played += 1
    finally:
        eng_plus.quit()
        eng_minus.quit()
    if played == 0:
        return 0.5, 0
    return plus_points / played, played


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {
        "iter": 0,
        "theta": dict(DEFAULT),
        "total_games": 0,
        "seed": SEED,
    }


def save_state(st):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2))
    tmp.replace(STATE)


def log(msg):
    line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def main():
    st = load_state()
    theta = {n: float(st["theta"].get(n, DEFAULT[n])) for n in NAMES}
    k0 = int(st["iter"])
    if k0 >= ITERS:
        log(f"already at iter {k0} >= {ITERS}; nothing to do")
        write_params(theta, BEST)
        return
    log(f"resume run={RUN_ID} at iter {k0}/{ITERS}, total_games={st['total_games']}")

    for k in range(k0 + 1, ITERS + 1):
        # Deterministic per-iteration RNG so resume reproduces the same run.
        rng = random.Random((st["seed"] << 20) ^ k)
        ck = {n: C0[n] / (k ** GAMMA) for n in NAMES}
        ak = {n: A0[n] / ((k + A_STAB) ** ALPHA) for n in NAMES}
        delta = {n: (1.0 if rng.random() < 0.5 else -1.0) for n in NAMES}

        theta_plus = {n: theta[n] + ck[n] * delta[n] for n in NAMES}
        theta_minus = {n: theta[n] - ck[n] * delta[n] for n in NAMES}

        score_plus, played = match(theta_plus, theta_minus, GAMES_PER_ITER, rng)
        st["total_games"] += played

        # y_plus - y_minus = 2*score_plus - 1; ghat_i = (y+ - y-)/(2 ck_i delta_i).
        # Gradient ASCENT (maximize score): theta += ak * ghat.
        y_diff = 2.0 * score_plus - 1.0
        for n in NAMES:
            ghat = y_diff / (2.0 * ck[n] * delta[n])
            theta[n] += ak[n] * ghat
            theta[n] = max(float(LO[n]), min(float(HI[n]), theta[n]))

        st["iter"] = k
        st["theta"] = theta
        save_state(st)
        write_params(theta, BEST)

        if k % 10 == 0 or k == k0 + 1:
            snap = " ".join(f"{n.split('.')[-1]}={clamp(n, theta[n])}" for n in NAMES[:6])
            log(f"iter {k}/{ITERS} plus_score={score_plus:.3f} games={st['total_games']} | {snap}")

    log(f"done: {ITERS} iters, {st['total_games']} games. best -> {BEST}")
    # Clean up scratch candidate files.
    for suffix in (".plus.params", ".minus.params"):
        p = OUT_DIR / f"{RUN_ID}{suffix}"
        if p.exists():
            p.unlink()


if __name__ == "__main__":
    main()
PY
