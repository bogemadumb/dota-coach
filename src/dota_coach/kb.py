"""Curated knowledge base over data/kb (built by tools/build_kb.py from the official datafeed). No network."""

import json
import re
from functools import cached_property
from pathlib import Path

import yaml

from dota_coach.config import ROOT

KB_DIR = ROOT / "data" / "kb"
ROLE_ORDER = ["Carry", "Support", "Nuker", "Disabler", "Jungler", "Durable", "Escape", "Pusher", "Initiator"]
ROLE_RU = {"Carry": "Керри", "Support": "Саппорт", "Nuker": "Нюкер", "Disabler": "Контроль", "Jungler": "Лесник",
           "Durable": "Живучесть", "Escape": "Побег", "Pusher": "Пушер", "Initiator": "Инициатор"}
ATTR_RU = {"str": "Сила", "agi": "Ловкость", "int": "Интеллект", "all": "Универсал"}
LEVELS = range(1, 31)
DAMAGE_RU = {"physical": "физический урон", "magical": "магический урон", "pure": "чистый урон"}
DISPEL_RU = {"basic": "рассеивается обычным диспелом", "strong": "рассеивается только сильным диспелом",
             "no": "не рассеивается"}
TEAM_RU = {"friendly": "союзники", "enemy": "враги", "custom": "особая цель"}
TYPE_RU = {"hero": "герои", "creep": "крипы", "building": "здания", "courier": "курьеры", "other": "прочее",
           "tree": "деревья", "custom": "особая"}
STATUS_RU = {"removed": "убран из игры", "shop": "в магазине", "recipe_scroll": "свиток рецепта", "no_scroll": "рецепт без свитка",
             "neutral_drop": "нейтральный (из лагерей)", "enhancement": "усиление нейтрального предмета",
             "free_stock": "бесплатно, запас ограничен", "special": "не продаётся (особый: выдаётся, падает или улучшается иначе)"}


def fnum(x) -> str:
    x = float(x)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.4f}".rstrip("0").rstrip(".")


def vstr(values) -> str:
    vals = [fnum(v) for v in values]
    if len(set(vals)) == 1:
        return vals[0]
    return "/".join(vals)


def load_formulas(path: Path = KB_DIR / "formulas.json") -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def derive_stats(base: dict, primary: str, level: int, formulas: dict | None = None) -> dict:
    """Hero stats at `level` without items/talents/buffs, from the official level-1 values and the fitted coefficients."""
    if level not in LEVELS:
        raise ValueError(f"level must be 1..30, got {level}")
    f = formulas or load_formulas()

    def coef(name):
        return f[name]["value"]

    steps = level - 1
    attrs = {a: base[a] + base[f"{a}_gain"] * steps for a in ("str", "agi", "int")}
    delta = {a: attrs[a] - base[a] for a in attrs}
    if primary == "all":
        bonus_damage = coef("damage_per_point_universal") * sum(attrs.values())
    else:
        bonus_damage = coef("damage_per_primary_point") * delta[primary]
    attack_speed = coef("base_attack_speed") + coef("attack_speed_per_agi") * attrs["agi"]
    attack_speed = max(coef("attack_speed_min"), min(coef("attack_speed_max"), attack_speed))
    armor = base["armor"] + coef("armor_per_agi") * delta["agi"]
    k = coef("armor_reduction_per_point")
    reduction = k * armor / (1 + k * abs(armor))
    dmg_min, dmg_max = base["damage_min"] + bonus_damage, base["damage_max"] + bonus_damage
    return {
        "level": level,
        "str": round(attrs["str"], 2), "agi": round(attrs["agi"], 2), "int": round(attrs["int"], 2),
        "health": round(base["health"] + coef("health_per_str") * delta["str"], 1),
        "mana": round(base["mana"] + coef("mana_per_int") * delta["int"], 1),
        "health_regen": round(base["health_regen"] + coef("health_regen_per_str") * delta["str"], 2),
        "mana_regen": round(base["mana_regen"] + coef("mana_regen_per_int") * delta["int"], 2),
        "armor": round(armor, 2),
        "phys_reduction_pct": round(reduction * 100, 1),
        "magic_resist_pct": base["magic_resist"],
        "damage_min": round(dmg_min, 1), "damage_max": round(dmg_max, 1),
        "damage_avg": round((dmg_min + dmg_max) / 2, 1),
        "attack_speed": round(attack_speed, 1),
        "attacks_per_second": round(attack_speed / (100 * base["bat"]), 3),
        "bat": base["bat"],
        "attack_range": base["attack_range"], "move_speed": base["move_speed"],
    }


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-zа-я]+", "", text.lower().replace("ё", "е"))


