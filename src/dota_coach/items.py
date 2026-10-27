"""[12] items: ranked purchase candidates (counter rules, enemy items, popular builds). Input for the model, not advice."""

import logging
import math
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .config import ROOT
from .match_picture import norm_item
from .state import GameState
from .timers import fmt_clock

log = logging.getLogger(__name__)

COUNTERS_PATH = ROOT / "data" / "counters.yaml"
ROLE_SETTINGS = ("auto", "core", "support")
TOP = 6
REASONS_CHARS = 200
PHASE_BORDERS = ((0, "start"), (900, "early"), (1800, "mid"))
CAP_FLOOR = 1000
CAP_PER_MINUTE = 330
CAP_POWER = 1.5
POPULAR_WEIGHT = 1.5
ENEMY_ITEM_WEIGHT = 2.0
RULE_DECAY = 0.85
RARITY_BASE = 0.25
RARITY_RANGE = (0.5, 2.5)
RARITY_POWER = 1.5
MAX_COUNTED_ENEMIES = 3
CONSUMABLES = {
    "tango", "clarity", "flask", "faerie_fire", "enchanted_mango", "smoke_of_deceit", "tpscroll", "dust",
    "magic_stick", "famango", "great_famango", "greater_famango", "greater_faerie_fire", "cheese", "tome_of_knowledge",
}
NEVER = {"tpscroll"}
WARDS = {"ward_observer", "ward_sentry", "ward_dispenser"}
AURA_GROUPS = [
    {"pipe"}, {"crimson_guard"}, {"mekansm", "guardian_greaves"}, {"boots_of_bearing"}, {"vladmir"}, {"assault"},
]
BASIC_BOOTS = {"boots", "power_treads", "phase_boots", "arcane_boots", "tranquil_boots"}
BOOTS_UPGRADES = {"guardian_greaves", "boots_of_bearing", "travel_boots", "travel_boots_2"}
LH_SUPPORT_BELOW = 2.0
LH_CORE_ABOVE = 4.5
LH_UNDECIDED_CORE = 3.0
ROLE_FROM_MINUTE = 480


def phase_of(clock: int | None) -> str:
    clock = 0 if clock is None else clock
    if clock < 0:
        return "start"
    for border, name in PHASE_BORDERS[1:]:
        if clock < border:
            return name
    return "late"


@lru_cache(maxsize=4)
def affordable_tier(clock: int | None) -> int:
    """Rough cost of a single item a hero can be expected to reach by now."""
    return max(CAP_FLOOR, int(CAP_PER_MINUTE * (clock or 0) / 60))


