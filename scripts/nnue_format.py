#!/usr/bin/env python3
"""Shared NNUE feature/format code for labzero (host side).

This is the single source of truth, on the Python side, for:
  * feature extraction (FEN -> active input indices, per perspective),
  * the quantization scheme, and
  * the `LZN1` binary layout the Rust engine (`engine/src/nnue.rs`) reads.

It deliberately re-implements the *exact* integer forward pass the engine uses
so the trainer can be checked against the engine bit-for-bit (see
`scripts/host-nnue-verify.sh`). If you change anything here, change
`engine/src/nnue.rs` to match, and vice versa.

Feature index for a piece (color c, type t in 0..5, square sq in 0..63) from a
given perspective P (chess.WHITE / chess.BLACK):
    rel_color = 0 if c == P else 1
    rel_sq    = sq if P == WHITE else sq ^ 56     # vertical flip
    idx       = rel_color*384 + t*64 + rel_sq
Square index matches python-chess and the engine (a1 = 0, rank*8 + file);
piece type t = python-chess piece_type - 1 (pawn..king -> 0..5).
"""

from __future__ import annotations

import struct
import sys

import chess

MAGIC = b"LZN1"
NUM_FEATURES = 768

# Quantization constants (mirrored in the trainer):
#   activations are scaled so 1.0 <-> QA, input weights/biases by QA, output
#   weights by QW_OUT. out_div = QA*QW_OUT maps the integer output to pawns,
#   then *100 -> centipawns.
QA = 127
QW_OUT = 64
OUT_DIV = QA * QW_OUT  # 8128


def active_indices(board: chess.Board, perspective: bool) -> list[int]:
    """Active feature indices for one perspective of `board`."""
    out = []
    for sq, piece in board.piece_map().items():
        rel_color = 0 if piece.color == perspective else 1
        rel_sq = sq if perspective == chess.WHITE else sq ^ 56
        t = piece.piece_type - 1  # PAWN(1)->0 .. KING(6)->5
        out.append(rel_color * 384 + t * 64 + rel_sq)
    return out


def pack(net: dict) -> bytes:
    """Serialize a quantized net dict to the LZN1 byte layout."""
    h = int(net["hidden"])
    w_in = net["w_in"]
    b_in = net["b_in"]
    w_out = net["w_out"]
    assert len(w_in) == NUM_FEATURES * h, "w_in size"
    assert len(b_in) == h, "b_in size"
    assert len(w_out) == 2 * h, "w_out size"
    buf = bytearray()
    buf += MAGIC
    buf += struct.pack("<I", h)
    buf += struct.pack("<I", NUM_FEATURES)
    buf += struct.pack(f"<{len(w_in)}h", *(int(x) for x in w_in))
    buf += struct.pack(f"<{len(b_in)}i", *(int(x) for x in b_in))
    buf += struct.pack(f"<{len(w_out)}h", *(int(x) for x in w_out))
    buf += struct.pack("<i", int(net["b_out"]))
    buf += struct.pack("<i", int(net["out_div"]))
    return bytes(buf)


def unpack(buf: bytes) -> dict:
    assert buf[:4] == MAGIC, "bad magic"
    off = 4
    (h,) = struct.unpack_from("<I", buf, off)
    off += 4
    (nf,) = struct.unpack_from("<I", buf, off)
    off += 4
    assert nf == NUM_FEATURES, "feature count"
    w_in = list(struct.unpack_from(f"<{NUM_FEATURES * h}h", buf, off))
    off += NUM_FEATURES * h * 2
    b_in = list(struct.unpack_from(f"<{h}i", buf, off))
    off += h * 4
    w_out = list(struct.unpack_from(f"<{2 * h}h", buf, off))
    off += 2 * h * 2
    (b_out,) = struct.unpack_from("<i", buf, off)
    off += 4
    (out_div,) = struct.unpack_from("<i", buf, off)
    return {
        "hidden": h,
        "w_in": w_in,
        "b_in": b_in,
        "w_out": w_out,
        "b_out": b_out,
        "out_div": out_div,
    }


def _trunc_div(num: int, den: int) -> int:
    """Integer division truncating toward zero, matching Rust `i64 / i64`."""
    q = abs(num) // abs(den)
    return q if (num >= 0) == (den >= 0) else -q


def int_forward(net: dict, board: chess.Board) -> int:
    """Reference integer forward pass; must equal `engine/src/nnue.rs`.

    Returns centipawns from the side-to-move's perspective.
    """
    h = net["hidden"]
    w_in = net["w_in"]
    b_in = net["b_in"]
    w_out = net["w_out"]
    stm = board.turn
    opp = not stm

    def accumulate(perspective):
        acc = list(b_in)
        for idx in active_indices(board, perspective):
            base = idx * h
            for j in range(h):
                acc[j] += w_in[base + j]
        return acc

    acc_stm = accumulate(stm)
    acc_opp = accumulate(opp)
    out = net["b_out"]
    for j in range(h):
        out += max(0, min(127, acc_stm[j])) * w_out[j]
    for j in range(h):
        out += max(0, min(127, acc_opp[j])) * w_out[h + j]
    return _trunc_div(out * 100, net["out_div"])


def random_net(hidden: int, seed: int) -> dict:
    """A small randomly-initialised quantized net, for format/parity testing."""
    import random

    rng = random.Random(seed)
    return {
        "hidden": hidden,
        "w_in": [rng.randint(-64, 64) for _ in range(NUM_FEATURES * hidden)],
        "b_in": [rng.randint(-32, 32) for _ in range(hidden)],
        "w_out": [rng.randint(-64, 64) for _ in range(2 * hidden)],
        "b_out": rng.randint(-1000, 1000),
        "out_div": OUT_DIV,
    }


def _main(argv: list[str]) -> int:
    if len(argv) >= 5 and argv[1] == "random-net":
        hidden, seed, out_path = int(argv[2]), int(argv[3]), argv[4]
        with open(out_path, "wb") as f:
            f.write(pack(random_net(hidden, seed)))
        print(f"wrote random net hidden={hidden} -> {out_path}")
        return 0
    if len(argv) >= 4 and argv[1] == "forward":
        net = unpack(open(argv[2], "rb").read())
        board = chess.Board(argv[3])
        print(int_forward(net, board))
        return 0
    print(
        "usage:\n"
        "  nnue_format.py random-net <hidden> <seed> <out.nnue>\n"
        "  nnue_format.py forward <net.nnue> <fen>",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
