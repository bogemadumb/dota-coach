"""Build hero cards: data/kb/cards/<hero>.md (full) and <hero>.short.md from KB layers 1-3 + counters + item rules."""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach import kb as kbmod  # noqa: E402
from dota_coach.config import ROOT  # noqa: E402
from dota_coach.kb_context import estimate_tokens  # noqa: E402
from dota_coach.match_picture import TAG_RU  # noqa: E402

KB_DIR = ROOT / "data" / "kb"
OUT_DIR = KB_DIR / "cards"
D2PT_MIN = 100
STRATZ_MIN = 300
MAX_POSITIONS = 2
RARE_CUTOFF = 0.02
SHORT_BUDGET = 250
POS_RU = {1: "керри (1)", 2: "мид (2)", 3: "оффлейн (3)", 4: "саппорт (4)", 5: "саппорт (5)"}
BRACKET_RU = {"high": "Divine–Immortal", "low": "Herald–Guardian"}
ATTR_NAMES = {"str": "сила", "agi": "ловкость", "int": "интеллект"}
BEHAVIOR_TARGET = (("unit_target", "на цель"), ("point", "в точку"), ("no_target", "без цели"))
DISPEL_SHORT = {"basic": "диспел обычный", "strong": "диспел только сильный", "no": "не диспеллится"}
DAMAGE_SHORT = {"physical": "физ. урон", "magical": "маг. урон", "pure": "чистый урон"}
SURVIVOR_NOTE = ("Δ = винрейт предмета минус средний винрейт позиции, п.п. Поздние предметы выглядят лучше просто потому, "
                 "что игра до них дошла (долгая игра): сравнивай предметы с похожим временем покупки.")


PLACEHOLDER_NOTE = "Примечание: «[?]» в тексте — число, которое официальные данные не раскрыли; не называй его, скажи «не уверен»."


class Ctx:
    def __init__(self) -> None:
        self.kb = kbmod.default()
        self.items = self.kb.index["items"]
        self.heroes = self.kb.index["heroes"]
        counters = yaml.safe_load((ROOT / "data" / "counters.yaml").read_text(encoding="utf-8"))
        self.counter_tags = counters["tags"]
        self.rules = counters["rules"]
        self.hero_tags = {k: v.get("tags") or [] for k, v in
                          yaml.safe_load((ROOT / "data" / "hero_tags.yaml").read_text(encoding="utf-8"))["heroes"].items()}
        self.item_rules = yaml.safe_load((KB_DIR / "item_rules.yaml").read_text(encoding="utf-8"))
        self.item_tags: dict[str, list[str]] = {}
        for rule in self.rules:
            for item in rule["items"]:
                tags = self.item_tags.setdefault(item, [])
                if rule["tag"] not in tags:
                    tags.append(rule["tag"])
        self.counter_items = set(self.item_tags) | {i for entry in counters_enemy(counters) for i in entry}

    def item_name(self, key: str) -> str:
        row = self.items.get(key)
        return row["ru"] if row else key.replace("_", " ").title()

    def hero_name(self, key: str) -> str:
        row = self.heroes.get(key)
        return row["ru"] if row else key


def counters_enemy(counters: dict):
    return [v.get("items") or [] for v in (counters.get("enemy_items") or {}).values()]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def delta(item_wr: float, pos_wr: float) -> str:
    d = (item_wr - pos_wr) * 100
    return f"Δ{d:+.1f}".replace("-", "−")


def fnum(x) -> str:
    return kbmod.fnum(x)


