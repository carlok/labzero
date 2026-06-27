from lichess_bot import ladder_stats


def game(
    *,
    game_id="g1",
    winner="white",
    status="mate",
    rated=True,
    perf="blitz",
    variant="standard",
    initial=180,
    increment=2,
    bot_color="white",
    opponent_rating=1700,
):
    white_user = {"id": "labzerobot0", "name": "LabZeroBot0"}
    black_user = {"id": "opp", "name": "Opponent"}
    if bot_color == "black":
        white_user, black_user = black_user, white_user
    payload = {
        "id": game_id,
        "createdAt": 1000,
        "rated": rated,
        "perf": perf,
        "variant": variant,
        "clock": {"initial": initial, "increment": increment},
        "status": status,
        "players": {
            "white": {"user": white_user, "rating": 1800 if bot_color == "white" else opponent_rating},
            "black": {"user": black_user, "rating": opponent_rating if bot_color == "white" else 1800},
        },
    }
    if winner is not None:
        payload["winner"] = winner
    return payload


def test_parse_finished_game_filters_to_completed_rated_3_plus_2():
    parsed = ladder_stats.parse_finished_game(game(), "LabZeroBot0", 180, 2)
    assert parsed is not None
    assert parsed.result == "W"
    assert parsed.opponent == "Opponent"
    assert parsed.opponent_rating == 1700

    assert ladder_stats.parse_finished_game(game(rated=False), "LabZeroBot0", 180, 2) is None
    assert ladder_stats.parse_finished_game(game(perf="rapid"), "LabZeroBot0", 180, 2) is None
    assert ladder_stats.parse_finished_game(game(variant="chess960"), "LabZeroBot0", 180, 2) is None
    assert ladder_stats.parse_finished_game(game(initial=60, increment=0), "LabZeroBot0", 180, 2) is None
    assert ladder_stats.parse_finished_game(game(status="aborted", winner=None), "LabZeroBot0", 180, 2) is None


def test_parse_results_for_black_wins_draws_losses():
    black_win = ladder_stats.parse_finished_game(game(bot_color="black", winner="black"), "labzerobot0", 180, 2)
    black_loss = ladder_stats.parse_finished_game(game(bot_color="black", winner="white"), "labzerobot0", 180, 2)
    draw = ladder_stats.parse_finished_game(game(winner=None, status="draw"), "labzerobot0", 180, 2)

    assert black_win and black_win.result == "W"
    assert black_loss and black_loss.result == "L"
    assert draw and draw.result == "D"


def test_report_groups_recent_games_into_rounds_of_ten():
    games = [
        ladder_stats.FinishedGame(str(i), i, "W" if i % 3 else "L", "mate", "white", f"opp{i}", 1600 + i, 1800)
        for i in range(25)
    ]

    report = ladder_stats.build_report(games, 10)

    assert "window: 25 games 16W-0D-9L" in report
    assert "round 1: 10 games" in report
    assert "round 2: 10 games" in report
    assert "round 3: 5 games" in report


def test_summarize_counts_draw_score_and_average_opponent():
    games = [
        ladder_stats.FinishedGame("w", 1, "W", "mate", "white", "a", 1000, 1500),
        ladder_stats.FinishedGame("d", 2, "D", "draw", "black", "b", 1200, 1500),
        ladder_stats.FinishedGame("l", 3, "L", "resign", "white", "c", 1400, 1500),
    ]

    assert ladder_stats.summarize(games) == {
        "games": 3,
        "wins": 1,
        "draws": 1,
        "losses": 1,
        "score": 1.5,
        "score_pct": 50.0,
        "avg_opp": 1200,
    }
