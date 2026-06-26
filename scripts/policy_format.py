#!/usr/bin/env python3
"""Shared policy feature/format code for labzero (host side).

Mirrors `engine/src/policy.rs`: 768 STM sparse features, 64 hidden clipped ReLU,
4096 from-to logits. Binary magic `LZP1`.
"""

from __future__ import annotations

import struct
import sys

import chess

MAGIC = b"LZP1"
NUM_FEATURES = 768
NUM_MOVES = 4096
QA = 127


def active_indices_stm(board: chess.Board) -> list[int]:
    """Active feature indices from side-to-move perspective."""
    perspective = board.turn
    out = []
    for sq, piece in board.piece_map().items():
        rel_color = 0 if piece.color == perspective else 1
        rel_sq = sq if perspective == chess.WHITE else sq ^ 56
        t = piece.piece_type - 1
        out.append(rel_color * 384 + t * 64 + rel_sq)
    return out


def move_index(from_sq: int, to_sq: int) -> int:
    return from_sq * 64 + to_sq


def pack(net: dict) -> bytes:
    h = int(net["hidden"])
    w_in = net["w_in"]
    b_in = net["b_in"]
    w_out = net["w_out"]
    b_out = net["b_out"]
    assert len(w_in) == NUM_FEATURES * h
    assert len(b_in) == h
    assert len(w_out) == h * NUM_MOVES
    assert len(b_out) == NUM_MOVES
    buf = bytearray()
    buf += MAGIC
    buf += struct.pack("<I", h)
    buf += struct.pack("<I", NUM_FEATURES)
    buf += struct.pack(f"<{len(w_in)}h", *(int(x) for x in w_in))
    buf += struct.pack(f"<{len(b_in)}i", *(int(x) for x in b_in))
    buf += struct.pack(f"<{len(w_out)}h", *(int(x) for x in w_out))
    buf += struct.pack(f"<{len(b_out)}i", *(int(x) for x in b_out))
    return bytes(buf)


def unpack(buf: bytes) -> dict:
    assert buf[:4] == MAGIC, "bad magic"
    off = 4
    (h,) = struct.unpack_from("<I", buf, off)
    off += 4
    (nf,) = struct.unpack_from("<I", buf, off)
    off += 4
    assert nf == NUM_FEATURES
    w_in = list(struct.unpack_from(f"<{NUM_FEATURES * h}h", buf, off))
    off += NUM_FEATURES * h * 2
    b_in = list(struct.unpack_from(f"<{h}i", buf, off))
    off += h * 4
    w_out = list(struct.unpack_from(f"<{h * NUM_MOVES}h", buf, off))
    off += h * NUM_MOVES * 2
    b_out = list(struct.unpack_from(f"<{NUM_MOVES}i", buf, off))
    return {"hidden": h, "w_in": w_in, "b_in": b_in, "w_out": w_out, "b_out": b_out}


def int_forward_move(net: dict, board: chess.Board, uci: str) -> int:
    """Reference integer logit for one UCI move; must match Rust policy.rs."""
    move = chess.Move.from_uci(uci)
    if move not in board.legal_moves:
        raise ValueError(f"illegal move {uci}")
    acc = list(net["b_in"])
    for idx in active_indices_stm(board):
        base = idx * net["hidden"]
        for j in range(net["hidden"]):
            acc[j] += net["w_in"][base + j]
    hidden = [max(0, min(QA, a)) for a in acc]
    midx = move_index(move.from_square, move.to_square)
    out = net["b_out"][midx]
    for j, a in enumerate(hidden):
        out += a * net["w_out"][j * NUM_MOVES + midx]
    return int(out)


def random_net(hidden: int, seed: int) -> dict:
    import random

    rng = random.Random(seed)
    return {
        "hidden": hidden,
        "w_in": [rng.randint(-32, 32) for _ in range(NUM_FEATURES * hidden)],
        "b_in": [rng.randint(-16, 16) for _ in range(hidden)],
        "w_out": [rng.randint(-32, 32) for _ in range(hidden * NUM_MOVES)],
        "b_out": [rng.randint(-64, 64) for _ in range(NUM_MOVES)],
    }


def _main(argv: list[str]) -> int:
    if len(argv) >= 5 and argv[1] == "random-net":
        hidden, seed, out_path = int(argv[2]), int(argv[3]), argv[4]
        with open(out_path, "wb") as f:
            f.write(pack(random_net(hidden, seed)))
        print(f"wrote random policy net hidden={hidden} -> {out_path}")
        return 0
    if len(argv) >= 5 and argv[1] == "forward":
        net = unpack(open(argv[2], "rb").read())
        board = chess.Board(argv[3])
        print(int_forward_move(net, board, argv[4]))
        return 0
    print(
        "usage:\n"
        "  policy_format.py random-net <hidden> <seed> <out.lzp>\n"
        "  policy_format.py forward <net.lzp> <fen> <uci>",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
