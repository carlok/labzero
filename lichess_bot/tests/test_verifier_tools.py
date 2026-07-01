import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_verifier(name: str):
    path = ROOT / "verifier" / "python" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


perft_crosscheck = load_verifier("perft_crosscheck.py")


def test_perft_crosscheck_strips_epd_operations():
    line = '5Q2/4P2k/6p1/1b5p/7q/1p3K2/1P6/4R3 b - - 5 65 am h4e1; id "sgc0lgbr_065_qxe1";'

    assert (
        perft_crosscheck.fen_from_position_line(line)
        == "5Q2/4P2k/6p1/1b5p/7q/1p3K2/1P6/4R3 b - - 5 65"
    )


def test_perft_crosscheck_accepts_four_field_epd():
    assert (
        perft_crosscheck.fen_from_position_line("8/8/8/8/8/8/8/K6k w - - bm a1a2;")
        == "8/8/8/8/8/8/8/K6k w - - 0 1"
    )
