"""[11] MatchPicture: all 10 heroes with known items, their age and source, net worth estimates."""

import logging
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .config import ROOT
from .gsi_fields import hero_short
from .state import GameState
from .timers import fmt_clock

log = logging.getLogger(__name__)

HERO_TAGS_PATH = ROOT / "data" / "hero_tags.yaml"
SOURCES = ("gsi", "scout", "realtime", "screen")
STALE_AFTER = 120
HIDDEN_ITEMS = {"tpscroll"}
TAG_RU = {
    "evasion": "уклонение",
    "illusions": "иллюзии",
    "summons": "призывы",
    "invisibility": "невидимость",
    "heal": "лечение",
    "magic_burst": "магический урон",
    "physical_burst": "физический урон",
    "disable_chain": "контроль",
    "silence": "сайленс",
    "escape": "мобильность",
    "tanky_armor": "танк",
    "passive_core": "пассивки",
    "ethereal_ghost": "эфир",
    "mana_dependent": "мана",
    "pushers": "пуш",
    "root_leash": "рут",
    "bkb_pierce_ult": "ульта пробивает BKB",
}


def norm_item(key: str) -> str:
    return key.removeprefix("item_")


@lru_cache(maxsize=4)
def load_hero_tags(path: Path = HERO_TAGS_PATH) -> dict[str, list[str]]:
    if not path.exists():
        log.warning("hero tags file not found: %s", path)
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: list(v.get("tags") or []) for k, v in (data.get("heroes") or {}).items()}


def tags_ru(tags: list[str]) -> list[str]:
    return [TAG_RU.get(t, t) for t in tags]


@dataclass
class KnownItem:
    key: str
    source: str
    seen_at: int | None


@dataclass
class HeroPicture:
    hero: str
    team: str | None
    name: str
    tags: list[str] = field(default_factory=list)
    items: list[KnownItem] = field(default_factory=list)
    level: int | None = None
    net_worth: int | None = None
    net_worth_source: str | None = None
    net_worth_at: int | None = None
    is_me: bool = False

    @property
    def has_data(self) -> bool:
        return bool(self.items) or self.net_worth is not None

    def item_keys(self) -> list[str]:
        return [i.key for i in self.items]


class _Plain:
    def hero(self, key):
        return (key or "?").replace("_", " ").title()

    def item(self, key):
        return norm_item(key or "?").replace("_", " ").title()

    def item_info(self, key):
        return None


