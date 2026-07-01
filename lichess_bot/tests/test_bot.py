import json
from dataclasses import dataclass
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
    assert cfg.log_level == "normal"
    assert cfg.max_bot_challenges_per_day == 100
    assert cfg.bot_challenge_quota_margin == 10
    assert cfg.move_overhead_ms == 500
    assert cfg.uci_threads == 4
    assert cfg.uci_hash_mb == 64
    assert cfg.avoid_bots_file.endswith("lichess_bot/local/avoid-bots.json")
    assert cfg.opponent_cooldown_file.endswith("lichess_bot/local/opponent-cooldown.json")
    assert cfg.accept_draw_enabled is True
    assert cfg.accept_draw_losing_score == -100
    assert cfg.notify_provider == "none"
    assert cfg.notify_busy_human_challenge is True
    assert cfg.notify_radar_after_game is True
    assert cfg.notify_radar_after_game_delay_sec == 2
    assert cfg.notify_block_summary is True
    assert cfg.oracle_after_block is False
    assert cfg.oracle_max_positions == 40
    assert cfg.oracle_nodes == 20000
    assert cfg.oracle_script.endswith("scripts/host-oracle-label.py")
    assert cfg.oracle_out_dir.endswith("data/oracle")
    assert cfg.oracle_report_dir.endswith("docs/oracle")
    assert cfg.radar_min_blitz_games == 20
    assert cfg.radar_allow_provisional is False
    assert cfg.cancel_stale_outgoing_challenges is True
    assert cfg.opponent_cooldown_sec == 1200
    assert cfg.chat_rooms == ["player"]
    assert cfg.opening_first_move == "book"
    assert cfg.target_expected_score_min is None
    assert cfg.target_expected_score_max is None

    with pytest.raises(ValueError, match="accept_from"):
        make_config(tmp_path, accept_from="everyone")
    with pytest.raises(ValueError, match="challenge_color"):
        make_config(tmp_path, challenge_color="blue")
    with pytest.raises(ValueError, match="log_level"):
        make_config(tmp_path, log_level="chatty")
    with pytest.raises(ValueError, match="opening_first_move"):
        make_config(tmp_path, opening_first_move="c4")
    with pytest.raises(ValueError, match="threads"):
        make_config(tmp_path, threads=0)
    with pytest.raises(ValueError, match="notify_provider"):
        make_config(tmp_path, notify_provider="email")
    with pytest.raises(ValueError, match="chat_rooms"):
        make_config(tmp_path, chat_rooms=["player", "team"])
    with pytest.raises(ValueError, match="target_expected_score_min"):
        make_config(tmp_path, target_expected_score_min=-0.1)
    with pytest.raises(ValueError, match="target_expected_score_max"):
        make_config(tmp_path, target_expected_score_max=1.1)
    with pytest.raises(ValueError, match="target_expected_score_min must be <="):
        make_config(tmp_path, target_expected_score_min=0.6, target_expected_score_max=0.5)

    both_rooms = make_config(tmp_path, chat_rooms=["player", "spectator", "player"])
    assert both_rooms.chat_rooms == ["player", "spectator"]


def test_move_line_formatting_is_readable():
    me = bot.format_move_line(
        "game1",
        17,
        chess.BLACK,
        "e7e5",
        is_me=True,
        source="book",
        status="posting",
        score_cp=42,
    )
    assert "9..." in me
    assert "🤖 ME" in me
    assert "🔵 Black" in me
    assert "e7e5" in me
    assert "📚 book" in me
    assert "score=+42" in me
    assert "posting" in me
    assert "game=game1" in me

    opponent = bot.format_move_line(
        "game1",
        16,
        chess.WHITE,
        "e2e4",
        is_me=False,
        status="received",
    )
    assert "9." in opponent
    assert "🆚 OPP" in opponent
    assert "⚪ White" in opponent
    assert "received" in opponent


def test_move_source_labels_show_book_or_no_book():
    assert bot.move_source_label("book") == "📚 book"
    assert bot.move_source_label("engine") == "🧠 engine no-book"
    assert bot.move_source_label("tablebase") == "🧩 tablebase no-book"


def test_log_level_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LABZERO_BOT_LOG_LEVEL", "verbose")
    cfg = make_config(tmp_path, log_level="quiet")
    assert cfg.log_level == "verbose"
    assert bot.log_allows(cfg, "normal")
    assert bot.log_allows(cfg, "verbose")


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


