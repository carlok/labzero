import importlib.util
import random
import sys
from pathlib import Path

import chess
import chess.pgn


ROOT = Path(__file__).resolve().parents[2]


def load_generator():
    path = ROOT / "experiments" / "puzzle" / "lichess_puzzle_generator.py"
    spec = importlib.util.spec_from_file_location("lichess_puzzle_generator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generator = load_generator()


def write_game(
    f,
    *,
    site: str,
    white_elo: int,
    black_elo: int,
    termination: str = "Normal",
    result: str = "1-0",
    moves: str = "1. e4 e5 2. Nf3 Nc6 1-0",
) -> None:
    f.write(
        "\n".join(
            [
                '[Event "Rated blitz game"]',
                f'[Site "{site}"]',
                '[White "WhitePlayer"]',
                '[Black "BlackPlayer"]',
                f'[WhiteElo "{white_elo}"]',
                f'[BlackElo "{black_elo}"]',
                f'[Termination "{termination}"]',
                f'[Result "{result}"]',
                "",
                moves,
                "",
            ]
        )
        + "\n"
    )


def test_eligible_headers_filters_threshold_and_accepts_normal_result():
    headers = chess.pgn.Headers(
        {
            "WhiteElo": "2030",
            "BlackElo": "2099",
            "Termination": "Normal",
            "Result": "1/2-1/2",
        }
    )
    assert generator.eligible_headers(headers, 2030) == (True, "ok")

    headers["BlackElo"] = "2029"
    assert generator.eligible_headers(headers, 2030) == (False, "elo")

    headers["BlackElo"] = "2099"
    headers["Termination"] = "Time forfeit"
    assert generator.eligible_headers(headers, 2030) == (False, "termination")


def test_sample_game_refs_streams_pgn_and_skips_low_elo(tmp_path):
    pgn_dir = tmp_path / "lichess"
    pgn_dir.mkdir()
    pgn_path = pgn_dir / "sample.pgn"
    with pgn_path.open("w", encoding="utf-8") as f:
        write_game(
            f,
            site="https://lichess.org/low00001",
            white_elo=2100,
            black_elo=1800,
            result="1-0",
        )
        write_game(
            f,
            site="https://lichess.org/high0001",
            white_elo=2030,
            black_elo=2040,
            result="0-1",
        )

    refs, stats = generator.sample_game_refs(
        pgn_dir,
        min_elo=2030,
        sample_games=5,
        max_games_scanned=10,
        rng=random.Random(1),
    )

    assert stats["scanned"] == 2
    assert stats["eligible"] == 1
    assert [ref.game_id for ref in refs] == ["high0001"]

    game = generator.read_game(refs[0])
    assert game is not None
    assert game.headers["Site"] == "https://lichess.org/high0001"


def test_epd_line_contains_best_move_and_source_metadata():
    candidate = generator.PuzzleCandidate(
        category="material",
        fen=chess.STARTING_FEN,
        bm="e2e4",
        played="d2d4",
        game_id="game1234",
        ply=17,
        white_elo=2100,
        black_elo=2110,
        gap_cp=220,
        best_cp=150,
        second_cp=-70,
        best_mate=None,
        source="/tmp/lichess_db_standard_rated_2016-03.pgn",
    )

    line = generator.epd_line(candidate)

    assert " bm e2e4;" in line
    assert 'id "game1234"' in line
    assert "played=d2d4" in line
    assert "welo=2100" in line
    assert "belo=2110" in line


def test_classify_uses_transparent_heuristics():
    board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert generator.classify(board, chess.Move.from_uci("a7a8q"), None) == "endgame"

    board = chess.Board("4k3/8/8/8/8/8/4q3/4R1K1 w - - 0 1")
    assert generator.classify(board, chess.Move.from_uci("e1e2"), None) == "endgame"

    board = chess.Board("4k3/ppppppp1/8/8/8/8/PPPPPPP1/4K2R w - - 0 1")
    assert generator.classify(board, chess.Move.from_uci("h1h8"), None) == "king_attack"

    board = chess.Board()
    assert generator.classify(board, chess.Move.from_uci("e2e4"), None) == "tactical"
