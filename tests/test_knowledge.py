import json

import pytest

from dota_coach.knowledge import CACHE_DIR, Knowledge


def _item(i, dname, cost, components=None, tier=None, abilities=None):
    d = {"id": i, "dname": dname, "cost": cost, "components": components, "abilities": abilities or []}
    if tier:
        d["tier"] = tier
    return d


ITEMS = {
    "ogre_axe": _item(21, "Ogre Axe", 1000),
    "mithril_hammer": _item(8, "Mithril Hammer", 1600),
    "belt_of_strength": _item(22, "Belt of Strength", 450),
    "blade_of_alacrity": _item(3, "Blade of Alacrity", 1000),
    "boots_of_elegance": _item(5, "Boots of Elegance", 450),
    "recipe_black_king_bar": _item(115, "Black King Bar Recipe", 1450),
    "black_king_bar": _item(116, "Black King Bar", 4050, ["mithril_hammer", "ogre_axe"], abilities=[
        {"type": "active", "title": "Avatar", "description": "Grants immunity. Duration: 9s."},
        {"type": "passive", "title": "Strength", "description": "Bonus."}]),
    "blink": _item(1, "Blink Dagger", 2250),
    "sange": _item(10, "Sange", 1900, ["ogre_axe", "belt_of_strength"]),
    "yasha": _item(11, "Yasha", 1900, ["blade_of_alacrity", "boots_of_elegance"]),
    "sange_and_yasha": _item(12, "Sange and Yasha", 4200, ["sange", "yasha"]),
    "arcane_ring": _item(349, "Arcane Ring", 0, tier=1),
}


def _hero(i, name, display, roles, attr="agi", atk="Melee"):
    return {"id": i, "name": f"npc_dota_hero_{name}", "localized_name": display, "roles": roles,
            "primary_attr": attr, "attack_type": atk}


HEROES = {
    "1": _hero(1, "antimage", "Anti-Mage", ["Carry"]),
    "2": _hero(2, "nevermore", "Shadow Fiend", ["Carry", "Nuker"], atk="Ranged"),
    "3": _hero(3, "pudge", "Pudge", ["Disabler"], attr="str"),
    "4": _hero(4, "slark", "Slark", ["Carry", "Escape"]),
}


def _mu(rows):
    return [{"hero_id": h, "games_played": g, "wins": w} for h, g, w in rows]


@pytest.fixture
def kb(tmp_path):
    const = tmp_path / "dotaconstants"
    od = tmp_path / "opendota"
    const.mkdir()
    od.mkdir()
    (const / "heroes.json").write_text(json.dumps(HEROES))
    (const / "items.json").write_text(json.dumps(ITEMS))
    (const / "item_ids.json").write_text(json.dumps({str(v["id"]): k for k, v in ITEMS.items()}))
    (const / "abilities.json").write_text(json.dumps({
        "nevermore_requiem": {"dname": "Requiem of Souls", "mc": ["150", "175", "200"], "cd": ["120", "110", "100"],
                              "behavior": "No Target"},
        "nevermore_necromastery": {"dname": "Necromastery", "is_innate": True, "behavior": ["Passive", "Hidden"]},
        "special_bonus_unique_nevermore_7": {"dname": "+30 Shadowraze Stack Damage"},
    }))
    (const / "hero_abilities.json").write_text(json.dumps({
        "npc_dota_hero_nevermore": {
            "abilities": ["nevermore_requiem", "nevermore_necromastery", "generic_hidden"],
            "talents": [{"name": "special_bonus_unique_nevermore_7", "level": 1}],
        }
    }))
    pop = {"start_game_items": {"21": 5, "22": 9}, "early_game_items": {"1": 3, "116": 10, "999": 50},
           "mid_game_items": {}, "late_game_items": {"116": 1}}
    (od / "hero_2_item_popularity.json").write_text(json.dumps({"fetched_at": "x", "data": pop}))
    mu = {
        1: [(2, 200, 120), (3, 100, 60), (4, 100, 40)],
        2: [(1, 200, 80), (3, 100, 45), (4, 10, 9)],
        3: [(1, 100, 40), (2, 100, 55), (4, 100, 50)],
        4: [(1, 100, 60), (2, 10, 1), (3, 100, 30)],
    }
    for hid, rows in mu.items():
        (od / f"hero_{hid}_matchups.json").write_text(json.dumps({"fetched_at": "x", "data": _mu(rows)}))
    return Knowledge(tmp_path)