def test_notify_block_summary_message_formats_score():
    summaries = [
        bot.FinishedGameSummary("g1", "WIN", "1-0", "A", 2010, "mate"),
        bot.FinishedGameSummary("g2", "DRAW", "1/2-1/2", "B", 2020, "draw"),
        bot.FinishedGameSummary("g3", "LOSS", "0-1", "C", 2030, "mate"),
    ]

    text = bot.notify_message_block_summary(summaries, 3)

    assert "3-game block" in text
    assert "1W-1D-1L" in text
    assert "score=1.5/3 (50.0%)" in text
    assert "avg opponent: 2020" in text


def test_oracle_after_block_builds_command_from_finished_pgns(tmp_path):
    cfg = make_config(
        tmp_path,
        oracle_stockfish="/opt/stockfish",
        oracle_max_positions=12,
        oracle_nodes=3456,
        pgn_directory=str(tmp_path / "pgn"),
    )
    pgn_dir = Path(cfg.pgn_directory)
    pgn_dir.mkdir(parents=True)
    pgn_path = pgn_dir / "20260630_LabZeroBot0_vs_Other_game1234.pgn"
    pgn_path.write_text('[Site "https://lichess.org/game1234"]\n\n1. e4 e5 *\n')
    summary = bot.FinishedGameSummary("game1234", "WIN", "1-0", "Other", 2000, "mate")

    command = bot.build_oracle_after_block_command(cfg, [summary], "data/oracle/out.jsonl", "docs/oracle/out.md")

    assert command[0].endswith("python") or "python" in command[0]
    assert "--stockfish" in command
    assert "/opt/stockfish" in command
    assert "--max-positions" in command
    assert "12" in command
    assert "--nodes" in command
    assert "3456" in command
    assert str(pgn_path) in command


def test_run_oracle_after_block_runs_only_with_finished_summaries(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, notify_provider="telegram", pgn_directory=str(tmp_path / "pgn"))
    pgn_dir = Path(cfg.pgn_directory)
    pgn_dir.mkdir(parents=True)
    (pgn_dir / "20260630_LabZeroBot0_vs_Other_game1234.pgn").write_text(
        '[Site "https://lichess.org/game1234"]\n\n1. e4 e5 *\n'
    )
    out_path = tmp_path / "oracle.jsonl"
    report_path = tmp_path / "oracle.md"
    calls = []
    notifications = []
    monkeypatch.setattr(bot, "oracle_output_paths", lambda cfg: (str(out_path), str(report_path)))

    def fake_run(command, check=False, capture_output=True, text=True, timeout=300):
        calls.append(command)
        out_path.write_text(
            json.dumps(
                {
                    "source": {"id": "game1234", "ply": 12},
                    "student": {"move": "e2e4"},
                    "moves": [{"uci": "e2e4", "rank": 3, "bucket": "mistake", "delta_utility": 0.2}],
                }
            )
            + "\n"
        )

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    monkeypatch.setattr(bot.subprocess, "run", fake_run)
    monkeypatch.setattr(bot, "notify", lambda cfg, text: notifications.append(text))

    empty_state = bot.RuntimeState()
    bot.run_oracle_after_block(cfg, empty_state, 1)
    assert calls == []

    state = bot.RuntimeState()
    state.record_finished_game(bot.FinishedGameSummary("game1234", "WIN", "1-0", "Other", 2000, "mate"), {"other"})
    bot.run_oracle_after_block(cfg, state, 1)

    assert len(calls) == 1
    assert "--pgn" in calls[0]
    assert len(notifications) == 1
    assert "ORACLE block analysis" in notifications[0]
    assert "game1234 ply 12" in notifications[0]


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


def test_runtime_state_tracks_opponent_cooldown(monkeypatch):
    state = bot.RuntimeState()
    fake_now = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: fake_now[0])

    state.record_finished_game(
        bot.FinishedGameSummary("g1", "WIN", "1-0", "Maia5", 1510, "mate"),
        {"maia5"},
    )

    assert state.opponent_cooldown_remaining("Maia5", 1200) == 1200
    fake_now[0] += 1195
    assert 0 < state.opponent_cooldown_remaining("maia5", 1200) <= 5
    fake_now[0] += 10
    assert state.opponent_cooldown_remaining("maia5", 1200) == 0
    assert state.finished_game_summaries()[0].game_id == "g1"


def test_runtime_state_persists_opponent_cooldown(monkeypatch, tmp_path):
    cooldown_path = tmp_path / "opponent-cooldown.json"
    fake_now = [1000.0]
    monkeypatch.setattr(bot.time, "time", lambda: fake_now[0])
    state = bot.RuntimeState(opponent_cooldown_file=str(cooldown_path))

    state.record_finished_game(
        bot.FinishedGameSummary("g1", "WIN", "1-0", "Maia5", 1510, "mate"),
        {"Maia5", "maia5"},
    )

    fresh_state = bot.RuntimeState(opponent_cooldown_file=str(cooldown_path))
    assert fresh_state.opponent_cooldown_remaining("maia5", 1200) == 1200

    fake_now[0] += 1195
    assert 0 < fresh_state.opponent_cooldown_remaining("MAIA5", 1200) <= 5