class MatchPicture:
    def __init__(self, names=None, tags: dict[str, list[str]] | None = None) -> None:
        self.names = names or _Plain()
        self.tags = tags if tags is not None else load_hero_tags()
        self.reset()

    def reset(self) -> None:
        self.heroes: dict[str, HeroPicture] = {}
        self.team: str | None = None
        self.me: str | None = None
        self.gold: int = 0

    def _cost(self, key: str) -> int:
        info = self.names.item_info(key)
        return info.cost if info else 0

    def _hero(self, key: str, team: str | None = None) -> HeroPicture:
        pic = self.heroes.get(key)
        if pic is None:
            pic = self.heroes[key] = HeroPicture(key, team, self.names.hero(key), list(self.tags.get(key, [])))
        if team and not pic.team:
            pic.team = team
        return pic

    def update_state(self, state: GameState) -> None:
        if state.team:
            self.team = state.team
        if state.draft:
            for team in ("radiant", "dire"):
                for key in state.draft.picks[team]:
                    self._hero(key, team)
        if state.hero:
            self.me = state.hero
            me = self._hero(state.hero, state.team)
            for pic in self.heroes.values():
                pic.is_me = pic.hero == state.hero
            self.gold = state.gold
            me.level = state.level or me.level
            keys = [norm_item(k) for k in state.item_names()]
            if state.teleport:
                keys.append(norm_item(state.teleport.name))
            me.items = [KnownItem(k, "gsi", state.clock) for k in keys]

    def update_seen(self, hero: str, items: list[str], source: str, clock: int | None, level: int | None = None,
                    net_worth: int | None = None, partial: bool = False) -> list[str]:
        """Record what a source saw. Returns item keys that were not known before for this hero."""
        if source not in SOURCES:
            raise ValueError(f"unknown source: {source}")
        key = hero_short(hero)
        pic = self._hero(key)
        if pic.is_me and source != "gsi":
            return []
        new_keys = [norm_item(i) for i in items]
        before = Counter(pic.item_keys())
        if partial:
            fresh = {k: KnownItem(k, source, clock) for k in new_keys}
            pic.items = [fresh.pop(i.key, i) for i in pic.items] + list(fresh.values())
        else:
            newest = max((i.seen_at for i in pic.items if i.seen_at is not None), default=None)
            if clock is not None and newest is not None and clock < newest:
                new_keys = []
            else:
                pic.items = [KnownItem(k, source, clock) for k in new_keys]
        if level is not None:
            pic.level = level
        if net_worth is not None:
            pic.net_worth, pic.net_worth_source, pic.net_worth_at = int(net_worth), source, clock
        return list((Counter(i.key for i in pic.items) - before).elements())

    def networth(self, pic: HeroPicture) -> tuple[int | None, bool]:
        """(value, is_estimate). Source value wins; else item costs (+ current gold for our hero)."""
        if pic.net_worth is not None:
            return pic.net_worth, False
        if not pic.items:
            return None, True
        total = sum(self._cost(i.key) for i in pic.items)
        if pic.is_me:
            total += self.gold
        return total, True

    def allies(self) -> list[HeroPicture]:
        return [p for p in self.heroes.values() if self.team and p.team == self.team and not p.is_me]

    def enemies(self) -> list[HeroPicture]:
        return [p for p in self.heroes.values() if self.team and p.team and p.team != self.team]

    def team_totals(self) -> dict:
        out = {}
        for team in ("radiant", "dire"):
            values = [self.networth(p)[0] for p in self.heroes.values() if p.team == team]
            known = [v for v in values if v is not None]
            out[team] = {"net_worth": sum(known), "known": len(known)}
        total_known = out["radiant"]["known"] + out["dire"]["known"]
        advantage = None
        if self.team in out:
            mine, theirs = out[self.team], out["dire" if self.team == "radiant" else "radiant"]
            if mine["known"] and theirs["known"]:
                advantage = mine["net_worth"] - theirs["net_worth"]
        return {"teams": out, "advantage": advantage, "known": total_known, "partial": total_known < 10}

    def _items_text(self, pic: HeroPicture, clock: int | None) -> str:
        shown = [i for i in pic.items if i.key not in HIDDEN_ITEMS]
        if not shown:
            return "предметы неизвестны"
        groups: dict[str, list[str]] = {}
        for i in shown:
            age = clock - i.seen_at if clock is not None and i.seen_at is not None else 0
            label = f"давно {age // 60} мин" if age > STALE_AFTER else ""
            groups.setdefault(label, []).append(self.names.item(i.key))
        parts = [", ".join(v) + (f" ({k})" if k else "") for k, v in sorted(groups.items(), key=lambda kv: kv[0] != "")]
        return "; ".join(parts)

    def _line(self, pic: HeroPicture, clock: int | None, with_tags: bool) -> str:
        head = pic.name + (" (ты)" if pic.is_me else "")
        if pic.level:
            head += f", ур. {pic.level}"
        bits = [head]
        if with_tags and pic.tags:
            bits.append(", ".join(tags_ru(pic.tags)))
        bits.append(self._items_text(pic, clock))
        value, estimate = self.networth(pic)
        if value is not None:
            bits.append(f"NW {'≈' if estimate else ''}{value}")
        return "- " + " | ".join(bits)

    def to_text(self, clock: int | None, tags: bool = True) -> str:
        if not self.heroes:
            return ""
        lines = []
        for title, group in (("Союзники", [p for p in self.heroes.values() if p.is_me] + self.allies()),
                             ("Враги", self.enemies())):
            if group:
                lines.append(f"{title}:")
                lines += [self._line(p, clock, tags) for p in group]
        totals = self.team_totals()
        if totals["advantage"] is None:
            lines.append("Перевес по фарму: неизвестен, предметов врагов не видели.")
        else:
            lines.append(f"Перевес по фарму: мы {totals['advantage']:+d} (оценка по стоимости известных предметов"
                         + (f", данные по {totals['known']} из 10 героев" if totals["partial"] else "") + ").")
        return "\n".join(lines)

    def to_dict(self, clock: int | None) -> dict:
        heroes = []
        for p in self.heroes.values():
            value, estimate = self.networth(p)
            heroes.append({
                "hero": p.hero, "team": p.team, "name": p.name, "tags": p.tags, "is_me": p.is_me, "level": p.level,
                "net_worth": value, "net_worth_estimate": estimate,
                "items": [{"key": i.key, "source": i.source, "seen_at": i.seen_at,
                           "age": clock - i.seen_at if clock is not None and i.seen_at is not None else None}
                          for i in p.items],
            })
        return {"heroes": heroes, **self.team_totals(), "clock": fmt_clock(clock) if clock is not None else None}
