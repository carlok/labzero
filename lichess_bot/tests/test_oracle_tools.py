import importlib.util
import sys
from pathlib import Path

import chess


ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


oracle = load_script("host-oracle-label.py")


def write_pgn(path: Path, white: str, black: str, site: str, moves: str) -> None:
    path.write_text(
        "\n".join(
            [
                '[Event "Test"]',
                f'[Site "{site}"]',
                f'[White "{white}"]',
                f'[Black "{black}"]',
                '[WhiteLichessId "labzerobot0"]' if white == "LabZeroBot0" else '[WhiteLichessId "other"]',
                '[BlackLichessId "labzerobot0"]' if black == "LabZeroBot0" else '[BlackLichessId "other"]',
                '[Result "*"]',
                "",
                moves,
                "",
            ]
        )
    )


def test_pgn_dedupe_prefers_local_over_export(tmp_path):
    local = tmp_path / "20260630_LabZeroBot0_vs_Other_abcdefgh.pgn"
    export = tmp_path / "20260630_abcdefgh_export.pgn"
    write_pgn(local, "LabZeroBot0", "Other", "https://lichess.org/abcdefgh", "1. e4 e5 *")
    write_pgn(export, "LabZeroBot0", "Other", "https://lichess.org/abcdefgh", "1. d4 d5 *")

    assert oracle.index_pgn_paths([export, local]) == [local]


def test_extract_labzero_samples_from_white_and_black_games(tmp_path):
    white_game = tmp_path / "white_abcd1234.pgn"
    black_game = tmp_path / "black_wxyz9876.pgn"
    write_pgn(white_game, "LabZeroBot0", "Other", "https://lichess.org/abcd1234", "1. e4 e5 2. Nf3 *")
    write_pgn(black_game, "Other", "LabZeroBot0", "https://lichess.org/wxyz9876", "1. d4 Nf6 2. c4 *")

    white_samples = oracle.extract_labzero_samples(white_game, ("labzerobot0",))
    black_samples = oracle.extract_labzero_samples(black_game, ("labzerobot0",))

    assert [sample.move.uci() for sample in white_samples] == ["e2e4", "g1f3"]
    assert [sample.move.uci() for sample in black_samples] == ["g8f6"]
    assert white_samples[0].game_id == "abcd1234"
    assert black_samples[0].game_id == "wxyz9876"


def test_pgn_analysis_priority_orders_losses_before_draws_before_wins(tmp_path):
    loss = tmp_path / "loss_loss0001.pgn"
    draw = tmp_path / "draw_draw0001.pgn"
    win = tmp_path / "win_win00001.pgn"
    write_pgn(loss, "LabZeroBot0", "Other", "https://lichess.org/loss0001", "1. e4 e5 0-1")
    loss.write_text(loss.read_text().replace('[Result "*"]', '[Result "0-1"]'))
    write_pgn(draw, "LabZeroBot0", "Other", "https://lichess.org/draw0001", "1. e4 e5 1/2-1/2")
    draw.write_text(draw.read_text().replace('[Result "*"]', '[Result "1/2-1/2"]'))
    write_pgn(win, "LabZeroBot0", "Other", "https://lichess.org/win00001", "1. e4 e5 1-0")
    win.write_text(win.read_text().replace('[Result "*"]', '[Result "1-0"]'))

    paths = [win, draw, loss]
    paths.sort(key=lambda path: oracle.pgn_analysis_priority(path, ("labzerobot0",)))

    assert paths == [loss, draw, win]


def test_label_position_schema_and_student_bucket():
    board = chess.Board()
    sample = oracle.PositionSample(
        board=board,
        move=chess.Move.from_uci("g1f3"),
        game_id="game1234",
        ply=0,
        source_path="sample.pgn",
        result="*",
    )
    fake_scores = {
        "e2e4": (80, None),
        "g1f3": (-200, None),
    }

    record = oracle.label_position(None, sample, nodes=1, fake_scores=fake_scores)
    student = oracle.student_move_label(record)

    assert record["schema"] == "labzero.move_quality.v1"
    assert record["source"]["id"] == "game1234"
    assert record["student"]["move"] == "g1f3"
    assert record["moves"][0]["uci"] == "e2e4"
    assert student["uci"] == "g1f3"
    assert student["rank"] > 1
    assert student["bucket"] in {"inaccuracy", "mistake", "blunder"}


def test_bucket_assignment_thresholds():
    assert oracle.bucket_for_loss(0.0, 0, None) == "best"
    assert oracle.bucket_for_loss(0.02, 50, None) == "excellent"
    assert oracle.bucket_for_loss(0.05, 120, None) == "playable"
    assert oracle.bucket_for_loss(0.10, 200, None) == "inaccuracy"
    assert oracle.bucket_for_loss(0.20, 400, None) == "mistake"
    assert oracle.bucket_for_loss(0.40, 900, None) == "blunder"
