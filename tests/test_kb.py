import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_kb import UNKNOWN, fill, render, strip_html  # noqa: E402
from dota_coach.kb import KB, derive_stats, load_formulas  # noqa: E402

OFFICIAL = ROOT / "data" / "cache" / "official" / "english"
DOTACONSTANTS = ROOT / "data" / "cache" / "dotaconstants"
needs_cache = pytest.mark.skipif(not OFFICIAL.exists(), reason="official datafeed cache not downloaded")

PLACEHOLDER = re.compile(r"%\w+%|%%|\{[a-zA-Z]:|<\s*/?\s*(?:br|h1|font|span|b|i)\b", re.I)


@pytest.fixture(scope="module")
def kb():
    return KB()


def raw_hero(name: str) -> dict:
    for path in (OFFICIAL / "heroes").glob("*.json"):
        hero = json.loads(path.read_text(encoding="utf-8"))["result"]["data"]["heroes"][0]
        if hero["name"] == f"npc_dota_hero_{name}":
            return hero
    raise KeyError(name)


def raw_ability(hero: str, key: str) -> dict:
    return next(a for a in raw_hero(hero)["abilities"] if a["name"] == key)


def raw_item(key: str) -> dict:
    for path in (OFFICIAL / "items").glob("*.json"):
        item = json.loads(path.read_text(encoding="utf-8"))["result"]["data"]["items"][0]
        if item["name"] == f"item_{key}":
            return item
    raise KeyError(key)


def raw_special(ability: dict, name: str) -> list:
    return next(sv["values_float"] for sv in ability["special_values"] if sv["name"] == name)


def hero_texts(h: dict):
    for a in h["abilities"]:
        yield a["key"], a["desc_ru"]
        yield a["key"], a["desc_en"]
        for n in a["notes_ru"] + a["notes_en"]:
            yield a["key"], n
        for blk in (a["shard"], a["scepter"]):
            if blk:
                yield a["key"], blk["text_ru"] or ""
                yield a["key"], blk["text_en"] or ""
    for tier in h["talents"]:
        for o in tier["options"]:
            yield o["key"], o["text_ru"]
            yield o["key"], o["text_en"]


def item_texts(it: dict):
    yield it["key"], it["desc_ru"]
    yield it["key"], it["desc_en"]
    for n in it["notes_ru"] + it["notes_en"]:
        yield it["key"], n
    for sec in it["sections_ru"] + it["sections_en"]:
        yield it["key"], sec["text"]
    for b in it["bonuses"]:
        yield it["key"], b["text_ru"]
    for field in ("shard_text_ru", "scepter_text_ru"):
        if it[field]:
            yield it["key"], it[field]


def test_index_counts_and_id_maps(kb):
    idx = kb.index
    assert len(kb.heroes()) == 127 == idx["counts"]["heroes"]
    assert idx["counts"]["items"] == len(kb.items()) > 500
    assert idx["patch"] == "7.41f"
    assert idx["hero_id_to_key"]["14"] == "pudge" and idx["item_id_to_key"]["116"] == "black_king_bar"
    assert all(kb.hero(k)["key"] == k for k in kb.heroes())


def test_no_placeholders_left_in_rendered_texts(kb):
    leftovers, unknown_in = [], set()
    pairs = [(w, t) for k in kb.heroes() for w, t in hero_texts(kb.hero(k))]
    pairs += [(w, t) for k in kb.items() for w, t in item_texts(kb.item(k))]
    for where, text in pairs:
        if PLACEHOLDER.search(text):
            leftovers.append((where, PLACEHOLDER.search(text).group(0)))
        if UNKNOWN in text:
            unknown_in.add(where)
    assert leftovers == []
    listed = json.loads((ROOT / "data" / "kb" / "unresolved_placeholders.json").read_text(encoding="utf-8"))
    assert unknown_in == {row["where"].split(":")[0] for row in listed}
    assert len(listed) <= 40