class KB:
    def __init__(self, root: Path = KB_DIR):
        self.root = Path(root)
        self._cache: dict[tuple[str, str], dict] = {}

    def _read(self, *parts: str):
        path = self.root.joinpath(*parts)
        if not path.exists():
            raise FileNotFoundError(f"{path} missing, run tools/update_official.py and tools/build_kb.py")
        return json.loads(path.read_text(encoding="utf-8"))

    @cached_property
    def index(self) -> dict:
        return self._read("index.json")

    @cached_property
    def aliases(self) -> dict[str, dict[str, list[str]]]:
        path = self.root / "aliases.yaml"
        if not path.exists():
            return {"heroes": {}, "items": {}}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {"heroes": data.get("heroes") or {}, "items": data.get("items") or {}}

    @cached_property
    def _names(self) -> list[tuple[str, str, str, str]]:
        """(norm, kind, key, via) for every searchable name."""
        out = []
        for kind, rows in (("hero", self.index["heroes"]), ("item", self.index["items"])):
            for key, row in rows.items():
                out.append((norm(key), kind, key, "key"))
                out.append((norm(row["ru"]), kind, key, "ru"))
                out.append((norm(row["en"]), kind, key, "en"))
        for kind, table in (("hero", self.aliases["heroes"]), ("item", self.aliases["items"])):
            for key, names in table.items():
                for name in names:
                    out.append((norm(name), kind, key, "alias"))
        return [row for row in out if row[0]]

    def heroes(self) -> list[str]:
        return list(self.index["heroes"])

    def items(self) -> list[str]:
        return list(self.index["items"])

    def _resolve(self, kind: str, ref) -> str:
        rows = self.index["heroes" if kind == "hero" else "items"]
        id_map = self.index["hero_id_to_key" if kind == "hero" else "item_id_to_key"]
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            key = id_map.get(str(int(ref)))
            if key:
                return key
        elif isinstance(ref, str):
            text = ref.strip()
            prefix = "npc_dota_hero_" if kind == "hero" else "item_"
            low = text.lower()
            if low in rows:
                return low
            if low.removeprefix(prefix) in rows:
                return low.removeprefix(prefix)
            n = norm(text)
            hits = [(k, via) for nm, kd, k, via in self._names if kd == kind and nm == n]
            if hits:
                order = {"key": 0, "alias": 1, "ru": 2, "en": 2}
                hits.sort(key=lambda h: (order[h[1]], not rows[h[0]].get("purchasable", True), h[0]))
                return hits[0][0]
        raise KeyError(f"unknown {kind}: {ref!r}")

    def hero(self, ref) -> dict:
        key = self._resolve("hero", ref)
        if ("hero", key) not in self._cache:
            self._cache[("hero", key)] = self._read("heroes", f"{key}.json")
        return self._cache[("hero", key)]

    def item(self, ref) -> dict:
        key = self._resolve("item", ref)
        if ("item", key) not in self._cache:
            self._cache[("item", key)] = self._read("items", f"{key}.json")
        return self._cache[("item", key)]

    def ability(self, key: str) -> dict:
        """Hero ability, hero talent (kind 'talent') or an item by its key."""
        key = key.strip()
        hero_key = self.index["ability_to_hero"].get(key)
        if hero_key:
            return next(a for a in self.hero(hero_key)["abilities"] if a["key"] == key)
        hero_key = self.index["talent_to_hero"].get(key)
        if hero_key:
            for tier in self.hero(hero_key)["talents"]:
                for option in tier["options"]:
                    if option["key"] == key:
                        return {**option, "kind": "talent", "level": tier["level"], "hero": hero_key}
        try:
            return self.item(key)
        except KeyError:
            raise KeyError(f"unknown ability: {key!r}") from None

    def builds_into(self, item) -> list[str]:
        return list(self.item(item)["builds_into"])

    def search(self, text: str, kind: str | None = None, limit: int = 10) -> list[dict]:
        n = norm(re.sub(r"^(item_|npc_dota_hero_)", "", text.strip().lower()))
        if not n:
            return []
        best: dict[tuple[str, str], tuple[int, str]] = {}
        for nm, kd, key, via in self._names:
            if kind and kd != kind:
                continue
            if nm == n:
                score = 100 if via != "key" else 95
            elif len(n) >= 3 and nm.startswith(n):
                score = 70
            elif len(n) >= 3 and n in nm:
                score = 40
            else:
                continue
            if via == "alias":
                score += 1
            if best.get((kd, key), (0, ""))[0] < score:
                best[(kd, key)] = (score, via)
        rows = {"hero": self.index["heroes"], "item": self.index["items"]}
        found = []
        for (kd, key), (score, via) in best.items():
            row = rows[kd][key]
            penalty = 0 if row.get("purchasable", True) and not row.get("recipe") else 1
            found.append((-score, penalty, kd != "hero", key, kd, row, via))
        found.sort(key=lambda r: r[:4])
        return [{"kind": kd, "key": key, "name_ru": row["ru"], "name_en": row["en"], "score": -neg, "via": via}
                for neg, _, _, key, kd, row, via in found[:limit]]

    def hero_text(self, hero, level: int | None = None, full: bool = True) -> str:
        return hero_card(self.hero(hero), level, full, self.index["patch"])

    def item_text(self, item, full: bool = True) -> str:
        return item_card(self.item(item), self, full)


