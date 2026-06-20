#!/usr/bin/env bash
# Quick local game: labzero (host) vs Stockfish (host). No Lichess, no Podman.
#
#   export STOCKFISH="/path/to/stockfish-macos-m1-apple-silicon"
#   ./scripts/host-vs-stockfish.sh
#
# Optional: DEPTH=3 PLIES=40 ./scripts/host-vs-stockfish.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABZERO="${LABZERO_ENGINE:-${ROOT}/target/release/labzero}"
STOCKFISH="${STOCKFISH:?Set STOCKFISH to your Stockfish binary path}"
DEPTH="${DEPTH:-2}"
PLIES="${PLIES:-80}"

if [[ ! -x "${LABZERO}" ]]; then
  echo "labzero not found. Run: ./scripts/build-host-engine.sh" >&2
  exit 1
fi
if [[ ! -x "${STOCKFISH}" ]]; then
  echo "Stockfish not executable: ${STOCKFISH}" >&2
  exit 1
fi

VENV="${ROOT}/.venv-host-test"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
  "${VENV}/bin/pip" install -q python-chess
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

python3 - "${LABZERO}" "${STOCKFISH}" "${DEPTH}" "${PLIES}" <<'PY'
import sys
import chess
import chess.engine

labzero, stockfish, depth, max_plies = sys.argv[1:5]
depth = int(depth)
max_plies = int(max_plies)

print(f"labzero:    {labzero}")
print(f"stockfish:  {stockfish}")
print(f"depth={depth} max_plies={max_plies}")
print()

with chess.engine.SimpleEngine.popen_uci(labzero) as w, chess.engine.SimpleEngine.popen_uci(
    stockfish
) as b:
    board = chess.Board()
    for ply in range(max_plies):
        if board.is_game_over():
            break
        eng = w if board.turn == chess.WHITE else b
        result = eng.play(board, chess.engine.Limit(depth=depth))
        if result.move is None:
            print(f"ply {ply}: no move from engine")
            sys.exit(1)
        if result.move not in board.legal_moves:
            print(f"ply {ply}: illegal move {result.move}")
            sys.exit(1)
        board.push(result.move)
        side = "W" if not board.turn else "B"
        print(f"{ply + 1:3d}. {side} {result.move.uci()}")

print()
print(f"Result: {board.result()} ({board.status()})")
print("host-vs-stockfish: PASS")
PY
