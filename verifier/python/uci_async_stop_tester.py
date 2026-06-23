#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import selectors
import subprocess
import sys
import time

import chess


def send(proc: subprocess.Popen[bytes], line: str) -> None:
    assert proc.stdin is not None
    proc.stdin.write(f"{line}\n".encode())
    proc.stdin.flush()


def read_until(proc: subprocess.Popen[bytes], pred, timeout: float, seen: list[str]) -> str | None:
    assert proc.stdout is not None
    fd = proc.stdout.fileno()
    buf = b""
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout

    def handle_line(raw: str) -> str | None:
        line = raw.strip()
        if not line:
            return None
        seen.append(line)
        if pred(line):
            return line
        return None

    while time.monotonic() < deadline:
        events = sel.select(max(0.0, deadline - time.monotonic()))
        if not events:
            break
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            matched = handle_line(raw.decode(errors="replace"))
            if matched is not None:
                return matched
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    args = parser.parse_args()

    proc = subprocess.Popen(
        [args.engine],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    seen: list[str] = []

    try:
        send(proc, "uci")
        if read_until(proc, lambda s: s == "uciok", 2.0, seen) is None:
            print(f"FAIL: missing uciok; seen={seen}", file=sys.stderr)
            return 1

        send(proc, "isready")
        if read_until(proc, lambda s: s == "readyok", 2.0, seen) is None:
            print(f"FAIL: missing readyok before search; seen={seen}", file=sys.stderr)
            return 1

        send(proc, "position startpos")
        send(proc, "go infinite")
        time.sleep(0.1)

        send(proc, "isready")
        if read_until(proc, lambda s: s == "readyok", 1.0, seen) is None:
            print(f"FAIL: engine did not answer isready during search; seen={seen}", file=sys.stderr)
            return 1

        send(proc, "stop")
        best = read_until(proc, lambda s: s.startswith("bestmove "), 1.0, seen)
        if best is None:
            print(f"FAIL: missing bestmove after stop; seen={seen}", file=sys.stderr)
            return 1

        move_text = best.split()[1]
        move = chess.Move.from_uci(move_text)
        if move not in chess.Board().legal_moves:
            print(f"FAIL: illegal startpos bestmove {move_text}", file=sys.stderr)
            return 1

        send(proc, "quit")
        proc.wait(timeout=2.0)
        print("uci_async_stop_tester: PASS")
        return 0
    finally:
        if proc.poll() is None:
            try:
                send(proc, "stop")
                send(proc, "quit")
                proc.wait(timeout=0.5)
            except Exception:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
