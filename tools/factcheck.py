"""Fact-check of the model about Dota 2 7.41f: question bank from the official KB, graded runs with and without cards."""

import argparse
import asyncio
import json
import math
import random
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach.config import ROOT  # noqa: E402
from dota_coach.kb import KB, KB_DIR, load_formulas, norm  # noqa: E402

FACT_DIR = KB_DIR / "factcheck"
QUESTIONS_PATH = FACT_DIR / "questions.json"
SEED = 741
SEED_B = 2026
QUESTIONS_B_PATH = FACT_DIR / "questions_b.json"
EXCL: dict[str, set[str]] = {"items": set(), "heroes": set(), "abilities": set()}
BANK_B = {"removed": ["aegis", "roshans_banner", "famango"], "pierce_extra": ["devastator", "revenants_brooch"]}
BATCH_SIZE = 10
CONTEXT_TOKEN_LIMIT = 20000
CYR_CHARS_PER_TOKEN = 2.3
LAT_CHARS_PER_TOKEN = 3.5
CYR_RE = re.compile(r"[а-яА-ЯёЁ]")
CATEGORIES = ["items", "abilities", "heroes", "talents", "mechanics"]
TARGET = {"items": 45, "abilities": 45, "heroes": 20, "talents": 10}
SYSTEM_BARE = "Ты эксперт по Dota 2, патч 7.41f. Отвечай кратко."
SYSTEM_CARDS = SYSTEM_BARE + " Данные из справочника в сообщении точны для патча 7.41f и важнее твоей памяти."
MECH_FILES = {"A": KB_DIR / "mechanics_a.md", "B": KB_DIR / "mechanics_b.md"}
ATTR_OPTIONS = [("str", "сила"), ("agi", "ловкость"), ("int", "интеллект"), ("all", "универсал")]
STAT_LABELS = {"str": "Strength", "agi": "Agility", "int": "Intelligence", "damage": "Damage", "armor": "Armor",
               "health": "Health", "mana": "Mana", "all": "All Attributes", "move_speed": "Movement Speed",
               "attack": "Attack Speed", "hp_regen": "Health Regen", "mana_regen": "Mana Regen"}
YES = {"да", "yes", "true", "верно", "истина", "ага", "y", "1", "+"}
NO = {"нет", "no", "false", "неверно", "ложь", "n", "0", "-"}
LETTERS = "ABCDEFGH"
UNVERIFIED = "не проверено"


def hero_name(kb: KB, key: str) -> str:
    return kb.hero(key)["name_en"]


def item_name(kb: KB, key: str) -> str:
    return kb.item(key)["name_en"]


def strip_colon(text: str) -> str:
    return text.strip().rstrip(":").strip()