def test_hero_lookup_forms(kb):
    h = kb.hero("nevermore")
    assert h is kb.hero("nevermore") or h == kb.hero("npc_dota_hero_nevermore") == kb.hero(2) == kb.hero("2")
    assert kb.hero("Shadow Fiend") == h
    assert (h.name, h.primary_attr, h.attack_type, h.roles) == ("Shadow Fiend", "agi", "Ranged", ("Carry", "Nuker"))
    with pytest.raises(KeyError):
        kb.hero("nobody")
    with pytest.raises(KeyError):
        kb.hero(999)


def test_hero_abilities_and_talents(kb):
    h = kb.hero("nevermore")
    assert [a.key for a in h.abilities] == ["nevermore_requiem", "nevermore_necromastery"]
    req = h.abilities[0]
    assert (req.name, req.cooldown, req.mana) == ("Requiem of Souls", "120/110/100", "150/175/200")
    assert h.abilities[1].innate and h.abilities[1].cooldown is None
    assert [(t.level, t.name) for t in h.talents] == [(1, "+30 Shadowraze Stack Damage")]


def test_item_lookup(kb):
    a = kb.item("item_black_king_bar")
    assert a == kb.item("black_king_bar")
    assert (a.name, a.cost, a.is_recipe, a.neutral_tier) == ("Black King Bar", 4050, False, None)
    assert a.components == ("mithril_hammer", "ogre_axe")
    assert a.active == ("Avatar: Grants immunity.",) and a.passive == ("Strength: Bonus.",)
    assert kb.item("recipe_black_king_bar").is_recipe
    assert kb.item("arcane_ring").neutral_tier == 1
    assert kb.item_by_id(1).key == "blink"
    with pytest.raises(KeyError):
        kb.item("item_nope")


def test_item_components_recursive(kb):
    assert sorted(kb.item_components("item_sange_and_yasha")) == sorted(
        ["ogre_axe", "belt_of_strength", "blade_of_alacrity", "boots_of_elegance"])
    assert kb.item_components("blink") == []


def test_popular_items(kb):
    start = kb.popular_items("nevermore", "start")
    assert [p.key for p in start] == ["belt_of_strength", "ogre_axe"]
    assert start[0] == ("belt_of_strength", "Belt of Strength", 450, 9)
    early = kb.popular_items(2, "early")
    assert [p.key for p in early] == ["black_king_bar", "blink"]
    assert kb.popular_items("nevermore", "early", top=1)[0].count == 10
    assert kb.popular_items("nevermore", "mid") == []
    with pytest.raises(ValueError):
        kb.popular_items("nevermore", "night")


def test_matchups(kb):
    m = kb.matchups("antimage")
    assert m[0].hero == "nevermore" and m[0].games == 200 and m[0].winrate == pytest.approx(0.6)
    assert {x.hero for x in m} == {"nevermore", "pudge", "slark"}


def test_best_counters_ranking(kb):
    res = kb.best_counters(["antimage"], top=5, min_games=50)
    assert [r.hero for r in res] == ["slark", "nevermore", "pudge"]
    assert res[0].score == pytest.approx(0.1) and res[1].score == pytest.approx(-0.1)
    assert [r.hero for r in kb.best_counters(["antimage"], top=1)] == ["slark"]


def test_best_counters_multi_enemy_and_pool(kb):
    res = kb.best_counters(["antimage", "pudge"], min_games=50)
    assert [r.hero for r in res] == ["slark", "nevermore"]
    assert res[0].score == pytest.approx((0.6 - 0.5) + (0.3 - 0.5))
    assert res[1].score == pytest.approx((0.4 - 0.5) + (0.45 - 0.5))
    assert res[1].winrate == pytest.approx((80 + 45) / 300)
    res = kb.best_counters(["antimage"], pool=["nevermore", "antimage"])
    assert [r.hero for r in res] == ["nevermore"]
    assert kb.best_counters(["antimage"], top=0) == []


def test_best_counters_min_games_filters_sparse(kb):
    res = kb.best_counters(["slark"], min_games=50)
    assert "nevermore" not in [r.hero for r in res]
    assert "nevermore" in [r.hero for r in kb.best_counters(["slark"], min_games=5)]


def plan(kb, owned, gold, cand):
    return kb.next_items_affordable(owned, gold, cand)


def test_affordable_with_owned_components(kb):
    bkb, blink = plan(kb, ["item_ogre_axe", "item_mithril_hammer"], 1500, ["item_black_king_bar", "item_blink"])
    assert bkb.cost_left == 1450 and bkb.parts == (("recipe_black_king_bar", 1450),)
    assert bkb.affordable and bkb.gold_short == 0 and bkb.next_part == ("recipe_black_king_bar", 1450)
    assert not bkb.owned
    assert blink.cost_left == 2250 and not blink.affordable and blink.gold_short == 750
    assert blink.next_part is None