def threatens_through_bkb(hero: dict, exclude: dict | None = None) -> bool:
    """True if one of the hero's ultimates affects enemies through BKB (official data): pierces, hits enemies,
    is not passive and is not a pure self-buff; `exclude` is the documented list of the undecidable ones."""
    if exclude and hero["key"] in exclude:
        return False
    for a in hero["abilities"]:
        if a["kind"] != "ultimate" or a["bkb_pierce"] is not True or "enemies_yes" not in (a["immunity"] or ""):
            continue
        beh = set(a["behavior"])
        if "passive" in beh:
            continue
        if {"no_target", "immediate"} <= beh and a["damage_type"] is None and "enemy" not in a["target_team"]:
            continue
        return True
    return False


def _cd(values) -> str:
    return vstr(values)


def _ability_tags(a: dict) -> list[str]:
    tags = []
    beh = set(a["behavior"])
    tags.append("пассивная" if "passive" in beh else "активная")
    if "channelled" in beh:
        tags.append("канальная")
    for flag, ru in (("no_target", "без цели"), ("unit_target", "на цель"), ("point", "в точку"),
                     ("aoe", "по области"), ("toggle", "переключаемая"), ("autocast", "автокаст"),
                     ("attack", "модификатор атаки"), ("vector_targeting", "векторная"), ("aura", "аура")):
        if flag in beh:
            tags.append(ru)
    if a["damage_type"]:
        tags.append(DAMAGE_RU[a["damage_type"]])
    if a["bkb_pierce"] is True:
        tags.append("пробивает БКБ")
    elif a["bkb_pierce"] is False:
        tags.append("не пробивает БКБ")
    if a["dispellable"] in DISPEL_RU:
        tags.append(DISPEL_RU[a["dispellable"]])
    team = [TEAM_RU[t] for t in a["target_team"] if t in TEAM_RU]
    if team and "no_target" not in beh:
        tags.append("цели: " + "+".join(team))
    return tags