def test_renderer_cases():
    ctx = {"a": "85/150/215/280", "b": "13", "dur": "3"}
    assert render("Deals %a% damage for %dur%s", ctx, "t") == "Deals 85/150/215/280 damage for 3s"
    assert render("reduces by %b%%% (stacking)", ctx, "t") == "reduces by 13% (stacking)"
    assert render("+{s:b}% Speed", ctx, "t") == "+13% Speed"
    assert render("<h1>Active: X</h1>%a%<br><br>Y", ctx, "t") == "[Active: X] 85/150/215/280\nY"
    assert render("%missing% here", ctx, "t") == f"{UNKNOWN} here"
    assert strip_html("a&nbsp;b <font color='#fff'>c</font>") == "a b c"
    assert fill("%b%%", ctx, "t") == "13%"


def test_shadowraze_damage_matches_official(kb):
    ability = kb.ability("nevermore_shadowraze1")
    special = next(s for s in ability["specials"] if s["key"] == "shadowraze_damage")
    assert special["values"] == [85, 150, 215, 280]
    assert "85/150/215/280" in kb.hero_text("nevermore")
    if OFFICIAL.exists():
        raw = raw_special(raw_ability("nevermore", "nevermore_shadowraze1"), "shadowraze_damage")
        assert special["values"] == raw


@needs_cache
def test_bkb_matches_official(kb):
    bkb = kb.item("black_king_bar")
    raw = raw_item("black_king_bar")
    recipe = raw_item("recipe_black_king_bar")
    assert bkb["cost"] == raw["item_cost"] == 4050
    assert sorted(bkb["components"]) == ["mithril_hammer", "ogre_axe"]
    assert bkb["recipe_cost"] == recipe["item_cost"]
    assert bkb["cost"] == sum(kb.item(c)["cost"] for c in bkb["components"]) + bkb["recipe_cost"]
    text = kb.item_text("black_king_bar")
    assert "Ogre Axe" in text and "Mithril Hammer" in text and "рецепт (1450)" in text
    assert bkb["cooldown"] == raw["cooldowns"]
    assert "black_king_bar" in kb.builds_into("mithril_hammer") and "black_king_bar" in kb.builds_into("ogre_axe")


@needs_cache
def test_blink_cooldown_matches_official(kb):
    blink = kb.item("blink")
    assert blink["cooldown"] == raw_item("blink")["cooldowns"]
    assert blink["cost"] == raw_item("blink")["item_cost"]
    assert {"arcane_blink", "swift_blink", "overwhelming_blink"} <= set(blink["builds_into"])


@needs_cache
@pytest.mark.parametrize("hero,key,pierce", [
    ("pudge", "pudge_dismember", True),
    ("zuus", "zuus_thundergods_wrath", False),
    ("puck", "puck_dream_coil", False),
])
def test_bkb_pierce_matches_official_immunity(kb, hero, key, pierce):
    code = raw_ability(hero, key)["immunity"]
    ability = kb.ability(key)
    assert ability["immunity_code"] == code
    assert ability["bkb_pierce"] is pierce
    assert ability["bkb_pierce"] is (code in (1, 3))


@pytest.mark.skipif(not (DOTACONSTANTS / "abilities.json").exists(), reason="dotaconstants cache missing")
def test_decoded_flags_agree_with_dotaconstants(kb):
    dc = json.loads((DOTACONSTANTS / "abilities.json").read_text(encoding="utf-8"))
    dispel = {"Yes": "basic", "No": "no", "Strong Dispels Only": "strong"}
    damage = {"Physical": "physical", "Magical": "magical", "Pure": "pure"}
    checked = 0
    for hero in kb.heroes():
        for a in kb.hero(hero)["abilities"]:
            ref = dc.get(a["key"])
            if not ref:
                continue
            if ref.get("bkbpierce") in ("Yes", "No") and a["immunity_code"] in (1, 2, 3, 4):
                assert a["bkb_pierce"] is (ref["bkbpierce"] == "Yes"), a["key"]
                checked += 1
            if ref.get("dispellable") in dispel:
                assert a["dispellable"] == dispel[ref["dispellable"]], a["key"]
            if isinstance(ref.get("dmg_type"), str) and ref["dmg_type"] in damage:
                assert a["damage_type"] == damage[ref["dmg_type"]], a["key"]
    assert checked > 400