def test_load_opponent_cooldown_ignores_bad_files(tmp_path):
    cooldown_path = tmp_path / "opponent-cooldown.json"
    cooldown_path.write_text("{bad json")

    assert bot.load_opponent_cooldown(str(cooldown_path)) == {}


def test_runtime_state_sigint_paths_without_forcing_exit(monkeypatch):
    state = bot.RuntimeState()

    with pytest.raises(SystemExit):
        state.handle_sigint(2, None)

    state = bot.RuntimeState()
    state.begin_game("g1", "starting")
    state.handle_sigint(2, None)
    assert state._force_quit is True


def test_run_game_worker_notifies_on_unexpected_exit(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, notify_provider="telegram")
    state = bot.RuntimeState()
    notifications: list[str] = []
    monkeypatch.setattr(
        bot,
        "play_game",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(bot, "notify", lambda cfg, text: notifications.append(text))

    bot.run_game_worker("token", object(), "game1", "labzerobot0", cfg, state)

    assert len(notifications) == 1
    assert "GAME WORKER STOPPED game1" in notifications[0]
    assert "boom" in notifications[0]


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


def test_engine_limit_caps_movetime_on_low_clock(tmp_path):
    cfg = make_config(tmp_path, move_overhead_ms=500, max_movetime_ms=5000)
    limit = bot.engine_limit(
        cfg,
        chess.Board(),
        {"wtime": 6000, "btime": 180000, "winc": 2000, "binc": 2000},
    )

    assert limit.white_clock == pytest.approx(5.5)
    assert limit.time == pytest.approx(0.5)


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


def test_syzygy_selection_prefers_shortest_win():
    slow_win = chess.Move.from_uci("e1e2")
    fast_win = chess.Move.from_uci("e1f1")

    picked = bot.select_syzygy_move([(2, 24, slow_win), (2, 6, fast_win)])

    assert picked == fast_win


def test_syzygy_selection_prefers_draw_over_long_loss():
    draw = chess.Move.from_uci("e1e2")
    long_loss = chess.Move.from_uci("e1f1")

    picked = bot.select_syzygy_move([(0, 2, draw), (-2, 90, long_loss)])

    assert picked == draw


def test_syzygy_selection_prefers_longest_resistance_when_losing():
    short_loss = chess.Move.from_uci("e1e2")
    long_loss = chess.Move.from_uci("e1f1")

    picked = bot.select_syzygy_move([(-2, 8, short_loss), (-2, 80, long_loss)])

    assert picked == long_loss


@dataclass
class FakeBookEntry:
    move: chess.Move
    weight: int = 1


def test_preferred_first_book_move_uses_configured_book_move_only():
    board = chess.Board()
    entries = [
        FakeBookEntry(chess.Move.from_uci("g1f3")),
        FakeBookEntry(chess.Move.from_uci("d2d4")),
    ]

    assert bot.preferred_first_book_move(board, entries, "d4") == chess.Move.from_uci("d2d4")
    assert bot.preferred_first_book_move(board, entries, "e4") is None
    assert bot.preferred_first_book_move(board, entries, "book") is None


def test_preferred_first_book_move_applies_only_to_white_first_move():
    board = chess.Board()
    board.push(chess.Move.from_uci("g1f3"))
    entries = [FakeBookEntry(chess.Move.from_uci("d7d5"))]

    assert bot.preferred_first_book_move(board, entries, "d4") is None


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


def test_elo_expected_score():
    assert bot.elo_expected_score(2000, 2000) == pytest.approx(0.5)
    assert bot.elo_expected_score(2000, 2200) == pytest.approx(0.240253, abs=0.000001)
    assert bot.elo_expected_score(2000, 1800) == pytest.approx(0.759747, abs=0.000001)


def test_choose_candidates_filters_by_expected_score(monkeypatch, tmp_path):
    cfg = make_config(
        tmp_path,
        min_blitz_games=20,
        target_rating_min_delta=-300,
        target_rating_max_delta=300,
        target_expected_score_min=0.35,
        target_expected_score_max=0.60,
    )
    users = [
        {"username": "too-soft", "perfs": {"blitz": {"rating": 1800, "games": 100}}},
        {"username": "good", "perfs": {"blitz": {"rating": 2050, "games": 100}}},
        {"username": "too-hard", "perfs": {"blitz": {"rating": 2200, "games": 100}}},
    ]
    monkeypatch.setattr(bot.random, "shuffle", lambda items: None)

    candidates = bot.choose_candidates(users, "self", 2000, cfg)

    assert [user["username"] for user in candidates] == ["good"]


def test_choose_candidates_closest_superior_uses_nearest_stronger(tmp_path):
    cfg = make_config(tmp_path, min_blitz_games=20, target_rating_min_delta=-200, target_rating_max_delta=300)
    users = [
        {"username": "lower", "perfs": {"blitz": {"rating": 1900, "games": 100}}},
        {"username": "far", "perfs": {"blitz": {"rating": 2200, "games": 100}}},
        {"username": "near-b", "perfs": {"blitz": {"rating": 2030, "games": 100}}},
        {"username": "near-a", "perfs": {"blitz": {"rating": 2030, "games": 100}}},
        {"username": "exact", "perfs": {"blitz": {"rating": 2000, "games": 100}}},
    ]

    candidates = bot.choose_candidates(users, "self", 2000, cfg, closest_superior=True)

    assert [user["username"] for user in candidates] == ["near-a", "near-b", "far"]


def test_choose_candidates_closest_superior_skips_too_hard_by_expected_score(tmp_path):
    cfg = make_config(
        tmp_path,
        min_blitz_games=20,
        target_rating_min_delta=0,
        target_rating_max_delta=400,
        target_expected_score_min=0.35,
    )
    users = [
        {"username": "near", "perfs": {"blitz": {"rating": 2050, "games": 100}}},
        {"username": "too-hard", "perfs": {"blitz": {"rating": 2200, "games": 100}}},
    ]

    candidates = bot.choose_candidates(users, "self", 2000, cfg, closest_superior=True)

    assert [user["username"] for user in candidates] == ["near"]


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


def test_play_game_reconnects_after_transient_stream_drop(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)
    state = bot.RuntimeState()
    state.begin_game("game1", "starting")
    posted: list[tuple[str, str]] = []
    monkeypatch.setattr(bot.time, "sleep", lambda delay: None)
    monkeypatch.setattr(bot, "maybe_chat", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bot,
        "choose_move",
        lambda *args, **kwargs: bot.MoveDecision(chess.Move.from_uci("e7e5"), score_cp=0),
    )
    monkeypatch.setattr(
        bot,
        "bot_make_move",
        lambda token, game_id, move, offering_draw=False: posted.append((game_id, move)),
    )

    def dropped_stream():
        yield {
            "type": "gameFull",
            "white": {"id": "maia5", "name": "maia5", "title": "BOT", "rating": 1510},
            "black": {"id": "labzerobot0", "name": "LabZeroBot0", "title": "BOT", "rating": 1500},
            "state": {"moves": "", "wtime": 180000, "btime": 180000},
        }
        raise bot.urllib.error.URLError("temporary stream drop")

    streams = [
        dropped_stream(),
        iter(
            [
                {"type": "gameState", "moves": "e2e4", "wtime": 180000, "btime": 180000},
                {"type": "gameState", "moves": "e2e4 e7e5", "status": "draw"},
            ]
        ),
    ]
    monkeypatch.setattr(bot, "bot_game_stream", lambda token, game_id: streams.pop(0))

    bot.play_game("token", object(), "game1", "labzerobot0", cfg, state)

    assert posted == [("game1", "e7e5")]
    assert state.active_count() == 0


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


def test_bot_make_move_with_retry_retries_transient_error(monkeypatch):
    calls = []

    def flaky_move(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise bot.urllib.error.URLError("temporary network drop")

    monkeypatch.setattr(bot.time, "sleep", lambda delay: None)
    monkeypatch.setattr(bot, "bot_make_move", flaky_move)

    bot.bot_make_move_with_retry("token", "game1", "e2e4", False)

    assert len(calls) == 2


def test_bot_make_move_with_retry_does_not_retry_stale_error(monkeypatch):
    calls = []

    def stale_move(*args, **kwargs):
        calls.append(args)
        raise bot.ApiError('HTTP 400: {"error":"Not your turn, or game already over"}')

    monkeypatch.setattr(bot, "bot_make_move", stale_move)

    with pytest.raises(bot.ApiError):
        bot.bot_make_move_with_retry("token", "game1", "e2e4", False)

    assert len(calls) == 1


def test_challenge_cooldown_seconds_parses_rate_limit():
    assert bot.challenge_cooldown_seconds(Exception('{"seconds":10053}')) == 10053
    assert bot.challenge_cooldown_seconds(Exception("played 100 games against other bots today")) == 3600
    assert bot.challenge_cooldown_seconds(Exception("other error")) is None


def test_challenge_id_from_response_shapes():
    assert bot.challenge_id_from_response({"challenge": {"id": "abc123"}}) == "abc123"
    assert bot.challenge_id_from_response({"id": "def456"}) == "def456"
    assert bot.challenge_id_from_response({}) is None
    assert bot.challenge_id_from_response([]) is None


def test_challenge_users_only_sends_one_in_single_game_mode(monkeypatch, tmp_path):
    cfg = make_config(tmp_path, max_parallel_games=1)
    sent = []
    monkeypatch.setattr(bot, "send_challenge", lambda token, username, cfg: sent.append(username))

    bot.challenge_users("token", ["a", "b", "c"], cfg)

    assert sent == ["a"]


def test_closest_superior_tries_next_after_one_idle_cycle(monkeypatch, tmp_path):
    cfg = make_config(
        tmp_path,
        challenge_interval_sec=1,
        target_rating_min_delta=-100,
        target_rating_max_delta=200,
    )
    quota = bot.ChallengeQuota(str(tmp_path / "quota.json"), daily_limit=100, margin=10)
    state = bot.RuntimeState()
    users = [
        {"username": "near", "perfs": {"blitz": {"rating": 2010, "games": 100}}},
        {"username": "next", "perfs": {"blitz": {"rating": 2020, "games": 100}}},
    ]
    sent = []
    cancelled = []
    fake_now = [0.0]

    monkeypatch.setattr(bot, "own_blitz_rating", lambda token, cfg: 2000)
    monkeypatch.setattr(bot, "online_bots", lambda token: users)
    monkeypatch.setattr(bot, "send_challenge", lambda token, username, cfg: sent.append(username) or f"chal-{username}")
    monkeypatch.setattr(bot, "cancel_challenge", lambda token, challenge_id, username: cancelled.append((challenge_id, username)) or True)
    monkeypatch.setattr(bot.time, "time", lambda: fake_now[0])

    def fake_sleep(seconds):
        fake_now[0] += seconds
        if len(sent) >= 2:
            state.stop.set()

    monkeypatch.setattr(bot.time, "sleep", fake_sleep)

    bot.challenge_loop("token", "self", cfg, state, quota, closest_superior=True)

    assert sent == ["near", "next"]
    assert cancelled == [("chal-near", "near")]


def test_challenge_loop_skips_recent_opponent(monkeypatch, tmp_path):
    cfg = make_config(
        tmp_path,
        challenge_interval_sec=1,
        opponent_cooldown_sec=1200,
        target_rating_min_delta=-100,
        target_rating_max_delta=200,
    )
    quota = bot.ChallengeQuota(str(tmp_path / "quota.json"), daily_limit=100, margin=10)
    state = bot.RuntimeState()
    fake_now = [5000.0]
    monkeypatch.setattr(bot.time, "time", lambda: fake_now[0])
    state.record_finished_game(
        bot.FinishedGameSummary("g1", "WIN", "1-0", "near", 2010, "mate"),
        {"near"},
    )
    users = [
        {"username": "near", "perfs": {"blitz": {"rating": 2010, "games": 100}}},
        {"username": "next", "perfs": {"blitz": {"rating": 2020, "games": 100}}},
    ]
    sent = []

    monkeypatch.setattr(bot, "own_blitz_rating", lambda token, cfg: 2000)
    monkeypatch.setattr(bot, "online_bots", lambda token: users)
    monkeypatch.setattr(bot, "send_challenge", lambda token, username, cfg: sent.append(username) or f"chal-{username}")

    def fake_sleep(seconds):
        fake_now[0] += seconds
        state.stop.set()

    monkeypatch.setattr(bot.time, "sleep", fake_sleep)

    bot.challenge_loop("token", "self", cfg, state, quota, closest_superior=True)

    assert sent == ["next"]


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
    assert bot.cancel_challenge("token", "chal/1", "SomeBot")

    assert calls[0] == ("token", "POST", "/api/bot/game/game/1/move/e2e4?offeringDraw=true", None)
    assert calls[1] == ("token", "POST", "/api/bot/game/game/1/resign", None)
    assert calls[2] == ("token", "POST", "/api/bot/game/game/1/abort", None)
    assert calls[3] == ("token", "POST", "/api/bot/game/game/1/chat", {"room": "player", "text": "hello"})
    assert calls[4] == ("token", "POST", "/api/challenge/chal%2F1/cancel", None)

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