def _special_lines(a: dict) -> list[str]:
    lines = []
    for sv in a["specials"]:
        if sv["system"] or not sv["heading_ru"] or not sv["values"]:
            continue
        line = f"{sv['heading_ru'].rstrip(':')}: {vstr(sv['values'])}{'%' if sv['percent'] else ''}"
        mods = []
        if "values_scepter" in sv:
            mods.append(f"Аганим {vstr(sv['values_scepter'])}")
        if "values_shard" in sv:
            mods.append(f"шард {vstr(sv['values_shard'])}")
        for t in sv.get("talents", []):
            if "values_with" in t:
                mods.append(f"талант {t['level']} {vstr(t['values_with'])}")
            else:
                mods.append(f"талант {t['level']} {t['op']} {fnum(t['value'])}")
        if mods:
            line += " (" + "; ".join(mods) + ")"
        lines.append(line)
    return lines


def _ability_block(i: int, a: dict, full: bool) -> list[str]:
    names = a["name_ru"] if a["name_ru"] == a["name_en"] else f"{a['name_ru']} / {a['name_en']}"
    head = f"{i}. {names} [{a['key']}]"
    if a["innate"]:
        head += " [врождённая]"
    head += " — " + ", ".join(_ability_tags(a))
    nums = []
    if a["cooldown"]:
        nums.append(f"КД {_cd(a['cooldown'])}")
    if a["mana_cost"]:
        nums.append(f"мана {_cd(a['mana_cost'])}")
    if a["cast_range"]:
        nums.append(f"дальность {_cd(a['cast_range'])}")
    if a["cast_point"]:
        nums.append(f"каст-поинт {_cd(a['cast_point'])}")
    if a["channel_time"]:
        nums.append(f"канал {_cd(a['channel_time'])}")
    lines = [head + (". " + "; ".join(nums) if nums else "")]
    if not full:
        return lines
    if a["desc_ru"]:
        lines.append("   " + a["desc_ru"].replace("\n", " "))
    vals = _special_lines(a)
    if vals:
        lines.append("   Значения: " + "; ".join(vals))
    for note in a["notes_ru"]:
        lines.append("   Примечание: " + note.replace("\n", " "))
    for key, label in (("scepter", "Аганим"), ("shard", "Шард")):
        block = a[key]
        if block and block["text_ru"]:
            lines.append(f"   {label}: " + block["text_ru"].replace("\n", " "))
    return lines


def _stats_line(label: str, s: dict) -> str:
    return (f"{label}: сила {fnum(s['str'])}, ловкость {fnum(s['agi'])}, интеллект {fnum(s['int'])}; "
            f"HP {fnum(s['health'])} (+{fnum(s['health_regen'])}/с), мана {fnum(s['mana'])} (+{fnum(s['mana_regen'])}/с); "
            f"броня {fnum(s['armor'])} (физ. -{fnum(s['phys_reduction_pct'])}%); "
            f"урон {fnum(s['damage_min'])}-{fnum(s['damage_max'])} (ср. {fnum(s['damage_avg'])}); "
            f"скорость атаки {fnum(s['attack_speed'])} ({fnum(s['attacks_per_second'])} атак/с, БАТ {fnum(s['bat'])})")


def hero_card(h: dict, level: int | None, full: bool, patch: str) -> str:
    b = h["base"]
    roles = ", ".join(f"{ROLE_RU[r]} {lv}" for r, lv in h["roles"].items())
    names = h["name_ru"] if h["name_ru"] == h["name_en"] else f"{h['name_ru']} / {h['name_en']}"
    lines = [
        f"{names} [{h['key']}] — патч {patch}; основной атрибут: {ATTR_RU[h['primary_attr']]}, "
        f"{'ближний' if h['attack_type'] == 'melee' else 'дальний'} бой, сложность {h['complexity']}/3. Роли: {roles}.",
        f"Прирост за уровень: сила +{fnum(b['str_gain'])}, ловкость +{fnum(b['agi_gain'])}, "
        f"интеллект +{fnum(b['int_gain'])}.",
    ]
    if level is None:
        lines.append(_stats_line("Ур.1 (без предметов)", h["level1"]))
        lines.append(_stats_line("Ур.25 (без предметов и талантов)", h["level25"]))
    else:
        stats = derive_stats(b, h["primary_attr"], level)
        lines.append(_stats_line(f"Ур.{level} (без предметов и талантов)", stats))
    lines.append(f"Дальность атаки {fnum(b['attack_range'])}"
                 + (f", скорость снаряда {fnum(b['projectile_speed'])}" if h["attack_type"] == "ranged" else "")
                 + f"; скорость {fnum(b['move_speed'])}, поворот {fnum(b['turn_rate'])}, "
                   f"обзор {fnum(b['sight_day'])}/{fnum(b['sight_night'])}, сопр. магии {fnum(b['magic_resist'])}%.")
    lines.append("Способности:")
    for i, a in enumerate(h["abilities"], 1):
        lines.extend(_ability_block(i, a, full))
    lines.append("Таланты:")
    for tier in h["talents"]:
        lines.append(f"  {tier['level']}: " + " | ".join(o["text_ru"] for o in tier["options"]))
    return "\n".join(lines)


