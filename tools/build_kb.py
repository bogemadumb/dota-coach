"""Normalize data/cache/official into the curated knowledge base data/kb (heroes, items, index, formulas)."""

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach.config import ROOT  # noqa: E402
from dota_coach.kb import ROLE_ORDER, derive_stats, fnum, load_formulas, vstr  # noqa: E402

OFF = ROOT / "data" / "cache" / "official"
KB = ROOT / "data" / "kb"
LANGS = {"ru": "russian", "en": "english"}
HERO_PREFIX = "npc_dota_hero_"
NEUTRAL_NONE = 4294967295
PRIMARY = {0: "str", 1: "agi", 2: "int", 3: "all"}

BEHAVIOR_BITS = {
    0: "hidden", 1: "passive", 2: "no_target", 3: "unit_target", 4: "point", 5: "aoe", 6: "not_learnable",
    7: "channelled", 8: "item", 9: "toggle", 10: "directional", 11: "immediate", 12: "autocast",
    13: "optional_unit_target", 14: "optional_point", 15: "optional_no_target", 16: "aura", 17: "attack",
    18: "dont_resume_movement", 19: "root_disables", 20: "unrestricted", 21: "ignore_pseudo_queue",
    22: "ignore_channel", 23: "dont_cancel_movement", 24: "dont_alert_target", 25: "dont_resume_attack",
    26: "normal_when_stolen", 27: "ignore_backswing", 28: "rune_target", 29: "dont_cancel_channel",
    30: "vector_targeting", 31: "last_resort_point", 32: "can_self_cast", 33: "show_in_guides",
    34: "unlocked_by_effect_index", 35: "suppress_associated_consumable", 36: "free_draw_targeting",
    37: "ignore_silence",
}
BEHAVIOR_RU = {
    "hidden": "скрытая", "passive": "пассивная", "no_target": "без цели", "unit_target": "на цель",
    "point": "в точку", "aoe": "по области", "channelled": "канальная", "toggle": "переключаемая",
    "directional": "по направлению", "immediate": "мгновенная", "autocast": "автокаст",
    "optional_unit_target": "цель по желанию", "optional_point": "точка по желанию", "aura": "аура",
    "attack": "модификатор атаки", "vector_targeting": "векторная", "root_disables": "блокируется корнями",
    "unrestricted": "работает под ограничениями", "can_self_cast": "можно на себя",
    "ignore_silence": "игнорирует silence",
}
TARGET_TEAM = {1: "friendly", 2: "enemy", 4: "custom"}
TARGET_TYPE = {1: "hero", 2: "creep", 4: "building", 16: "courier", 32: "other", 64: "tree", 128: "custom"}
TARGET_FLAGS = {
    2: "ranged_only", 4: "melee_only", 8: "dead", 16: "magic_immune_enemies", 32: "not_magic_immune_allies",
    64: "invulnerable", 128: "fow_visible", 256: "no_invis", 512: "not_ancients", 1024: "player_controlled",
    2048: "not_dominated", 4096: "not_summoned", 8192: "not_illusions", 16384: "not_attack_immune",
    32768: "mana_only", 65536: "check_disable_help", 131072: "not_creep_hero", 262144: "out_of_world",
    524288: "not_nightmared", 1048576: "prefer_enemies", 2097152: "respect_obstructions",
}
DAMAGE_TYPE = {1: "physical", 2: "magical", 4: "pure"}
DISPELLABLE = {0: None, 1: "strong", 2: "basic", 3: "no"}
IMMUNITY = {0: None, 1: True, 2: False, 3: True, 4: False, 5: False}
IMMUNITY_NAME = {0: "none", 1: "allies_yes", 2: "allies_no", 3: "enemies_yes", 4: "enemies_no",
                 5: "allies_yes_enemies_no"}
OP_NAME = {0: "add", 1: "multiply", 2: "subtract", 3: "percent_increase", 4: "percent_decrease", 5: "set"}
ABILITY_TYPE = {0: "basic", 1: "ultimate", 2: "talent"}