def test_aliases_resolve(kb):
    assert kb.item("бкб")["key"] == "black_king_bar"
    assert kb.item("блинк")["key"] == "blink"
    assert kb.hero("фантомка")["key"] == "phantom_assassin"
    assert kb.hero("сф")["key"] == "nevermore"
    assert kb.search("бкб")[0]["key"] == "black_king_bar"
    assert kb.search("сф")[0]["key"] == "nevermore"
    assert kb.search("Shadow Fiend")[0]["key"] == "nevermore"
    assert kb.search("item_blink")[0]["key"] == "blink"
    assert kb.search("") == []


def test_aliases_file_is_consistent(kb):
    total = sum(len(v) for t in kb.aliases.values() for v in t.values())
    assert total >= 60
    assert set(kb.aliases["heroes"]) <= set(kb.heroes())
    assert set(kb.aliases["items"]) <= set(kb.items())
    from dota_coach.kb import norm
    for table in kb.aliases.values():
        seen: dict[str, str] = {}
        for key, names in table.items():
            for name in names:
                assert seen.setdefault(norm(name), key) == key, f"alias {name!r} maps to {seen[norm(name)]} and {key}"


def test_lookup_variants(kb):
    assert kb.hero(14)["key"] == kb.hero("npc_dota_hero_pudge")["key"] == kb.hero("Pudge")["key"] == "pudge"
    assert kb.item("item_black_king_bar")["id"] == kb.item(116)["id"] == 116
    assert kb.ability("zuus_thundergods_wrath")["hero"] == "zuus"
    assert kb.ability("black_king_bar")["key"] == "black_king_bar"
    with pytest.raises(KeyError):
        kb.hero("no_such_hero")
    with pytest.raises(KeyError):
        kb.item("no_such_item")
    with pytest.raises(KeyError):
        kb.ability("no_such_ability")


def test_cards_are_compact_and_complete(kb):
    hero = kb.hero_text("nevermore")
    assert "Ур.1" in hero and "Ур.25" in hero and "Таланты:" in hero and "[врождённая]" in hero
    assert "Ур.10" in kb.hero_text("nevermore", level=10) and "Ур.25" not in kb.hero_text("nevermore", level=10)
    assert len(kb.hero_text("nevermore", full=False)) < len(hero)
    item = kb.item_text("black_king_bar")
    assert "4050" in item and "Бонусы" in item and "КД 95" in item
    assert not PLACEHOLDER.search(hero + item)


def test_level_formulas_against_official_level_one(kb):
    formulas = load_formulas()
    for key in kb.heroes():
        h = kb.hero(key)
        b = h["base"]
        l1 = derive_stats(b, h["primary_attr"], 1, formulas)
        assert l1["health"] == pytest.approx(b["health"], abs=0.1)
        assert l1["mana"] == pytest.approx(b["mana"], abs=0.1)
        assert l1["armor"] == pytest.approx(b["armor"], abs=0.01)
    sf = kb.hero("nevermore")
    l25 = sf["level25"]
    assert l25["str"] == pytest.approx(sf["base"]["str"] + 24 * sf["base"]["str_gain"], abs=0.01)
    assert l25["health"] - sf["level1"]["health"] == pytest.approx(22 * (l25["str"] - sf["base"]["str"]), abs=0.2)
    assert sf["level25"]["attack_speed"] == pytest.approx(100 + l25["agi"], abs=0.1)
    assert all(formulas[k]["verify"] in (True, False) and formulas[k]["source"]
               for k in formulas if isinstance(formulas[k], dict))


@needs_cache
def test_hero_base_matches_raw_for_every_hero(kb):
    for path in (OFFICIAL / "heroes").glob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))["result"]["data"]["heroes"][0]
        h = kb.hero(raw["id"])
        assert h["base"]["health"] == raw["max_health"] and h["base"]["move_speed"] == raw["movement_speed"]
        assert h["primary_attr_code"] == raw["primary_attr"]
        assert len(h["talents"]) == 4 and all(len(t["options"]) == 2 for t in h["talents"])


def test_every_item_recipe_tree_is_finite_and_reverse_index_is_consistent(kb):
    for key in kb.items():
        it = kb.item(key)
        for parent in it["builds_into"]:
            p = kb.item(parent)
            assert key in {c for v in [p["components"]] + p["component_variants"] for c in v}
        assert it["key"] not in it["builds_into"]
    tree = kb.item("heart")["recipe_tree"]
    assert [c["key"] for c in tree["components"]] == kb.item("heart")["components"]
