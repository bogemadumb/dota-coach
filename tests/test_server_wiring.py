import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from fastapi.testclient import TestClient  # noqa: E402

from dota_coach.config import DEFAULTS  # noqa: E402
from dota_coach.server import Core, create_app  # noqa: E402
from dota_coach.voice import SilentVoice  # noqa: E402
from simulate import Match  # noqa: E402

TOKEN = "t"
TIMINGS = """
schedule:
  - {id: rune, first: 120, interval: 120, lead: 10, say: "Руна", priority: 3}
relative:
  roshan_killed:
    - {id: rosh, after: 10, lead: 0, say: "Рошан", priority: 3}
"""


def make(tmp_path):
    path = tmp_path / "timings.yaml"
    path.write_text(TIMINGS, encoding="utf-8")
    cfg = dict(DEFAULTS, gsi_token=TOKEN, log_raw_gsi=False)
    core = Core(cfg, voice=SilentVoice(), timings_path=path)
    return core, TestClient(create_app(cfg, core))


def feed(client, match, start, stop):
    for clock in range(start, stop + 1):
        match.advance(clock)
        client.post("/gsi", json=match.payload("pregame" if clock < 0 else "game", clock, 0))


def test_settings_roundtrip_and_validation(tmp_path):
    core, client = make(tmp_path)
    assert client.get("/api/settings").json() == {"mode": "normal", "voice_style": "commands", "voice_enabled": True, "brain_enabled": True, "role": "auto"}
    r = client.post("/api/settings", json={"mode": "chatty", "voice_style": "coach", "voice_enabled": False})
    assert r.status_code == 200 and r.json() == {"mode": "chatty", "voice_style": "coach", "voice_enabled": False, "brain_enabled": True, "role": "auto"}
    assert core.cfg["mode"] == "chatty"
    assert client.post("/api/settings", json={"mode": "loud"}).status_code == 400
    assert client.post("/api/settings", json={"voice_enabled": "yes"}).status_code == 400
    assert client.post("/api/settings", json={"nope": 1}).status_code == 400
    assert client.post("/api/settings", json=[1]).status_code == 400
    assert client.get("/api/settings").json()["mode"] == "chatty"


def test_mark_needs_clock_then_schedules_hint(tmp_path):
    core, client = make(tmp_path)
    assert client.post("/api/mark/roshan_killed").status_code == 400
    match = Match(TOKEN, seed=1)
    feed(client, match, -90, 100)
    r = client.post("/api/mark/roshan_killed")
    assert r.status_code == 200 and r.json()["clock"] == 100 and r.json()["rules"] == 1
    assert client.post("/api/mark/BAD!").status_code in (400, 404)
    q = core.bus.subscribe()
    feed(client, match, 101, 112)
    hints = []
    while not q.empty():
        topic, payload = q.get_nowait()
        if topic == "hint":
            hints.append(payload)
    assert [h["id"] for h in hints] == ["rune@120", "rosh:roshan_killed@100@110"]
    assert {"say", "detail"} <= hints[0].keys()


def test_game_event_roshan_marks_and_ticks_produce_hints(tmp_path):
    core, client = make(tmp_path)
    match = Match(TOKEN, seed=1)
    feed(client, match, -90, 1125)
    assert "rune@120" in core.arbiter.seen
    assert "rosh:roshan_killed@1110@1120" in core.arbiter.seen


def test_new_match_resets_timers_and_arbiter(tmp_path):
    core, client = make(tmp_path)
    feed(client, Match(TOKEN, seed=1), -90, 130)
    assert core.arbiter.seen and core.timers.fired
    client.post("/gsi", json=Match(TOKEN, seed=2).payload("pregame", -90, 0))
    assert core.arbiter.seen == set() and core.timers.fired == set()


def test_missing_timings_file_does_not_break_server(tmp_path):
    cfg = dict(DEFAULTS, gsi_token=TOKEN, log_raw_gsi=False)
    core = Core(cfg, voice=SilentVoice(), timings_path=tmp_path / "none.yaml")
    client = TestClient(create_app(cfg, core))
    feed(client, Match(TOKEN, seed=1), -90, 20)
    assert core.arbiter.seen == set()


def test_lifespan_runs_and_stops_arbiter(tmp_path):
    core, client = make(tmp_path)
    with client:
        assert client.get("/api/settings").status_code == 200
