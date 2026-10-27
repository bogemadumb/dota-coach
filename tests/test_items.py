import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fake_claude import Factory  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dota_coach.brain import KnowledgeNames  # noqa: E402
from dota_coach.config import DEFAULTS  # noqa: E402
from dota_coach.items import Advice, Candidate, ItemAdvisor, ItemsTrigger, detect_role, phase_of  # noqa: E402
from dota_coach.match_picture import MatchPicture  # noqa: E402
from dota_coach.server import Core, create_app  # noqa: E402
from dota_coach.state import Draft, GameState, Item  # noqa: E402
from dota_coach.voice import SilentVoice  # noqa: E402
from simulate import Match  # noqa: E402


@pytest.fixture(scope="module")
def names():
    n = KnowledgeNames()
    if n.kn is None:
        pytest.skip("no knowledge cache")
    return n


def make_state(hero="nevermore", clock=1500, gold=800, items=(), last_hits=300, enemies=("puck", "pudge", "zuus", "slark", "phantom_assassin"),
               allies=("crystal_maiden", "mars", "antimage", "omniknight"), phase="game", **kw):
    inv = [Item(n, f"slot{i}") for i, n in enumerate(items)]
    return GameState(received_at=0, phase=phase, clock=clock, team="radiant", hero=hero, gold=gold, last_hits=last_hits,
                     inventory=inv, draft=Draft(picks={"radiant": [hero, *allies], "dire": list(enemies)}), **kw)


def advise(names, state, ally_items=None, enemy_items=None, role="auto"):
    pic = MatchPicture(names)
    pic.update_state(state)
    for hero, items in (ally_items or {}).items():
        pic.update_seen(hero, items, "scout", state.clock)
    for hero, items in (enemy_items or {}).items():
        pic.update_seen(hero, items, "scout", state.clock)
    return ItemAdvisor(names, pic).compute(state, role)


def keys(advice):
    return [c.key for c in advice.candidates]


def test_phase_borders():
    assert [phase_of(c) for c in (-30, 0, 899, 900, 1799, 1800, None)] == ["start", "early", "early", "mid", "mid", "late", "early"]


def test_role_by_hero_and_manual_override(names):
    kn = names.kn
    assert detect_role(make_state("nevermore", clock=300, last_hits=0), kn)[0] == "core"
    assert detect_role(make_state("lion", clock=300, last_hits=0), kn)[0] == "support"
    assert detect_role(make_state("lion", clock=300), kn, "core") == ("core", "выбрана вручную")
    assert detect_role(make_state("nevermore", clock=300), kn, "support")[0] == "support"


def test_role_refined_by_last_hits_after_eight_minutes(names):
    kn = names.kn
    poor_carry = make_state("nevermore", clock=720, last_hits=12)
    assert detect_role(poor_carry, kn)[0] == "support"
    assert detect_role(make_state("nevermore", clock=479, last_hits=0), kn)[0] == "core"
    assert detect_role(make_state("mars", clock=900, last_hits=10), kn)[0] == "support"
    assert detect_role(make_state("lion", clock=900, last_hits=90), kn)[0] == "core"
    assert detect_role(make_state("lion", clock=900, last_hits=30), kn)[0] == "support"


def test_role_for_hero_without_carry_or_support_uses_last_hits(names):
    kn = names.kn
    assert "Carry" not in kn.hero("puck").roles and "Support" not in kn.hero("puck").roles
    assert detect_role(make_state("puck", clock=600, last_hits=70), kn)[0] == "core"
    assert detect_role(make_state("puck", clock=600, last_hits=10), kn)[0] == "support"
    assert detect_role(make_state("puck", clock=300, last_hits=0), kn)[0] == "core"


def test_core_vs_phantom_assassin_gets_true_strike_items(names):
    adv = advise(names, make_state(gold=3000))
    assert adv.role == "core"
    assert "monkey_king_bar" in keys(adv) or "bloodthorn" in keys(adv)
    top = next(c for c in adv.candidates if c.key in ("monkey_king_bar", "bloodthorn"))
    assert "Phantom Assassin" in " ".join(top.reasons)


