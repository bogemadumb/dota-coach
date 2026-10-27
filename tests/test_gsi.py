import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from fastapi.testclient import TestClient  # noqa: E402

from dota_coach import gsi_fields  # noqa: E402
from dota_coach.config import DEFAULTS  # noqa: E402
from dota_coach.events import EventDetector  # noqa: E402
from dota_coach.server import create_app  # noqa: E402
from simulate import Match  # noqa: E402

TOKEN = "t"


def run_match(until: int) -> tuple[Match, list]:
    match = Match(TOKEN, seed=1)
    det = EventDetector()
    events = []
    for step in range(11):
        events += det.feed(gsi_fields.parse(match.payload("draft", -150 + step, step)))
    for clock in range(-90, until + 1):
        match.advance(clock)
        phase = "pregame" if clock < 0 else "game"
        events += det.feed(gsi_fields.parse(match.payload(phase, clock, 0)))
    return match, events


def kinds(events, kind):
    return [e for e in events if e.kind == kind]


def test_parse_game_payload():
    match = Match(TOKEN, seed=1)
    for clock in range(-90, 400):
        match.advance(clock)
    s = gsi_fields.parse(match.payload("game", 399, 0))
    assert s.phase == "game"
    assert s.clock == 399
    assert s.hero == "nevermore"
    assert s.team == "radiant"
    assert s.gold == int(match.gold)
    assert "item_bottle" in s.item_names()
    assert s.neutral is None
    assert s.teleport.name == "item_tpscroll"
    assert len(s.abilities) == 6
    assert all(i.name != "empty" for i in s.inventory)


def test_parse_empty_payload():
    s = gsi_fields.parse({})
    assert s.phase == "unknown" and s.clock is None and s.hero is None and s.draft is None


def test_draft_picks_detected_in_order():
    _, events = run_match(0)
    picks = kinds(events, "hero_picked")
    assert [p.data["hero"] for p in picks[:2]] == ["nevermore", "puck"]
    assert len(picks) == 10


def test_death_respawn_levels_items():
    _, events = run_match(500)
    assert len(kinds(events, "match_started")) == 1
    died = kinds(events, "hero_died")
    assert [e.clock for e in died] == [430]
    assert died[0].data["respawn_seconds"] > 0
    assert kinds(events, "hero_respawned")[0].clock > 430
    assert [e.data["level"] for e in kinds(events, "level_up")][:3] == [2, 3, 4]
    added = [e.data["item"] for e in kinds(events, "item_added")]
    assert added[:4] == ["item_tango", "item_branches", "item_branches", "item_faerie_fire"]
    assert "item_arcane_ring" in added
    removed = [e.data["item"] for e in kinds(events, "item_removed")]
    assert removed == ["item_faerie_fire", "item_tango"]


def test_game_event_reported_once():
    _, events = run_match(1200)
    rosh = [e for e in kinds(events, "game_event") if e.data["type"] == "roshan_killed"]
    assert len(rosh) == 1


def test_tick_every_second():
    _, events = run_match(60)
    ticks = [e.clock for e in kinds(events, "tick")]
    assert ticks == list(range(-90, 61))


def test_server_rejects_bad_token_and_keeps_draft():
    cfg = dict(DEFAULTS, gsi_token=TOKEN, log_raw_gsi=False)
    client = TestClient(create_app(cfg))
    match = Match(TOKEN, seed=1)
    bad = match.payload("game", 0, 0)
    bad["auth"]["token"] = "wrong"
    assert client.post("/gsi", json=bad).status_code == 403
    assert client.post("/gsi", json=match.payload("draft", -140, 10)).status_code == 200
    match.advance(-90)
    assert client.post("/gsi", json=match.payload("pregame", -90, 0)).status_code == 200
    state = client.get("/api/state").json()["state"]
    assert state["phase"] == "pregame"
    assert len(state["draft"]["picks"]["dire"]) == 5
