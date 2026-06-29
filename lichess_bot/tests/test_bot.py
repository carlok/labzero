import json
from pathlib import Path

import chess
import pytest

from lichess_bot import bot


def make_config(tmp_path, **overrides):
    cfg = {
        "engine": "lichess_bot/bin/labzero-macos-aarch64-0.6.1",
        "pgn_directory": str(tmp_path / "pgn"),
        "challenge_quota_file": str(tmp_path / "quota.json"),
        "challenge_control_file": str(tmp_path / "control.json"),
    }
    cfg.update(overrides)
    return bot.BotConfig.from_dict(cfg, rated_override=False)


def test_config_defaults_and_validation(tmp_path):
    cfg = make_config(tmp_path)

    assert cfg.rated is False
    assert cfg.max_parallel_games == 1
    assert cfg.accept_from == "any"
    assert cfg.challenge_color == "random"
    assert cfg.max_bot_challenges_per_day == 100
    assert cfg.bot_challenge_quota_margin == 10
    assert cfg.move_overhead_ms == 500
    assert cfg.uci_threads == 4
    assert cfg.uci_hash_mb == 64
    assert cfg.avoid_bots_file.endswith("lichess_bot/local/avoid-bots.json")
    assert cfg.accept_draw_enabled is True
    assert cfg.accept_draw_losing_score == -100
    assert cfg.notify_provider == "none"
    assert cfg.notify_busy_human_challenge is True
    assert cfg.notify_radar_after_game is True
    assert cfg.notify_radar_after_game_delay_sec == 2
    assert cfg.radar_min_blitz_games == 20
    assert cfg.radar_allow_provisional is False
    assert cfg.chat_rooms == ["player"]

    with pytest.raises(ValueError, match="accept_from"):
        make_config(tmp_path, accept_from="everyone")
    with pytest.raises(ValueError, match="challenge_color"):
        make_config(tmp_path, challenge_color="blue")
    with pytest.raises(ValueError, match="threads"):
        make_config(tmp_path, threads=0)
    with pytest.raises(ValueError, match="notify_provider"):
        make_config(tmp_path, notify_provider="email")
    with pytest.raises(ValueError, match="chat_rooms"):
        make_config(tmp_path, chat_rooms=["player", "team"])

    both_rooms = make_config(tmp_path, chat_rooms=["player", "spectator", "player"])
    assert both_rooms.chat_rooms == ["player", "spectator"]


def test_notify_message_formatting(tmp_path):
    cfg = make_config(tmp_path, notify_provider="telegram", pgn_directory=str(tmp_path / "pgn"))
    game_full = {
        "white": {"id": "labzerobot0", "name": "LabZeroBot0", "title": "BOT", "rating": 1500},
        "black": {"id": "maia5", "name": "maia5", "title": "BOT", "rating": 1510},
    }

    start = bot.notify_message_start("abc123", cfg, chess.WHITE, game_full)
    assert "▶️ START abc123" in start
    assert "unrated 3+2" in start
    assert "bot=white" in start
    assert "White: BOT LabZeroBot0 · 1500" in start
    assert "Black: BOT maia5 · 1510" in start
    assert "https://lichess.org/abc123" in start

    export_path = tmp_path / "pgn" / "20260628-120000_abc123_export.pgn"
    export_path.parent.mkdir(parents=True)
    export_path.write_text(
        '[WhiteElo "1500"]\n[BlackElo "1510"]\n[WhiteRatingDiff "+7"]\n[BlackRatingDiff "-2"]\n1. e4 e5 *\n'
    )
    end = bot.notify_message_end(
        "abc123",
        cfg,
        chess.WHITE,
        "1-0",
        game_full,
        {"status": "mate"},
        str(tmp_path / "pgn" / "game.pgn"),
    )
    assert "✅ WIN abc123" in end
    assert "status=mate" in end
    assert "White: BOT LabZeroBot0 · 1500 (+7) → 1507" in end
    assert "Black: BOT maia5 · 1510 (-2) → 1508" in end
    assert "📄 game.pgn" in end
    assert "/tmp/" not in end
    assert str(tmp_path) not in end


def test_format_elo_line():
    assert bot.format_elo_line(1949, 7) == "1949 (+7) → 1956"
    assert bot.format_elo_line(1949, -2) == "1949 (-2) → 1947"
    assert bot.format_elo_line(1949, None) == "1949"


def test_notify_basename():
    assert bot.notify_basename("/Users/me/pgn/game.pgn") == "game.pgn"
    assert bot.notify_basename(None) is None