STAT_RU = {
    "damage": "к урону", "mana_regen": "к восстановлению маны", "health": "к здоровью", "str": "к силе",
    "hp_regen": "к восстановлению здоровья", "armor": "к броне", "int": "к интеллекту",
    "attack": "к скорости атаки", "all": "ко всем характеристикам", "mana": "к мане",
    "move_speed": "к скорости передвижения", "agi": "к ловкости", "spell_resist": "к сопротивлению магии",
    "cast_range": "к дальности применения", "evasion": "к уклонению",
    "spell_lifesteal": "к вампиризму от заклинаний", "lifesteal": "к вампиризму",
    "restoration_amp": "к усилению восстановления", "attack_range": "к дальности атаки дальнего боя",
    "attack_range_melee": "к дальности атаки ближнего боя", "attack_range_all": "к дальности атаки",
    "cooldown_reduction": "к снижению перезарядки", "aoe_bonus": "к радиусу действия",
    "max_mana_percentage": "к максимальной мане", "slow_resistance": "к сопротивлению замедлениям",
    "debuff_amp": "к усилению негативных эффектов", "status_resist": "к сопротивлению эффектам",
    "projectile_speed": "к скорости снарядов", "primary_attribute": "к основной характеристике",
    "attack_pct": "к скорости атаки", "healing_amp": "к усилению лечения",
    "selected_attrib": "к выбранной характеристике", "manacost_reduction": "к снижению расхода маны",
}
STAT_EN = {
    "damage": "Damage", "mana_regen": "Mana Regen", "health": "Health", "str": "Strength",
    "hp_regen": "Health Regen", "armor": "Armor", "int": "Intelligence", "attack": "Attack Speed",
    "all": "All Attributes", "mana": "Mana", "move_speed": "Movement Speed", "agi": "Agility",
    "spell_resist": "Magic Resistance", "cast_range": "Cast Range", "evasion": "Evasion",
    "spell_lifesteal": "Spell Lifesteal", "lifesteal": "Lifesteal", "restoration_amp": "Restoration Amp",
    "attack_range": "Ranged Attack Range", "attack_range_melee": "Melee Attack Range",
    "attack_range_all": "Attack Range", "cooldown_reduction": "Cooldown Reduction", "aoe_bonus": "AoE",
    "max_mana_percentage": "Max Mana", "slow_resistance": "Slow Resistance", "debuff_amp": "Debuff Amp",
    "status_resist": "Status Resistance", "projectile_speed": "Projectile Speed",
    "primary_attribute": "Primary Attribute", "attack_pct": "Attack Speed", "healing_amp": "Healing Amp",
    "selected_attrib": "Selected Attribute", "manacost_reduction": "Mana Cost Reduction",
}

UNKNOWN = "[?]"
TOKEN = re.compile(r"%%|%(\w+)%|\{[a-zA-Z]:(\w+)\}")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean(values):
    return [round(float(v), 4) for v in values]


def strip_html(text: str) -> str:
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<h1>(.*?)</h1>", lambda m: f"\n[{m.group(1).strip()}] ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def decode_bits(value: int, table: dict[int, str], bit_index: bool = False) -> list[str]:
    out = []
    for bit in range(64):
        if value >> bit & 1:
            key = bit if bit_index else 1 << bit
            out.append(table.get(key, f"bit{bit}"))
    return out


def apply_op(values: list[float], op: int, v: float) -> list[float] | None:
    if op == 0:
        return [round(x + v, 4) for x in values]
    if op == 1:
        return [round(x * v, 4) for x in values]
    if op == 2:
        return [round(x - v, 4) for x in values]
    if op == 3:
        return [round(x * (1 + v / 100), 4) for x in values]
    if op == 4:
        return [round(x * (1 - v / 100), 4) for x in values]
    return None


class Leftovers:
    def __init__(self):
        self.items: list[tuple[str, str]] = []

    def add(self, where: str, name: str):
        self.items.append((where, name))


LEFT = Leftovers()
LEGACY_TALENTS: set[str] = set()


def spec_ctx(specials: list[dict], mode: str = "base") -> dict[str, str]:
    ctx = {}
    for sv in specials:
        vals = sv["values_float"]
        if mode == "shard" and sv["values_shard"]:
            vals = sv["values_shard"]
        elif mode == "scepter" and sv["values_scepter"]:
            vals = sv["values_scepter"]
        if not vals:
            vals = (sv["values_shard"] or sv["values_scepter"] or [b["value"] for b in sv["bonuses"]]
                    or sv["facet_bonus"]["values"])
        if vals:
            ctx[sv["name"].lower()] = vstr(vals)
    return ctx


def fill(text: str, ctx: dict[str, str], where: str, resolver=None) -> str:
    def sub(m):
        if m.group(0) == "%%":
            return "%"
        name = m.group(1) or m.group(2)
        val = ctx.get(name.lower())
        if val is None and resolver:
            val = resolver(name)
        if val is None:
            LEFT.add(where, name)
            return UNKNOWN
        return val

    return TOKEN.sub(sub, text)


