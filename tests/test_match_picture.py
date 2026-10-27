import pytest

from dota_coach.brain import KnowledgeNames
from dota_coach.match_picture import MatchPicture, load_hero_tags
from dota_coach.state import Draft, GameState, Item

RADIANT = ["nevermore", "crystal_maiden", "mars", "antimage", "lion"]
DIRE = ["puck", "pudge", "slark", "phantom_assassin", "zuus"]


@pytest.fixture(scope="module")
def names():
    n = KnowledgeNames()
    if n.kn is None:
        pytest.skip("no knowledge cache")
    return n


def state(clock=600, gold=500, items=("item_bottle", "item_power_treads"), team="radiant", hero="nevermore", level=10):
    inv = [Item(name, f"slot{i}") for i, name in enumerate(items)]
    return GameState(received_at=0, phase="game", clock=clock, team=team, hero=hero, gold=gold, level=level,
                     inventory=inv, draft=Draft(picks={"radiant": list(RADIANT), "dire": list(DIRE)}))


def test_ten_heroes_with_teams_names_and_tags(names):
    pic = MatchPicture(names)
    pic.update_state(state())
    assert len(pic.heroes) == 10
    assert {p.team for p in pic.allies()} == {"radiant"} and len(pic.allies()) == 4
    assert [p.hero for p in pic.enemies()] == DIRE
    assert pic.heroes["nevermore"].is_me and pic.heroes["nevermore"].name == "Shadow Fiend"
    assert "evasion" in pic.heroes["phantom_assassin"].tags
    assert pic.heroes["phantom_assassin"].name == "Phantom Assassin"


def test_own_items_from_gsi_are_fresh_and_normalized(names):
    pic = MatchPicture(names)
    pic.update_state(state(clock=700))
    me = pic.heroes["nevermore"]
    assert me.item_keys() == ["bottle", "power_treads"]
    assert {(i.source, i.seen_at) for i in me.items} == {("gsi", 700)}
    pic.update_state(state(clock=760, items=("item_bottle",)))
    assert pic.heroes["nevermore"].item_keys() == ["bottle"]
    assert pic.heroes["nevermore"].items[0].seen_at == 760


def test_own_net_worth_is_items_plus_gold(names):
    pic = MatchPicture(names)
    pic.update_state(state(gold=500, items=("item_bottle", "item_power_treads")))
    value, estimate = pic.networth(pic.heroes["nevermore"])
    assert estimate is True
    assert value == 675 + 1400 + 500


def test_update_seen_stores_source_and_clock_and_returns_new_items(names):
    pic = MatchPicture(names)
    pic.update_state(state())
    new = pic.update_seen("phantom_assassin", ["item_desolator", "item_power_treads"], "scout", 620)
    assert sorted(new) == ["desolator", "power_treads"]
    pa = pic.heroes["phantom_assassin"]
    assert {(i.key, i.source, i.seen_at) for i in pa.items} == {("desolator", "scout", 620), ("power_treads", "scout", 620)}
    again = pic.update_seen("phantom_assassin", ["item_desolator", "item_power_treads", "item_black_king_bar"], "realtime", 700)
    assert again == ["black_king_bar"]
    assert {i.source for i in pa.items} == {"realtime"}


def test_older_snapshot_does_not_overwrite_newer(names):
    pic = MatchPicture(names)
    pic.update_state(state())
    pic.update_seen("puck", ["item_blink"], "realtime", 800)
    assert pic.update_seen("puck", ["item_bottle"], "screen", 700) == []
    assert pic.heroes["puck"].item_keys() == ["blink"]


def test_partial_update_merges(names):
    pic = MatchPicture(names)
    pic.update_state(state())
    pic.update_seen("pudge", ["item_blink", "item_arcane_boots"], "scout", 600)
    new = pic.update_seen("pudge", ["item_blink", "item_black_king_bar"], "screen", 900, partial=True)
    assert new == ["black_king_bar"]
    by_key = {i.key: i for i in pic.heroes["pudge"].items}
    assert set(by_key) == {"blink", "arcane_boots", "black_king_bar"}
    assert by_key["blink"].seen_at == 900 and by_key["arcane_boots"].seen_at == 600