def test_support_vs_invisible_enemy_gets_dust_or_sentry(names):
    st = make_state("lion", clock=1000, last_hits=15, enemies=("clinkz", "bounty_hunter", "puck", "pudge", "slark"))
    adv = advise(names, st)
    assert adv.role == "support"
    assert {"dust", "ward_sentry"} & set(keys(adv))


def test_core_invisible_rule_gives_dust_but_no_wards(names):
    st = make_state(clock=1000, enemies=("clinkz", "bounty_hunter", "riki", "pudge", "slark"), last_hits=250)
    adv = advise(names, st)
    assert adv.role == "core"
    assert "ward_sentry" not in keys(adv) and "ward_observer" not in keys(adv) and "ward_dispenser" not in keys(adv)


def test_weight_grows_with_number_of_enemies_with_tag(names):
    one = advise(names, make_state(clock=2000, gold=3000, enemies=("phantom_assassin", "pudge", "lion", "crystal_maiden", "axe")))
    many = advise(names, make_state(clock=2000, gold=3000, enemies=("phantom_assassin", "windrunner", "arc_warden", "pudge", "axe")))
    s_one = next(c.score for c in one.candidates if c.key == "monkey_king_bar")
    s_many = next(c.score for c in many.candidates if c.key == "monkey_king_bar")
    assert s_many > s_one


def test_enemy_item_reaction(names, monkeypatch):
    monkeypatch.setattr("dota_coach.items.TOP", 40)
    st = make_state(clock=2000, gold=3000, enemies=("lion", "crystal_maiden", "pudge", "axe", "abaddon"))
    base = advise(names, st)
    adv = advise(names, st, enemy_items={"abaddon": ["item_butterfly"]})
    cand = next(c for c in adv.candidates if c.key == "monkey_king_bar")
    assert "Butterfly" in " ".join(cand.reasons)
    before = next((c.score for c in base.candidates if c.key == "monkey_king_bar"), 0)
    assert cand.score > before


def test_enemy_glimmer_reaction_suggests_dust(names, monkeypatch):
    monkeypatch.setattr("dota_coach.items.TOP", 40)
    st = make_state(clock=2000, gold=3000, enemies=("lion", "crystal_maiden", "pudge", "axe", "abaddon"))
    adv = advise(names, st, enemy_items={"lion": ["item_glimmer_cape"]})
    dust = next(c for c in adv.candidates if c.key == "dust")
    assert "Glimmer" in " ".join(dust.reasons)
    assert "dust" not in keys(advise(names, st))


def test_owned_items_and_boots_family_excluded(names):
    st = make_state(gold=3000, items=("item_black_king_bar", "item_power_treads", "item_blink"))
    adv = advise(names, st)
    assert "black_king_bar" not in keys(adv) and "power_treads" not in keys(adv) and "boots" not in keys(adv)
    assert not any(k in keys(adv) for k in ("arcane_boots", "tranquil_boots", "phase_boots"))


def test_consumables_components_and_recipes_dropped(names):
    st = make_state(clock=-30, phase="pregame", gold=600)
    adv = advise(names, st)
    assert not set(keys(adv)) & {"tango", "clarity", "flask", "faerie_fire", "enchanted_mango", "tpscroll", "smoke_of_deceit"}
    mid = advise(names, make_state(clock=1300, gold=1500))
    assert not set(keys(mid)) & {"blade_of_alacrity", "staff_of_wizardry", "ogre_axe", "demon_edge", "reaver", "boots"}
    assert not any(k.startswith("recipe_") for k in keys(mid))
    assert all(c.cost > 0 for c in mid.candidates)


def test_start_phase_only_popular_items(names):
    adv = advise(names, make_state(clock=-30, phase="pregame", gold=600))
    assert adv.phase == "start" and adv.candidates
    assert all("популярно" in c.reasons[0] for c in adv.candidates)


