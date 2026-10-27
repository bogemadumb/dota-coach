import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from dota_coach import gsi_fields  # noqa: E402
from simulate import COSTS, HEROES, MAIN_SLOTS, Match  # noqa: E402


def run_match(hero, until):
    match = Match("t", seed=7, hero=hero)
    for clock in range(-90, until + 1):
        match.advance(clock)
    return match


def test_big_items_stay_in_main_inventory_and_cheapest_is_sold():
    match = run_match("nevermore", 1500)
    assert len(match.items) <= MAIN_SLOTS
    assert "item_black_king_bar" in match.items and "item_satanic" in match.items
    assert "item_branches" not in match.items
    state = gsi_fields.parse(match.payload("game", 1500, 0))
    assert state.backpack == []
    names = {i.name for i in state.inventory}
    assert {"item_black_king_bar", "item_satanic", "item_blink"} <= names


def test_branches_are_sold_before_other_items():
    match = run_match("nevermore", 1500)
    kept_costs = [COSTS[i] for i in match.items]
    assert min(kept_costs) >= 450


def test_support_profile_has_low_last_hits_and_support_items():
    sup = run_match("lion", 900)
    core = run_match("nevermore", 900)
    assert sup.last_hits * 2.5 < core.last_hits
    assert sup.last_hits / 15 < 3
    assert "item_arcane_boots" in sup.items and "item_power_treads" in core.items
    state = gsi_fields.parse(sup.payload("game", 900, 0))
    assert state.hero == "lion" and state.hero_id == 26
    assert any(a.name == "lion_finger_of_death" and a.ultimate for a in state.abilities)


def test_default_hero_unchanged():
    state = gsi_fields.parse(Match("t", seed=1).payload("game", 100, 0))
    assert state.hero == "nevermore" and state.hero_id == 11
    assert set(HEROES) == {"nevermore", "lion"}
