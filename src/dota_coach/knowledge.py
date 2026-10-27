"""Offline knowledge base over data/cache (filled by tools/update_data.py). No network."""

import json
from collections import Counter as Multiset
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import NamedTuple

from dota_coach.config import ROOT

CACHE_DIR = ROOT / "data" / "cache"
HERO_PREFIX = "npc_dota_hero_"
ITEM_PREFIX = "item_"
ULTIMATE_OVERRIDE = {"clinkz": "clinkz_burning_army", "invoker": "invoker_invoke"}
PHASES = {
    "start": "start_game_items",
    "early": "early_game_items",
    "mid": "mid_game_items",
    "late": "late_game_items",
}


@dataclass(frozen=True)
class Ability:
    key: str
    name: str
    cooldown: str | None = None
    mana: str | None = None
    behavior: str | None = None
    innate: bool = False
    desc: str | None = None
    bkb_pierce: str | None = None


@dataclass(frozen=True)
class Talent:
    key: str
    name: str
    level: int


@dataclass(frozen=True)
class Hero:
    id: int
    key: str
    name: str
    primary_attr: str
    attack_type: str
    roles: tuple[str, ...]
    abilities: tuple[Ability, ...] = field(default=(), compare=False)
    talents: tuple[Talent, ...] = field(default=(), compare=False)

    @property
    def npc_name(self) -> str:
        return HERO_PREFIX + self.key

    @property
    def ultimate(self) -> Ability | None:
        forced = ULTIMATE_OVERRIDE.get(self.key)
        if forced:
            return next((a for a in self.abilities if a.key == forced), None)
        pool = [a for a in self.abilities if not a.innate and a.behavior and "Hidden" not in a.behavior]
        return pool[-1] if pool else None


@dataclass(frozen=True)
class Item:
    key: str
    id: int
    name: str
    cost: int
    components: tuple[str, ...]
    is_recipe: bool
    neutral_tier: int | None
    active: tuple[str, ...]
    passive: tuple[str, ...]


class PopularItem(NamedTuple):
    key: str
    name: str
    cost: int
    count: int


class Matchup(NamedTuple):
    hero: str
    games: int
    winrate: float


@dataclass(frozen=True)
class CounterPick:
    hero: str
    name: str
    score: float
    winrate: float
    pairs: tuple[Matchup, ...]


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    cost_total: int
    cost_left: int
    parts: tuple[tuple[str, int], ...]
    owned: bool
    affordable: bool
    gold_short: int
    next_part: tuple[str, int] | None


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    cut = text.find(". ")
    if 0 < cut < limit:
        return text[: cut + 1]
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _fmt(value) -> str | None:
    if value in (None, False, "", 0, "0"):
        return None
    if isinstance(value, list):
        return "/".join(str(v) for v in value)
    return str(value)


def norm_item(key: str) -> str:
    return key.removeprefix(ITEM_PREFIX)