def load_counters(path: Path = COUNTERS_PATH) -> dict:
    if not path.exists():
        log.warning("counters file not found: %s", path)
        return {"rules": [], "enemy_items": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {"rules": data.get("rules") or [], "enemy_items": data.get("enemy_items") or {}}


def detect_role(state: GameState, kn, setting: str = "auto") -> tuple[str, str]:
    if setting in ("core", "support"):
        return setting, "выбрана вручную"
    roles: tuple = ()
    try:
        roles = kn.hero(state.hero).roles if kn and state.hero else ()
    except Exception:
        roles = ()
    carry, support = "Carry" in roles, "Support" in roles
    base = "core" if carry and not support else "support" if support and not carry else None
    clock = state.clock
    rate = state.last_hits / (clock / 60) if clock is not None and clock >= ROLE_FROM_MINUTE else None
    if rate is not None:
        if base == "core" and rate < LH_SUPPORT_BELOW:
            return "support", f"герой-керри, но {rate:.1f} добиваний в минуту"
        if base == "support" and rate >= LH_CORE_ABOVE:
            return "core", f"герой-саппорт, но {rate:.1f} добиваний в минуту"
        if base is None:
            role = "core" if rate >= LH_UNDECIDED_CORE else "support"
            return role, f"по добиваниям: {rate:.1f} в минуту"
    return base or "core", "по герою" if base else "по умолчанию"


@dataclass
class Candidate:
    key: str
    name: str
    cost: int
    cost_left: int
    affordable: bool
    gold_short: int
    next_part: dict | None
    reasons: list[str]
    score: float


@dataclass
class Advice:
    clock: int | None = None
    role: str = "core"
    role_note: str = ""
    role_setting: str = "auto"
    phase: str = "start"
    gold: int = 0
    candidates: list[Candidate] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["clock_text"] = fmt_clock(self.clock) if self.clock is not None else None
        return data

    def signature(self) -> tuple:
        return (self.role, self.phase, tuple((c.key, c.cost_left, c.affordable, c.next_part and c.next_part["key"])
                                             for c in self.candidates), tuple(self.excluded))

    def to_text(self) -> str:
        if not self.candidates:
            return ""
        role = "кор" if self.role == "core" else "саппорт"
        lines = [f"Роль: {role} ({self.role_note}). Золото {self.gold}. Кандидаты по убыванию важности, это не финальный совет:"]
        for n, c in enumerate(self.candidates, 1):
            if c.affordable:
                money = "хватает золота сейчас"
            else:
                money = f"не хватает {c.gold_short}"
            line = f"{n}. {c.name} ({c.cost}): осталось {c.cost_left}, {money}"
            if c.next_part:
                tag = "можно купить часть" if c.next_part["affordable"] else "ближайшая часть"
                line += f"; {tag}: {c.next_part['name']} {c.next_part['cost']}"
            why = c.reasons[0]
            if len(c.reasons) > 1 and len(why) + len(c.reasons[1]) < REASONS_CHARS:
                why += "; " + c.reasons[1]
            line += ". " + why
            lines.append(line)
        if self.excluded:
            lines.append("Не берём: " + "; ".join(self.excluded) + ".")
        return "\n".join(lines)


class ItemAdvisor:
    def __init__(self, names, picture, counters_path: Path = COUNTERS_PATH) -> None:
        self.names = names
        self.picture = picture
        self.counters_path = counters_path
        self._popular: dict[tuple[str, str], list] = {}

    @property
    def kn(self):
        return getattr(self.names, "kn", None)

    def reset(self) -> None:
        self._popular.clear()

    def _rarity(self, tag: str) -> float:
        """A tag carried by a quarter of the pool weighs 1.0; rarer tags weigh more, common ones less."""
        pool = self.picture.tags
        share = sum(tag in t for t in pool.values()) / len(pool) if pool else RARITY_BASE
        if share <= 0:
            return RARITY_RANGE[1] ** RARITY_POWER
        low, high = RARITY_RANGE
        return min(high, max(low, math.log(1 / share) / math.log(1 / RARITY_BASE))) ** RARITY_POWER

    def _popular_items(self, hero: str, phase: str) -> list:
        key = (hero, phase)
        if key not in self._popular:
            try:
                self._popular[key] = self.kn.popular_items(hero, phase, 14)
            except Exception:
                self._popular[key] = []
        return self._popular[key]

    def _part_name(self, key: str) -> str:
        if key.startswith("recipe_"):
            return "рецепт " + self.names.item(key.removeprefix("recipe_"))
        return self.names.item(key)

    def compute(self, state: GameState | None, role_setting: str = "auto") -> Advice:
        kn = self.kn
        if state is None or not state.hero or kn is None:
            return Advice(role_setting=role_setting)
        counters = load_counters(self.counters_path)
        clock = state.clock
        role, note = detect_role(state, kn, role_setting)
        phase = phase_of(clock)
        advice = Advice(clock=clock, role=role, role_note=note, role_setting=role_setting, phase=phase, gold=state.gold)
        entries: dict[str, dict] = {}

        def add(key: str, score: float, reason: str, source: str) -> None:
            e = entries.setdefault(norm_item(key), {"score": 0.0, "reasons": [], "sources": set()})
            e["score"] += score
            e["sources"].add(source)
            if reason not in e["reasons"]:
                e["reasons"].append(reason)

        enemies = self.picture.enemies()
        by_tag: dict[str, list[str]] = {}
        for enemy in enemies:
            for tag in enemy.tags:
                by_tag.setdefault(tag, []).append(enemy.name)
        for rule in counters["rules"]:
            heroes = by_tag.get(rule.get("tag"))
            roles = rule.get("roles") or ["any"]
            if not heroes or not (role in roles or "any" in roles):
                continue
            weight = min(len(heroes), MAX_COUNTED_ENEMIES) * self._rarity(rule["tag"])
            reason = f"{rule.get('reason', '')} (у врагов: {', '.join(heroes)})"
            for idx, item in enumerate(rule.get("items") or []):
                add(item, weight * RULE_DECAY ** idx, reason, "rule")

        for enemy in enemies:
            for item in dict.fromkeys(enemy.item_keys()):
                react = counters["enemy_items"].get(item)
                if not react:
                    continue
                reason = f"{react.get('reason', '')} ({enemy.name}: {self.names.item(item)})"
                for idx, target in enumerate(react.get("items") or []):
                    add(target, ENEMY_ITEM_WEIGHT * RULE_DECAY ** idx, reason, "enemy_item")

        popular = self._popular_items(state.hero, phase)
        top_count = popular[0].count if popular else 0
        for p in popular:
            add(p.key, POPULAR_WEIGHT * p.count / top_count, "популярно у героя на этой стадии", "popular")

        owned = [norm_item(k) for k in state.item_names()]
        owned_set = set(owned)
        ally_items: dict[str, str] = {}
        for ally in self.picture.allies():
            for key in ally.item_keys():
                ally_items.setdefault(key, ally.name)

        survivors: dict[str, dict] = {}
        for key, e in entries.items():
            if self._dropped(key, e, role, phase, owned_set, ally_items, advice):
                continue
            survivors[key] = e
        if not survivors:
            return advice

        cap = affordable_tier(clock)
        plans = {p.key: p for p in kn.next_items_affordable(owned, state.gold, list(survivors))}
        ranked = []
        for key, e in survivors.items():
            plan = plans.get(key)
            if plan is None or plan.owned:
                continue
            score = e["score"]
            if plan.cost_total > cap:
                score *= (cap / plan.cost_total) ** CAP_POWER
            if plan.affordable:
                score *= 1.25
            if plan.cost_total:
                score *= 1 + 0.3 * (1 - plan.cost_left / plan.cost_total)
            ranked.append((score, plan, e))
        ranked.sort(key=lambda r: (-r[0], r[1].cost_left, r[1].key))
        for score, plan, e in ranked[:TOP]:
            advice.candidates.append(Candidate(
                key=plan.key, name=plan.name, cost=plan.cost_total, cost_left=plan.cost_left,
                affordable=plan.affordable, gold_short=plan.gold_short, next_part=self._next_part(plan),
                reasons=e["reasons"][:3], score=round(score, 2),
            ))
        return advice

    def _next_part(self, plan) -> dict | None:
        if plan.next_part:
            key, cost = plan.next_part
            affordable = True
        elif plan.parts:
            parts = [p for p in plan.parts if not p[0].startswith("recipe_")] or list(plan.parts)
            key, cost = min(parts, key=lambda p: p[1])
            affordable = False
        else:
            return None
        return {"key": key, "name": self._part_name(key), "cost": cost, "affordable": affordable}

    def _dropped(self, key: str, e: dict, role: str, phase: str, owned: set[str], ally_items: dict[str, str],
                 advice: Advice) -> bool:
        kn = self.kn
        try:
            info = kn.item(key)
        except KeyError:
            return True
        if info.is_recipe or info.neutral_tier is not None or info.cost <= 0 or key in NEVER:
            return True
        if key in CONSUMABLES and not (key == "dust" and e["sources"] & {"rule", "enemy_item"}):
            return True
        if phase == "start" and "popular" not in e["sources"]:
            return True
        if key in WARDS and role != "support":
            return True
        if phase != "start" and not info.components and not info.active and kn.used_as_component(key):
            return True
        if key in BASIC_BOOTS and owned & (BASIC_BOOTS | BOOTS_UPGRADES):
            return True
        for group in AURA_GROUPS:
            if key in group:
                for other in group:
                    if other in ally_items:
                        if e["score"] >= 1.0:
                            advice.excluded.append(f"{info.name} (уже у {ally_items[other]})")
                        return True
        return False


class ItemsTrigger:
    """When to ask the model about purchases. Enemy-item and death requests are raised elsewhere and call mark()."""

    DEBOUNCE = 45
    IDLE = 240
    MIN_CLOCK = 60

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.notified: set[tuple[str, str]] = set()
        self.last_items: int | None = None
        self.idle_from: int | None = None

    def mark(self, clock: int | None) -> None:
        self.last_items = clock

    def check(self, state: GameState, advice: Advice, last_request_clock: int | None) -> str | None:
        clock = state.clock
        if state.phase != "game" or not state.alive or state.paused or clock is None or clock < self.MIN_CLOCK:
            return None
        if self.idle_from is None or clock < self.idle_from:
            self.idle_from = clock
        if self.last_items is not None and clock < self.last_items:
            self.last_items = None
        if self.last_items is not None and clock - self.last_items < self.DEBOUNCE:
            return None
        top = advice.candidates[0] if advice.candidates else None
        if top and top.next_part and top.next_part["affordable"]:
            sig = (top.key, top.next_part["key"])
            if sig not in self.notified:
                self.notified.add(sig)
                self.last_items = clock
                part = top.next_part
                return f"Золота хватает на {part['name']} ({part['cost']}) — шаг к {top.name}."
        last = max(x for x in (self.idle_from, last_request_clock, self.last_items) if x is not None)
        if clock - last >= self.IDLE:
            self.last_items = clock
            return "Плановый обзор покупок: давно не было советов."
        return None
