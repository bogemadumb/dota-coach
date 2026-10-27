"""Compare data/kb (official datafeed) with the dotaconstants cache and write data/kb/diff_vs_dotaconstants.md."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach.config import ROOT  # noqa: E402
from dota_coach.kb import KB, fnum, vstr  # noqa: E402

DC = ROOT / "data" / "cache" / "dotaconstants"
OUT = ROOT / "data" / "kb" / "diff_vs_dotaconstants.md"
NUM = re.compile(r"-?(?:\d+\.\d+|\d+|\.\d+)")


def nums(value) -> list[float]:
    if value is None or value is False:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        out: list[float] = []
        for v in value:
            out += nums(v)
        return out
    return [float(x) for x in NUM.findall(str(value))]


def collapse(values: list[float]) -> list[float]:
    vals = [round(v, 4) for v in values]
    return vals[:1] if vals and len(set(vals)) == 1 else vals


def same(a: list[float], b: list[float]) -> bool:
    a, b = collapse(a), collapse(b)
    if len(a) == 1 and len(b) > 1:
        b = b[:1]
    return len(a) == len(b) and all(abs(x - y) < 1e-3 for x, y in zip(a, b))


def rel(old: list[float], new: list[float]) -> float:
    if not old or not new:
        return 1.0
    o, n = collapse(old), collapse(new)
    if len(o) == 1 and len(n) > 1:
        n = n[:1]
    if len(o) != len(n):
        return 1.0
    return max(abs(y - x) / max(abs(x), 1.0) for x, y in zip(o, n))


def show(values: list[float]) -> str:
    return vstr(values) if values else "-"


def main() -> int:
    kb = KB()
    dc_items = json.loads((DC / "items.json").read_text(encoding="utf-8"))
    dc_heroes = json.loads((DC / "heroes.json").read_text(encoding="utf-8"))
    dc_abilities = json.loads((DC / "abilities.json").read_text(encoding="utf-8"))
    dc_hero_abilities = json.loads((DC / "hero_abilities.json").read_text(encoding="utf-8"))
    dc_patch = json.loads((DC / "patch.json").read_text(encoding="utf-8"))[-1]

    rows: list[tuple[float, str, str]] = []
    seen = {"items": 0, "item_values": 0, "hero_params": 0, "abilities": 0, "ability_values": 0}
    item_cost, item_comp, item_cd, item_attr = [], [], [], []
    only_kb_items, only_dc_items = [], []

    for key in kb.items():
        it = kb.item(key)
        if it["neutral_tier"] or it["enhancement"] or it["shop"]["status"] in ("special",):
            continue
        d = dc_items.get(key)
        if d is None:
            only_kb_items.append(key)
            continue
        seen["items"] += 1
        if int(d.get("cost") or 0) != it["cost"] and not (it["shop"]["status"] == "removed"):
            old, new = d.get("cost") or 0, it["cost"]
            item_cost.append((key, old, new))
            rows.append((abs(new - old) / max(old, 100), f"предмет {key}", f"цена {old} -> {new}"))
        dc_comp = [c for c in (d.get("components") or []) if c]
        if sorted(dc_comp) != sorted(it["components"]) and not it["is_recipe"]:
            item_comp.append((key, dc_comp, it["components"]))
        for label, old, new in (("КД", nums(d.get("cd")), it["cooldown"]), ("мана", nums(d.get("mc")), it["mana_cost"])):
            if old and new and not same(old, new):
                item_cd.append((key, label, old, new))
                rows.append((rel(old, new), f"предмет {key}", f"{label} {show(old)} -> {show(new)}"))
        dc_attr = {a["key"].lower(): nums(a.get("value")) for a in d.get("attrib") or []}
        for sv in it["specials"]:
            old = dc_attr.get(sv["key"].lower())
            if sv["system"] or old is None or not sv["values"] or not old:
                continue
            seen["item_values"] += 1
            if not same(old, sv["values"]):
                item_attr.append((key, sv["key"], old, sv["values"]))
                rows.append((rel(old, sv["values"]), f"предмет {key}", f"{sv['key']} {show(old)} -> {show(sv['values'])}"))
    for key, d in dc_items.items():
        if key not in kb.index["items"] and d.get("cost") and not d.get("tier"):
            only_dc_items.append(key)

    hero_base, abil_cd, abil_val, abil_new, abil_gone, talent_diff = [], [], [], [], [], []
    for key in kb.heroes():
        h = kb.hero(key)
        d = dc_heroes[str(h["id"])]
        b, primary = h["base"], h["primary_attr"]
        prim_add = b[primary] if primary in ("str", "agi", "int") else 0
        pairs = [
            ("сила", d["base_str"], b["str"]), ("ловкость", d["base_agi"], b["agi"]), ("интеллект", d["base_int"], b["int"]),
            ("прирост силы", d["str_gain"], b["str_gain"]), ("прирост ловкости", d["agi_gain"], b["agi_gain"]),
            ("прирост интеллекта", d["int_gain"], b["int_gain"]),
            ("броня", d["base_armor"] + d["base_agi"] / 6, b["armor"]),
            ("урон мин", d["base_attack_min"] + prim_add, b["damage_min"]),
            ("урон макс", d["base_attack_max"] + prim_add, b["damage_max"]),
            ("скорость", d["move_speed"], b["move_speed"]), ("дальность атаки", d["attack_range"], b["attack_range"]),
            ("БАТ", d["attack_rate"], b["bat"]), ("скорость снаряда", d.get("projectile_speed") or 0, b["projectile_speed"]),
            ("поворот", d["turn_rate"] if d.get("turn_rate") is not None else b["turn_rate"], b["turn_rate"]),
            ("сопр. магии", d["base_mr"], b["magic_resist"]),
        ]
        for label, old, new in pairs:
            seen["hero_params"] += 1
            if abs(float(old) - float(new)) > 1e-2:
                hero_base.append((key, label, old, new))
                rows.append((abs(new - old) / max(abs(old), 1.0), f"герой {key}", f"{label} {fnum(old)} -> {fnum(new)}"))

        dc_list = dc_hero_abilities.get(f"npc_dota_hero_{key}", {})
        dc_keys = [a for a in dc_list.get("abilities", []) if dc_abilities.get(a, {}).get("dname")]
        kb_keys = [a["key"] for a in h["abilities"]]
        for a in kb_keys:
            if a not in dc_keys and not any(a.startswith(k.rstrip("0123456789")) for k in dc_keys):
                abil_new.append((key, a))
        for a in dc_keys:
            if a not in kb_keys and not any(k.startswith(a.rstrip("0123456789")) for k in kb_keys):
                abil_gone.append((key, a))
        dc_talents = {t["name"] for t in dc_list.get("talents", [])}
        kb_talents = {o["key"] for t in h["talents"] for o in t["options"]}
        if dc_talents != kb_talents:
            talent_diff.append((key, sorted(kb_talents - dc_talents), sorted(dc_talents - kb_talents)))

        for a in h["abilities"]:
            d_ab = dc_abilities.get(a["key"])
            if not d_ab:
                continue
            seen["abilities"] += 1
            for label, old, new in (("КД", nums(d_ab.get("cd")), a["cooldown"]), ("мана", nums(d_ab.get("mc")), a["mana_cost"])):
                if old and new and not same(old, new):
                    abil_cd.append((key, a["key"], label, old, new))
                    rows.append((rel(old, new), f"способность {a['key']}", f"{label} {show(old)} -> {show(new)}"))
            dc_attr = {x["key"].lower(): nums(x.get("value")) for x in d_ab.get("attrib") or []}
            for sv in a["specials"]:
                old = dc_attr.get(sv["key"].lower())
                if sv["system"] or not old or not sv["values"]:
                    continue
                seen["ability_values"] += 1
                if not same(old, sv["values"]):
                    abil_val.append((key, a["key"], sv["key"], sv["heading_en"] or "", old, sv["values"]))
                    rows.append((rel(old, sv["values"]), f"способность {a['key']}",
                                 f"{sv['key']} {show(old)} -> {show(sv['values'])}"))

    rows.sort(key=lambda r: -r[0])
    fresh = []
    notes_path = ROOT / "data" / "cache" / "official" / "english" / "patchnotes" / "7.41f.json"
    if notes_path.exists():
        ids = json.loads((DC / "item_ids.json").read_text(encoding="utf-8"))
        for entry in json.loads(notes_path.read_text(encoding="utf-8")).get("items", []):
            text = " ".join(n["note"] for n in entry.get("ability_notes", []))
            key = ids.get(str(entry.get("ability_id")))
            if key and "cost" in text.lower() and key in dc_items and key in kb.index["items"]:
                fresh.append((key, dc_items[key].get("cost"), kb.item(key)["cost"], text[:120]))
    lines = [
        "# Расхождения официального datafeed и dotaconstants",
        "",
        f"Официальный слой: патч {kb.index['patch']} (datafeed от {kb.index['fetched'][:10]}). "
        f"dotaconstants: последний патч в patch.json — {dc_patch['name']} ({dc_patch['date'][:10]}).",
        "Слева старое значение dotaconstants, справа официальное. «Относительное изменение» = |новое - старое| / max(старое, 1).",
        "",
        "## Сводка",
        "",
        f"- предметы: цена отличается у {len(item_cost)}, состав (компоненты) у {len(item_comp)}, КД/мана у {len(item_cd)}, "
        f"числовые значения у {len(item_attr)}; только в официальном слое {len(only_kb_items)}, только в dotaconstants {len(only_dc_items)}",
        f"- герои: расхождений базовых характеристик {len(hero_base)} (у {len({r[0] for r in hero_base})} героев из {len(kb.heroes())})",
        f"- способности: КД/мана {len(abil_cd)}, значения {len(abil_val)}, новых способностей {len(abil_new)}, исчезнувших {len(abil_gone)}; "
        f"наборы талантов отличаются у {len(talent_diff)} героев",
        "",
        f"Сколько сравнено: предметов {seen['items']}, числовых значений предметов {seen['item_values']}, "
        f"параметров героев {seen['hero_params']}, способностей {seen['abilities']}, числовых значений способностей {seen['ability_values']}.",
        "",
        "## Вывод о свежести",
        "",
        "Кэш dotaconstants уже соответствует патчу 7.41f (хотя patch.json заканчивается на 7.41). Проверка по заметкам 7.41f "
        "(предметы с изменением цены):",
        "",
        "| предмет | цена в dotaconstants | цена официально | заметка 7.41f |",
        "|---|---|---|---|",
        *[f"| {k} | {a} | {b} | {t} |" for k, a, b, t in fresh],
        "",
        "## Топ-20 расхождений по относительному изменению",
        "",
        "| # | что | расхождение | относит. изменение |",
        "|---|---|---|---|",
    ]
    for i, (score, what, text) in enumerate(rows[:20], 1):
        lines.append(f"| {i} | {what} | {text} | {score:.0%} |")

    lines += ["", "## Предметы: цена", "", "| предмет | dotaconstants | официально |", "|---|---|---|"]
    for key, old, new in sorted(item_cost, key=lambda r: -abs(r[2] - r[1])):
        lines.append(f"| {key} | {old} | {new} |")
    lines += ["", "## Предметы: состав", "", "| предмет | dotaconstants | официально |", "|---|---|---|"]
    for key, old, new in item_comp:
        lines.append(f"| {key} | {', '.join(old) or '-'} | {', '.join(new) or '-'} |")
    lines += ["", "## Предметы: КД и мана", "", "| предмет | параметр | dotaconstants | официально |", "|---|---|---|---|"]
    for key, label, old, new in item_cd:
        lines.append(f"| {key} | {label} | {show(old)} | {show(new)} |")
    lines += ["", "## Предметы: числовые значения", "", "| предмет | значение | dotaconstants | официально |", "|---|---|---|---|"]
    for key, sv, old, new in sorted(item_attr, key=lambda r: -rel(r[2], r[3])):
        lines.append(f"| {key} | {sv} | {show(old)} | {show(new)} |")
    lines += ["", "## Предметы: есть только с одной стороны", "",
              f"Только в официальном слое (продаются или рецепты, не нейтральные): {', '.join(sorted(only_kb_items)) or '-'}", "",
              f"Только в dotaconstants (не нейтральные, с ценой): {', '.join(sorted(only_dc_items)) or '-'}"]
    lines += ["", "## Герои: базовые характеристики", "", "| герой | параметр | dotaconstants | официально |", "|---|---|---|---|"]
    for key, label, old, new in hero_base:
        lines.append(f"| {key} | {label} | {fnum(old)} | {fnum(new)} |")
    lines += ["", "## Способности: КД и мана", "", "| герой | способность | параметр | dotaconstants | официально |",
              "|---|---|---|---|---|"]
    for hero, ab, label, old, new in sorted(abil_cd, key=lambda r: -rel(r[3], r[4])):
        lines.append(f"| {hero} | {ab} | {label} | {show(old)} | {show(new)} |")
    lines += ["", "## Способности: значения", "", "| герой | способность | значение | dotaconstants | официально |",
              "|---|---|---|---|---|"]
    for hero, ab, sv, head, old, new in sorted(abil_val, key=lambda r: -rel(r[4], r[5])):
        lines.append(f"| {hero} | {ab} | {sv} | {show(old)} | {show(new)} |")
    lines += ["", "## Способности: новые и исчезнувшие", "",
              "Новые в официальном слое: " + (", ".join(f"{h}:{a}" for h, a in abil_new) or "-"), "",
              "Исчезли (есть в dotaconstants, нет в официальном): " + (", ".join(f"{h}:{a}" for h, a in abil_gone) or "-")]
    lines += ["", "## Таланты: наборы отличаются", "", "| герой | новые таланты | исчезнувшие таланты |", "|---|---|---|"]
    for hero, new, gone in talent_diff:
        lines.append(f"| {hero} | {', '.join(new) or '-'} | {', '.join(gone) or '-'} |")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {OUT} ({OUT.stat().st_size} bytes)")
    print("\n".join(lines[8:34]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