def test_wards_only_for_support(names):
    sup = advise(names, make_state("lion", clock=-30, phase="pregame", gold=600, last_hits=0))
    core = advise(names, make_state("nevermore", clock=-30, phase="pregame", gold=600, last_hits=0))
    assert not set(keys(core)) & {"ward_sentry", "ward_dispenser", "ward_observer"}
    assert sup.role == "support"


def test_ally_aura_deduplicated_only_when_ally_items_known(names):
    enemies = ("lina", "zuus", "lich", "skywrath_mage", "puck")
    st = make_state("lion", clock=1800, gold=5000, last_hits=15, enemies=enemies, allies=("dazzle", "mars", "antimage", "axe"))
    unknown = advise(names, st)
    assert "pipe" in keys(unknown)
    known = advise(names, st, ally_items={"dazzle": ["item_pipe", "item_boots"]})
    assert "pipe" not in keys(known)
    assert any("Pipe of Insight" in x and "Dazzle" in x for x in known.excluded)
    assert "Не берём" in known.to_text()


def test_mekansm_and_greaves_share_a_slot(names):
    enemies = ("lina", "zuus", "lich", "skywrath_mage", "puck")
    st = make_state("lion", clock=1800, gold=5000, last_hits=15, enemies=enemies, allies=("dazzle", "mars", "antimage", "axe"))
    adv = advise(names, st, ally_items={"axe": ["item_guardian_greaves"]})
    assert not set(keys(adv)) & {"mekansm", "guardian_greaves"}


def test_affordability_and_next_part(names):
    rich = advise(names, make_state(clock=2000, gold=9000))
    assert any(c.affordable and c.gold_short == 0 for c in rich.candidates)
    poor = advise(names, make_state(clock=2000, gold=100))
    assert all(not c.affordable and c.gold_short == c.cost_left - 100 for c in poor.candidates)
    assert all(c.next_part and not c.next_part["affordable"] for c in poor.candidates if c.cost > c.next_part["cost"])
    mid = advise(names, make_state(clock=2000, gold=1400))
    part = next(c for c in mid.candidates if c.next_part and c.next_part["affordable"] and not c.affordable)
    assert part.next_part["cost"] <= 1400 < part.cost_left


def test_partially_built_item_cost_left_shrinks(names):
    st = make_state(clock=2000, gold=500, items=("item_demon_edge", "item_javelin"))
    adv = advise(names, st)
    mkb = next(c for c in adv.candidates if c.key == "monkey_king_bar")
    assert mkb.cost_left < mkb.cost


def test_top_six_and_text_and_dict(names):
    adv = advise(names, make_state(gold=3000))
    assert 1 <= len(adv.candidates) <= 6
    scores = [c.score for c in adv.candidates]
    assert scores == sorted(scores, reverse=True)
    text = adv.to_text()
    assert text.startswith("Роль: кор") and "не финальный совет" in text and "1. " in text
    data = adv.to_dict()
    assert data["candidates"][0]["name"] and data["clock_text"] == "25:00"
    assert Advice().to_text() == ""


def test_no_hero_or_state_gives_empty_advice(names):
    pic = MatchPicture(names)
    adv = ItemAdvisor(names, pic)
    assert adv.compute(None).candidates == []
    assert adv.compute(GameState(received_at=0, phase="draft", clock=-100)).candidates == []


def candidate(key="blink", part_key="boots", affordable=True, cost_left=500):
    part = {"key": part_key, "name": part_key, "cost": 500, "affordable": affordable}
    return Candidate(key, key, 2250, cost_left, False, 0, part, ["r"], 1.0)


def trig_state(clock, **kw):
    return GameState(received_at=0, phase=kw.pop("phase", "game"), clock=clock, hero="nevermore", **kw)


