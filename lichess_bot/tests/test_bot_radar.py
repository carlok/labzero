import json

from lichess_bot import bot_radar


def user(name, rating, games=30, prov=False):
    return {
        "id": name.lower(),
        "username": name,
        "perfs": {"blitz": {"rating": rating, "games": games, "prov": prov}},
    }


def test_eligible_blitz_bots_filters_games_and_provisional():
    users = [
        user("A", 1800, games=30),
        user("LowGames", 1900, games=3),
        user("Prov", 2000, games=30, prov=True),
        {"username": "NoBlitz", "perfs": {}},
    ]

    rows = bot_radar.eligible_blitz_bots(users, min_games=20, allow_provisional=False)
    assert [row["username"] for row in rows] == ["A"]

    rows_with_prov = bot_radar.eligible_blitz_bots(users, min_games=20, allow_provisional=True)
    assert [row["username"] for row in rows_with_prov] == ["A", "Prov"]


def test_build_snapshot_stats_and_percentile(tmp_path):
    cfg = bot_radar.RadarConfig(
        interval_sec=60,
        min_blitz_games=20,
        allow_provisional=False,
        notify_interval_min=60,
        output_dir=str(tmp_path),
    )
    snapshot = bot_radar.build_snapshot(
        [
            user("A", 1600),
            user("B", 1800),
            user("C", 2000),
            user("D", 2200),
            user("E", 2400),
        ],
        own_rating=2100,
        cfg=cfg,
    )

    stats = snapshot["stats"]
    assert stats["count"] == 5
    assert stats["min"] == 1600
    assert stats["max"] == 2400
    assert stats["median"] == 2000
    assert stats["percentile"] == 60.0
    assert stats["below_or_equal"] == 3
    assert stats["above"] == 2
    assert [row["username"] for row in stats["nearest_stronger"]] == ["D", "E"]
    assert stats["buckets"]["2000-2099"] == 1


def test_save_and_format_snapshot(tmp_path):
    cfg = bot_radar.RadarConfig(
        interval_sec=60,
        min_blitz_games=20,
        allow_provisional=False,
        notify_interval_min=60,
        output_dir=str(tmp_path),
    )
    snapshot = bot_radar.build_snapshot([user("A", 1800), user("B", 2200)], 1900, cfg)
    path = bot_radar.save_snapshot(snapshot, cfg.output_dir)
    lines = path.read_text().splitlines()

    assert len(lines) == 1
    assert json.loads(lines[0])["own_rating"] == 1900
    text = bot_radar.format_snapshot(snapshot)
    assert "LabZero bot radar" in text
    assert "own blitz: 1900" in text
    assert "nearest stronger: B 2200" in text


def test_run_once_uses_api_and_saves(monkeypatch, tmp_path):
    cfg = bot_radar.RadarConfig(
        interval_sec=60,
        min_blitz_games=20,
        allow_provisional=False,
        notify_interval_min=60,
        output_dir=str(tmp_path),
    )
    fake_bot_cfg = object()
    monkeypatch.setattr(bot_radar.bot, "own_blitz_rating", lambda token, cfg: 2000)
    monkeypatch.setattr(bot_radar.bot, "online_bots", lambda token: [user("A", 1900), user("B", 2100)])

    snapshot, path = bot_radar.run_once("token", fake_bot_cfg, cfg)

    assert snapshot["stats"]["percentile"] == 50.0
    assert path.exists()
