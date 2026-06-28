"""Tests for host-benchmark-analyze.py parse_txt."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parent / "host-benchmark-analyze.py"
_spec = importlib.util.spec_from_file_location("host_benchmark_analyze", _MODULE)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
parse_game_lines = _mod.parse_game_lines
parse_txt = _mod.parse_txt


PARTIAL_NO_FOOTER = """\
labzero host benchmark  2026-06-28T08:58:20+00:00
status:      in progress
games:       16
time control: 3+2 (wtime real-clock)

games:
game  1: draw 1/2-1/2  (0)  [0-0-1]
game  2: loss 1-0  (0)  [0-1-1]
game  3: loss 0-1  (0)  [0-2-1]
game  4: loss 1-0  (0)  [0-3-1]
game  5: loss 0-1  (0)  [0-4-1]
"""

COMPLETE_WITH_FOOTER = """\
labzero host benchmark  2026-06-28T08:04:55+00:00
status:      in progress
games:       4
time control: 3+2 (wtime real-clock)

games:
game  1: win  1-0  (0)  [1-0-0]
game  2: draw 1/2-1/2  (0)  [1-0-1]
game  3: draw 1/2-1/2  (0)  [1-0-2]
game  4: draw 1/2-1/2  (0)  [1-0-3]

---
status:      complete
score:       1-0-3  (W-L-D for labzero)
truncated:   0
illegal:     0
errors:      0
"""

INTERRUPTED_WITH_FOOTER = """\
status:      in progress
games:       16
games:
game  1: loss 0-1  (0)  [0-1-0]
game  2: draw 1/2-1/2  (0)  [0-1-1]

---
status:      interrupted
score:       0-1-1  (W-L-D for labzero)
truncated:   0
illegal:     0
errors:      0
"""


def write_tmp(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_parse_game_lines_bracket():
    lines = parse_game_lines(PARTIAL_NO_FOOTER)
    assert len(lines) == 5
    assert lines[-1]["cumulative"] == (0, 4, 1)


def test_partial_no_footer(tmp_path):
    path = write_tmp(tmp_path, "partial.txt", PARTIAL_NO_FOOTER)
    meta = parse_txt(path)
    assert meta["wins"] == 0 and meta["losses"] == 4 and meta["draws"] == 1
    assert meta["games_planned"] == 16
    assert meta["games_completed"] == 5
    assert meta["partial"] is True
    assert meta["status"] == "in-progress/no-footer"


def test_complete_with_footer(tmp_path):
    path = write_tmp(tmp_path, "complete.txt", COMPLETE_WITH_FOOTER)
    meta = parse_txt(path)
    assert meta["wins"] == 1 and meta["losses"] == 0 and meta["draws"] == 3
    assert meta["status"] == "complete"
    assert meta["partial"] is False


def test_interrupted_with_footer(tmp_path):
    path = write_tmp(tmp_path, "interrupted.txt", INTERRUPTED_WITH_FOOTER)
    meta = parse_txt(path)
    assert meta["wins"] == 0 and meta["losses"] == 1 and meta["draws"] == 1
    assert meta["status"] == "interrupted"
    assert meta["partial"] is True