def test_trigger_fires_once_per_part_and_respects_debounce():
    t = ItemsTrigger()
    adv = Advice(candidates=[candidate("blink", "boots")])
    assert t.check(trig_state(100), adv, None) is not None
    assert t.check(trig_state(110), adv, None) is None
    assert t.check(trig_state(160), adv, None) is None
    adv2 = Advice(candidates=[candidate("blink", "gloves")])
    assert t.check(trig_state(120), adv2, None) is None
    assert t.check(trig_state(146), adv2, None) is not None
    assert t.check(trig_state(300), adv2, None) is None


def test_trigger_debounced_part_still_fires_later():
    t = ItemsTrigger()
    t.mark(100)
    adv = Advice(candidates=[candidate("blink", "boots")])
    assert t.check(trig_state(120), adv, None) is None
    assert t.check(trig_state(146), adv, None) is not None


def test_trigger_needs_affordable_part_alive_game_phase_and_min_clock():
    t = ItemsTrigger()
    unaffordable = Advice(candidates=[candidate(affordable=False)])
    assert t.check(trig_state(100), unaffordable, None) is None
    good = Advice(candidates=[candidate()])
    assert t.check(trig_state(100, alive=False), good, None) is None
    assert t.check(trig_state(100, phase="pregame"), good, None) is None
    assert t.check(trig_state(100, paused=True), good, None) is None
    assert t.check(trig_state(30), good, None) is None
    assert t.check(trig_state(100), good, None) is not None


def test_trigger_idle_every_four_minutes_only_if_nothing_else_asked():
    t = ItemsTrigger()
    empty = Advice()
    assert t.check(trig_state(100), empty, None) is None
    assert t.check(trig_state(339), empty, None) is None
    assert t.check(trig_state(340), empty, None) is not None
    assert t.check(trig_state(500), empty, None) is None
    assert t.check(trig_state(570), empty, None) is None
    t2 = ItemsTrigger()
    t2.check(trig_state(100), empty, None)
    assert t2.check(trig_state(340), empty, 200) is None
    assert t2.check(trig_state(440), empty, 200) is not None


def test_trigger_reset_and_clock_going_back():
    t = ItemsTrigger()
    adv = Advice(candidates=[candidate()])
    assert t.check(trig_state(500), adv, None) is not None
    t.reset()
    assert t.check(trig_state(100), adv, None) is not None


def wiring(**cfg_over):
    factory = Factory()
    cfg = dict(DEFAULTS, gsi_token="t", log_raw_gsi=False, **cfg_over)
    core = Core(cfg, voice=SilentVoice(), client_factory=factory)
    return core, factory, TestClient(create_app(cfg, core))


def ingest_until(core, match, stop, start=-90, draft=True):
    if draft:
        for step in range(11):
            core.ingest(match.payload("draft", -150 + step, step))
        for s in range(10):
            core.ingest(match.payload("strategy", -100 + s, 0))
    for clock in range(start, stop + 1):
        match.advance(clock)
        core.ingest(match.payload("pregame" if clock < 0 else "game", clock, 0))


def test_core_enemy_key_item_triggers_items_request_bypassing_debounce():
    core, factory, _ = wiring()
    match = Match("t", seed=3)
    ingest_until(core, match, 300)
    core.brain.pending.clear()
    core.items_trigger.mark(300)
    new = core.see_items("phantom_assassin", ["item_black_king_bar", "item_boots"], "scout")
    assert sorted(new) == ["black_king_bar", "boots"]
    req = core.brain.pending["items"]
    assert "Phantom Assassin" in req.note and "Black King Bar" in req.note and "Boots" not in req.note
    core.brain.pending.clear()
    assert core.see_items("phantom_assassin", ["item_black_king_bar", "item_boots"], "scout") == []
    assert "items" not in core.brain.pending
    core.see_items("pudge", ["item_blink"], "scout")
    assert "Pudge" in core.brain.pending["items"].note


def test_core_ally_key_item_does_not_trigger():
    core, _, _ = wiring()
    ingest_until(core, Match("t", seed=3), 300)
    core.brain.pending.clear()
    core.see_items("mars", ["item_black_king_bar"], "scout")
    assert "items" not in core.brain.pending