class Knowledge:
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.dir = Path(cache_dir)

    def _json(self, *parts: str):
        path = self.dir.joinpath(*parts)
        if not path.exists():
            raise FileNotFoundError(f"{path} missing, run tools/update_data.py")
        return json.loads(path.read_text(encoding="utf-8"))

    def _opendota(self, name: str):
        return self._json("opendota", name)["data"]

    @cached_property
    def _heroes_raw(self) -> dict[str, dict]:
        return self._json("dotaconstants", "heroes.json")

    @cached_property
    def _items_raw(self) -> dict[str, dict]:
        return self._json("dotaconstants", "items.json")

    @cached_property
    def _item_ids(self) -> dict[int, str]:
        return {int(k): v for k, v in self._json("dotaconstants", "item_ids.json").items()}

    @cached_property
    def _abilities_raw(self) -> dict[str, dict]:
        return self._json("dotaconstants", "abilities.json")

    @cached_property
    def _hero_abilities_raw(self) -> dict[str, dict]:
        return self._json("dotaconstants", "hero_abilities.json")

    @cached_property
    def _hero_index(self) -> dict[str, int]:
        index: dict[str, int] = {}
        for raw in self._heroes_raw.values():
            hid = int(raw["id"])
            index[raw["name"].removeprefix(HERO_PREFIX)] = hid
            index.setdefault(raw["localized_name"].lower(), hid)
        return index

    def _hero_id(self, ref: int | str) -> int:
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            hid = int(ref)
            if str(hid) in self._heroes_raw:
                return hid
        elif isinstance(ref, str):
            hid = self._hero_index.get(ref.removeprefix(HERO_PREFIX).lower())
            if hid is not None:
                return hid
        raise KeyError(f"unknown hero: {ref!r}")

    def heroes(self) -> list[Hero]:
        return [self.hero(int(i)) for i in sorted(self._heroes_raw, key=int)]

    def hero(self, ref: int | str) -> Hero:
        """By short name ('nevermore'), id, 'npc_dota_hero_nevermore' or display name."""
        hid = self._hero_id(ref)
        raw = self._heroes_raw[str(hid)]
        return Hero(
            id=hid,
            key=raw["name"].removeprefix(HERO_PREFIX),
            name=raw["localized_name"],
            primary_attr=raw["primary_attr"],
            attack_type=raw["attack_type"],
            roles=tuple(raw.get("roles") or ()),
            abilities=self._hero_abilities(raw["name"]),
            talents=self._hero_talents(raw["name"]),
        )

    def _hero_abilities(self, npc_name: str) -> tuple[Ability, ...]:
        out = []
        for key in self._hero_abilities_raw.get(npc_name, {}).get("abilities", []):
            raw = self._abilities_raw.get(key)
            if not raw or not raw.get("dname"):
                continue
            behavior = raw.get("behavior")
            if isinstance(behavior, list):
                behavior = ", ".join(behavior)
            out.append(Ability(key, raw["dname"], _fmt(raw.get("cd")), _fmt(raw.get("mc")),
                               behavior, bool(raw.get("is_innate")), _short(raw.get("desc") or "", 120) or None,
                               raw.get("bkbpierce")))
        return tuple(out)

    def _hero_talents(self, npc_name: str) -> tuple[Talent, ...]:
        out = []
        for t in self._hero_abilities_raw.get(npc_name, {}).get("talents", []):
            raw = self._abilities_raw.get(t["name"], {})
            out.append(Talent(t["name"], raw.get("dname") or t["name"], int(t["level"])))
        return tuple(out)

    def item(self, key: str) -> Item:
        """By key with or without 'item_' prefix."""
        k = norm_item(key)
        raw = self._items_raw.get(k)
        if raw is None:
            raise KeyError(f"unknown item: {key!r}")
        active, passive = [], []
        for ab in raw.get("abilities") or []:
            line = f"{ab.get('title', '')}: {_short(ab.get('description', ''))}".strip(": ")
            (active if ab.get("type") == "active" else passive).append(line)
        tier = raw.get("tier")
        return Item(
            key=k,
            id=int(raw["id"]),
            name=raw.get("dname") or k,
            cost=int(raw.get("cost") or 0),
            components=tuple(c for c in raw.get("components") or () if c),
            is_recipe=k.startswith("recipe_"),
            neutral_tier=int(tier) if tier is not None else None,
            active=tuple(active),
            passive=tuple(passive),
        )

    @cached_property
    def _component_keys(self) -> frozenset[str]:
        used: set[str] = set()
        for key, raw in self._items_raw.items():
            if raw.get("tier") is None and not key.startswith("recipe_"):
                used.update(norm_item(c) for c in raw.get("components") or () if c)
        return frozenset(used)

    def used_as_component(self, key: str) -> bool:
        return norm_item(key) in self._component_keys

    def item_by_id(self, item_id: int) -> Item:
        return self.item(self._item_ids[int(item_id)])

    def item_components(self, key: str) -> list[str]:
        """All leaf components, recursively (recipe cost not included)."""
        item = self.item(key)
        if not item.components:
            return []
        leaves: list[str] = []
        for comp in item.components:
            sub = self.item_components(comp)
            leaves.extend(sub or [norm_item(comp)])
        return leaves

    def popular_items(self, hero: int | str, phase: str, top: int | None = None) -> list[PopularItem]:
        if phase not in PHASES:
            raise ValueError(f"phase must be one of {sorted(PHASES)}")
        hid = self._hero_id(hero)
        data = self._opendota(f"hero_{hid}_item_popularity.json").get(PHASES[phase], {})
        out = []
        for item_id, count in data.items():
            key = self._item_ids.get(int(item_id))
            if key is None or key not in self._items_raw:
                continue
            item = self.item(key)
            out.append(PopularItem(key, item.name, item.cost, int(count)))
        out.sort(key=lambda p: (-p.count, p.key))
        return out[:top]

    def matchups(self, hero: int | str) -> list[Matchup]:
        """Win rate of `hero` against each enemy hero, most games first."""
        hid = self._hero_id(hero)
        out = []
        for row in self._opendota(f"hero_{hid}_matchups.json"):
            eid = str(row["hero_id"])
            games = int(row["games_played"])
            if eid not in self._heroes_raw or games <= 0:
                continue
            key = self._heroes_raw[eid]["name"].removeprefix(HERO_PREFIX)
            out.append(Matchup(key, games, int(row["wins"]) / games))
        out.sort(key=lambda m: -m.games)
        return out

    def best_counters(self, enemies: list[int | str], pool: list[int | str] | None = None,
                      top: int = 5, min_games: int = 50) -> list[CounterPick]:
        """Heroes ranked by summed (win rate - 0.5) against all given enemies.

        A hero is considered only if it has >= min_games against every enemy.
        """
        enemy_ids = [self._hero_id(e) for e in enemies]
        cand_ids = [self._hero_id(p) for p in pool] if pool is not None else [int(i) for i in self._heroes_raw]
        enemy_keys = [self.hero(e).key for e in enemy_ids]
        picks = []
        for cid in cand_ids:
            if cid in enemy_ids:
                continue
            by_enemy = {m.hero: m for m in self.matchups(cid)}
            pairs = []
            for ek in enemy_keys:
                m = by_enemy.get(ek)
                if m is None or m.games < min_games:
                    break
                pairs.append(m)
            else:
                score = sum(m.winrate - 0.5 for m in pairs)
                total = sum(m.games for m in pairs)
                wr = sum(m.winrate * m.games for m in pairs) / total if total else 0.5
                hero = self.hero(cid)
                picks.append(CounterPick(hero.key, hero.name, score, wr, tuple(pairs)))
        picks.sort(key=lambda p: -p.score)
        return picks[:top]

    def _plan_cost(self, key: str, pool: Multiset, parts: list[tuple[str, int]]) -> int:
        if pool[key] > 0:
            pool[key] -= 1
            return 0
        item = self.item(key)
        if not item.components:
            parts.append((key, item.cost))
            return item.cost
        total = 0
        comps = [norm_item(c) for c in item.components]
        recipe = max(0, item.cost - sum(self.item(c).cost for c in comps))
        if recipe:
            parts.append((f"recipe_{key}", recipe))
            total += recipe
        for c in comps:
            total += self._plan_cost(c, pool, parts)
        return total

    def next_items_affordable(self, owned: list[str], gold: int, candidates: list[str]) -> list[Plan]:
        """For each candidate: parts still to buy (owned components excluded) and whether gold covers them."""
        owned_keys = Multiset(norm_item(k) for k in owned if norm_item(k) in self._items_raw)
        plans = []
        for cand in candidates:
            item = self.item(cand)
            pool = Multiset(owned_keys)
            parts: list[tuple[str, int]] = []
            if pool[item.key] > 0:
                left, has = 0, True
            else:
                left, has = self._plan_cost(item.key, pool, parts), False
            buyable = [p for p in parts if p[1] <= gold]
            plans.append(Plan(
                key=item.key, name=item.name, cost_total=item.cost, cost_left=left,
                parts=tuple(parts), owned=has, affordable=left <= gold,
                gold_short=max(0, left - gold),
                next_part=max(buyable, key=lambda p: p[1]) if buyable else None,
            ))
        return plans


_default: Knowledge | None = None


def default() -> Knowledge:
    global _default
    if _default is None:
        _default = Knowledge()
    return _default
