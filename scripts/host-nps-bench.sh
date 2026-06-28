#!/usr/bin/env bash
# Reproducible host NPS probe for the native LabZero binary.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

ENGINE="${LABZERO_ENGINE:-${ROOT}/target/release/labzero}"
OUT_DIR="${OUT_DIR:-${ROOT}/docs/perf}"
DEPTH="${DEPTH:-8}"
HASH="${HASH:-64}"
THREADS_LIST="${THREADS_LIST:-1 4 8}"
PYTHON_BIN="${PYTHON:-python3}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${OUT_DIR}/nps_${STAMP}.tsv"

FENS=(
  "startpos"
  "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 2 3"
  "r2q1rk1/ppp2ppp/2n1bn2/3pp3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 8"
  "8/5pk1/6p1/2Pp4/3Pp1P1/4P2P/5PK1/8 w - - 0 41"
)

if [[ ! -x "${ENGINE}" ]]; then
  echo "host-nps-bench: engine not executable: ${ENGINE}" >&2
  echo "Run ./scripts/build-host-engine.sh first." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

{
  printf "stamp\tcommit\tengine\tthreads\thash_mb\tdepth\tfen_id\tbestmove\tnodes\tnps\ttime_ms\n"
} >"${OUT}"

run_one() {
  local threads="$1"
  local fen_id="$2"
  local fen="$3"
  local info bestmove nodes nps time_ms

  local output
  output="$(
    env -u LABZERO_NNUE -u LABZERO_NNUE_MODE -u LABZERO_NNUE_SCALE \
      -u LABZERO_POLICY -u LABZERO_POLICY_MODE -u LABZERO_EVAL_PARAMS \
      LABZERO_ROOT_POLICY=raw ENGINE="${ENGINE}" THREADS="${threads}" HASH="${HASH}" DEPTH="${DEPTH}" FEN="${fen}" \
      "${PYTHON_BIN}" - <<'PY'
import os
import subprocess
import sys

engine = os.environ["ENGINE"]
threads = os.environ["THREADS"]
hash_mb = os.environ["HASH"]
depth = os.environ["DEPTH"]
fen = os.environ["FEN"]

proc = subprocess.Popen(
    [engine],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
    bufsize=1,
)

def send(line: str) -> None:
    assert proc.stdin is not None
    proc.stdin.write(line + "\n")
    proc.stdin.flush()

def read_until(prefix: str) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="")
        if line.startswith(prefix):
            return
    raise RuntimeError(f"engine exited before {prefix}")

send("uci")
read_until("uciok")
send("isready")
read_until("readyok")
send(f"setoption name Threads value {threads}")
send(f"setoption name Hash value {hash_mb}")
send("ucinewgame")
if fen == "startpos":
    send("position startpos")
else:
    send(f"position fen {fen}")
send(f"go depth {depth}")
read_until("bestmove")
send("quit")
try:
    proc.wait(timeout=2)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait(timeout=2)
PY
  )"

  info="$(printf "%s\n" "${output}" | awk '/^info depth / { line=$0 } END { print line }')"
  bestmove="$(printf "%s\n" "${output}" | awk '/^bestmove / { print $2; exit }')"
  nodes="$(printf "%s\n" "${info}" | awk '{ for (i=1; i<=NF; i++) if ($i=="nodes") { print $(i+1); exit } }')"
  nps="$(printf "%s\n" "${info}" | awk '{ for (i=1; i<=NF; i++) if ($i=="nps") { print $(i+1); exit } }')"
  time_ms="$(printf "%s\n" "${info}" | awk '{ for (i=1; i<=NF; i++) if ($i=="time") { print $(i+1); exit } }')"

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
    "${STAMP}" "${COMMIT}" "${ENGINE}" "${threads}" "${HASH}" "${DEPTH}" \
    "${fen_id}" "${bestmove:-?}" "${nodes:-0}" "${nps:-0}" "${time_ms:-0}" \
    | tee -a "${OUT}"
}

for threads in ${THREADS_LIST}; do
  for i in "${!FENS[@]}"; do
    run_one "${threads}" "$((i + 1))" "${FENS[$i]}"
  done
done

echo "Saved: ${OUT}"