def test_notify_telegram_best_effort(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, notify_provider="telegram")
    calls = []

    monkeypatch.setenv("LABZERO_NOTIFY_TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("LABZERO_NOTIFY_TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(
        bot.urllib.request,
        "urlopen",
        lambda req, timeout=0: calls.append((req, timeout))
        or (_ for _ in ()).throw(RuntimeError("offline")),
    )

    bot.notify(cfg, "hello")

    assert len(calls) == 1


def test_telegram_document_request_shape(monkeypatch, tmp_path):
    file_path = tmp_path / "probe.txt"
    file_path.write_text("hello file")
    monkeypatch.setenv("LABZERO_NOTIFY_TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("LABZERO_NOTIFY_TELEGRAM_CHAT_ID", "chat")

    req = bot.telegram_document_request(file_path, "caption")

    assert req.full_url == "https://api.telegram.org/bottoken/sendDocument"
    assert req.get_method() == "POST"
    assert "multipart/form-data" in req.get_header("Content-type")
    assert b'name="chat_id"' in req.data
    assert b"chat" in req.data
    assert b'name="caption"' in req.data
    assert b"caption" in req.data
    assert b'filename="probe.txt"' in req.data
    assert b"hello file" in req.data


def test_telegram_document_request_requires_env(monkeypatch, tmp_path):
    monkeypatch.delenv("LABZERO_NOTIFY_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("LABZERO_NOTIFY_TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(RuntimeError, match="LABZERO_NOTIFY_TELEGRAM_TOKEN"):
        bot.telegram_document_request(tmp_path / "probe.txt", "caption")


def test_notify_test_text_and_file(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, notify_provider="telegram")
    calls = []
    file_path = tmp_path / "probe.txt"
    file_path.write_text("hello")
    monkeypatch.setattr(bot, "send_telegram_notification", lambda text: calls.append(("text", text)))
    monkeypatch.setattr(bot, "send_telegram_document", lambda path, caption: calls.append(("file", path, caption)))

    bot.notify_test(cfg, "hello text", None)
    bot.notify_test(cfg, "hello file", str(file_path))

    assert calls == [("text", "hello text"), ("file", str(file_path), "hello file")]


def test_notify_test_requires_telegram_provider(tmp_path):
    cfg = make_config(tmp_path)

    with pytest.raises(RuntimeError, match="notify_provider"):
        bot.notify_test(cfg, "hello", None)


def test_notify_message_radar_after_game():
    rows = [
        {"username": "WeakBot", "rating": 1800},
        {"username": "NearBot", "rating": 2010},
        {"username": "FarBot", "rating": 2300},
    ]

    text = bot.notify_message_radar_after_game(2000, rows)

    assert "RADAR after game" in text
    assert "own blitz: 2000" in text
    assert "online bots: 3 filtered" in text
    assert "percentile: 33.3th" in text
    assert "above=2" in text
    assert "nearest stronger: NearBot 2010, FarBot 2300" in text


def test_notify_radar_after_game_uses_telegram_when_enabled(monkeypatch, tmp_path):
    cfg = make_config(
        tmp_path,
        notify_provider="telegram",
        notify_radar_after_game_delay_sec=0,
        radar_min_blitz_games=20,
    )
    notifications: list[str] = []
    monkeypatch.setattr(bot, "own_blitz_rating", lambda token, cfg: 2000)
    monkeypatch.setattr(
        bot,
        "online_bots",
        lambda token: [
            {"username": "WeakBot", "perfs": {"blitz": {"rating": 1800, "games": 40, "prov": False}}},
            {"username": "NearBot", "perfs": {"blitz": {"rating": 2010, "games": 40, "prov": False}}},
            {"username": "TooNew", "perfs": {"blitz": {"rating": 2200, "games": 1, "prov": False}}},
        ],
    )
    monkeypatch.setattr(bot, "notify", lambda cfg, text: notifications.append(text))

    bot.notify_radar_after_game("token", cfg)

    assert len(notifications) == 1
    assert "online bots: 2 filtered" in notifications[0]
    assert "nearest stronger: NearBot 2010" in notifications[0]


def test_notify_radar_after_game_skips_when_notifications_disabled(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, notify_provider="none")
    monkeypatch.setattr(
        bot,
        "online_bots",
        lambda token: (_ for _ in ()).throw(AssertionError("should not poll")),
    )

    bot.notify_radar_after_game("token", cfg)


def test_main_notify_test_text_does_not_need_lichess_token(monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('notify_provider = "telegram"\n')
    calls = []
    monkeypatch.delenv("LICHESS_TOKEN", raising=False)
    monkeypatch.setenv("LABZERO_NOTIFY_TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("LABZERO_NOTIFY_TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(bot, "send_telegram_notification", lambda text: calls.append(text))
    monkeypatch.setattr(
        bot.sys,
        "argv",
        [
            "bot.py",
            "--config",
            str(config),
            "--env-file",
            str(tmp_path / "missing.env"),
            "--notify-test",
            "--notify-test-text",
            "hello from test",
        ],
    )

    assert bot.main() == 0
    assert calls == ["hello from test"]


def test_main_notify_test_missing_env_fails_without_lichess_token(monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('notify_provider = "telegram"\n')
    monkeypatch.delenv("LICHESS_TOKEN", raising=False)
    monkeypatch.delenv("LABZERO_NOTIFY_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("LABZERO_NOTIFY_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(
        bot.sys,
        "argv",
        [
            "bot.py",
            "--config",
            str(config),
            "--env-file",
            str(tmp_path / "missing.env"),
            "--notify-test",
        ],
    )

    assert bot.main() == 1


def test_notify_disabled_does_not_call_telegram(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)
    monkeypatch.setattr(
        bot,
        "send_telegram_notification",
        lambda text: (_ for _ in ()).throw(AssertionError("called")),
    )

    bot.notify(cfg, "hello")


def test_runtime_state_game_limit():
    state = bot.RuntimeState(games_limit=2)

    state.begin_game("g1", "starting")
    state.end_game("g1")
    assert not state.stop.is_set()
    assert state.completed_games == 0

    state.begin_game("g1", "starting")
    state.end_game("g1", finished=True)
    assert not state.stop.is_set()
    assert state.completed_games == 1

    state.begin_game("g2", "starting")
    state.end_game("g2", finished=True)
    assert state.stop.is_set()
    assert state.completed_games == 2


def test_runtime_state_enforces_single_game():
    state = bot.RuntimeState()

    assert state.try_begin_game("g1", "starting", 1)
    assert not state.try_begin_game("g1", "again", 1)
    assert not state.try_begin_game("g2", "starting", 1)
    assert state.snapshot() == {"g1": "starting"}

    state.update_game("g1", "ply=4")
    assert state.snapshot()["g1"] == "ply=4"
    state.end_game("g1")
    assert state.try_begin_game("g2", "starting", 1)


def test_runtime_state_reserves_capacity_before_game_start():
    state = bot.RuntimeState()

    assert state.try_reserve_slot("in:challenge1", 1)
    assert state.active_count() == 1
    assert not state.try_reserve_slot("in:challenge2", 1)
    assert state.try_begin_game("game1", "starting", 1)
    assert state.snapshot() == {"game1": "starting"}
    assert state.active_count() == 1
    assert not state.try_begin_game("game2", "starting", 1)
    state.end_game("game1")
    assert state.active_count() == 0


def test_runtime_state_tracks_pending_outgoing_bot_games():
    state = bot.RuntimeState()

    state.mark_outgoing_bot_challenge("Maia5")
    assert state.consume_outgoing_bot_game({"id": "maia5", "name": "maia5"})
    assert not state.consume_outgoing_bot_game({"id": "maia5", "name": "maia5"})
    assert not state.consume_outgoing_bot_game({"id": "other", "name": "Other"})


def test_runtime_state_sigint_paths_without_forcing_exit(monkeypatch):
    state = bot.RuntimeState()

    with pytest.raises(SystemExit):
        state.handle_sigint(2, None)

    state = bot.RuntimeState()
    state.begin_game("g1", "starting")
    state.handle_sigint(2, None)
    assert state._force_quit is True


def test_clock_limit_uses_milliseconds_and_overhead(tmp_path):
    cfg = make_config(tmp_path, move_overhead_ms=500, max_movetime_ms=5000)
    limit = bot.engine_limit(
        cfg,
        chess.Board(),
        {"wtime": 180000, "btime": 170000, "winc": 2000, "binc": 1000},
    )

    assert limit.white_clock == pytest.approx(179.5)
    assert limit.black_clock == pytest.approx(169.5)
    assert limit.white_inc == pytest.approx(1.5)
    assert limit.black_inc == pytest.approx(0.5)
    assert limit.time == pytest.approx(5.0)
    assert bot.clock_seconds(1000, 2) == pytest.approx(1.0)


def test_engine_limit_prefers_depth_or_movetime(tmp_path):
    depth_cfg = make_config(tmp_path, search_depth=7)
    time_cfg = make_config(tmp_path, movetime_ms=1200)

    assert bot.engine_limit(depth_cfg, chess.Board()).depth == 7
    assert bot.engine_limit(time_cfg, chess.Board()).time == pytest.approx(1.2)


def test_player_object_supports_direct_and_nested_game_shapes():
    direct = {"white": {"id": "labzero", "name": "LabZero", "rating": 1500}}
    nested = {
        "players": {
            "black": {
                "user": {"id": "maia", "username": "maia5", "title": "BOT"},
                "rating": 1510,
                "provisional": False,
            }
        }
    }

    assert bot.player_user_id(direct, "white") == "labzero"
    nested_player = bot.player_obj(nested, "black")
    assert nested_player["id"] == "maia"
    assert nested_player["rating"] == 1510
    assert nested_player["provisional"] is False
    assert bot.user_name({"username": "SomeUser"}) == "SomeUser"
    assert bot.safe_filename_part("A/B C!") == "A_B_C"


def test_player_and_result_stdout_labels():
    game_full = {
        "white": {"id": "lab", "name": "LabZeroBot0", "title": "BOT", "rating": 1800},
        "black": {"id": "maia", "name": "maia5", "title": "BOT", "rating": 1510},
    }

    assert bot.matchup_label(game_full) == "White: BOT LabZeroBot0 (1800) vs Black: BOT maia5 (1510)"
    assert bot.result_for_bot("1-0", chess.WHITE) == ("WIN", "✅")
    assert bot.result_for_bot("0-1", chess.WHITE) == ("LOSS", "❌")
    assert bot.result_for_bot("1/2-1/2", chess.BLACK) == ("DRAW", "🤝")
    assert bot.result_for_bot("*", chess.BLACK) == ("UNKNOWN", "❔")


def test_small_helpers_cover_empty_and_error_paths(tmp_path):
    assert bot.optional_int(None) is None
    assert bot.optional_int("") is None
    assert bot.optional_int("7") == 7
    assert bot.optional_resolved_path("") is None
    assert bot.resolved_path_list("") == []
    assert bot.resolved_path_list("lichess_bot") == [str(bot.ROOT / "lichess_bot")]
    assert bot.user_id(None) == ""
    assert bot.user_name(None) == "unknown"
    assert bot.player_rating({"rating": "bad"}) is None
    assert bot.piece_count(chess.Board()) == 32
    assert bot.book_move(chess.Board(), make_config(tmp_path)) is None
    assert bot.syzygy_move(chess.Board(), make_config(tmp_path)) is None


def test_maybe_chat_ignores_empty_and_api_errors(monkeypatch):
    calls = []

    def fake_chat(token, game_id, room, text):
        calls.append((token, game_id, room, text))
        raise RuntimeError("chat disabled")

    monkeypatch.setattr(bot, "bot_chat", fake_chat)

    bot.maybe_chat("token", "game", "player", "")
    bot.maybe_chat("token", "game", "player", "hello")

    assert calls == [("token", "game", "player", "hello")]


def test_maybe_chat_rooms_posts_to_each_room(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "maybe_chat", lambda token, game_id, room, text: calls.append((room, text)))

    bot.maybe_chat_rooms("token", "game", ["player", "spectator"], "hello")

    assert calls == [("player", "hello"), ("spectator", "hello")]


def test_draw_offer_policy_accepts_only_reasonable_cases(tmp_path):
    cfg = make_config(tmp_path)
    board = chess.Board()

    assert bot.draw_offer_pending({"drawOffer": "black"}, chess.WHITE)
    assert not bot.draw_offer_pending({"drawOffer": "white"}, chess.WHITE)
    assert bot.should_accept_draw_offer(cfg, board, chess.WHITE, -150, {"wtime": 180000})
    assert not bot.should_accept_draw_offer(cfg, board, chess.WHITE, 80, {"wtime": 180000})
    assert bot.should_accept_draw_offer(cfg, board, chess.WHITE, 80, {"wtime": 5000})

    ending = chess.Board("8/8/8/8/8/4k3/8/4K3 w - - 0 50")
    assert bot.should_accept_draw_offer(cfg, ending, chess.WHITE, 0, {"wtime": 180000})

    disabled = make_config(tmp_path, accept_draw_enabled=False)
    assert not bot.should_accept_draw_offer(disabled, board, chess.WHITE, -150, {"wtime": 180000})


def test_save_pgn_writes_players_elos_titles_and_result(tmp_path):
    cfg = make_config(tmp_path)
    board = bot.board_from_moves("e2e4 e7e5 g1f3 b8c6")
    game_full = {
        "white": {
            "id": "labzerobot0",
            "name": "LabZeroBot0",
            "title": "BOT",
            "rating": 1500,
            "provisional": True,
        },
        "black": {
            "id": "maia5",
            "name": "maia5",
            "title": "BOT",
            "rating": 1510,
            "provisional": False,
        },
    }
    game_state = {"moves": "e2e4 e7e5 g1f3 b8c6", "status": "outoftime", "winner": "white"}

    saved = bot.save_pgn(cfg, "abc123", board, game_full, game_state)

    pgn_path = next(Path(cfg.pgn_directory).glob("*LabZeroBot0_vs_maia5_abc123.pgn"))
    assert saved == str(pgn_path)
    pgn = pgn_path.read_text()
    assert '[White "LabZeroBot0"]' in pgn
    assert '[Black "maia5"]' in pgn
    assert '[WhiteElo "1500"]' in pgn
    assert '[BlackElo "1510"]' in pgn
    assert '[WhiteTitle "BOT"]' in pgn
    assert '[BlackTitle "BOT"]' in pgn
    assert '[WhiteLichessId "labzerobot0"]' in pgn
    assert '[Result "1-0"]' in pgn


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"winner": "white", "status": "mate"}, "1-0"),
        ({"winner": "black", "status": "resign"}, "0-1"),
        ({"status": "draw"}, "1/2-1/2"),
        ({"status": "stalemate"}, "1/2-1/2"),
        ({}, "*"),
    ],
)
def test_pgn_result_from_lichess_terminal_state(state, expected):
    assert bot.pgn_result(chess.Board(), state) == expected


def test_claimable_repetition_is_not_terminal_without_lichess_status():
    board = chess.Board()
    for _ in range(3):
        board.push_san("Nf3")
        board.push_san("Nf6")
        board.push_san("Ng1")
        board.push_san("Ng8")
    assert board.can_claim_threefold_repetition()
    assert board.is_game_over(claim_draw=True)
    assert not board.is_game_over(claim_draw=False)
    assert not bot.is_game_terminal(board, {})
    assert bot.pgn_result(board, {}) == "*"


def test_is_game_terminal_honors_lichess_timeout():
    board = chess.Board()
    assert bot.is_game_terminal(board, {"status": "outoftime", "winner": "white"})


def test_should_claim_available_draw_on_low_time(tmp_path):
    cfg = make_config(tmp_path)
    board = chess.Board()
    for _ in range(3):
        board.push_san("Nf3")
        board.push_san("Nf6")
        board.push_san("Ng1")
        board.push_san("Ng8")
    game_state = {"wtime": 8000, "btime": 60000}
    assert bot.should_claim_available_draw(cfg, board, chess.WHITE, game_state)
    assert not bot.should_claim_available_draw(cfg, board, chess.BLACK, game_state)


def test_should_not_claim_draw_on_equal_score_without_low_time(tmp_path):
    cfg = make_config(tmp_path)
    board = chess.Board()
    for _ in range(3):
        board.push_san("Nf3")
        board.push_san("Nf6")
        board.push_san("Ng1")
        board.push_san("Ng8")
    game_state = {"wtime": 60000, "btime": 60000}
    assert not bot.should_claim_available_draw(cfg, board, chess.WHITE, game_state)


def test_is_game_already_over_error():
    assert bot.is_game_already_over_error(
        bot.ApiError('HTTP 400: {"error":"Not your turn, or game already over"}')
    )
    assert bot.is_game_already_over_error(
        bot.ApiError('HTTP 400: {"error":"This is not the time to claim draw"}')
    )
    assert not bot.is_game_already_over_error(bot.ApiError("HTTP 500"))


def test_enrich_state_from_export():
    pgn = '[Result "1/2-1/2"]\n1. e4 e5 *'
    board, state = bot.enrich_state_from_export(pgn, chess.Board(), {})
    assert state["status"] == "draw"


def test_challenge_compatibility_filters_policy(tmp_path):
    cfg = make_config(tmp_path, accept_from="any", min_rating=1400, max_rating=1800)
    challenge = {
        "rated": False,
        "challenger": {"id": "maia5", "name": "maia5", "title": "BOT", "rating": 1510},
        "variant": {"key": "standard"},
        "timeControl": {"limit": 180, "increment": 2},
    }

    assert bot.is_compatible_challenge(challenge, cfg) == (True, "ok")
    assert bot.is_compatible_challenge({**challenge, "rated": True}, cfg) == (False, "rated mismatch")
    assert bot.is_compatible_challenge({**challenge, "variant": {"key": "chess960"}}, cfg) == (False, "variant mismatch")
    assert bot.is_compatible_challenge({**challenge, "timeControl": {"limit": 60, "increment": 0}}, cfg) == (
        False,
        "time control mismatch",
    )
    low = {**challenge, "challenger": {"id": "low", "rating": 1200}}
    assert bot.is_compatible_challenge(low, cfg) == (False, "rating too low")

    avoid_path = tmp_path / "avoid.json"
    avoid_path.write_text(json.dumps({"bots": ["maia5"]}))
    avoid_cfg = make_config(tmp_path, avoid_bots_file=str(avoid_path))
    assert bot.is_compatible_challenge(challenge, avoid_cfg) == (False, "avoided bot")


def test_accept_or_decline_challenge_actions(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)
    state = bot.RuntimeState()
    actions = []

    def fake_action(token, action, challenge_id, challenger, reason):
        actions.append((action, challenge_id, challenger, reason))
        return True

    monkeypatch.setattr(bot, "challenge_action", fake_action)

    challenge = {
        "id": "chal1",
        "rated": False,
        "challenger": {"id": "human1", "name": "HumanOne", "rating": 1500},
        "variant": {"key": "standard"},
        "timeControl": {"limit": 180, "increment": 2},
    }
    bot.accept_or_decline_challenge("token", challenge, cfg, state, "labzerobot0")
    assert actions[-1][0] == "accept"

    bot.accept_or_decline_challenge("token", {**challenge, "id": "chal2"}, cfg, state, "labzerobot0")
    assert actions[-1] == ("decline", "chal2", "HumanOne", "busy")


def test_busy_human_challenge_notifies_operator(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, notify_provider="telegram")
    state = bot.RuntimeState()
    state.begin_game("active", "playing")
    actions = []
    notifications = []
    monkeypatch.setattr(bot, "challenge_action", lambda *args: actions.append(args) or True)
    monkeypatch.setattr(bot, "notify", lambda cfg, text: notifications.append(text))

    challenge = {
        "id": "chal1",
        "rated": False,
        "challenger": {"id": "human1", "name": "HumanOne", "rating": 1500},
        "variant": {"key": "standard"},
        "timeControl": {"limit": 180, "increment": 2},
    }
    bot.accept_or_decline_challenge("token", challenge, cfg, state, "labzerobot0")

    assert actions[-1] == ("token", "decline", "chal1", "HumanOne", "busy")
    assert len(notifications) == 1
    assert "HumanOne" in notifications[0]
    assert "reason=busy" in notifications[0]


def test_busy_bot_challenge_does_not_notify_operator(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, notify_provider="telegram")
    state = bot.RuntimeState()
    state.begin_game("active", "playing")
    actions = []
    notifications = []
    monkeypatch.setattr(bot, "challenge_action", lambda *args: actions.append(args) or True)
    monkeypatch.setattr(bot, "notify", lambda cfg, text: notifications.append(text))

    challenge = {
        "id": "chal1",
        "rated": False,
        "challenger": {"id": "maia5", "name": "maia5", "title": "BOT", "rating": 1510},
        "variant": {"key": "standard"},
        "timeControl": {"limit": 180, "increment": 2},
    }
    bot.accept_or_decline_challenge("token", challenge, cfg, state, "labzerobot0")

    assert actions[-1] == ("token", "decline", "chal1", "maia5", "busy")
    assert notifications == []


def test_failed_accept_releases_reserved_capacity(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)
    state = bot.RuntimeState()

    def fake_action(token, action, challenge_id, challenger, reason):
        return False

    monkeypatch.setattr(bot, "challenge_action", fake_action)

    challenge = {
        "id": "chal1",
        "rated": False,
        "challenger": {"id": "human1", "name": "HumanOne", "rating": 1500},
        "variant": {"key": "standard"},
        "timeControl": {"limit": 180, "increment": 2},
    }
    bot.accept_or_decline_challenge("token", challenge, cfg, state, "labzerobot0")

    assert state.active_count() == 0


def test_choose_candidates_filters_and_shuffles(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, min_blitz_games=20, target_rating_min_delta=0, target_rating_max_delta=100)
    users = [
        {"username": "self", "perfs": {"blitz": {"rating": 1500, "games": 100}}},
        {"username": "weak", "perfs": {"blitz": {"rating": 1499, "games": 100}}},
        {"username": "few", "perfs": {"blitz": {"rating": 1510, "games": 5}}},
        {"username": "prov", "perfs": {"blitz": {"rating": 1520, "games": 100, "prov": True}}},
        {"username": "good", "perfs": {"blitz": {"rating": 1550, "games": 100}}},
    ]
    monkeypatch.setattr(bot.random, "shuffle", lambda items: None)

    assert [u["username"] for u in bot.choose_candidates(users, "self", 1500, cfg)] == ["good"]

    allow_prov = make_config(tmp_path, allow_provisional=True, target_rating_max_delta=100)
    assert [u["username"] for u in bot.choose_candidates(users, "self", 1500, allow_prov)] == ["prov", "good"]

    avoid_path = tmp_path / "avoid.json"
    avoid_path.write_text(json.dumps(["good"]))
    avoid_cfg = make_config(tmp_path, target_rating_max_delta=100, avoid_bots_file=str(avoid_path))
    assert bot.choose_candidates(users, "self", 1500, avoid_cfg) == []


def test_load_avoid_bots_accepts_list_and_object(tmp_path):
    avoid_path = tmp_path / "avoid.json"

    assert bot.load_avoid_bots(str(avoid_path)) == set()
    avoid_path.write_text(json.dumps(["SomeBot", "  OtherBot  ", ""]))
    assert bot.load_avoid_bots(str(avoid_path)) == {"somebot", "otherbot"}
    avoid_path.write_text(json.dumps({"bots": ["ThirdBot"]}))
    assert bot.load_avoid_bots(str(avoid_path)) == {"thirdbot"}
    avoid_path.write_text("{not-json")
    assert bot.load_avoid_bots(str(avoid_path)) == set()


def test_quota_and_control_file(tmp_path):
    quota_path = tmp_path / "quota.json"
    quota = bot.ChallengeQuota(str(quota_path), daily_limit=100, margin=10)

    assert quota.stop_at == 90
    assert quota.remaining() == 90
    quota.record_attempt()
    assert json.loads(quota_path.read_text())["sent"] == 1
    assert quota.remaining() == 89

    control_path = tmp_path / "control.json"
    assert not bot.stop_after_current_game(str(control_path))
    control_path.write_text(json.dumps({"stop_after_current_game": True}))
    assert bot.stop_after_current_game(str(control_path))
    control_path.write_text("{not-json")
    assert not bot.stop_after_current_game(str(control_path))


def test_play_game_sends_hello_after_first_ply(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, chat_rooms=["player", "spectator"])
    state = bot.RuntimeState()
    state.begin_game("game1", "starting")
    chats: list[tuple] = []
    notifications: list[str] = []
    monkeypatch.setattr(bot, "maybe_chat", lambda *args, **kwargs: chats.append(args))
    monkeypatch.setattr(bot, "notify", lambda cfg, text: notifications.append(text))
    monkeypatch.setattr(bot, "choose_move", lambda *args, **kwargs: bot.MoveDecision(chess.Move.from_uci("e7e5"), score_cp=0))
    monkeypatch.setattr(bot, "bot_make_move", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bot,
        "bot_game_stream",
        lambda token, game_id: iter(
            [
                {
                    "type": "gameFull",
                    "white": {"id": "maia5", "name": "maia5", "title": "BOT", "rating": 1510},
                    "black": {"id": "labzerobot0", "name": "LabZeroBot0", "title": "BOT", "rating": 1500},
                    "state": {"moves": "", "wtime": 180000, "btime": 180000},
                },
                {"type": "gameState", "moves": "e2e4", "wtime": 180000, "btime": 180000},
                {"type": "gameState", "moves": "e2e4 e7e5", "status": "draw"},
            ]
        ),
    )

    bot.play_game("token", object(), "game1", "labzerobot0", cfg, state)

    assert len(chats) == 4
    assert chats[0][2:] == ("player", bot.format_chat(cfg.hello, me="labzerobot0", opponent="maia5"))
    assert chats[1][2:] == ("spectator", bot.format_chat(cfg.hello, me="labzerobot0", opponent="maia5"))
    assert chats[2][2:] == ("player", bot.format_chat(cfg.goodbye, me="labzerobot0", opponent="maia5"))
    assert chats[3][2:] == ("spectator", bot.format_chat(cfg.goodbye, me="labzerobot0", opponent="maia5"))
    assert len(notifications) == 2
    assert "▶️ START game1" in notifications[0]
    assert "🤝 DRAW game1" in notifications[1]


def test_play_game_counts_quota_only_when_pending_bot_game_starts(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)
    quota = bot.ChallengeQuota(str(tmp_path / "quota.json"), daily_limit=100, margin=10)
    state = bot.RuntimeState()
    state.begin_game("game1", "starting")
    state.mark_outgoing_bot_challenge("maia5")
    monkeypatch.setattr(bot, "maybe_chat", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bot,
        "bot_game_stream",
        lambda token, game_id: iter(
            [
                {
                    "type": "gameFull",
                    "white": {"id": "maia5", "name": "maia5", "title": "BOT", "rating": 1510},
                    "black": {"id": "labzerobot0", "name": "LabZeroBot0", "title": "BOT", "rating": 1500},
                    "state": {"moves": ""},
                },
                {"type": "gameState", "moves": "", "status": "draw"},
            ]
        ),
    )

    bot.play_game("token", object(), "game1", "labzerobot0", cfg, state, quota)

    assert quota.sent == 1
    assert state.active_count() == 0


def test_play_game_accepts_reasonable_draw_offer_with_next_move(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)
    state = bot.RuntimeState()
    state.begin_game("game1", "starting")
    posted = []
    monkeypatch.setattr(bot, "maybe_chat", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "choose_move", lambda *args, **kwargs: bot.MoveDecision(chess.Move.from_uci("e2e4"), score_cp=-150))
    monkeypatch.setattr(bot, "bot_make_move", lambda token, game_id, move, offering_draw=False: posted.append((move, offering_draw)))
    monkeypatch.setattr(
        bot,
        "bot_game_stream",
        lambda token, game_id: iter(
            [
                {
                    "type": "gameFull",
                    "white": {"id": "labzerobot0", "name": "LabZeroBot0", "title": "BOT", "rating": 1500},
                    "black": {"id": "maia5", "name": "maia5", "title": "BOT", "rating": 1510},
                    "state": {"moves": "", "drawOffer": "black", "wtime": 180000, "btime": 180000},
                },
                {"type": "gameState", "moves": "e2e4", "status": "draw"},
            ]
        ),
    )

    bot.play_game("token", object(), "game1", "labzerobot0", cfg, state)

    assert posted == [("e2e4", True)]


def test_play_game_stale_move_post_counts_as_finished(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, pgn_directory=str(tmp_path / "pgn"))
    state = bot.RuntimeState(games_limit=1)
    state.begin_game("MSJKIZQY", "starting")
    exports: list[str] = []

    def reject_move(*args, **kwargs):
        raise bot.ApiError(
            'HTTP 400 Bad Request POST /api/bot/game/MSJKIZQY/move/h2h3: {"error":"Not your turn, or game already over"}'
        )

    monkeypatch.setattr(bot, "maybe_chat", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "choose_move", lambda *args, **kwargs: bot.MoveDecision(chess.Move.from_uci("h2h3"), score_cp=50))
    monkeypatch.setattr(bot, "bot_make_move", reject_move)
    monkeypatch.setattr(bot, "fetch_game_export_pgn", lambda token, game_id: exports.append(game_id) or '[Event "x"]\n* * *')
    monkeypatch.setattr(
        bot,
        "bot_game_stream",
        lambda token, game_id: iter(
            [
                {
                    "type": "gameFull",
                    "white": {"id": "labzerobot0", "name": "LabZeroBot0", "title": "BOT", "rating": 1500},
                    "black": {"id": "maia5", "name": "maia5", "title": "BOT", "rating": 1510},
                    "state": {"moves": "", "wtime": 180000, "btime": 180000},
                },
                {"type": "gameState", "moves": "", "wtime": 180000, "btime": 180000},
            ]
        ),
    )

    bot.play_game("token", object(), "MSJKIZQY", "labzerobot0", cfg, state)

    assert exports == ["MSJKIZQY"]
    assert state.completed_games == 1
    assert state.stop.is_set()
    assert list((tmp_path / "pgn").glob("*_export.pgn"))


def test_is_stale_move_error():
    assert bot.is_stale_move_error(
        bot.ApiError('HTTP 400: {"error":"Not your turn, or game already over"}')
    )
    assert not bot.is_stale_move_error(bot.ApiError("HTTP 500"))


def test_challenge_cooldown_seconds_parses_rate_limit():
    assert bot.challenge_cooldown_seconds(Exception('{"seconds":10053}')) == 10053
    assert bot.challenge_cooldown_seconds(Exception("played 100 games against other bots today")) == 3600
    assert bot.challenge_cooldown_seconds(Exception("other error")) is None


def test_challenge_users_only_sends_one_in_single_game_mode(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, max_parallel_games=1)
    sent = []
    monkeypatch.setattr(bot, "send_challenge", lambda token, username, cfg: sent.append(username))

    bot.challenge_users("token", ["a", "b", "c"], cfg)

    assert sent == ["a"]


def test_api_wrapper_endpoints_and_online_bot_shapes(monkeypatch):
    calls = []
    responses = []

    def fake_api_request(token, method, path, data=None):
        calls.append((token, method, path, data))
        if responses:
            return responses.pop(0)
        return None

    monkeypatch.setattr(bot, "api_request", fake_api_request)

    bot.bot_make_move("token", "game/1", "e2e4", offering_draw=True)
    bot.bot_resign("token", "game/1")
    bot.bot_abort("token", "game/1")
    bot.bot_chat("token", "game/1", "player", "hello")

    assert calls[0] == ("token", "POST", "/api/bot/game/game/1/move/e2e4?offeringDraw=true", None)
    assert calls[1] == ("token", "POST", "/api/bot/game/game/1/resign", None)
    assert calls[2] == ("token", "POST", "/api/bot/game/game/1/abort", None)
    assert calls[3] == ("token", "POST", "/api/bot/game/game/1/chat", {"room": "player", "text": "hello"})

    responses.extend([[{"username": "a"}], {"users": [{"username": "b"}]}, {"online": [{"username": "c"}]}, {}])
    assert bot.online_bots("token") == [{"username": "a"}]
    assert bot.online_bots("token") == [{"username": "b"}]
    assert bot.online_bots("token") == [{"username": "c"}]
    assert bot.online_bots("token") == []

    responses.extend([{"id": "lab"}, []])
    assert bot.api_account("token") == {"id": "lab"}
    assert bot.api_account("token") == {}


def test_challenge_decline_busy_sends_reason(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "api_request", lambda *args: calls.append(args))

    assert bot.challenge_action("token", "decline", "chal1", "HumanOne", "busy")

    assert calls == [("token", "POST", "/api/challenge/chal1/decline", {"reason": "busy"})]


def test_own_blitz_rating_uses_fallbacks(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, fallback_blitz_rating=1500)
    responses = [
        {"perfs": {"blitz": {"rating": 1555, "prov": False}}},
        {"perfs": {"blitz": {"rating": 1600, "prov": True}}},
    ]

    monkeypatch.setattr(bot, "api_account", lambda token: responses.pop(0))
    assert bot.own_blitz_rating("token", cfg) == 1555
    assert bot.own_blitz_rating("token", cfg) == 1500

    monkeypatch.setattr(bot, "api_account", lambda token: (_ for _ in ()).throw(RuntimeError("boom")))
    assert bot.own_blitz_rating("token", cfg) == 1500


def test_format_chat_and_color_helpers():
    assert bot.format_chat("Hi {me}, gl {opponent}", me="LabZero", opponent="Maia") == "Hi LabZero, gl Maia"
    assert bot.is_bot_user({"title": "BOT"})
    assert bot.challenge_rating({"challenger": {"rating": "1510"}}) == 1510
    assert bot.challenge_rating({"challenger": {"rating": "bad"}}) is None
    assert bot.bot_color_from_full({"white": {"id": "lab"}, "black": {"id": "maia"}}, "lab") == chess.WHITE
    assert bot.bot_color_from_full({"white": {"id": "lab"}, "black": {"id": "maia"}}, "maia") == chess.BLACK