def test_own_hero_ignores_other_sources_and_bad_source_raises(names):
    pic = MatchPicture(names)
    pic.update_state(state())
    assert pic.update_seen("nevermore", ["item_blink"], "scout", 650) == []
    assert pic.heroes["nevermore"].item_keys() == ["bottle", "power_treads"]
    with pytest.raises(ValueError):
        pic.update_seen("puck", [], "rumor", 1)


def test_net_worth_source_value_wins_else_item_costs(names):
    pic = MatchPicture(names)
    pic.update_state(state())
    pic.update_seen("slark", ["item_blink"], "scout", 600)
    value, estimate = pic.networth(pic.heroes["slark"])
    assert (value, estimate) == (2250, True)
    pic.update_seen("slark", ["item_blink"], "realtime", 700, net_worth=7800, level=14)
    assert pic.networth(pic.heroes["slark"]) == (7800, False)
    assert pic.heroes["slark"].level == 14
    assert pic.networth(pic.heroes["zuus"]) == (None, True)


def test_team_totals_partial_flag_and_advantage(names):
    pic = MatchPicture(names)
    pic.update_state(state(gold=0, items=("item_bottle",)))
    totals = pic.team_totals()
    assert totals["partial"] is True and totals["known"] == 1 and totals["advantage"] is None
    pic.update_seen("puck", ["item_blink"], "scout", 600)
    totals = pic.team_totals()
    assert totals["advantage"] == 675 - 2250 and totals["known"] == 2
    for hero in RADIANT[1:]:
        pic.update_seen(hero, ["item_boots"], "realtime", 600)
    for hero in DIRE[1:]:
        pic.update_seen(hero, ["item_boots"], "realtime", 600)
    assert pic.team_totals()["partial"] is False and pic.team_totals()["known"] == 10


def test_to_text_unknown_fresh_and_stale_items(names):
    pic = MatchPicture(names)
    pic.update_state(state(clock=1000))
    pic.update_seen("puck", ["item_blink", "item_arcane_boots"], "scout", 1000)
    pic.update_seen("pudge", ["item_blink"], "scout", 640)
    text = pic.to_text(1000)
    lines = {ln.split(" | ")[0].lstrip("- ").split(",")[0]: ln for ln in text.splitlines() if ln.startswith("- ")}
    assert "предметы неизвестны" in lines["Slark"]
    assert "Blink Dagger, Arcane Boots" in lines["Puck"] and "давно" not in lines["Puck"]
    assert "Blink Dagger (давно 6 мин)" in lines["Pudge"]
    assert "мобильность" in lines["Puck"] and "контроль" in lines["Pudge"]
    assert "NW ≈" in lines["Shadow Fiend (ты)"]
    assert text.startswith("Союзники:") and "Враги:" in text
    assert "Перевес по фарму: мы" in text and "из 10" in text


def test_two_minutes_is_not_stale_three_is(names):
    pic = MatchPicture(names)
    pic.update_state(state(clock=1000))
    pic.update_seen("puck", ["item_blink"], "scout", 880)
    assert "давно" not in pic.to_text(1000).split("Puck")[1].splitlines()[0]
    assert "давно 3 мин" in pic.to_text(1060).split("Puck")[1].splitlines()[0]


def test_to_text_without_tags_and_empty(names):
    pic = MatchPicture(names)
    assert pic.to_text(0) == ""
    pic.update_state(state())
    assert "уклонение" in pic.to_text(600) and "уклонение" not in pic.to_text(600, tags=False)


def test_reset_and_new_hero_from_source(names):
    pic = MatchPicture(names)
    pic.update_state(state())
    pic.reset()
    assert pic.heroes == {} and pic.team is None
    pic.update_seen("axe", ["item_blink"], "screen", 100)
    assert pic.heroes["axe"].team is None and pic.heroes["axe"].tags


def test_to_dict_has_ages(names):
    pic = MatchPicture(names)
    pic.update_state(state(clock=1000))
    pic.update_seen("puck", ["item_blink"], "scout", 700)
    puck = next(h for h in pic.to_dict(1000)["heroes"] if h["hero"] == "puck")
    assert puck["items"] == [{"key": "blink", "source": "scout", "seen_at": 700, "age": 300}]


def test_hero_tags_file_loads():
    tags = load_hero_tags()
    assert tags["phantom_assassin"] and len(tags) > 100