def test_nothing_owned_full_price(kb):
    (p,) = plan(kb, [], 10000, ["black_king_bar"])
    assert p.cost_left == p.cost_total == 4050
    assert sorted(k for k, _ in p.parts) == ["mithril_hammer", "ogre_axe", "recipe_black_king_bar"]
    assert p.affordable


def test_partial_gold_next_part(kb):
    (p,) = plan(kb, [], 1100, ["black_king_bar"])
    assert not p.affordable and p.gold_short == 4050 - 1100
    assert p.next_part == ("ogre_axe", 1000)


def test_already_owned_candidate(kb):
    (p,) = plan(kb, ["item_blink", "item_ogre_axe"], 0, ["item_blink"])
    assert p.owned and p.cost_left == 0 and p.affordable and p.parts == () and p.next_part is None


def test_nested_recipe_owned_intermediate(kb):
    (p,) = plan(kb, ["item_sange", "item_blade_of_alacrity"], 1000, ["item_sange_and_yasha"])
    # owned: sange (1900) + blade (1000); left: recipe_sya 400 + recipe_yasha 450 + boots 450
    assert p.cost_left == 4200 - 1900 - 1000 == 1300
    assert dict(p.parts) == {"recipe_sange_and_yasha": 400, "recipe_yasha": 450, "boots_of_elegance": 450}
    assert not p.affordable and p.gold_short == 300
    (q,) = plan(kb, ["item_sange", "item_blade_of_alacrity"], 1300, ["sange_and_yasha"])
    assert q.affordable


def test_owned_component_not_double_counted(kb):
    p2 = plan(kb, ["item_ogre_axe"], 5000, ["sange", "black_king_bar"])
    assert [x.cost_left for x in p2] == [900, 3050]


def test_unknown_owned_ignored_unknown_candidate_raises(kb):
    (p,) = plan(kb, ["item_empty", "item_tango"], 100, ["blink"])
    assert p.cost_left == 2250
    with pytest.raises(KeyError):
        plan(kb, [], 100, ["item_nope"])


def test_duplicate_owned_items(kb):
    (p,) = plan(kb, ["ogre_axe", "ogre_axe", "belt_of_strength"], 0, ["sange"])
    assert p.cost_left == 450 and p.parts == (("recipe_sange", 450),)


def test_missing_cache_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="update_data"):
        Knowledge(tmp_path).hero("nevermore")


@pytest.mark.skipif(not (CACHE_DIR / "dotaconstants" / "heroes.json").exists(), reason="real cache absent")
def test_real_cache_sanity():
    real = Knowledge()
    assert real.item("item_black_king_bar").cost > 0
    assert len(real.hero("nevermore").abilities) >= 4
    assert len(real.heroes()) >= 120
    assert real.item_components("black_king_bar") == ["mithril_hammer", "ogre_axe"]
    if (CACHE_DIR / "opendota" / "hero_11_item_popularity.json").exists():
        assert real.popular_items("nevermore", "late")
        assert real.matchups("nevermore")


def test_ability_description_and_bkb_flag_and_ultimate(kb, tmp_path):
    raw = json.loads((tmp_path / "dotaconstants" / "abilities.json").read_text())
    raw["nevermore_requiem"].update({"desc": "Releases souls. " + "x" * 300, "bkbpierce": "No"})
    (tmp_path / "dotaconstants" / "abilities.json").write_text(json.dumps(raw))
    fresh = Knowledge(tmp_path)
    req = next(a for a in fresh.hero("nevermore").abilities if a.key == "nevermore_requiem")
    assert req.desc == "Releases souls." and req.bkb_pierce == "No"
    assert fresh.hero("nevermore").ultimate.key == "nevermore_requiem"
    assert fresh.hero("antimage").ultimate is None


def test_used_as_component_and_blank_components_ignored(kb):
    assert kb.used_as_component("ogre_axe") and kb.used_as_component("item_blade_of_alacrity")
    assert not kb.used_as_component("blink") and not kb.used_as_component("sange_and_yasha")
    kb._items_raw["pipe_like"] = _item(300, "Pipe Like", 3000, ["ogre_axe", "belt_of_strength", ""])
    assert kb.item("pipe_like").components == ("ogre_axe", "belt_of_strength")
    (p,) = plan(kb, [], 0, ["pipe_like"])
    assert p.cost_left == 3000