def weights(kb_dir: Path = KB_DIR) -> tuple[dict[str, float], dict[str, float]]:
    heroes: dict[str, float] = {}
    items: dict[str, float] = {}
    for path in sorted((kb_dir / "builds_stratz").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        bracket = data["brackets"].get("mid") or next(iter(data["brackets"].values()), {"positions": {}})
        total = 0
        for pos in bracket["positions"].values():
            total += pos["matches"]
            for row in pos.get("core", []) + pos.get("boots", []):
                items[row["item"]] = items.get(row["item"], 0) + row["matches"]
        heroes[data["hero"]] = total
    return heroes, items


def wsample(rng: random.Random, keys, weight: dict[str, float], k: int) -> list[str]:
    scored = []
    for key in sorted(keys):
        w = math.sqrt(weight.get(key, 0)) + 1.0
        scored.append((math.log(max(rng.random(), 1e-12)) / w, key))
    scored.sort(reverse=True)
    return [key for _, key in scored[:k]]


def option_list(options: list[tuple[str, str]]) -> str:
    return "; ".join(f"{k} — {t}" for k, t in options)


def mk(qid, category, subtype, question, answer, answer_type, source, tolerance=0, **extra) -> dict:
    row = {"id": qid, "category": category, "subtype": subtype, "question": question, "answer": answer,
           "answer_type": answer_type, "tolerance": tolerance, "source": source}
    row.update({k: v for k, v in extra.items() if v is not None})
    return row


def shop_items(kb: KB) -> list[str]:
    out = []
    for key, row in kb.index["items"].items():
        if row["status"] != "shop" or row["recipe"] or row["cost"] <= 0 or not row["en"]:
            continue
        out.append(key)
    return out


def own_abilities(hero: dict) -> list[dict]:
    return [a for a in hero["abilities"] if not a["innate"] and not a["granted_by_scepter"] and not a["granted_by_shard"]]


DEALS_RE = re.compile(r"\b(deal|deals|dealing|damages)\b", re.I)


def deals_damage(ability: dict) -> bool:
    return "passive" not in ability["behavior"] and bool(DEALS_RE.search(ability["desc_en"] or ""))


def level_value(values: list, level: int):
    return values[min(level, len(values)) - 1]


def active_sections(item: dict) -> list[dict]:
    return [s for s in item["sections_ru"] if s["kind"] == "active"]


def duration_specials(item: dict) -> list[dict]:
    return [s for s in item["specials"] if not s["system"] and "duration" in s["key"]]


def derive(kb: KB, ref: dict):
    """Re-compute the gold answer of a KB-derived question from the current KB."""
    kind = ref["kind"]
    if kind == "item_cost":
        return kb.item(ref["item"])["cost"]
    if kind == "item_components":
        return sorted(set(kb.item(ref["item"])["components"]))
    if kind == "item_cooldown":
        return kb.item(ref["item"])["cooldown"][0]
    if kind == "item_bonus":
        return kb.item(ref["item"])["bonuses"][ref["index"]]["values"][0]
    if kind == "item_duration":
        sv = next(s for s in kb.item(ref["item"])["specials"] if s["key"] == ref["special"])
        return sv["values"][0]
    if kind == "item_in_shop":
        return kb.item(ref["item"])["shop"]["status"] == "shop"
    if kind == "item_pierce":
        return kb.item(ref["item"])["bkb_pierce"]
    if kind == "ability_pierce":
        return kb.ability(ref["ability"])["bkb_pierce"]
    if kind == "ability_damage_type":
        return kb.ability(ref["ability"])["damage_type"]
    if kind == "ability_dispel":
        return kb.ability(ref["ability"])["dispellable"] == "basic"
    if kind == "ability_cooldown":
        return level_value(kb.ability(ref["ability"])["cooldown"], ref["level"])
    if kind == "ability_mana":
        return level_value(kb.ability(ref["ability"])["mana_cost"], ref["level"])
    if kind == "ability_special":
        sv = next(s for s in kb.ability(ref["ability"])["specials"] if s["key"] == ref["special"])
        return level_value(sv["values"], ref["level"])
    if kind == "ability_ultimate":
        hero = kb.hero(ref["hero"])
        return [a["key"] for a in own_abilities(hero) if a["kind"] == "ultimate"]
    if kind == "hero_innate":
        return next(a["name_en"] for a in kb.hero(ref["hero"])["abilities"] if a["innate"])
    if kind == "hero_attr":
        return kb.hero(ref["hero"])["primary_attr"]
    if kind == "hero_attack_type":
        return kb.hero(ref["hero"])["attack_type"]
    if kind == "hero_bat":
        return kb.hero(ref["hero"])["base"]["bat"]
    if kind == "hero_armor":
        return kb.hero(ref["hero"])["level1"]["armor"]
    if kind == "hero_move_speed":
        return kb.hero(ref["hero"])["base"]["move_speed"]
    if kind == "talent_level":
        for tier in kb.hero(ref["hero"])["talents"]:
            if any(o["key"] == ref["talent"] for o in tier["options"]):
                return tier["level"]
        raise KeyError(ref["talent"])
    if kind == "talent_present":
        tier = next(t for t in kb.hero(ref["hero"])["talents"] if t["level"] == ref["level"])
        return any(o["key"] == ref["talent"] for o in tier["options"])
    if kind == "item_special":
        sv = next(s for s in kb.item(ref["item"])["specials"] if s["key"] == ref["special"])
        return abs(sv["values"][ref.get("index", 0)])
    if kind == "item_special_count":
        sv = next(s for s in kb.item(ref["item"])["specials"] if s["key"] == ref["special"])
        return len(sv["values"])
    if kind == "formula":
        return load_formulas()[ref["name"]]["value"]
    if kind == "armor_formula":
        k = load_formulas()["armor_reduction_per_point"]["value"]
        return round(100 * k * ref["armor"] / (1 + k * abs(ref["armor"])), 1)
    if kind == "all_heroes_magic_resist":
        return {kb.hero(h)["base"]["magic_resist"] for h in kb.heroes()}
    raise KeyError(kind)


def gen_items(kb: KB, rng_seed: int, item_w: dict[str, float]) -> list[dict]:
    pool = [k for k in shop_items(kb) if k not in EXCL["items"]]
    used: set[str] = set()
    out: list[dict] = []

    def pick(subtype: str, k: int, ok) -> list[str]:
        rng = random.Random(f"{rng_seed}:items:{subtype}")
        cands = [key for key in pool if key not in used and ok(kb.item(key))]
        chosen = wsample(rng, cands, item_w, k)
        used.update(chosen)
        return chosen

    for key in pick("cost", 7, lambda it: it["cost"] >= 1000 and not it["neutral_tier"]):
        ref = {"kind": "item_cost", "item": key}
        out.append(mk(f"item_cost.{key}", "items", "item_cost",
                      f"Сколько золота стоит предмет {item_name(kb, key)} в патче 7.41f (полная цена, с рецептом)?",
                      derive(kb, ref), "number", "datafeed items", 0, ref=ref, items=[key]))

    def comps_ok(it):
        c = it["components"]
        return (2 <= len(c) <= 4 and len(set(c)) == len(c) and it["cost_consistent"] and not it["component_variants"]
                and not any(x.startswith("recipe_") for x in c))

    for key in pick("components", 7, comps_ok):
        ref = {"kind": "item_components", "item": key}
        out.append(mk(f"item_components.{key}", "items", "item_components",
                      f"Из каких предметов собирается {item_name(kb, key)} в патче 7.41f? "
                      "Назови готовые предметы-компоненты без свитка рецепта.",
                      derive(kb, ref), "items_set", "datafeed items", 0, ref=ref, items=[key]))

    def cd_ok(it):
        return len(it["cooldown"]) == 1 and it["cooldown"][0] > 0 and len(active_sections(it)) == 1

    for key in pick("cooldown", 7, cd_ok):
        ref = {"kind": "item_cooldown", "item": key}
        out.append(mk(f"item_cooldown.{key}", "items", "item_cooldown",
                      f"Какова перезарядка активной способности предмета {item_name(kb, key)} в секундах?",
                      derive(kb, ref), "number", "datafeed items", 0.05, ref=ref, items=[key]))

    def bonus_pairs(it):
        stats = [b["stat"] for b in it["bonuses"]]
        return [(i, b) for i, b in enumerate(it["bonuses"])
                if b["stat"] in STAT_LABELS and stats.count(b["stat"]) == 1 and len(b["values"]) == 1
                and not b["percent"]]

    for key in pick("bonus", 7, lambda it: bool(bonus_pairs(it)) and not it["neutral_tier"]):
        rng = random.Random(f"{rng_seed}:items:bonus_pick:{key}")
        index, b = rng.choice(bonus_pairs(kb.item(key)))
        ref = {"kind": "item_bonus", "item": key, "index": index}
        out.append(mk(f"item_bonus.{key}", "items", "item_bonus",
                      f"Сколько даёт предмет {item_name(kb, key)} по бонусу «{STAT_LABELS[b['stat']]}»? "
                      "Нужно число (плоский бонус предмета, без сборных вариантов).",
                      derive(kb, ref), "number", "datafeed items", 0.01, ref=ref, items=[key]))

    def dur_ok(it):
        d = duration_specials(it)
        return len(active_sections(it)) == 1 and len(d) == 1 and len(d[0]["values"]) == 1 and d[0]["values"][0] > 0

    for key in pick("duration", 5, dur_ok):
        sv = duration_specials(kb.item(key))[0]
        ref = {"kind": "item_duration", "item": key, "special": sv["key"]}
        out.append(mk(f"item_duration.{key}", "items", "item_duration",
                      f"Сколько секунд длится основной эффект активной способности предмета "
                      f"{item_name(kb, key)} (параметр «{sv['key']}» в данных)?",
                      derive(kb, ref), "number", "datafeed items", 0.05, ref=ref, items=[key]))

    removed = BANK_B["removed"] if EXCL["items"] else ["eternal_shroud", "cornucopia", "hood_of_defiance"]
    rng = random.Random(f"{rng_seed}:items:shop")
    present = [k for k in wsample(rng, [x for x in pool if x not in used], item_w, 4)]
    used.update(present)
    shop_keys = removed + present
    rng.shuffle(shop_keys)
    for key in shop_keys:
        ref = {"kind": "item_in_shop", "item": key}
        out.append(mk(f"item_in_shop.{key}", "items", "item_in_shop",
                      f"Можно ли в патче 7.41f купить {item_name(kb, key)} в магазине? (да/нет)",
                      derive(kb, ref), "yes_no", "datafeed items shop.status", 0, ref=ref, items=[key]))

    pierce_pool = ["assault", "desolator", "blight_stone", "basher", "wraith_pact", "pavise", "meteor_hammer",
                   "solar_crest"]
    if EXCL["items"]:
        pierce_pool = [k for k in pierce_pool + BANK_B["pierce_extra"] if k not in EXCL["items"]]
    rng = random.Random(f"{rng_seed}:items:pierce")
    for key in sorted(rng.sample(pierce_pool, 5)):
        ref = {"kind": "item_pierce", "item": key}
        out.append(mk(f"item_pierce.{key}", "items", "item_pierce",
                      f"Пробивает ли иммунитет к дебаффам (BKB) основной эффект предмета {item_name(kb, key)} "
                      "в патче 7.41f? (да/нет)",
                      derive(kb, ref), "yes_no", "datafeed items bkb_pierce", 0, ref=ref, items=[key]))
    return out


def gen_abilities(kb: KB, rng_seed: int, hero_w: dict[str, float]) -> list[dict]:
    heroes = [h for h in sorted(kb.heroes()) if h not in EXCL["heroes"]]
    used_ab: set[str] = set(EXCL["abilities"])
    used_hero: dict[str, int] = {}
    out: list[dict] = []

    def ability_pool(ok) -> list[tuple[str, str]]:
        return [(h, a["key"]) for h in heroes for a in own_abilities(kb.hero(h)) if a["key"] not in used_ab and ok(a)]

    def pick(subtype: str, k: int, ok) -> list[tuple[str, str]]:
        rng = random.Random(f"{rng_seed}:abilities:{subtype}")
        pool = ability_pool(ok)
        by_hero: dict[str, list[str]] = {}
        for h, a in pool:
            by_hero.setdefault(h, []).append(a)
        cands = [h for h in by_hero if used_hero.get(h, 0) < 2]
        chosen = []
        for h in wsample(rng, cands, hero_w, k):
            a = rng.choice(sorted(by_hero[h]))
            chosen.append((h, a))
            used_ab.add(a)
            used_hero[h] = used_hero.get(h, 0) + 1
        return chosen

    def an(key: str) -> str:
        return kb.ability(key)["name_en"]

    def active_enemy(a):
        return "passive" not in a["behavior"] and "enemy" in a["target_team"]

    for sign, k in ((True, 4), (False, 4)):
        for h, a in pick(f"pierce_{sign}", k, lambda a, s=sign: active_enemy(a) and a["bkb_pierce"] is s):
            ref = {"kind": "ability_pierce", "ability": a}
            out.append(mk(f"ability_pierce.{a}", "abilities", "ability_pierce",
                          f"Пробивает ли способность {an(a)} героя {hero_name(kb, h)} иммунитет к дебаффам (BKB) "
                          "в патче 7.41f? (да/нет)",
                          derive(kb, ref), "yes_no", "datafeed abilities bkb_pierce", 0, ref=ref, hero=h))

    dmg_options = [("physical", "физический"), ("magical", "магический"), ("pure", "чистый")]
    for dtype, k in (("physical", 2), ("pure", 2), ("magical", 1)):
        for h, a in pick(f"dmg_{dtype}", k, lambda a, d=dtype: a["damage_type"] == d and deals_damage(a)):
            ref = {"kind": "ability_damage_type", "ability": a}
            out.append(mk(f"ability_damage_type.{a}", "abilities", "ability_damage_type",
                          f"Какой тип урона наносит способность {an(a)} героя {hero_name(kb, h)}? "
                          f"Варианты: {option_list(dmg_options)}.",
                          derive(kb, ref), "choice", "datafeed abilities damage_type", 0,
                          options=[{"key": k_, "text": t} for k_, t in dmg_options], ref=ref, hero=h))

    for dval, k in (("basic", 3), ("no", 2), ("strong", 2)):
        for h, a in pick(f"dispel_{dval}", k, lambda a, d=dval: a["dispellable"] == d and active_enemy(a)):
            ref = {"kind": "ability_dispel", "ability": a}
            out.append(mk(f"ability_dispel.{a}", "abilities", "ability_dispel",
                          f"Можно ли снять эффект способности {an(a)} героя {hero_name(kb, h)} с цели обычным "
                          "(базовым) диспелом? (да/нет)",
                          derive(kb, ref), "yes_no", "datafeed abilities dispellable", 0, ref=ref, hero=h))

    def multi(values):
        return len(values) >= 2 and len(set(values)) >= 2

    rng = random.Random(f"{rng_seed}:abilities:levels")
    for h, a in pick("cooldown", 6, lambda a: multi(a["cooldown"])):
        level = rng.randint(1, len(kb.ability(a)["cooldown"]))
        ref = {"kind": "ability_cooldown", "ability": a, "level": level}
        out.append(mk(f"ability_cooldown.{a}", "abilities", "ability_cooldown",
                      f"Какова перезарядка способности {an(a)} героя {hero_name(kb, h)} на {level}-м уровне "
                      "прокачки в секундах (без талантов, Аганима и шарда)?",
                      derive(kb, ref), "number", "datafeed abilities cooldown", 0.05, ref=ref, hero=h))
    for h, a in pick("mana", 3, lambda a: multi(a["mana_cost"])):
        level = rng.randint(1, len(kb.ability(a)["mana_cost"]))
        ref = {"kind": "ability_mana", "ability": a, "level": level}
        out.append(mk(f"ability_mana.{a}", "abilities", "ability_mana",
                      f"Сколько маны стоит способность {an(a)} героя {hero_name(kb, h)} на {level}-м уровне "
                      "прокачки (без талантов и модификаторов)?",
                      derive(kb, ref), "number", "datafeed abilities mana_cost", 0.05, ref=ref, hero=h))

    def special_rows(a):
        heads = [strip_colon(s["heading_en"]) for s in a["specials"] if not s["system"] and s["heading_en"]]
        return [s for s in a["specials"] if not s["system"] and s["heading_en"] and "$" not in s["heading_en"]
                and multi(s["values"]) and heads.count(strip_colon(s["heading_en"])) == 1
                and not s.get("talents") and "values_scepter" not in s and "values_shard" not in s]

    for h, a in pick("special", 5, lambda a: bool(special_rows(a))):
        sv = rng.choice(special_rows(kb.ability(a)))
        level = rng.randint(1, len(sv["values"]))
        ref = {"kind": "ability_special", "ability": a, "special": sv["key"], "level": level}
        unit = " (в процентах, число без знака)" if sv["percent"] else ""
        out.append(mk(f"ability_special.{a}", "abilities", "ability_special",
                      f"Способность {an(a)} героя {hero_name(kb, h)}: чему равно значение «{strip_colon(sv['heading_en'])}» "
                      f"на {level}-м уровне прокачки{unit}?",
                      derive(kb, ref), "number", "datafeed abilities specials", 0.02, ref=ref, hero=h))

    rng = random.Random(f"{rng_seed}:abilities:ultimate")
    single_ult = [h for h in heroes if len([a for a in own_abilities(kb.hero(h)) if a["kind"] == "ultimate"]) == 1
                  and len(own_abilities(kb.hero(h))) >= 4]
    for h in wsample(rng, single_ult, hero_w, 5):
        abil = own_abilities(kb.hero(h))
        names = [a["name_en"] for a in abil]
        if len(set(names)) != len(names):
            continue
        order = sorted(range(len(abil)), key=lambda i: rng.random())
        opts = [(LETTERS[n], abil[i]["name_en"]) for n, i in enumerate(order[:5])]
        ult = next(a for a in abil if a["kind"] == "ultimate")
        if ult["name_en"] not in [t for _, t in opts]:
            opts[-1] = (opts[-1][0], ult["name_en"])
        gold = next(k_ for k_, t in opts if t == ult["name_en"])
        ref = {"kind": "ability_ultimate", "hero": h}
        out.append(mk(f"ability_ultimate.{h}", "abilities", "ability_ultimate",
                      f"Какая из способностей героя {hero_name(kb, h)} — ультимейт? Варианты: {option_list(opts)}.",
                      gold, "choice", "datafeed abilities kind", 0,
                      options=[{"key": k_, "text": t} for k_, t in opts], ref=ref, hero=h,
                      ultimate=ult["name_en"]))

    rng = random.Random(f"{rng_seed}:abilities:innate")
    for h in wsample(rng, heroes, hero_w, 6):
        ab = next(a for a in kb.hero(h)["abilities"] if a["innate"])
        ref = {"kind": "hero_innate", "hero": h}
        aliases = sorted({ab["key"], ab["name_ru"]} - {ab["name_en"]})
        out.append(mk(f"hero_innate.{h}", "abilities", "hero_innate",
                      f"Как называется врождённая (innate) способность героя {hero_name(kb, h)} в патче 7.41f?",
                      ab["name_en"], "text_key", "datafeed abilities innate", 0, aliases=aliases, ref=ref, hero=h))
    return out


def gen_heroes(kb: KB, rng_seed: int, hero_w: dict[str, float]) -> list[dict]:
    heroes = [h for h in sorted(kb.heroes()) if h not in EXCL["heroes"]]
    used: set[str] = set()
    out: list[dict] = []

    def pick(subtype: str, k: int, ok=lambda h: True) -> list[str]:
        rng = random.Random(f"{rng_seed}:heroes:{subtype}")
        chosen = wsample(rng, [h for h in heroes if h not in used and ok(kb.hero(h))], hero_w, k)
        used.update(chosen)
        return chosen

    attr_opts = ATTR_OPTIONS
    for h in pick("attr", 5):
        ref = {"kind": "hero_attr", "hero": h}
        out.append(mk(f"hero_attr.{h}", "heroes", "hero_attr",
                      f"Какой основной атрибут у героя {hero_name(kb, h)}? Варианты: {option_list(attr_opts)}.",
                      derive(kb, ref), "choice", "datafeed heroes primary_attr", 0,
                      options=[{"key": k_, "text": t} for k_, t in attr_opts], ref=ref, hero=h))
    atk_opts = [("melee", "ближний бой"), ("ranged", "дальний бой")]
    for h in pick("attack", 3):
        ref = {"kind": "hero_attack_type", "hero": h}
        out.append(mk(f"hero_attack_type.{h}", "heroes", "hero_attack_type",
                      f"Ближний или дальний бой у героя {hero_name(kb, h)}? Варианты: {option_list(atk_opts)}.",
                      derive(kb, ref), "choice", "datafeed heroes attack_type", 0,
                      options=[{"key": k_, "text": t} for k_, t in atk_opts], ref=ref, hero=h))
    for h in pick("bat_odd", 2, lambda x: x["base"]["bat"] != 1.7) + pick("bat", 2):
        ref = {"kind": "hero_bat", "hero": h}
        out.append(mk(f"hero_bat.{h}", "heroes", "hero_bat",
                      f"Каково базовое время атаки (BAT) героя {hero_name(kb, h)} в секундах?",
                      derive(kb, ref), "number", "datafeed heroes attack_rate", 0.01, ref=ref, hero=h))
    for h in pick("armor", 4):
        ref = {"kind": "hero_armor", "hero": h}
        out.append(mk(f"hero_armor.{h}", "heroes", "hero_armor",
                      f"Сколько брони у героя {hero_name(kb, h)} на 1 уровне без предметов "
                      "(суммарное значение, как в интерфейсе, с учётом ловкости)?",
                      derive(kb, ref), "number", "datafeed heroes armor + agi/6", 0.2, ref=ref, hero=h))
    for h in pick("ms", 4):
        ref = {"kind": "hero_move_speed", "hero": h}
        out.append(mk(f"hero_move_speed.{h}", "heroes", "hero_move_speed",
                      f"Какова базовая скорость передвижения героя {hero_name(kb, h)}?",
                      derive(kb, ref), "number", "datafeed heroes movement_speed", 0, ref=ref, hero=h))
    return out


def gen_talents(kb: KB, rng_seed: int, hero_w: dict[str, float]) -> list[dict]:
    heroes = [h for h in sorted(kb.heroes()) if h not in EXCL["heroes"]]
    out: list[dict] = []
    rng = random.Random(f"{rng_seed}:talents")
    chosen = wsample(rng, heroes, hero_w, 10)
    level_opts = [("10", "ряд 10 уровня"), ("15", "ряд 15 уровня"), ("20", "ряд 20 уровня"), ("25", "ряд 25 уровня")]

    def uniq(hero: dict) -> list[tuple[int, dict]]:
        texts = [o["text_en"] for t in hero["talents"] for o in t["options"]]
        return [(t["level"], o) for t in hero["talents"] for o in t["options"] if texts.count(o["text_en"]) == 1]

    for n, h in enumerate(chosen):
        hero = kb.hero(h)
        cands = uniq(hero)
        if n < 5:
            level, opt = rng.choice(cands)
            ref = {"kind": "talent_level", "hero": h, "talent": opt["key"]}
            out.append(mk(f"talent_level.{h}", "talents", "talent_level",
                          f"В каком ряду талантов (10, 15, 20 или 25 уровень) у героя {hero_name(kb, h)} "
                          f"находится талант «{opt['text_en']}»? Ответь числом: {option_list(level_opts)}.",
                          str(derive(kb, ref)), "choice", "datafeed heroes talents", 0,
                          options=[{"key": k_, "text": t} for k_, t in level_opts], ref=ref, hero=h))
        else:
            level, opt = rng.choice(cands)
            truth = rng.random() < 0.5
            ask_level = level
            if not truth:
                ask_level = rng.choice([t["level"] for t in hero["talents"] if t["level"] != level])
            ref = {"kind": "talent_present", "hero": h, "level": ask_level, "talent": opt["key"]}
            out.append(mk(f"talent_present.{h}", "talents", "talent_present",
                          f"Есть ли у героя {hero_name(kb, h)} в ряду талантов {ask_level} уровня вариант "
                          f"«{opt['text_en']}»? (да/нет)",
                          derive(kb, ref), "yes_no", "datafeed heroes talents", 0, ref=ref, hero=h))
    return out


def mech(qid, question, answer, answer_type, file, section, evidence, tolerance=0, kw=None, check=None, **extra):
    if answer_type == "yes_no":
        answer = answer == "yes"
    return mk(f"mech.{qid}", "mechanics", "mechanics", question, answer, answer_type,
              f"mechanics_{file.lower()}.md, {section}", tolerance, file=file, evidence=evidence,
              kw=kw or [], check=check, **extra)


def mechanics_questions() -> list[dict]:
    yn = "yes_no"
    num = "number"
    shard_opts = [("A", "тому, кто нанёс последний удар"), ("B", "одному из двух героев убившей команды с наименьшим нетворсом"),
                  ("C", "всем героям убившей команды"), ("D", "герою с наибольшим уроном по Tormentor")]
    return [
        mech("universal_damage", "Сколько основного урона атаки даёт герою-универсалу каждое очко каждого из трёх "
             "атрибутов в патче 7.41f?", 0.45, num, "A", "1. Атрибуты",
             "каждая единица **каждого** из трёх атрибутов даёт **+0.45 к основному урону**", 0.005,
             ["универсал", "universal", "урон"], {"kind": "formula", "name": "damage_per_point_universal"}),
        mech("bkb_level1", "Сколько секунд длится иммунитет к дебаффам (Avatar) у Black King Bar на 1-м уровне?",
             9, num, "A", "5. Иммунитет",
             "длительность **9/8/7 с** по уровням", 0, ["bkb", "black king bar", "avatar"],
             {"kind": "item_special", "item": "black_king_bar", "special": "duration", "index": 0}),
        mech("mkb_chance", "Какой шанс (в процентах) пробить уклонение у Monkey King Bar в патче 7.41f?", 80, num, "B",
             "3. Ближний и дальний бой", "шанс 80%, 70 магического урона", 0, ["monkey king bar", "mkb"],
             {"kind": "item_special", "item": "monkey_king_bar", "special": "bonus_chance"}),
        mech("vessel_reduction", "На сколько процентов Spirit Vessel (Soul Release) снижает лечение врага в патче 7.41f?",
             70, num, "A", "10. Lifesteal", "**Spirit Vessel** Soul Release на враге −70%", 0,
             ["spirit vessel", "health restoration"],
             {"kind": "item_special", "item": "spirit_vessel", "special": "restoration_reduction_enemy"}),
        mech("skadi_vessel", "Враг получает снижение восстановления здоровья −50% от Eye of Skadi и −70% от Spirit Vessel. "
             "Какое итоговое снижение в процентах по правилам патча 7.41f?", 85, num, "A", "10. Lifesteal",
             "отрицательная часть = 1−0.5×0.3 = **85%** снижения", 0.5, ["spirit vessel", "skadi", "убывающе"]),
        mech("shiva_healing", "Снижает ли Freezing Aura у Shiva's Guard лечение и восстановление здоровья врагов "
             "в патче 7.41f? (да/нет)", "no", yn, "A", "10. Lifesteal",
             "**Shiva's Guard больше не снижает Health Restoration**", 0, ["shiva", "health restoration"]),
        mech("bloodthorn_crit", "Даёт ли Bloodthorn критический удар в патче 7.41f? (да/нет)", "no", yn, "A",
             "11. Скорость атаки", "Bloodthorn в текущем описании крита **не имеет**", 0, ["bloodthorn", "крит"]),
        mech("basher_melee", "Какой шанс оглушения (в процентах) у Skull Basher для героя ближнего боя?", 25, num, "A",
             "11. Скорость атаки", "шанс **25% у ближних** героев и **10% у дальних**", 0, ["skull basher", "bash"],
             {"kind": "item_special", "item": "basher", "special": "bash_chance_melee"}),
        mech("basher_ranged", "Какой шанс оглушения (в процентах) у Skull Basher для героя дальнего боя?", 10, num, "A",
             "11. Скорость атаки", "шанс **25% у ближних** героев и **10% у дальних**", 0, ["skull basher", "bash"],
             {"kind": "item_special", "item": "basher", "special": "bash_chance_ranged"}),
        mech("diffusal_illusions", "Сжигают ли мана иллюзии с Diffusal Blade (Manabreak) в патче 7.41f? (да/нет)", "no",
             yn, "B", "1. Иллюзии", "Diffusal Blade и Disperser: иллюзии НЕ сжигают ману (с 7.40)", 0,
             ["diffusal", "иллюзии"]),
        mech("facets", "Есть ли в патче 7.41f грани героев (facets)? (да/нет)", "no", yn, "B", "12. Facets",
             "В текущем патче 7.41f фасетов нет", 0, ["facets", "фасет", "грани"]),
        mech("talent_points", "Сколько отдельных талант-очков (не очков умений) получает герой до максимального "
             "уровня в патче 7.41f?", 8, num, "B", "5. Таблица опыта и уровни",
             "(всего 8 талантов у каждого героя)", 0, ["таланты", "талант-очк"]),
        mech("talent_ability_point", "Тратится ли в патче 7.41f очко умения на изучение таланта? (да/нет)", "no", yn, "B",
             "5. Таблица опыта и уровни", "Думают, что талант забирает очко умения (до 7.40 так было). Теперь отдельные очки.",
             0, ["талант", "очко умения"]),
        mech("neutral_t1_minute", "С какой минуты игры доступен нейтральный предмет Tier 1 в патче 7.41f?", 0, num, "B",
             "7. Нейтральные предметы", "Считают, что Tier 1 нейтрал только с 5:00: в 7.41 доступен с 0:00", 0,
             ["tier 1", "madstone", "нейтральн"]),
        mech("neutral_t1_cost", "Сколько Madstone нужно для крафта нейтрального предмета Tier 1 в патче 7.41f?", 6, num, "B",
             "7. Нейтральные предметы", "Крафт Tier 1 стоит 5». С 7.41 стоит 6 Madstone.", 0,
             ["madstone", "tier 1", "крафт"]),
        mech("armor_10", "Какое снижение физического урона в процентах даёт 10 брони по формуле патча 7.41f?", 37.5, num,
             "A", "2. Броня", "10 брони → урон ×0.625 (−37.5%)", 0.1, ["броня", "формула", "0.06"],
             {"kind": "armor_formula", "armor": 10}),
        mech("magic_resist_cloak", "У героя базовое сопротивление магии 25%, он покупает Cloak (+18% сопротивления). "
             "Каково итоговое сопротивление магии в процентах (источники перемножаются)?", 38.5, num, "A",
             "3. Магическое сопротивление", "итог 1−0.75×0.82 = **38.5%**", 0.1,
             ["магическое сопротивление", "cloak", "мультипликативно"]),
        mech("wisdom_shrine", "Сколько опыта даёт третья активация Святилища мудрости (Wisdom Shrine) в патче 7.41f?", 800,
             num, "B", "8. Руны", "(200/500/800 и далее)", 0, ["wisdom shrine", "святилищ"]),
        mech("tormentor_shard", "Кто получает Aghanim's Shard за убийство Tormentor в патче 7.41f? Варианты: "
             f"{option_list(shard_opts)}.", "B", "choice", "B", "6. Aghanim's Scepter и Shard",
             "один из двух героев убившей команды с наименьшим нетворсом", 0, ["tormentor", "shard"],
             options=[{"key": k_, "text": t} for k_, t in shard_opts]),
        mech("stack_penalty", "На сколько процентов уменьшается награда за крипов в застаканном нейтральном лагере "
             "(штраф за стак) в патче 7.41f?", 20, num, "B", "4. Золото и опыт",
             "Стак-крип с 7.39e даёт штраф 20% (раньше 15%)", 0, ["стак", "штраф"]),
        mech("haste_duration", "Сколько секунд длится руна Haste в патче 7.41f?", 22, num, "A",
             "12. Скорость передвижения", "длительность **22 с**", 0, ["haste", "руна"]),
        mech("lifesteal_nonhero", "На сколько процентов уменьшен вампиризм от атак (lifesteal) против негероев?", 40, num,
             "A", "10. Lifesteal", "Против **негероев** Lifesteal уменьшен на **40%**", 0, ["lifesteal", "негерое"]),
        mech("evasion_stack", "У героя Butterfly (35% уклонения), Radiance (25%) и Heaven's Halberd (25%). "
             "Каков итоговый шанс уклонения в процентах (стакаются убывающе)?", 63.4, num, "A", "8. Уклонение",
             "1 − 0.65×0.75×0.75 = **63.4%**", 0.2, ["evasion", "уклонение", "убывающе"]),
        mech("crit_stack", "Складываются ли шансы и множители критического удара у двух предметов (Daedalus и "
             "Crystalys) на одном герое? (да/нет)", "no", yn, "A", "11. Скорость атаки",
             "Несколько источников крита **не стакаются**", 0, ["крит", "daedalus", "crystalys"]),
        mech("cleave_ranged", "Работает ли Cleave у Battle Fury на героях дальнего боя? (да/нет)", "no", yn, "A",
             "11. Скорость атаки", "Cleave — только **ближние** юниты", 0, ["cleave", "battle fury", "ближн"]),
        mech("status_slow", "Уменьшает ли статус-сопротивление силу (процент) замедления движения, начиная с патча "
             "7.34? (да/нет)", "no", yn, "A", "9. Статус-сопротивление",
             "С 7.34 статус-сопротивление **не влияет на силу замедления**", 0, ["статус-сопротивление", "замедлен"]),
        mech("status_stack", "Два источника статус-сопротивления 50% и 16% дают какое итоговое статус-сопротивление "
             "в процентах (стакаются мультипликативно)?", 58, num, "A", "9. Статус-сопротивление",
             "Bulldoze 50% + Sange and Yasha 16% → 58%", 0.1, ["статус-сопротивление", "мультипликативно"]),
        mech("bkb_pure", "Защищает ли Debuff Immunity (BKB) от чистого урона способностей, которые не пробивают "
             "иммунитет к дебаффам? (да/нет)", "yes", yn, "A", "5. Иммунитет",
             "**100% иммунитет к чистому и отражённому урону**", 0, ["debuff immunity", "чистый урон", "bkb"]),
        mech("strength_mr", "Даёт ли сила (Strength) героя сопротивление магии в патче 7.41f? (да/нет)", "no", yn, "A",
             "1. Атрибуты", "Strength **не даёт** магического сопротивления", 0, ["strength", "сила", "магическое"]),
        mech("hp_per_str", "Сколько максимального здоровья даёт 1 единица силы в патче 7.41f?", 22, num, "A",
             "1. Атрибуты", "даёт **+22 к максимальному HP**", 0, ["strength", "hp"],
             {"kind": "formula", "name": "health_per_str"}),
        mech("base_magic_resist", "Каково базовое сопротивление магии героев в процентах?", 25, num, "A",
             "1. Атрибуты", "Базовое магическое сопротивление: **25% у всех героев**", 0, ["магическое сопротивление"],
             {"kind": "all_heroes_magic_resist"}),
        mech("blade_mail_immune", "Наносит ли отражённый урон (например, Blade Mail) урон герою под Debuff Immunity "
             "в патче 7.41? (да/нет)", "no", yn, "A", "4. Типы урона",
             "«Reflected damage doesn't affect Debuff Immune units»", 0, ["blade mail", "отражённый", "debuff immunity"]),
        mech("abyssal_pierce", "Пробивает ли актив Overwhelm у Abyssal Blade иммунитет к дебаффам? (да/нет)", "yes", yn, "A",
             "5. Иммунитет", "**Abyssal Blade Overwhelm пробивает** иммунитет", 0, ["abyssal", "overwhelm"]),
        mech("silver_edge_pierce", "Пробивает ли Shadow Walk у Silver Edge (Break) иммунитет к дебаффам? (да/нет)", "no",
             yn, "A", "5. Иммунитет", "Silver Edge Shadow Walk (Break, лимит скорости 200) **не пробивает**", 0,
             ["silver edge", "break"]),
    ]


def mechanics_questions_b() -> list[dict]:
    """Second bank: facts from mechanics_a/b that the first bank does not ask (official or datafeed-backed lines only)."""
    yn, num = "yes_no", "number"
    neutral_opts = [("A", "6"), ("B", "8"), ("C", "10"), ("D", "12")]
    return [
        mech("b_mana_per_int", "Сколько максимальной маны даёт 1 единица интеллекта в патче 7.41f?", 12, num, "A",
             "1. Атрибуты", "**+12 к максимальной мане**", 0, ["интеллект", "мана"]),
        mech("b_hp_regen_str", "Сколько регенерации здоровья (в единицах в секунду) даёт 1 единица силы?", 0.1, num, "A",
             "1. Атрибуты", "**+0.1 к регенерации HP**", 0.005, ["сила", "регенерац"]),
        mech("b_base_hp", "Сколько базового здоровья (до вклада силы) у всех героев в патче 7.41f?", 120, num, "A",
             "1. Атрибуты", "Базовое HP: **120** у всех 127 героев", 0, ["базовое hp", "120"]),
        mech("b_int_mr", "Сколько процентов базового сопротивления магии даёт 1 единица интеллекта?", 0.1, num, "A",
             "1. Атрибуты", "**+0.1% к базовому магическому сопротивлению**", 0.005, ["интеллект", "магическ"]),
        mech("b_armor_20", "Какое снижение физического урона в процентах даёт 20 брони по формуле патча 7.41f?", 54.5, num,
             "A", "2. Броня", "20 → ×0.4545 (−54.5%)", 0.1, ["броня", "формула"]),
        mech("b_armor_neg", "Как меняется получаемый физический урон при −10 брони (в процентах, плюс — больше урона)?",
             37.5, num, "A", "2. Броня", "−10 → ×1.375 (+37.5%)", 0.1, ["броня", "отрицательная"]),
        mech("b_glimmer_cloak", "У героя базовое сопротивление магии 25%, Cloak даёт 18%, Glimmer Cape даёт 20%. "
             "Каково итоговое сопротивление магии в процентах (источники перемножаются)?", 50.8, num, "A",
             "3. Магическое сопротивление", "= 50.8%", 0.1, ["cloak", "glimmer", "мультипликативно"]),
        mech("b_bkb_mr", "Сколько процентов магического сопротивления даёт Debuff Immunity от Black King Bar "
             "в патче 7.41f?", 60, num, "A", "3. Магическое сопротивление", "BKB 60% (с 7.35c, было 50%)", 0,
             ["bkb", "магическ"]),
        mech("b_desolator", "На сколько единиц Desolator снижает броню цели?", 6, num, "A", "2. Броня",
             "Desolator −6 на 7 с", 0, ["desolator", "броня"]),
        mech("b_aeon_hp", "При каком проценте здоровья владельца срабатывает Combo Breaker у Aeon Disk "
             "(срабатывает, когда здоровье ниже этого значения)?", 70, num, "A", "6. Диспелы",
             "пассивно при HP < 70%", 0, ["aeon disk", "combo breaker"]),
        mech("b_aeon_sr", "Сколько процентов сопротивления статусам даёт Combo Breaker у Aeon Disk на 2.5 с?", 75, num, "A",
             "6. Диспелы", "+75% сопротивления статусу на 2.5 с", 0, ["aeon disk", "сопротивления статус"]),
        mech("b_silver_break", "Сколько секунд длится Break от Shadow Walk у Silver Edge?", 5, num, "A", "7. Break",
             "ломает пассивки на 5 с", 0, ["silver edge", "break"]),
        mech("b_break_items", "Отключает ли Break пассивные компоненты предметов (например, уклонение Butterfly)? "
             "(да/нет)", "no", yn, "A", "7. Break", "**Не отключает** пассивные компоненты предметов и талантов", 0,
             ["break", "butterfly", "пассивн"]),
        mech("b_evasion_spells", "Может ли уклонение (evasion) заставить промахнуться заклинание? (да/нет)", "no", yn, "A",
             "8. Уклонение", "уклониться от заклинаний evasion нельзя", 0, ["evasion", "заклинан"]),
        mech("b_satanic_ls", "Сколько процентов вампиризма (lifesteal) даёт Satanic в патче 7.41f?", 25, num, "A",
             "10. Lifesteal", "**Satanic 25%**", 0, ["satanic", "lifesteal"]),
        mech("b_bloodstone_sls", "Сколько процентов spell lifesteal даёт Bloodstone в патче 7.41f?", 20, num, "A",
             "10. Lifesteal", "**Bloodstone 20%**", 0, ["bloodstone", "spell lifesteal"]),
        mech("b_frost_hr", "На сколько процентов Orb of Frost снижает восстановление здоровья цели в патче 7.41f?", 15, num,
             "A", "10. Lifesteal", "**Orb of Frost** −15%", 0, ["orb of frost", "health restoration"]),
        mech("b_sange_hr", "Сколько процентов Health Restoration даёт Sange в патче 7.41f?", 12, num, "A", "10. Lifesteal",
             "Sange **+12%**", 0, ["sange", "health restoration"]),
        mech("b_daedalus_crit", "Какой множитель критического удара (в процентах урона) у Daedalus?", 225, num, "A",
             "11. Скорость атаки", "**Daedalus** 30% на 225%", 0, ["daedalus", "крит"]),
        mech("b_basher_cd", "Каков внутренний кулдаун Bash у Skull Basher в секундах?", 2.3, num, "A",
             "11. Скорость атаки", "оглушение 1.2 с, КД 2.3 с", 0.05, ["skull basher", "bash"]),
        mech("b_abyssal_stun", "Сколько секунд оглушает активная способность Overwhelm у Abyssal Blade?", 1.6, num, "A",
             "11. Скорость атаки", "актив, стан 1.6 с", 0.05, ["abyssal", "overwhelm"]),
        mech("b_bfury_heroes", "Какую долю урона атаки (в процентах) наносит Cleave у Battle Fury по героям?", 60, num, "A",
             "11. Скорость атаки", "**60% урона** по героям, **40% по крипам**", 0, ["battle fury", "cleave"]),
        mech("b_shiva_as", "На сколько единиц Freezing Aura у Shiva's Guard снижает скорость атаки врагов в патче 7.41f?",
             40, num, "A", "11. Скорость атаки", "Freezing Aura: −40 к AS", 0, ["shiva", "freezing aura"]),
        mech("b_mom_armor", "На сколько единиц Berserk у Mask of Madness снижает броню самого владельца в патче 7.41?", 7,
             num, "A", "2. Броня", "Mask of Madness снижает **собственную** броню на 7", 0, ["mask of madness", "броня"]),
        mech("b_abyssal_slow_res", "Сколько процентов Slow Resistance даёт Abyssal Blade в патче 7.41f?", 30, num, "A",
             "9. Статус-сопротивление", "**Abyssal Blade 30%**", 0, ["abyssal", "slow resistance"]),
        mech("b_manta_duration", "Сколько секунд существуют иллюзии от Manta Style?", 18, num, "B", "1. Иллюзии",
             "Manta Style: 2 иллюзии, 18 с", 0, ["manta", "иллюзии"]),
        mech("b_manta_melee", "Какую долю урона героя (в процентах) наносят иллюзии Manta Style у героя дальнего боя "
             "в патче 7.41f?", 25, num, "B", "1. Иллюзии", "Ближний бой наносит 33%, дальний 25%", 0, ["manta", "иллюзии"]),
        mech("b_illusion_roshan", "Какую долю атакующего урона (в процентах) наносят иллюзии по Рошану?", 20, num, "B",
             "1. Иллюзии", "иллюзии наносят 20% атакующего урона", 0, ["иллюзии", "рошан"]),
        mech("b_mekansm", "Сколько здоровья восстанавливает актив Restore у Mekansm в патче 7.41f?", 250, num, "B",
             "2. Ауры", "Restore 250 HP, кулдаун 50", 0, ["mekansm", "restore"]),
        mech("b_pipe_barrier", "Сколько магического урона поглощает барьер Pipe of Insight в патче 7.41f?", 425, num, "B",
             "2. Ауры", "Barrier поглощает 425 магического урона", 0, ["pipe", "barrier"]),
        mech("b_shiva_blast", "Сколько магического урона наносит Arctic Blast у Shiva's Guard в патче 7.41f?", 225, num, "B",
             "2. Ауры", "Arctic Blast 225 урона (7.41f)", 0, ["shiva", "arctic blast"]),
        mech("b_aegis", "Сколько минут держится Aegis of the Immortal после получения (в обычном режиме)?", 5, num, "B",
             "10. Крипы и объекты карты", "Aegis держится 5 минут", 0, ["aegis"]),
        mech("b_blessing_roshan", "Выпадает ли Aghanim's Blessing с Рошана в патче 7.41f? (да/нет)", "no", yn, "B",
             "6. Aghanim's Scepter и Shard", "Roshan больше не выдаёт Aghanim's Blessing (убрано в 7.38)", 0,
             ["roshan", "blessing"]),
        mech("b_neutral_t2_cost", "Сколько Madstone нужно для крафта нейтрального предмета Tier 2 в патче 7.41f? Варианты: "
             f"{option_list(neutral_opts)}.", "C", "choice", "B", "7. Нейтральные предметы",
             "Tier 2, 3, 4, 5 = по 10 Madstone", 0, ["madstone", "tier 2", "крафт"],
             options=[{"key": k_, "text": t} for k_, t in neutral_opts]),
        mech("b_enchant_wise", "Существует ли зачарование Wise (Wise Enchantment) нейтральных предметов в патче 7.41f? "
             "(да/нет)", "no", yn, "B", "7. Нейтральные предметы", "Boundless, Vast, Wise убраны (7.41)", 0,
             ["wise", "зачарован"]),
    ]


def used_entities(questions: list[dict]) -> dict[str, set[str]]:
    used = {"items": set(), "heroes": set(), "abilities": set()}
    for q in questions:
        used["items"].update(q.get("items") or [])
        if q.get("hero"):
            used["heroes"].add(q["hero"])
        ability = (q.get("ref") or {}).get("ability")
        if ability:
            used["abilities"].add(ability)
    return used


def build_questions(kb: KB | None = None, seed: int = SEED, kb_dir: Path = KB_DIR, bank: str = "a") -> list[dict]:
    kb = kb or KB()
    hero_w, item_w = weights(kb_dir)
    mechanics = mechanics_questions
    EXCL.update({"items": set(), "heroes": set(), "abilities": set()})
    if bank == "b":
        EXCL.update(used_entities(load_bank(QUESTIONS_PATH)))
        mechanics = mechanics_questions_b
    try:
        qs = (gen_items(kb, seed, item_w) + gen_abilities(kb, seed, hero_w) + gen_heroes(kb, seed, hero_w)
              + gen_talents(kb, seed, hero_w) + mechanics())
    finally:
        EXCL.update({"items": set(), "heroes": set(), "abilities": set()})
    ids = [q["id"] for q in qs]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate question ids: " + ", ".join(i for i in ids if ids.count(i) > 1))
    return qs


def write_bank(path: Path = QUESTIONS_PATH, kb: KB | None = None, seed: int = SEED, bank: str = "a") -> list[dict]:
    kb = kb or KB()
    qs = build_questions(kb, seed, bank=bank)
    counts = {c: sum(1 for q in qs if q["category"] == c) for c in CATEGORIES}
    doc = {"patch": kb.index["patch"], "seed": seed, "bank": bank, "kb_built": kb.index["built"], "count": len(qs),
           "counts": counts, "questions": qs}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return qs


def load_bank(path: Path = QUESTIONS_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["questions"]


def mech_text(file: str) -> str:
    return MECH_FILES[file].read_text(encoding="utf-8")


def evidence_line(file: str, evidence: str) -> str | None:
    for line in mech_text(file).splitlines():
        if evidence in line:
            return line
    return None


NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def parse_number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list) and value:
        return parse_number(value[0])
    if not isinstance(value, str):
        return None
    text = re.sub(r"(?<=\d)[  ](?=\d{3}(?!\d))", "", value.replace("−", "-").replace("–", "-"))
    m = NUM_RE.search(text)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


def grade_number(value, gold, tolerance=0) -> bool:
    got = parse_number(value)
    if got is None:
        return False
    return abs(got - float(gold)) <= float(tolerance) + 1e-9


def parse_yes_no(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value) if value in (0, 1) else None
    if not isinstance(value, str):
        return None
    words = re.findall(r"[a-zа-яё+\-0-9]+", value.lower().replace("ё", "е"))
    if not words:
        return None
    first = words[0]
    if first in YES:
        return True
    if first in NO:
        return False
    return None


def grade_yes_no(value, gold) -> bool:
    got = parse_yes_no(value)
    if got is None:
        return False
    gold_bool = gold if isinstance(gold, bool) else parse_yes_no(gold)
    return got == gold_bool


def grade_choice(value, gold, options=None) -> bool:
    if value is None:
        return False
    raw = value if isinstance(value, str) else str(value)
    n = norm(raw)
    if not n:
        return False
    options = options or []
    if n == norm(str(gold)):
        return True
    keys = {norm(o["key"]): o["key"] for o in options}
    if n in keys:
        return keys[n] == gold
    tokens = [norm(t) for t in re.findall(r"[^\s,.;:()—\-]+", raw)]
    if tokens and tokens[0] in keys and len(tokens[0]) >= 1 and re.match(r"^\W*[A-Za-z0-9]+\W", raw + " "):
        if tokens[0] in keys and len(raw.split()[0].strip(".,;:)(")) == len(tokens[0]):
            return keys[tokens[0]] == gold
    hits = [o["key"] for o in options if norm(o["text"]) and norm(o["text"]) in n]
    if len(hits) == 1:
        return hits[0] == gold
    return False


def resolve_item(kb: KB, name) -> str | None:
    if not isinstance(name, str) or not name.strip():
        return None
    hits = kb.search(name, "item", limit=5)
    exact = [h for h in hits if h["score"] >= 95]
    if exact:
        return exact[0]["key"]
    if hits and hits[0]["score"] >= 70:
        return hits[0]["key"]
    return None


def answer_item_keys(kb: KB, value) -> set[str] | None:
    if isinstance(value, str):
        value = [p for p in re.split(r"\s*(?:,|;|\n|\+| и )\s*", value) if p.strip()]
    if not isinstance(value, list):
        return None
    keys = set()
    for name in value:
        name = name if isinstance(name, str) else str(name)
        if re.search(r"recipe|рецепт", name, re.I):
            continue
        key = resolve_item(kb, name)
        if key is None:
            return None
        keys.add(key)
    return keys


def grade_items_set(kb: KB, value, gold) -> bool:
    got = answer_item_keys(kb, value)
    return got is not None and got == set(gold)


def grade_text_key(value, gold, aliases=()) -> bool:
    if not isinstance(value, str):
        return False
    n = norm(value)
    if not n:
        return False
    return any(norm(t) and norm(t) in n for t in [gold, *aliases])


def grade(kb: KB, q: dict, value) -> bool:
    kind = q["answer_type"]
    if kind == "number":
        return grade_number(value, q["answer"], q.get("tolerance", 0))
    if kind == "yes_no":
        return grade_yes_no(value, q["answer"])
    if kind == "choice":
        return grade_choice(value, q["answer"], q.get("options"))
    if kind == "items_set":
        return grade_items_set(kb, value, q["answer"])
    if kind == "text_key":
        return grade_text_key(value, q["answer"], q.get("aliases", []))
    raise ValueError(kind)


def parse_answers(text: str) -> dict[str, object]:
    """Pull {id: answer} out of a model reply that should be a JSON array but may carry fences or chatter."""
    text = re.sub(r"```(?:json)?", "", text or "", flags=re.I).strip()
    data = None
    for candidate in (text, text[text.find("["): text.rfind("]") + 1] if "[" in text else "",
                      text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            break
        except ValueError:
            continue
    out: dict[str, object] = {}
    if isinstance(data, dict):
        if "id" in data and "answer" in data:
            data = [data]
        elif isinstance(data.get("answers"), list):
            data = data["answers"]
        else:
            return {str(k): v for k, v in data.items()}
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and "id" in row and "answer" in row:
                out[str(row["id"])] = row["answer"]
        return out
    for m in re.finditer(r"\{[^{}]*\}", text):
        try:
            row = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(row, dict) and "id" in row and "answer" in row:
            out[str(row["id"])] = row["answer"]
    return out


FORMAT_HINT = {
    "number": "число (только число, без единиц и слов)",
    "yes_no": "строго «да» или «нет»",
    "choice": "только ключ выбранного варианта",
    "items_set": "массив названий предметов (английские названия), без рецептов",
    "text_key": "короткое название (английское)",
}


def interleave(questions: list[dict], limit: int | None) -> list[dict]:
    if not limit or limit >= len(questions):
        return list(questions)
    buckets = {c: [q for q in questions if q["category"] == c] for c in CATEGORIES}
    out = []
    while len(out) < limit and any(buckets.values()):
        for c in CATEGORIES:
            if buckets[c] and len(out) < limit:
                out.append(buckets[c].pop(0))
    order = {q["id"]: i for i, q in enumerate(questions)}
    return sorted(out, key=lambda q: order[q["id"]])


def chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def split_sections(file: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for line in mech_text(file).splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def mechanics_excerpt(q: dict, limit_chars: int = 6000) -> str:
    sections = split_sections(q["file"])
    wanted = q["source"].split(", ", 1)[1]
    title, lines = next((t, ls) for t, ls in sections if t.startswith(wanted.split(".")[0] + ".") or t == wanted)
    kws = [k.lower() for k in q.get("kw", [])]
    bullets: list[tuple[str, str]] = []
    heading = ""
    for ln in lines:
        if ln.startswith("### "):
            heading = ln[4:].lower()
        elif ln.startswith("- ") or ln.startswith("  - "):
            bullets.append((heading, ln))
    scored = [(sum(k in (h + " " + ln.lower()) for k in kws), i) for i, (h, ln) in enumerate(bullets)]
    top = sorted((x for x in scored if x[0] > 0), key=lambda x: (-x[0], x[1]))[:8]
    keep = sorted(i for _, i in top)
    body = "\n".join(bullets[i][1] for i in keep) if keep else "\n".join(ln for _, ln in bullets)[:limit_chars]
    return f"[Механики, файл {q['file']}, раздел {title}]\n{body}"


def fallback_context(kb: KB, q: dict) -> str:
    parts = []
    if q["category"] == "mechanics":
        parts.append(mechanics_excerpt(q))
    if q.get("hero"):
        parts.append(kb.hero_text(q["hero"]))
    for key in q.get("items", []):
        parts.append(kb.item_text(key))
    return "\n\n".join(parts)


def context_provider(kb: KB, force: str = "auto"):
    if force == "fallback":
        return "fallback", lambda q: fallback_context(kb, q)
    try:
        from dota_coach.kb_context import context_for_question
    except Exception:
        return "fallback", lambda q: fallback_context(kb, q)

    def provide(q: dict) -> str:
        try:
            return context_for_question(q["question"], q.get("hero")) or ""
        except Exception:
            return fallback_context(kb, q)

    return "kb_context", provide


def union_context(questions: list[dict], provide) -> str:
    seen: set[str] = set()
    blocks: list[str] = []
    for q in questions:
        for block in re.split(r"\n{2,}", provide(q)):
            key = block.strip()
            if key and key not in seen:
                seen.add(key)
                blocks.append(key)
    return "\n\n".join(blocks)


def tokens_of(text: str) -> int:
    cyr = len(CYR_RE.findall(text))
    return round(cyr / CYR_CHARS_PER_TOKEN + (len(text) - cyr) / LAT_CHARS_PER_TOKEN)


def build_prompt(questions: list[dict], context: str = "") -> str:
    lines = []
    if context:
        lines += ["Справочник по патчу 7.41f:", context, ""]
    lines += ["Ответь на вопросы. Ответ — строго JSON-массив без пояснений и без markdown: "
              '[{"id": "...", "answer": ...}], по одному объекту на вопрос, id скопируй как есть.', "", "Вопросы:"]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. [{q['id']}] {q['question']}")
        lines.append(f"   Формат ответа: {FORMAT_HINT[q['answer_type']]}.")
    return "\n".join(lines)


def make_batches(questions: list[dict], mode: str, provide=None, size: int = BATCH_SIZE,
                 token_limit: int = CONTEXT_TOKEN_LIMIT) -> list[tuple[list[dict], str]]:
    out: list[tuple[list[dict], str]] = []

    def add(group: list[dict]):
        ctx = union_context(group, provide) if mode == "cards" else ""
        if mode == "cards" and tokens_of(ctx) > token_limit and len(group) > 1:
            half = len(group) // 2
            add(group[:half])
            add(group[half:])
            return
        out.append((group, ctx))

    for group in chunks(questions, size):
        add(group)
    return out


def default_client_factory(options):
    from claude_agent_sdk import ClaudeSDKClient
    return ClaudeSDKClient(options=options)


def make_options(system: str, model: str):
    from claude_agent_sdk import ClaudeAgentOptions
    return ClaudeAgentOptions(system_prompt=system, model=model, tools=[], setting_sources=[], max_turns=1)


async def ask(client, text: str, timeout: float = 600.0) -> str:
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    async def run() -> str:
        await client.query(text)
        out = ""
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                out += "".join(b.text for b in msg.content if isinstance(b, TextBlock))
            elif isinstance(msg, ResultMessage):
                break
        return out

    return await asyncio.wait_for(run(), timeout)


async def run_batch(group: list[dict], context: str, system: str, model: str, client_factory, stats: dict) -> tuple[dict, list[str]]:
    client = client_factory(make_options(system, model))
    replies: list[str] = []
    answers: dict[str, object] = {}
    await client.connect()
    try:
        prompt = build_prompt(group, context)
        for attempt in range(3):
            stats["calls"] += 1
            try:
                reply = await ask(client, prompt)
            except Exception as exc:
                reply = ""
                stats["errors"].append(f"{type(exc).__name__}: {exc}")
            replies.append(reply)
            answers.update(parse_answers(reply))
            missing = [q for q in group if q["id"] not in answers]
            if not missing:
                break
            if not reply:
                continue
            prompt = ("В прошлом ответе не хватило или не разобрался JSON. Верни строго JSON-массив "
                      '[{"id": "...", "answer": ...}] только для этих вопросов:\n'
                      + "\n".join(f"[{q['id']}] {q['question']} Формат ответа: {FORMAT_HINT[q['answer_type']]}."
                                  for q in missing))
    finally:
        await client.disconnect()
    return answers, replies


async def run_mode(kb: KB, questions: list[dict], mode: str, model: str, client_factory=None,
                   concurrency: int = 3, size: int = BATCH_SIZE, context: str = "auto") -> dict:
    client_factory = client_factory or default_client_factory
    source, provide = ("none", None)
    if mode == "cards":
        source, provide = context_provider(kb, context)
    batches = make_batches(questions, mode, provide, size)
    system = SYSTEM_CARDS if mode == "cards" else SYSTEM_BARE
    stats = {"calls": 0, "errors": []}
    sem = asyncio.Semaphore(concurrency)
    started = time.time()

    async def one(group, ctx):
        async with sem:
            return await run_batch(group, ctx, system, model, client_factory, stats)

    outcomes = await asyncio.gather(*(one(g, c) for g, c in batches))
    rows = []
    for (group, ctx), (answers, replies) in zip(batches, outcomes):
        for q in group:
            value = answers.get(q["id"])
            rows.append({"id": q["id"], "category": q["category"], "question": q["question"], "gold": q["answer"],
                         "answer_type": q["answer_type"], "model_answer": value,
                         "correct": q["id"] in answers and grade(kb, q, value),
                         "answered": q["id"] in answers, "context_tokens": tokens_of(ctx)})
    order = {q["id"]: i for i, q in enumerate(questions)}
    rows.sort(key=lambda r: order[r["id"]])
    return {"mode": mode, "model": model, "date": date.today().isoformat(), "context_source": source,
            "questions": len(rows), "correct": sum(r["correct"] for r in rows), "calls": stats["calls"],
            "batches": len(batches), "errors": stats["errors"], "seconds": round(time.time() - started, 1),
            "results": rows}


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}%" if b else "-"


def fmt(value) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


RESULT_NAMES = ("bare", "cards", "cards_fallback")


def build_report(results: dict[str, dict], day: str) -> str:
    modes = [m for m in RESULT_NAMES if m in results]
    lines = [f"# Factcheck 7.41f, {day}", "",
             "Режимы: bare — без данных; cards — контекст из dota_coach.kb_context (боевой поиск по тексту вопроса); "
             "cards_fallback — карточки сущностей, названных в вопросе, плюс выдержка из mechanics_a/b "
             "(сущность берётся из метаданных вопроса, поэтому это верхняя граница, а не проверка поиска). "
             "null — модель отказалась отвечать из-за нехватки данных; в точности такой ответ считается ошибкой.", ""]
    for m in modes:
        r = results[m]
        lines.append(f"- {m}: модель {r['model']}, вопросов {r['questions']}, верных {r['correct']} "
                     f"({pct(r['correct'], r['questions'])}), вызовов {r['calls']}, пачек {r['batches']}, "
                     f"{r['seconds']} с, контекст: {r['context_source']}, без ответа (null): "
                     f"{sum(1 for x in r['results'] if x['model_answer'] is None)}")
    lines += ["", "## Точность по категориям", "", "| категория | вопросов | " + " | ".join(modes) + " |",
              "|---|---|" + "---|" * len(modes)]
    base = results[modes[0]]["results"]
    for c in CATEGORIES + ["ВСЕГО"]:
        sel = [r for r in base if c == "ВСЕГО" or r["category"] == c]
        if not sel:
            continue
        cells = []
        for m in modes:
            rows = [r for r in results[m]["results"] if c == "ВСЕГО" or r["category"] == c]
            ok = sum(r["correct"] for r in rows)
            cells.append(f"{ok}/{len(rows)} ({pct(ok, len(rows))})")
        lines.append(f"| {c} | {len(sel)} | " + " | ".join(cells) + " |")
    for m in ("cards", "cards_fallback"):
        if m in results:
            r = results[m]
            err = 100 * (r["questions"] - r["correct"]) / max(r["questions"], 1)
            lines += ["", f"Доля ошибок, {m} ({r['context_source']}): {err:.1f}% (цель из спецификации: не более 5%)."]
    for m in modes:
        wrong = [r for r in results[m]["results"] if not r["correct"]]
        lines += ["", f"## Ошибки: {m} ({len(wrong)})", ""]
        for r in wrong:
            lines.append(f"- `{r['id']}` — {r['question']}")
            lines.append(f"  эталон: {fmt(r['gold'])}; модель: {fmt(r['model_answer'])}")
    for cname in ("cards", "cards_fallback"):
        if "bare" not in results or cname not in results:
            continue
        a = {r["id"]: r for r in results["bare"]["results"]}
        both = [r for r in results[cname]["results"] if not r["correct"] and r["id"] in a and not a[r["id"]]["correct"]]
        lines += ["", f"## Неверно в bare и в {cname} ({len(both)}): кандидаты на сомнительный эталон", ""]
        for r in both:
            lines.append(f"- `{r['id']}` — {r['question']}")
            lines.append(f"  эталон: {fmt(r['gold'])}; bare: {fmt(a[r['id']]['model_answer'])}; "
                         f"{cname}: {fmt(r['model_answer'])}")
    return "\n".join(lines) + "\n"


def results_path(mode: str, day: str, out_dir: Path = FACT_DIR, bank: str = "a") -> Path:
    return out_dir / (f"results_{mode}_{day}.json" if bank == "a" else f"results_{bank}_{mode}_{day}.json")


def load_results(day: str, out_dir: Path = FACT_DIR, bank: str = "a") -> dict[str, dict]:
    out = {}
    for mode in RESULT_NAMES:
        p = results_path(mode, day, out_dir, bank)
        if p.exists():
            out[mode] = json.loads(p.read_text(encoding="utf-8"))
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="regenerate questions.json and exit")
    ap.add_argument("--mode", choices=["bare", "cards", "both"], default="both")
    ap.add_argument("--context", choices=["auto", "fallback"], default="auto",
                    help="cards context: kb_context if it exists (auto) or the built-in fallback")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--category", choices=CATEGORIES)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--bank", choices=["a", "b"], default="a", help="b: second bank, other seed, other entities")
    ap.add_argument("--questions", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=FACT_DIR)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)
    kb = KB()
    if args.questions is None:
        args.questions = QUESTIONS_B_PATH if args.bank == "b" else QUESTIONS_PATH
    if args.build or not args.questions.exists():
        qs = write_bank(args.questions, kb, SEED_B if args.bank == "b" else SEED, args.bank)
        print(f"questions.json: {len(qs)} questions", {c: sum(1 for q in qs if q['category'] == c) for c in CATEGORIES})
        if args.build:
            return
    day = date.today().isoformat()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if not args.report_only:
        questions = load_bank(args.questions)
        if args.category:
            questions = [q for q in questions if q["category"] == args.category]
        questions = interleave(questions, args.limit)
        for mode in (["bare", "cards"] if args.mode == "both" else [args.mode]):
            res = asyncio.run(run_mode(kb, questions, mode, args.model, concurrency=args.concurrency,
                                       context=args.context))
            name = "cards_fallback" if mode == "cards" and args.context == "fallback" else mode
            results_path(name, day, args.out_dir, args.bank).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n",
                                                            encoding="utf-8")
            print(f"{name}: {res['correct']}/{res['questions']} correct, {res['calls']} calls, "
                  f"context={res['context_source']}, errors={len(res['errors'])}", flush=True)
    results = load_results(day, args.out_dir, args.bank)
    if results:
        report = args.out_dir / (f"report_{day}.md" if args.bank == "a" else f"report_{args.bank}_{day}.md")
        report.write_text(build_report(results, day), encoding="utf-8")
        print("report:", report)


if __name__ == "__main__":
    main()