def item_card(it: dict, kb: "KB", full: bool) -> str:
    names = kb.index["items"]

    def label(k: str) -> str:
        row = names.get(k)
        return f"{row['ru']} ({row['cost']})" if row else k

    title = it["name_ru"] if it["name_ru"] == it["name_en"] else f"{it['name_ru']} / {it['name_en']}"
    head = f"{title} [{it['key']}] — {it['cost']} зол., {STATUS_RU[it['shop']['status']]}"
    if it["shop"]["status"] == "removed" and it["shop"].get("removed_in"):
        head += f" ({it['shop']['removed_in']})"
    if it["neutral_tier"]:
        head += f", нейтральный тир {it['neutral_tier']}"
    lines = [head + "."]
    if it["is_recipe"]:
        lines.append(f"Рецепт для: {it['recipe_of']}.")
    elif it["components"]:
        parts = " + ".join(label(c) for c in it["components"])
        if it["recipe_cost"]:
            parts += f" + рецепт ({it['recipe_cost']})"
        lines.append(f"Сборка: {parts}.")
        for variant in it["component_variants"][1:]:
            lines.append("Вариант: " + " + ".join(label(c) for c in variant) + ".")
        shop = it["shopping_list"]
        if shop and any(c["key"] != x for c, x in zip(shop["parts"], it["components"])):
            lines.append("Из базовых частей: " + ", ".join(f"{label(p['key'])}×{p['count']}" if p["count"] > 1
                                                           else label(p["key"]) for p in shop["parts"])
                         + (f"; рецепты: {', '.join(str(r['cost']) for r in shop['recipes'])}" if shop["recipes"] else "")
                         + ".")
    if it["builds_into"]:
        lines.append("Входит в: " + ", ".join(label(k) for k in it["builds_into"]) + ".")
    if it["bonuses"]:
        lines.append("Бонусы: " + "; ".join(b["text_ru"] for b in it["bonuses"]) + ".")
    nums = []
    if it["cooldown"]:
        nums.append(f"КД {_cd(it['cooldown'])}")
    if it["mana_cost"]:
        nums.append(f"мана {_cd(it['mana_cost'])}")
    if it["cast_range"]:
        nums.append(f"дальность {_cd(it['cast_range'])}")
    if it["channel_time"]:
        nums.append(f"канал {_cd(it['channel_time'])}")
    tags = [t for t in _ability_tags(it) if t not in ("активная", "пассивная")]
    if nums:
        lines.append(", ".join(nums) + (" (" + ", ".join(tags) + ")" if tags else "") + ".")
    else:
        key_tags = [t for t in tags if "БКБ" in t or "рассеивается" in t]
        if key_tags:
            lines.append("Эффекты предмета: " + ", ".join(key_tags) + ".")
    if not full:
        return "\n".join(lines)
    for sec in it["sections_ru"]:
        title = f"{sec['title']}: " if sec["title"] else ""
        lines.append(f"{title}{sec['text']}".replace("\n", " "))
    values = [f"{v['heading_ru']}: {vstr(v['values'])}{'%' if v['percent'] else ''}" for v in it["values"]]
    if values:
        lines.append("Значения: " + "; ".join(values) + ".")
    for note in it["notes_ru"]:
        lines.append("Примечание: " + note.replace("\n", " "))
    return "\n".join(lines)


_default: KB | None = None


def default() -> KB:
    global _default
    if _default is None:
        _default = KB()
    return _default