def render(text: str, ctx: dict[str, str], where: str, resolver=None) -> str:
    return strip_html(fill(text, ctx, where, resolver))


def render_all(texts: list[str], ctx, where, resolver=None) -> list[str]:
    return [render(t, ctx, where, resolver) for t in texts if t]


def behavior_info(raw: dict) -> dict:
    beh = int(raw["behavior"])
    flags = decode_bits(beh, BEHAVIOR_BITS, bit_index=True)
    team = raw["target_team"]
    return {
        "behavior": flags,
        "behavior_ru": [BEHAVIOR_RU[f] for f in flags if f in BEHAVIOR_RU],
        "target_team": [TARGET_TEAM[b] for b in (1, 2, 4) if team & b] if team else [],
        "target_type": [TARGET_TYPE[b] for b in sorted(TARGET_TYPE) if raw["target_type"] & b],
        "target_flags": decode_bits(raw["flags"], TARGET_FLAGS) if raw["flags"] else [],
        "damage_type": DAMAGE_TYPE.get(raw["damage"]),
        "bkb_pierce": IMMUNITY.get(raw["immunity"]),
        "immunity_code": raw["immunity"],
        "immunity": IMMUNITY_NAME.get(raw["immunity"], f"code{raw['immunity']}"),
        "dispellable": DISPELLABLE.get(raw["dispellable"], f"code{raw['dispellable']}"),
    }


def nonzero(arr):
    return clean(arr) if arr and any(abs(x) > 1e-9 for x in arr) else []


def build_specials(raw_ru: dict, raw_en: dict, talent_levels: dict[str, int], with_facets: bool = False) -> list[dict]:
    en = {sv["name"]: sv for sv in raw_en["special_values"]}
    out = []
    for sv in raw_ru["special_values"]:
        base = clean(sv["values_float"])
        entry = {
            "key": sv["name"],
            "system": sv["name"].startswith("Ability"),
            "heading_ru": strip_html(sv["heading_loc"]) or None,
            "heading_en": strip_html(en.get(sv["name"], {}).get("heading_loc", "")) or None,
            "values": base,
            "percent": bool(sv["is_percentage"]),
        }
        if sv["values_shard"]:
            entry["values_shard"] = clean(sv["values_shard"])
        if sv["values_scepter"]:
            entry["values_scepter"] = clean(sv["values_scepter"])
        bon = []
        for b in sv["bonuses"]:
            if talent_levels and b["name"] not in talent_levels:
                LEGACY_TALENTS.add(b["name"])
                continue
            row = {"talent": b["name"], "level": talent_levels.get(b["name"]), "op": OP_NAME.get(b["operation"], str(b["operation"])),
                   "value": round(b["value"], 4)}
            with_t = apply_op(base, b["operation"], b["value"]) if base else None
            if with_t is not None:
                row["values_with"] = with_t
            bon.append(row)
        if bon:
            entry["talents"] = bon
        fb = sv["facet_bonus"]
        if fb["name"] or sv["required_facet"]:
            entry["legacy_facet"] = {"facet": fb["name"] or sv["required_facet"], "values": clean(fb["values"]),
                                     "op": fb["operation"]}
        out.append(entry)
    return out


def mode_resolver(raw: dict, mode: str):
    svs = {sv["name"].lower(): sv for sv in raw["special_values"]}

    def resolve(name: str):
        low = name.lower()
        cands = [low]
        if low.startswith("bonus_"):
            cands.insert(0, low[6:])
        cands += [f"{mode}_{low}", f"{mode}_{low.removeprefix('bonus_')}"]
        for c in cands:
            sv = svs.get(c)
            if not sv:
                continue
            vals = sv[f"values_{mode}"] or sv["values_shard"] or sv["values_scepter"] or sv["values_float"]
            if vals:
                return vstr(vals)
        return None

    return resolve


def upgrade_block(raw_ru: dict, raw_en: dict, specials: list[dict], key: str, ctx_mode: str, where: str):
    text_ru, text_en = raw_ru[f"{key}_loc"], raw_en[f"{key}_loc"]
    values_key = f"values_{ctx_mode}"
    changes = []
    for sv in specials:
        new = sv.get(values_key)
        if new and new != sv["values"]:
            changes.append({"key": sv["key"], "heading_ru": sv["heading_ru"], "from": sv["values"], "to": new})
    if not text_ru and not changes:
        return None
    ctx_ru = spec_ctx(raw_ru["special_values"], ctx_mode)
    ctx_en = spec_ctx(raw_en["special_values"], ctx_mode)
    return {
        "text_ru": render(text_ru, ctx_ru, f"{where}:{key}:ru", mode_resolver(raw_ru, ctx_mode)) if text_ru else None,
        "text_en": render(text_en, ctx_en, f"{where}:{key}:en", mode_resolver(raw_en, ctx_mode)) if text_en else None,
        "changes": changes,
    }