def minute(t: float) -> str:
    return "в старте" if t < 1 else f"{t:.0f} мин"


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def sentence(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    cut = text.find(". ")
    if cut != -1:
        text = text[: cut + 1]
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def d2pt_positions(builds: dict | None) -> dict[int, dict]:
    if not builds:
        return {}
    src = (builds.get("sources") or {}).get("d2pt") or {}
    return {int(p): v for p, v in (src.get("positions") or {}).items() if v.get("matches", 0) >= D2PT_MIN}


def stratz_blocks(stratz: dict | None) -> dict[str, dict[int, dict]]:
    out = {"high": {}, "low": {}, "mid": {}}
    if not stratz:
        return out
    for bracket, data in (stratz.get("brackets") or {}).items():
        for p, v in (data.get("positions") or {}).items():
            out[bracket][int(p)] = v
    return out


def select_positions(d2: dict, st: dict) -> list[int]:
    qualified = set(d2)
    for bracket in ("high", "low"):
        qualified |= {p for p, v in st[bracket].items() if v["matches"] >= STRATZ_MIN}
    if d2:
        total = sum(v["matches"] for v in d2.values())
        share = {p: (d2[p]["matches"] / total if p in d2 else 0.0) for p in qualified}
    else:
        pool = st["high"] or st["low"]
        share = {p: pool[p].get("pos_share", 0.0) if p in pool else 0.0 for p in qualified}
    return sorted(qualified, key=lambda p: -share[p])


def header(ctx: Ctx, h: dict, positions: list[int]) -> list[str]:
    b = h["base"]
    roles = ", ".join(f"{kbmod.ROLE_RU[r]} {lv}" for r, lv in h["roles"].items())
    melee = h["attack_type"] == "melee"
    prim = h["primary_attr"]
    l1, l25 = h["level1"], h["level25"]
    lines = [
        f"# {h['name_ru']} [{h['key']}]",
        f"{roles} (роль 1–3). Основной атрибут: {kbmod.ATTR_RU[prim].lower()}. "
        f"{'Ближний' if melee else 'Дальний'} бой, дальность {fnum(b['attack_range'])}"
        + ("" if melee else f", снаряд {fnum(b['projectile_speed'])}")
        + f"; скорость {fnum(b['move_speed'])}, БАТ {fnum(b['bat'])}, сопр. магии {fnum(b['magic_resist'])}%.",
        f"Ур.1: сила {fnum(l1['str'])}, ловк. {fnum(l1['agi'])}, инт. {fnum(l1['int'])}; HP {fnum(round(l1['health']))}, мана {fnum(round(l1['mana']))}, "
        f"броня {fnum(l1['armor'])}, урон {fnum(l1['damage_min'])}–{fnum(l1['damage_max'])}, скорость атаки {fnum(l1['attack_speed'])}. "
        f"Ур.25 (без предметов): сила {fnum(l25['str'])}, ловк. {fnum(l25['agi'])}, инт. {fnum(l25['int'])}; HP {fnum(round(l25['health']))}, "
        f"мана {fnum(round(l25['mana']))}, броня {fnum(l25['armor'])}, урон {fnum(round(l25['damage_min']))}–{fnum(round(l25['damage_max']))}, "
        f"скорость атаки {fnum(round(l25['attack_speed']))}.",
    ]
    gains = {a: b[f"{a}_gain"] for a in ("str", "agi", "int")}
    per_point = {"str": "+22 HP, +0.1 реген HP", "agi": "+1 скор. атаки, +0.167 брони", "int": "+12 маны, +0.05 реген маны, +0.1% сопр. магии"}
    names = {"str": "сила", "agi": "ловкость", "int": "интеллект"}
    parts = []
    for a in ("str", "agi", "int"):
        text = f"{names[a]}"
        if a == prim:
            text += " (основной) +1 урона, "
        else:
            text += " "
        text += f"{per_point[a]} ({fnum(gains[a])}/ур."
        if a == prim:
            text += f" = +{fnum(gains[a])} урона/ур."
        parts.append(text + ")")
    if prim == "all":
        total = sum(gains.values())
        lines.append(f"Универсал: каждое очко КАЖДОГО атрибута даёт +0.45 урона; прирост {fnum(round(total, 2))} очка/ур. = +{fnum(round(total * 0.45, 2))} урона/ур. "
                     f"За очко: " + "; ".join(f"{names[a]} {per_point[a]} ({fnum(gains[a])}/ур.)" for a in ("str", "agi", "int")) + ".")
    else:
        lines.append("За очко атрибута (прирост за уровень): " + "; ".join(parts) + ". Остальные атрибуты урона не дают.")
    return lines


def ability_line(i: int, a: dict, compact: bool = False) -> list[str]:
    if "not_learnable" in a["behavior"] and not a["innate"] and not a["desc_ru"]:
        return []
    beh = set(a["behavior"])
    tags = []
    if a["innate"]:
        tags.append("врождённая")
    if a["kind"] == "ultimate":
        tags.append("ульт")
    if a["granted_by_scepter"]:
        tags.append("даёт Аганим")
    if a["granted_by_shard"]:
        tags.append("даёт шард")
    tags.append("пассив" if "passive" in beh else "актив")
    for flag, ru in (("channelled", "канал"), ("toggle", "переключатель"), ("autocast", "автокаст")):
        if flag in beh:
            tags.append(ru)
    for flag, ru in BEHAVIOR_TARGET:
        if flag in beh:
            tags.append(ru)
            break
    if "aoe" in beh:
        tags.append("по области")
    if a["damage_type"]:
        tags.append(DAMAGE_SHORT[a["damage_type"]])
    if a["bkb_pierce"] is True:
        tags.append("ПРОБИВАЕТ БКБ")
    elif a["bkb_pierce"] is False:
        tags.append("НЕ пробивает БКБ")
    if a["dispellable"] in DISPEL_SHORT:
        tags.append(DISPEL_SHORT[a["dispellable"]])
    nums = []
    if a["cooldown"]:
        nums.append(f"КД {kbmod.vstr(a['cooldown'])}")
    if a["channel_time"]:
        nums.append(f"канал {kbmod.vstr(a['channel_time'])}")
    taken = 0
    for sv in a["specials"]:
        if sv["system"] or not sv["heading_ru"] or not sv["values"] or taken >= (4 if compact else 99) or "текущий" in sv["heading_ru"].lower():
            continue
        head = sv["heading_ru"].rstrip(":").lower()
        if head in ("перезарядка", "расход маны") or not any(sv["values"]):
            continue
        nums.append(f"{head} {kbmod.vstr(sv['values'])}{'%' if sv['percent'] else ''}")
        taken += 1
    line = f"{i}. {a['name_ru']} — " + ", ".join(tags) + ("; " + "; ".join(nums) if nums else "") + "."
    extra = []
    for key, label in (("scepter", "Аганим"), ("shard", "Шард")):
        block = a[key]
        if not block:
            continue
        if block.get("text_ru"):
            extra.append(f"{label}: {clip(' '.join(block['text_ru'].split()), 80 if compact else 170)}")
        elif block.get("changes"):
            parts = [f"{c.get('heading_ru') or c['key']} {kbmod.vstr(c['from'])}→{kbmod.vstr(c['to'])}".replace(":", "")
                     for c in block["changes"][:3]]
            extra.append(f"{label}: " + "; ".join(parts))
    return [line + (" " + " ".join(extra) if extra else "")]


def abilities_block(h: dict) -> list[str]:
    lines = ["Способности (БКБ и диспел — официальные данные; «НЕ пробивает БКБ»: в иммунитете к дебаффам не действует):"]
    n = 0
    for a in h["abilities"]:
        out = ability_line(n + 1, a, compact=len(h['abilities']) > 8)
        if out:
            n += 1
            lines.extend(out)
    return lines


def talent_picks(d2: dict) -> dict[str, tuple[int, str]]:
    """talent key -> (pick share inside its tier, tier), pooled over positions."""
    counts: dict[str, int] = {}
    for v in d2.values():
        for tier in v.get("talents") or []:
            for side in ("left", "right"):
                node = tier.get(side) or {}
                if node.get("name"):
                    counts[node["name"]] = counts.get(node["name"], 0) + node.get("count", 0)
    return counts


def talents_block(h: dict, d2: dict, builds: dict | None) -> list[str]:
    lines = ["Таланты (в скобках выбор на 7000+, D2PT):"]
    counts = talent_picks(d2)
    for tier in h["talents"]:
        opts = tier["options"]
        total = sum(counts.get(o["key"], 0) for o in opts)
        texts = []
        for o in opts:
            share = counts.get(o["key"], 0) / total if total else None
            texts.append(f"{o['text_ru']}" + (f" ({share * 100:.0f}%)" if share is not None else ""))
        lines.append(f"- ур.{tier['level']}: " + " | ".join(texts))
    if not counts:
        lines.append("(статистика выбора талантов на высоком MMR недоступна)")
    return lines


def gather_items(block: dict) -> dict[str, dict]:
    """STRATZ core+boots -> item -> {rate, time, wr}."""
    out = {}
    total = block["matches"]
    for e in block.get("core") or []:
        out[e["item"]] = {"rate": e["buy_rate"], "time": e["avg_time_min"], "wr": e["winrate"], "n": e["matches"]}
    for e in block.get("boots") or []:
        out.setdefault(e["item"], {"rate": e["matches"] / total if total else 0, "time": e["avg_time_min"],
                                   "wr": e["winrate"], "n": e["matches"]})
    return out


def counter_hint(ctx: Ctx, item: str) -> str:
    tags = ctx.item_tags.get(item) or []
    if not tags:
        return ""
    return " — против: " + ", ".join(TAG_RU.get(t, t) for t in tags[:2])


def starting_text(ctx: Ctx, d2p: dict | None, stz: dict | None, first: bool = True) -> str:
    if d2p and d2p.get("starting"):
        sets = []
        for s in d2p["starting"][:(2 if first else 1)]:
            names = ", ".join(ctx.item_name(i) for i in s["items"])
            sets.append(f"{names} ({s['count']} игр, {pct(s['winrate'], 0)})")
        return "Старт (D2PT): " + " | ".join(sets) + "."
    if stz and stz.get("starting"):
        names = ", ".join(f"{ctx.item_name(e['item'])} ({pct(e['matches'] / stz['matches'], 0)})" for e in stz["starting"][: (5 if first else 3)])
        return "Старт (STRATZ high, доля игр): " + names + "."
    return ""


def ability_labels(h: dict) -> dict[str, str]:
    """First word of the name when it is unique among the hero's abilities, otherwise the full name."""
    firsts = [a["name_ru"].split()[0] for a in h["abilities"]]
    return {a["key"]: (a["name_ru"].split()[0] if firsts.count(a["name_ru"].split()[0]) == 1 else a["name_ru"]) for a in h["abilities"]}


def skill_text(ctx: Ctx, h: dict, d2p: dict | None) -> str:
    if not d2p or not d2p.get("skill_build"):
        return ""
    labels = ability_labels(h)
    top = d2p["skill_build"][0]
    order = ", ".join(f"{n} {labels.get(k) or ('талант' if k.startswith('special_bonus') else k)}" for n, k in enumerate(top["order"], 1))
    return (f"Прокачка по уровням (самая частая, {pct(top['pick_rate'], 0)} игр, винрейт {pct(top['winrate'], 0)}): {order}.")


def list_cap(block: dict) -> float:
    """Upper bound of the buy rate of an item missing from the STRATZ top-25 list."""
    core = block.get("core") or []
    return core[-1]["buy_rate"] if len(core) >= 25 else 0.01


def level_diff(ctx: Ctx, high: dict | None, low: dict | None, top: int = 3) -> list[str]:
    if not low:
        return []
    lines = []
    head = (f"На твоём уровне ({BRACKET_RU['low']}, STRATZ): {low['matches']} игр, винрейт {pct(low['winrate'])}"
            + (f" (на {BRACKET_RU['high']}: {pct(high['winrate'])})" if high else "") + ".")
    low_items = gather_items(low)
    if not high:
        top = sorted(low_items.items(), key=lambda kv: -kv[1]["rate"])[:6]
        lines.append(head + " Чаще всего покупают: " + ", ".join(
            f"{ctx.item_name(k)} ({pct(v['rate'], 0)}, {v['time']:.0f} мин, {delta(v['wr'], low['winrate'])})" for k, v in top) + ".")
        return lines
    high_items = gather_items(high)
    low_cap = list_cap(low)
    high_cap = list_cap(high)
    more, less, timing = [], [], []
    for key in set(low_items) | set(high_items):
        lo = low_items.get(key)
        hi = high_items.get(key)
        lo_rate, lo_cap = (lo["rate"], lo["rate"]) if lo else (0.0, low_cap)
        hi_rate, hi_cap = (hi["rate"], hi["rate"]) if hi else (0.0, high_cap)
        if lo_rate - hi_cap >= 0.10:
            more.append((lo_rate - hi_cap, key, lo, hi))
        if hi_rate - lo_cap >= 0.10:
            less.append((hi_rate - lo_cap, key, lo, hi))
        if lo and hi and lo["rate"] >= 0.30 and hi["rate"] >= 0.30 and abs(lo["time"] - hi["time"]) >= 2.0:
            timing.append((abs(lo["time"] - hi["time"]), key, lo, hi))
    more.sort(key=lambda x: -x[0])
    less.sort(key=lambda x: -x[0])
    timing.sort(key=lambda x: -x[0])
    bits = []
    timing = timing[: max(top - 1, 1)] if top > 1 else []
    if more:
        bits.append("покупают чаще: " + ", ".join(
            f"{ctx.item_name(k)} ({pct(lo['rate'], 0)} против {pct(hi['rate'], 0) if hi else '<' + pct(high_cap, 0)}, {delta(lo['wr'], low['winrate'])})"
            for _, k, lo, hi in more[:top]))
    if less:
        bits.append("покупают реже: " + ", ".join(
            f"{ctx.item_name(k)} ({pct(lo['rate'], 0) if lo else '<' + pct(low_cap, 0)} против {pct(hi['rate'], 0)})"
            for _, k, lo, hi in less[:top]))
    if timing:
        bits.append("покупают позже: " + ", ".join(
            f"{ctx.item_name(k)} {minute(lo['time'])} против {minute(hi['time'])}" for _, k, lo, hi in timing))
    bits = [b[0].upper() + b[1:] + "." for b in bits]
    lines.append(head + (" " + " ".join(bits) if bits else " Набор предметов почти совпадает с высоким уровнем."))
    return lines


def position_block(ctx: Ctx, h: dict, p: int, d2p: dict | None, st: dict, full: bool, first: bool) -> list[str]:
    high, low = st["high"].get(p), st["low"].get(p)
    src = []
    if d2p:
        src.append(f"D2PT 7000+: {d2p['matches']} игр, винрейт {pct(d2p['winrate'])}")
    if high:
        src.append(f"STRATZ {BRACKET_RU['high']}: {high['matches']}, {pct(high['winrate'])}")
    if low:
        src.append(f"STRATZ {BRACKET_RU['low']}: {low['matches']}, {pct(low['winrate'])}")
    lines = [f"## Позиция {POS_RU[p]}", "; ".join(src) + "."]
    if first:
        lines.append(SURVIVOR_NOTE)
    start = starting_text(ctx, d2p, high, first) if first else ""
    if start:
        lines.append(start)
    if d2p:
        wr = d2p["winrate"]
        core = sorted(d2p["core"], key=lambda e: e["avg_time_min"])[: (9 if full else 6)]
        lines.append("Основа (D2PT 7000+, по порядку покупки; минута, доля игр, Δ): " + ", ".join(
            f"{ctx.item_name(e['item'])} {minute(e['avg_time_min'])} ({pct(e['pick_rate'], 0)}, {delta(e['winrate'], wr)})" for e in core) + ".")
        situ = sorted(d2p["situational"], key=lambda e: -e["pick_rate"])[: (5 if full else 0)]
        if situ:
            lines.append("Ситуативные (D2PT 7000+; минута, доля игр, Δ): " + "; ".join(
            f"{ctx.item_name(e['item'])} {minute(e['avg_time_min'])} ({pct(e['pick_rate'], 0)}, {delta(e['winrate'], wr)})"
            + (counter_hint(ctx, e["item"]) if full else "") for e in situ) + ".")
    elif high:
        items = sorted(gather_items(high).items(), key=lambda kv: kv[1]["time"])
        lines.append("Основа (STRATZ Divine–Immortal, по порядку покупки; минута, доля игр, Δ): " + ", ".join(
            f"{ctx.item_name(k)} {minute(v['time'])} ({pct(v['rate'], 0)}, {delta(v['wr'], high['winrate'])})"
            for k, v in items if v["rate"] >= 0.25)[:(1000 if full else 560)].rsplit(", ", 1)[0] + ".")
        situ = [(k, v) for k, v in items if 0.08 <= v["rate"] < 0.25 and ctx.items.get(k, {}).get("cost", 0) >= 1000][: (5 if full else 3)]
        if situ:
            lines.append("Ситуативные (STRATZ Divine–Immortal): " + "; ".join(
                f"{ctx.item_name(k)} {minute(v['time'])} ({pct(v['rate'], 0)}, {delta(v['wr'], high['winrate'])})"
                + (counter_hint(ctx, k) if full else "") for k, v in situ) + ".")
    if full:
        sk = skill_text(ctx, h, d2p)
        if sk:
            lines.append(sk)
    lines.extend(level_diff(ctx, high, low, 3 if first else 1))
    return lines


def position_summary(p: int, d2p: dict | None, st: dict) -> str:
    bits = []
    if d2p:
        bits.append(f"D2PT {d2p['matches']} игр / {pct(d2p['winrate'])}")
    for bracket, label in (("high", "Divine–Immortal"), ("low", "Herald–Guardian")):
        block = st[bracket].get(p)
        if block:
            bits.append(f"{label} {block['matches']} / {pct(block['winrate'])}")
    return f"{POS_RU[p]}: " + ", ".join(bits)


def mismatch_lines(ctx: Ctx, h: dict, positions: list[int], d2: dict, st: dict) -> list[str]:
    rules = ctx.item_rules["items"]
    melee = h["attack_type"] == "melee"
    illusion_hero = h["key"] in ctx.item_rules["illusion_heroes"]
    candidates = []
    for item, r in rules.items():
        if r.get("removed") or item not in ctx.items:
            continue
        why = r.get("why") or {}
        reasons = []
        if h["key"] in (r.get("blocked_for_heroes") or []):
            reasons.append((0, why.get("blocked", "основной эффект у этого героя не работает")))
        if r.get("melee_only") and not melee:
            reasons.append((1, why.get("melee_only", "работает только в ближнем бою")))
        if r.get("ranged_only") and melee:
            reasons.append((1, why.get("ranged_only", "работает только у дальнего боя")))
        pen = r.get("ranged_penalty")
        if pen and not melee and pen["ranged"] < pen["melee"]:
            reasons.append((2, why.get("ranged_penalty", f"у дальнего боя слабее: {pen['ranged']} против {pen['melee']} ({pen['what']})")))
        if r.get("melee_penalty") and melee:
            reasons.append((2, why.get("melee_penalty", "бонус работает только у дальнего боя")))
        if illusion_hero and r.get("works_on_illusions") is False:
            reasons.append((3, why.get("illusions", "на иллюзии не копируется") + " (иллюзии героя — основа его силы)"))
        if reasons:
            candidates.append((min(k for k, _ in reasons), item not in ctx.counter_items, item, reasons[0][1]))
    out = []
    for _, _, item, reason in sorted(candidates):
        evidence = bought_evidence(item, positions, d2, st)
        if evidence is None:
            continue
        out.append(f"- {ctx.item_name(item)}: {reason}." + (f" {evidence}" if evidence else ""))
        if len(out) >= 4:
            break
    return out


def bought_evidence(item: str, positions: list[int], d2: dict, st: dict) -> str | None:
    """None if the item is bought by >= 2% anywhere in the data; otherwise a short statement of how rare it is."""
    exact = []
    for p in positions:
        d = d2.get(p)
        if d:
            for e in d["core"] + d["situational"]:
                if e["item"] == item:
                    return None
        high = st["high"].get(p)
        if high:
            for e in (high.get("core") or []) + (high.get("boots") or []):
                if e["item"] == item:
                    rate = e.get("buy_rate", e["matches"] / high["matches"] if high["matches"] else 0)
                    if rate >= RARE_CUTOFF:
                        return None
                    exact.append(rate)
    if not st["high"] and not d2:
        return None
    if exact:
        return f"На высоком MMR берут {pct(max(exact), 1)}."
    return ""


def matchup_lines(ctx: Ctx, stratz: dict | None) -> list[str]:
    if not stratz:
        return []
    lines = ["STRATZ, преимущество героя в п.п. (плюс — ему выгодно; в скобках игр):"]
    for bracket in ("high", "low"):
        vs = [r for r in (stratz.get("matchups") or {}).get(bracket, {}).get("vs", []) if r["matches"] >= 100]
        if not vs:
            continue
        vs.sort(key=lambda r: r["advantage"])
        def fmt(rows):
            return ", ".join(f"{ctx.hero_name(r['hero'])} {r['advantage']:+.1f} ({r['matches']})".replace("-", "−") for r in rows)
        lines.append(f"- {BRACKET_RU[bracket]}, тяжело против: {fmt(vs[:5])}.")
        lines.append(f"- {BRACKET_RU[bracket]}, легко против: {fmt(list(reversed(vs[-5:])))}.")
    with_ = [r for r in (stratz.get("matchups") or {}).get("high", {}).get("with", []) if r["matches"] >= 100]
    if with_:
        with_.sort(key=lambda r: -r["advantage"])
        lines.append(f"- {BRACKET_RU['high']}, хорошо в паре с: " + ", ".join(
            f"{ctx.hero_name(r['hero'])} {r['advantage']:+.1f} ({r['matches']})" for r in with_[:3]) + ".")
    return lines if len(lines) > 1 else []


def full_card(ctx: Ctx, key: str) -> str:
    h = ctx.kb.hero(key)
    builds = load_json(KB_DIR / "builds" / f"{key}.json")
    stratz = load_json(KB_DIR / "builds_stratz" / f"{key}.json")
    d2 = d2pt_positions(builds)
    st = stratz_blocks(stratz)
    positions = select_positions(d2, st)
    shown = positions[:MAX_POSITIONS]
    lines = header(ctx, h, shown)
    lines += abilities_block(h)
    lines += talents_block(h, d2, builds)
    if not shown:
        lines.append("Статистики сборок по позициям для этого героя нет.")
    for n, p in enumerate(shown):
        lines += position_block(ctx, h, p, d2.get(p), st, full=n == 0, first=n == 0)
    if len(positions) > len(shown):
        lines.append("Другие позиции (игры / винрейт, без разбора сборки; STRATZ): " + "; ".join(position_summary(p, d2.get(p), st) for p in positions[len(shown):]) + ".")
    mism = mismatch_lines(ctx, h, positions, d2, st)
    lines.append("## Что не подходит этому герою (механика предмета и редкие покупки на высоком MMR)")
    lines += mism or ["Явных несовместимостей предметов с механикой героя нет."]
    matchups = matchup_lines(ctx, stratz)
    if matchups:
        lines += ["## Против кого тяжело, с кем хорошо"] + matchups
    text = "\n".join(lines)
    if "[?]" in text:
        text += f"\n{PLACEHOLDER_NOTE}"
    return text + "\n"


DEPENDENT_STARTS = {"если", "когда", "который", "которая", "которые", "чтобы", "пока", "при"}
SHORT_NAMES = {
    "black_king_bar": "BKB", "monkey_king_bar": "MKB", "sphere": "Linken's", "mage_slayer": "Mage Slayer", "pipe": "Pipe",
    "blade_mail": "Blade Mail", "assault": "Assault", "butterfly": "Butterfly", "orchid": "Orchid", "bloodthorn": "Bloodthorn",
    "silver_edge": "Silver Edge", "spirit_vessel": "Vessel", "skadi": "Skadi", "shivas_guard": "Shiva's", "aeon_disk": "Aeon",
    "abyssal_blade": "Abyssal", "sheepstick": "Scythe", "glimmer_cape": "Glimmer", "force_staff": "Force", "lotus_orb": "Lotus",
    "guardian_greaves": "Greaves", "boots_of_bearing": "Bearing", "crimson_guard": "Crimson", "nullifier": "Nullifier",
    "satanic": "Satanic", "desolator": "Desolator", "diffusal_blade": "Diffusal", "disperser": "Disperser", "mjollnir": "Mjollnir",
    "maelstrom": "Maelstrom", "bfury": "Battle Fury", "radiance": "Radiance", "manta": "Manta", "rod_of_atos": "Atos",
    "gungir": "Gleipnir", "cyclone": "Eul's", "ghost": "Ghost", "dust": "Dust", "ward_sentry": "Sentry", "javelin": "Javelin",
    "solar_crest": "Solar Crest", "heavens_halberd": "Halberd", "magic_wand": "Wand", "power_treads": "Treads",
    "blink": "Blink", "ultimate_scepter": "Aghanim's", "aghanims_shard": "Shard", "devastator": "Devastator",
}


def short_name(ctx: Ctx, key: str) -> str:
    return SHORT_NAMES.get(key) or ctx.item_name(key)


def short_card(ctx: Ctx, key: str) -> str:
    h = ctx.kb.hero(key)
    builds = load_json(KB_DIR / "builds" / f"{key}.json")
    stratz = load_json(KB_DIR / "builds_stratz" / f"{key}.json")
    d2 = d2pt_positions(builds)
    st = stratz_blocks(stratz)
    positions = select_positions(d2, st)
    tags = ctx.hero_tags.get(key, [])
    roles = ", ".join(f"{kbmod.ROLE_RU[r]} {lv}" for r, lv in h["roles"].items())
    head = (f"{h['name_ru']}: {'ближний' if h['attack_type'] == 'melee' else 'дальний'} бой, {kbmod.ATTR_RU[h['primary_attr']].lower()}; {roles}."
            + (" Черты: " + ", ".join(TAG_RU.get(t, t) for t in tags) + "." if tags else ""))
    ult = next((a for a in h["abilities"] if a["kind"] == "ultimate"), None)
    ult_line = ""
    if ult:
        passive = " (пассивка)" if "passive" in ult["behavior"] else ""
        if ult["bkb_pierce"] is True:
            pierce = "ПРОБИВАЕТ БКБ" + passive
        elif ult["bkb_pierce"] is False:
            pierce = "НЕ пробивает БКБ" + passive
        else:
            pierce = "БКБ: нет данных" + passive
        ult_line = f"Ульт {ult['name_ru']}: {pierce}."
    abil = []
    for a in h["abilities"]:
        if a["kind"] == "ultimate" or a["innate"] or "not_learnable" in a["behavior"] or not a["desc_ru"]:
            continue
        abil.append(f"- {a['name_ru']}: {lead(a['desc_ru'], 62)}")
    core_items = []
    if positions:
        p = positions[0]
        if d2.get(p):
            core_items = [short_name(ctx, e["item"]) for e in sorted(d2[p]["core"], key=lambda e: e["avg_time_min"])
                          if e["item"] not in ("magic_wand", "tango", "branches", "faerie_fire", "bottle")]
        elif st["high"].get(p):
            core_items = [short_name(ctx, k) for k, v in sorted(gather_items(st["high"][p]).items(), key=lambda kv: kv[1]["time"])
                          if v["rate"] >= 0.3 and k not in ("magic_wand",)]
    pos_label = f" (поз. {positions[0]})" if positions else ""

    def assemble(n_abil: int, n_items: int, n_tags: int) -> str:
        buys = f"Сборка 7000+{pos_label}: " + ", ".join(core_items[:n_items]) + "." if core_items else ""
        against = counter_against(ctx, tags, n_tags)
        parts = [head, ult_line] + abil[:n_abil] + [buys, against]
        return "\n".join(x for x in parts if x) + "\n"

    for n_abil, n_items, n_tags in ((3, 6, 3), (3, 5, 2), (2, 5, 2), (2, 4, 2), (2, 4, 1), (1, 4, 1), (1, 3, 1), (0, 3, 1)):
        text = assemble(n_abil, n_items, n_tags)
        if estimate_tokens(text) <= SHORT_BUDGET:
            return text
    return text


def lead(text: str, limit: int) -> str:
    """First meaningful clause of an ability description, without leading all-caps tags."""
    text = " ".join((text or "").split())
    text = re.sub(r"^(?:[А-ЯЁA-Z]{4,}[ ,]*)+\s*[—-]\s*", "", text)
    if text.startswith("Векторное применение"):
        text = text.split(". ", 1)[-1] if ". " in text else text
    first = text.split(". ", 1)[0].rstrip(".")
    first = re.sub(r"^Герой ", "", first)
    first = first[:1].upper() + first[1:]
    if len(first) > limit and ", " in first:
        out = ""
        for clause in first.split(", "):
            if out and clause.split()[0].lower() in DEPENDENT_STARTS:
                break
            candidate = clause if not out else out + ", " + clause
            if len(candidate) > limit:
                break
            out = candidate
        out = re.sub(r"\s+(?:и|или|а|но)$", "", out)
        if len(out) >= 25:
            return out
    return clip(first, limit)


def counter_against(ctx: Ctx, tags: list[str], n_tags: int = 3) -> str:
    parts = []
    for tag in tags[:n_tags]:
        items = []
        for rule in ctx.rules:
            if rule["tag"] == tag and ("core" in rule["roles"] or "any" in rule["roles"]):
                for it in rule["items"]:
                    if it not in items:
                        items.append(it)
        if items:
            parts.append(f"{TAG_RU.get(tag, tag)}: " + ", ".join(short_name(ctx, i) for i in items[:3]))
    return "Против него: " + "; ".join(parts) + "." if parts else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hero", help="only this hero key; print instead of writing")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()
    ctx = Ctx()
    keys = [args.hero] if args.hero else sorted(ctx.heroes)
    if args.hero:
        print(full_card(ctx, args.hero))
        print("-----")
        print(short_card(ctx, args.hero))
        return
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    full_tokens, short_tokens = [], []
    for key in keys:
        full, short = full_card(ctx, key), short_card(ctx, key)
        (out / f"{key}.md").write_text(full, encoding="utf-8")
        (out / f"{key}.short.md").write_text(short, encoding="utf-8")
        full_tokens.append(estimate_tokens(full))
        short_tokens.append(estimate_tokens(short))
    print(f"{len(keys)} heroes: full avg {sum(full_tokens) / len(keys):.0f} (min {min(full_tokens)}, max {max(full_tokens)}) tokens, "
          f"short avg {sum(short_tokens) / len(keys):.0f} (max {max(short_tokens)})")


if __name__ == "__main__":
    main()