def test_core_tick_gold_trigger_and_debounce_and_topic():
    core, _, _ = wiring()
    q = core.bus.subscribe()
    match = Match("t", seed=3)
    ingest_until(core, match, 59)
    core.brain.pending.clear()
    fired = []
    for clock in range(60, 400):
        match.advance(clock)
        core.ingest(match.payload("game", clock, 0))
        if core.brain.pending.pop("items", None):
            fired.append(clock)
    assert fired and all(b - a >= 45 for a, b in zip(fired, fired[1:]))
    topics = []
    while not q.empty():
        topics.append(q.get_nowait()[0])
    assert "items" in topics


def test_death_request_includes_picture_and_candidates():
    core, factory, _ = wiring()
    match = Match("t", seed=3)
    ingest_until(core, match, 500)
    core.brain.pending.clear()
    match.alive, match.respawn = False, 30
    match.gold = 2500
    core.ingest(match.payload("game", 501, 0))
    assert "death" in core.brain.pending and "Золото 2" in core.brain.pending["death"].note
    text = core.brain_context("death")
    assert "Картина матча:" in text and "Покупки:" in text and "Кандидаты по убыванию" in text
    assert "Покупки:" in core.brain_context("items") and "Покупки:" in core.brain_context("periodic")
    assert "Покупки:" in core.brain_context("item_bought") and "Покупки:" in core.brain_context("plan")
    assert "Покупки:" not in core.brain_context("manual") and "Картина матча" not in core.brain_context("fight")


def test_api_items_and_role_setting():
    core, factory, client = wiring()
    match = Match("t", seed=3, hero="lion")
    for step in range(11):
        client.post("/gsi", json=match.payload("draft", -150 + step, step))
    for clock in range(-90, 700):
        match.advance(clock)
        client.post("/gsi", json=match.payload("pregame" if clock < 0 else "game", clock, 0))
    data = client.get("/api/items").json()
    assert data["role"] == "support" and data["role_setting"] == "auto" and data["candidates"]
    assert {"key", "name", "cost", "cost_left", "affordable", "reasons", "next_part"} <= data["candidates"][0].keys()
    r = client.post("/api/settings", json={"role": "core"})
    assert r.status_code == 200 and r.json()["role"] == "core"
    data = client.get("/api/items").json()
    assert data["role"] == "core" and data["role_setting"] == "core"
    assert client.post("/api/settings", json={"role": "carry"}).status_code == 400
    assert client.post("/api/settings", json={"role": "auto"}).json()["role"] == "auto"


def test_items_websocket_hello_and_live_update():
    core, factory, client = wiring()
    with client:
        match = Match("t", seed=3)
        for step in range(11):
            client.post("/gsi", json=match.payload("draft", -150 + step, step))
        for clock in range(-90, 100):
            match.advance(clock)
            client.post("/gsi", json=match.payload("pregame" if clock < 0 else "game", clock, 0))
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            assert hello["items"]["candidates"]
            client.post("/api/settings", json={"role": "support"})
            end = time.time() + 3
            got = None
            while time.time() < end:
                msg = ws.receive_json()
                if msg["type"] == "items":
                    got = msg
                    break
            assert got and got["items"]["role"] == "support"


def test_items_request_has_priority_between_death_and_item_bought():
    from dota_coach.brain import PRIORITY, REQUEST_TTL
    assert PRIORITY["death"] < PRIORITY["items"] < PRIORITY["item_bought"]
    assert REQUEST_TTL["items"] == 30.0


def test_new_match_resets_picture_and_trigger():
    core, _, _ = wiring()
    ingest_until(core, Match("t", seed=3), 200)
    core.see_items("puck", ["item_blink"], "scout")
    assert core.picture.heroes["puck"].items
    core.ingest(Match("t", seed=4).payload("pregame", -90, 0))
    assert core.picture.heroes.get("puck") is None or not core.picture.heroes["puck"].items
    assert core.items_trigger.notified == set()