def build_ability(raw_ru: dict, raw_en: dict, talent_levels: dict[str, int], hero_key: str | None = None) -> dict:
    where = raw_ru["name"]
    ctx_ru = spec_ctx(raw_ru["special_values"])
    ctx_en = spec_ctx(raw_en["special_values"])
    specials = build_specials(raw_ru, raw_en, talent_levels)
    info = behavior_info(raw_ru)
    out = {
        "key": raw_ru["name"], "id": raw_ru["id"], "hero": hero_key,
        "name_ru": raw_ru["name_loc"], "name_en": raw_en["name_loc"],
        "kind": ABILITY_TYPE.get(raw_ru["type"], str(raw_ru["type"])),
        "innate": bool(raw_ru["ability_is_innate"]),
        "granted_by_scepter": bool(raw_ru["ability_is_granted_by_scepter"]),
        "granted_by_shard": bool(raw_ru["ability_is_granted_by_shard"]),
        "max_level": raw_ru["max_level"],
        **info,
        "cooldown": nonzero(raw_ru["cooldowns"]),
        "mana_cost": nonzero(raw_ru["mana_costs"]),
        "health_cost": nonzero(raw_ru["health_costs"]),
        "gold_cost": nonzero(raw_ru["gold_costs"]),
        "cast_range": nonzero(raw_ru["cast_ranges"]),
        "cast_point": nonzero(raw_ru["cast_points"]),
        "channel_time": nonzero(raw_ru["channel_times"]),
        "duration": nonzero(raw_ru["durations"]),
        "desc_ru": render(raw_ru["desc_loc"], ctx_ru, f"{where}:desc:ru"),
        "desc_en": render(raw_en["desc_loc"], ctx_en, f"{where}:desc:en"),
        "notes_ru": render_all(raw_ru["notes_loc"], ctx_ru, f"{where}:notes:ru"),
        "notes_en": render_all(raw_en["notes_loc"], ctx_en, f"{where}:notes:en"),
        "specials": specials,
        "shard": upgrade_block(raw_ru, raw_en, specials, "shard", "shard", where),
        "scepter": upgrade_block(raw_ru, raw_en, specials, "scepter", "scepter", where),
    }
    return out


def talent_resolver(raw: dict, bonuses: list[dict]):
    own = spec_ctx(raw["special_values"])

    def resolve(name: str):
        low = name.lower()
        if low in own:
            return own[low]
        short = low.removeprefix("bonus_")
        for b in bonuses:
            if b["special"].lower() in (low, short):
                return fnum(b["value"])
        for b in bonuses:
            if short and (short in b["special"].lower() or b["special"].lower() in short):
                return fnum(b["value"])
        return None

    return resolve


def build_hero(hid: int, ru: dict, en: dict, formulas: dict) -> dict:
    h_ru, h_en = ru[hid], en[hid]
    key = h_ru["name"].removeprefix(HERO_PREFIX)
    talent_levels = {t["name"]: 10 + 5 * (i // 2) for i, t in enumerate(h_ru["talents"])}
    en_abilities = {a["name"]: a for a in h_en["abilities"]}
    en_talents = {t["name"]: t for t in h_en["talents"]}
    abilities = [build_ability(a, en_abilities[a["name"]], talent_levels, key) for a in h_ru["abilities"]]

    bonus_by_talent: dict[str, list[dict]] = {}
    for a in abilities:
        for sv in a["specials"]:
            for t in sv.get("talents", []):
                bonus_by_talent.setdefault(t["talent"], []).append({"ability": a["key"], "special": sv["key"],
                                                                    "op": t["op"], "value": t["value"]})
    talents = []
    for lvl in (10, 15, 20, 25):
        options = []
        for t in h_ru["talents"]:
            if talent_levels[t["name"]] != lvl:
                continue
            te = en_talents[t["name"]]
            bonuses = bonus_by_talent.get(t["name"], [])
            options.append({
                "key": t["name"],
                "text_ru": render(t["name_loc"], spec_ctx(t["special_values"]), f"{t['name']}:ru",
                                  talent_resolver(t, bonuses)),
                "text_en": render(te["name_loc"], spec_ctx(te["special_values"]), f"{t['name']}:en",
                                  talent_resolver(te, bonuses)),
                "affects": bonuses,
            })
        talents.append({"level": lvl, "options": options})

    base = {
        "str": h_ru["str_base"], "agi": h_ru["agi_base"], "int": h_ru["int_base"],
        "str_gain": h_ru["str_gain"], "agi_gain": h_ru["agi_gain"], "int_gain": h_ru["int_gain"],
        "damage_min": h_ru["damage_min"], "damage_max": h_ru["damage_max"], "bat": h_ru["attack_rate"],
        "attack_range": h_ru["attack_range"], "projectile_speed": h_ru["projectile_speed"],
        "armor": round(h_ru["armor"], 4), "magic_resist": h_ru["magic_resistance"],
        "move_speed": h_ru["movement_speed"], "turn_rate": h_ru["turn_rate"],
        "sight_day": h_ru["sight_range_day"], "sight_night": h_ru["sight_range_night"],
        "health": h_ru["max_health"], "mana": h_ru["max_mana"],
        "health_regen": round(h_ru["health_regen"], 4), "mana_regen": round(h_ru["mana_regen"], 4),
    }
    primary = PRIMARY[h_ru["primary_attr"]]
    innate = next((a["key"] for a in abilities if a["innate"]), None)
    return {
        "key": key, "id": hid, "name_ru": h_ru["name_loc"], "name_en": h_en["name_loc"],
        "primary_attr": primary, "primary_attr_code": h_ru["primary_attr"],
        "attack_type": "melee" if h_ru["attack_capability"] == 1 else "ranged",
        "complexity": h_ru["complexity"],
        "roles": {ROLE_ORDER[i]: lv for i, lv in enumerate(h_ru["role_levels"]) if lv > 0},
        "base": base,
        "level1": derive_stats(base, primary, 1, formulas),
        "level25": derive_stats(base, primary, 25, formulas),
        "innate": innate,
        "abilities": abilities,
        "talents": talents,
        "facets": h_ru["facets"],
    }


def slim_item_id(name: str) -> str:
    return name.removeprefix("item_")


def split_sections(filled: str) -> list[dict]:
    out = []
    for part in re.split(r"(?=<h1>)", filled):
        if not part.strip():
            continue
        m = re.match(r"<h1>(.*?)</h1>(.*)", part, flags=re.S)
        if m:
            title, body = strip_html(m.group(1)), strip_html(m.group(2))
        else:
            title, body = None, strip_html(part)
        out.append({"title": title, "text": body})
    return out


ACTIVE_WORDS = ("active", "use", "toggle", "актив", "использ", "переключ")
PASSIVE_WORDS = ("passive", "пассив")


def section_kind(title: str | None) -> str:
    low = (title or "").lower()
    if any(low.startswith(w) for w in PASSIVE_WORDS):
        return "passive"
    if any(low.startswith(w) for w in ACTIVE_WORDS):
        return "active"
    return "other"


def signed(v: float, sign: str) -> str:
    if v < 0:
        return fnum(v)
    return sign + fnum(v)


def build_bonuses(raw_ru: dict, raw_en: dict) -> tuple[list[dict], list[dict], dict]:
    en = {sv["name"]: sv for sv in raw_en["special_values"]}
    bonuses, info, stats = [], [], {}
    for sv in raw_ru["special_values"]:
        head = sv["heading_loc"]
        if not head or sv["name"].startswith("Ability"):
            continue
        vals = clean(sv["values_float"])
        if not vals:
            continue
        m = re.match(r"^([+-])\$(\w+)$", head)
        if m or head[0] in "+-":
            sign = head[0]
            token = m.group(2) if m else None
            if token:
                label_ru = STAT_RU.get(token, token)
                label_en = STAT_EN.get(token, token)
            else:
                label_ru = strip_html(head[1:])
                label_en = strip_html(en.get(sv["name"], {}).get("heading_loc", "")[1:])
            pct = "%" if sv["is_percentage"] else ""
            parts = [signed(v, sign) for v in vals]
            shown = parts[0] if len(set(parts)) == 1 else "/".join(parts)
            bonuses.append({"key": sv["name"], "stat": token, "label_ru": label_ru, "label_en": label_en,
                            "values": vals, "percent": bool(sv["is_percentage"]),
                            "text_ru": f"{shown}{pct} {label_ru}"})
            stats[token or sv["name"]] = vals[0] if len(vals) == 1 else vals
        else:
            info.append({"key": sv["name"], "heading_ru": strip_html(head).rstrip(":"),
                         "heading_en": strip_html(en.get(sv["name"], {}).get("heading_loc", "")).rstrip(":"),
                         "values": vals, "percent": bool(sv["is_percentage"])})
    return bonuses, info, stats


CURRENT_EPOCH = (7, 41)
LEGACY_NEUTRAL_IDS = range(287, 382)
REMOVAL_NOTES = ("item removed from the game", "removed", "removed item", "item cycled out")
RETURN_PREFIXES = ("returning", "new item", "added", "new tier")


def version_key(patch: str) -> tuple:
    return tuple(int(x) if x.isdigit() else ord(x) for x in re.findall(r"\d+|[a-z]", patch))


def patch_history() -> dict[int, list[tuple[str, str, list[str]]]]:
    """ability_id -> [(patch, section, notes)] over every cached official patch notes file, oldest first."""
    docs: dict[str, dict] = {}
    for sub in ("patchnotes", "patchnotes_old"):
        for p in (OFF / "english" / sub).glob("*.json"):
            doc = read(p)
            if "patch_number" in doc:
                docs.setdefault(doc["patch_number"], doc)
    out: dict[int, list] = {}
    for patch in sorted(docs, key=version_key):
        for sec in ("items", "neutral_items"):
            for it in docs[patch].get(sec, []):
                aid = it.get("ability_id", -1)
                if aid > 0:
                    notes = [re.sub(r"<[^>]+>", "", n["note"]).strip().rstrip(".").lower() for n in it.get("ability_notes", [])]
                    out.setdefault(aid, []).append((patch, sec, notes))
    return out


def removed_items(history: dict | None = None) -> dict[int, tuple[str, str]]:
    """ability_id -> (patch, basis): basis is 'patchnotes' (explicit removal note) or 'retired_neutral'."""
    history = history if history is not None else patch_history()
    out: dict[int, tuple[str, str]] = {}
    for aid, rows in history.items():
        state = None
        for patch, sec, notes in rows:
            if any(n in REMOVAL_NOTES for n in notes):
                state = (patch, "patchnotes")
            elif state and any(n.startswith(RETURN_PREFIXES) for n in notes):
                state = None
        if state:
            out[aid] = state
        elif rows and rows[-1][1] == "neutral_items":
            out[aid] = (rows[-1][0], "retired_neutral")
    return out


def shop_info(name: str, cost: int, is_recipe: bool, tier: int | None, stock_max: int, enhancement: bool,
              removed_in: tuple[str, str] | None = None) -> dict:
    """removed = gone from the game (patch notes, or a neutral artifact no longer in any tier);
    special = exists but cannot be bought (granted, dropped, upgraded, consumable from another source)."""
    if tier is not None:
        return {"purchasable": False, "status": "neutral_drop"}
    explicit = removed_in and removed_in[1] == "patchnotes" and (enhancement or version_key(removed_in[0]) >= CURRENT_EPOCH)
    if removed_in and (explicit or (cost == 0 and not enhancement)):
        explicit_patch = removed_in[0] if removed_in[1] == "patchnotes" else None
        return {"purchasable": False, "status": "removed", "removed_in": explicit_patch, "basis": removed_in[1]}
    if enhancement:
        return {"purchasable": False, "status": "enhancement"}
    if is_recipe:
        return {"purchasable": cost > 0, "status": "recipe_scroll" if cost > 0 else "no_scroll"}
    if cost > 0:
        return {"purchasable": True, "status": "shop"}
    if stock_max > 0:
        return {"purchasable": True, "status": "free_stock"}
    return {"purchasable": False, "status": "special"}


def build_items(ru_items, en_items, ru_list, formulas) -> dict[str, dict]:
    by_name = {d["name"]: d for d in ru_items.values()}
    ids = {d["id"]: slim_item_id(d["name"]) for d in ru_items.values()}
    out: dict[str, dict] = {}
    removed = removed_items()
    for iid, raw_ru in ru_items.items():
        raw_en = en_items[iid]
        name = raw_ru["name"]
        key = slim_item_id(name)
        ctx_ru = spec_ctx(raw_ru["special_values"])
        ctx_en = spec_ctx(raw_en["special_values"])
        tier_raw = ru_list[iid]["neutral_item_tier"]
        tier = tier_raw + 1 if tier_raw >= 0 else None
        is_recipe = key.startswith("recipe_")
        enhancement = key.startswith("enhancement_")
        cost = raw_ru["item_cost"]

        if is_recipe:
            target = by_name.get("item_" + key.removeprefix("recipe_"))
            variants = [[ids[c] for c in r["items"]] for r in ru_list[iid]["recipes"]]
            recipe_of = slim_item_id(target["name"]) if target else key.removeprefix("recipe_")
            components = variants[0] if variants else []
            recipe_cost = cost
        else:
            rec = by_name.get("item_recipe_" + key)
            variants = [[ids[c] for c in r["items"]] for r in ru_list[rec["id"]]["recipes"]] if rec else []
            variants = [v for v in variants if key not in v]
            recipe_of = None
            components = variants[0] if variants else []
            recipe_cost = rec["item_cost"] if rec else 0
        parts_cost = sum(by_name["item_" + c]["item_cost"] for c in components if "item_" + c in by_name)
        bonuses, info, stats = build_bonuses(raw_ru, raw_en)
        filled_ru = fill(raw_ru["desc_loc"], ctx_ru, f"{key}:desc:ru")
        filled_en = fill(raw_en["desc_loc"], ctx_en, f"{key}:desc:en")
        sec_ru = [{"kind": section_kind(s["title"]), **s} for s in split_sections(filled_ru)]
        sec_en = [{"kind": section_kind(s["title"]), **s} for s in split_sections(filled_en)]
        info_beh = behavior_info(raw_ru)
        out[key] = {
            "key": key, "id": iid, "name_ru": raw_ru["name_loc"], "name_en": raw_en["name_loc"],
            "cost": cost, "is_recipe": is_recipe, "recipe_of": recipe_of,
            "recipe_cost": recipe_cost if not is_recipe else None,
            "components": components,
            "component_variants": variants if len(variants) > 1 else [],
            "cost_consistent": (not components) or (not is_recipe and cost == parts_cost + recipe_cost) or is_recipe,
            "neutral_tier": tier, "enhancement": enhancement,
            "shop": shop_info(name, cost, is_recipe, tier, raw_ru["item_stock_max"], enhancement,
                              removed.get(iid) or (("", "legacy_neutral_id_block") if iid in LEGACY_NEUTRAL_IDS else None)),
            "stock_max": raw_ru["item_stock_max"], "initial_charges": raw_ru["item_initial_charges"],
            "bonuses": bonuses, "stats": stats, "values": info,
            "sections_ru": sec_ru, "sections_en": sec_en,
            "desc_ru": strip_html(filled_ru),
            "desc_en": strip_html(filled_en),
            "notes_ru": render_all(raw_ru["notes_loc"], ctx_ru, f"{key}:notes:ru"),
            "notes_en": render_all(raw_en["notes_loc"], ctx_en, f"{key}:notes:en"),
            "cooldown": nonzero(raw_ru["cooldowns"]), "mana_cost": nonzero(raw_ru["mana_costs"]),
            "cast_range": nonzero(raw_ru["cast_ranges"]), "channel_time": nonzero(raw_ru["channel_times"]),
            "shard_text_ru": render(raw_ru["shard_loc"], ctx_ru, f"{key}:shard:ru") if raw_ru["shard_loc"] else None,
            "scepter_text_ru": render(raw_ru["scepter_loc"], ctx_ru, f"{key}:scepter:ru") if raw_ru["scepter_loc"] else None,
            "specials": build_specials(raw_ru, raw_en, {}),
            **info_beh,
            "builds_into": [],
        }
    for key, it in out.items():
        if it["is_recipe"]:
            continue
        for c in {c for v in ([it["components"]] + it["component_variants"]) for c in v}:
            if c in out:
                out[c]["builds_into"].append(key)
    for it in out.values():
        it["builds_into"] = sorted(set(it["builds_into"]))
    for it in out.values():
        it["recipe_tree"] = recipe_tree(it["key"], out) if not it["is_recipe"] else None
        flat = flatten(it["recipe_tree"]) if it["recipe_tree"] else None
        it["shopping_list"] = flat
    return out


def recipe_tree(key: str, items: dict, depth: int = 0) -> dict:
    it = items[key]
    node = {"key": key, "name_ru": it["name_ru"], "cost": it["cost"]}
    if it["components"] and depth < 8:
        node["recipe_cost"] = it["recipe_cost"]
        node["components"] = [recipe_tree(c, items, depth + 1) for c in it["components"] if c in items]
    return node


def flatten(node: dict) -> dict:
    leaves: dict[str, int] = {}
    recipes: list[dict] = []

    def walk(n):
        comps = n.get("components")
        if not comps:
            leaves[n["key"]] = leaves.get(n["key"], 0) + 1
            return
        if n.get("recipe_cost"):
            recipes.append({"item": n["key"], "cost": n["recipe_cost"]})
        for c in comps:
            walk(c)

    walk(node)
    return {"parts": [{"key": k, "count": c} for k, c in leaves.items()], "recipes": recipes}


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_lang(lang: str):
    base = OFF / lang
    heroes = {int(p.stem): read(p)["result"]["data"]["heroes"][0] for p in (base / "heroes").glob("*.json")}
    items = {int(p.stem): read(p)["result"]["data"]["items"][0] for p in (base / "items").glob("*.json")}
    ilist = {i["id"]: i for i in read(base / "itemlist.json")["result"]["data"]["itemabilities"]}
    return heroes, items, ilist


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    heroes_ru, items_ru, ilist_ru = load_lang(LANGS["ru"])
    heroes_en, items_en, _ = load_lang(LANGS["en"])

    if KB.exists():
        for sub in ("heroes", "items"):
            for p in (KB / sub).glob("*.json"):
                p.unlink()
    formulas = load_formulas()

    hero_rows, ability_to_hero, talent_to_hero = {}, {}, {}
    for hid in sorted(heroes_ru):
        hero = build_hero(hid, heroes_ru, heroes_en, formulas)
        write_json(KB / "heroes" / f"{hero['key']}.json", hero)
        hero_rows[hero["key"]] = {"id": hid, "ru": hero["name_ru"], "en": hero["name_en"]}
        for a in hero["abilities"]:
            ability_to_hero[a["key"]] = hero["key"]
        for t in hero["talents"]:
            for o in t["options"]:
                talent_to_hero[o["key"]] = hero["key"]

    items = build_items(items_ru, items_en, ilist_ru, formulas)
    item_rows = {}
    for key, it in items.items():
        write_json(KB / "items" / f"{key}.json", it)
        item_rows[key] = {"id": it["id"], "ru": it["name_ru"], "en": it["name_en"], "cost": it["cost"],
                          "tier": it["neutral_tier"], "recipe": it["is_recipe"],
                          "purchasable": it["shop"]["purchasable"], "status": it["shop"]["status"]}

    patches = read(OFF / "english" / "patchnoteslist.json")["patches"]
    last = max(patches, key=lambda p: p["patch_timestamp"])
    fetched = datetime.fromtimestamp((OFF / "english" / "herolist.json").stat().st_mtime, timezone.utc)
    status_counts: dict[str, int] = {}
    for r in item_rows.values():
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    index = {
        "patch": last["patch_number"],
        "patch_date": datetime.fromtimestamp(last["patch_timestamp"], timezone.utc).date().isoformat(),
        "source": "https://www.dota2.com/datafeed/",
        "fetched": fetched.isoformat(timespec="seconds"),
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {"heroes": len(hero_rows), "items": len(item_rows), "abilities": len(ability_to_hero),
                   "talents": len(talent_to_hero), "item_status": status_counts},
        "hero_id_to_key": {str(r["id"]): k for k, r in hero_rows.items()},
        "item_id_to_key": {str(r["id"]): k for k, r in item_rows.items()},
        "heroes": hero_rows, "items": item_rows,
        "ability_to_hero": ability_to_hero, "talent_to_hero": talent_to_hero,
    }
    write_json(KB / "index.json", index)

    seen_pairs = sorted({(w.rsplit(":", 1)[0], n) for w, n in LEFT.items})
    write_json_pretty(KB / "unresolved_placeholders.json",
                      [{"where": w, "placeholder": n} for w, n in seen_pairs])
    print(f"heroes {len(hero_rows)}, items {len(item_rows)}, abilities {len(ability_to_hero)}")
    print(f"unresolved placeholders: {len(LEFT.items)}; stale talent bonuses skipped: {len(LEGACY_TALENTS)}")
    seen = {}
    for where, name in LEFT.items:
        seen.setdefault(name, []).append(where)
    for name, wheres in sorted(seen.items(), key=lambda kv: -len(kv[1]))[:60]:
        print(f"  {name}: {len(wheres)}  e.g. {wheres[0]}")
    return 0


def write_json_pretty(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
