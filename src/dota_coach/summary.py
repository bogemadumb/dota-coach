"""Compact Russian text snapshot of the match for the model. Pure: no I/O, no clock."""

from dataclasses import asdict, is_dataclass

from .match_picture import tags_ru
from .state import GameState, Item
from .timers import fmt_clock

PHASE_RU = {
    "loading": "загрузка", "draft": "пики", "strategy": "стратегия", "pregame": "до старта",
    "game": "игра", "post": "конец", "unknown": "нет игры",
}
TEAM_RU = {"radiant": "Radiant", "dire": "Dire"}
HIDDEN_ABILITY_PREFIXES = ("special_bonus", "generic_hidden", "ability_capture")
MAX_EVENTS = 8


def pretty(key: str | None) -> str:
    if not key:
        return "?"
    key = key.removeprefix("item_").removeprefix("npc_dota_hero_")
    return key.replace("_", " ").title()


class PlainNames:
    def hero(self, key: str | None) -> str:
        return pretty(key)

    def item(self, key: str) -> str:
        return pretty(key)

    def ability(self, hero_key: str | None, key: str) -> str:
        return pretty(key)

    def ability_info(self, hero_key: str | None, key: str):
        return None

    def ultimate(self, hero_key: str | None):
        return None

    def tags(self, hero_key: str | None) -> list[str]:
        return []


def _items(items: list[Item], names) -> str:
    if not items:
        return "—"
    out = []
    for i in items:
        label = names.item(i.name)
        if i.charges:
            label += f" x{i.charges}"
        if i.cooldown > 0:
            label += f" (откат {int(i.cooldown + 0.999)} с)"
        out.append(label)
    return ", ".join(out)


def _event(e: dict, names) -> str | None:
    kind, data = e.get("kind"), e.get("data") or {}
    clock = e.get("clock")
    stamp = fmt_clock(clock) if clock is not None else "--:--"
    if kind == "hero_died":
        text = f"игрок погиб, возрождение {data.get('respawn_seconds', '?')} с"
    elif kind == "hero_respawned":
        text = "игрок возродился"
    elif kind == "level_up":
        text = f"уровень {data.get('level')}"
    elif kind == "item_added":
        text = f"получен {names.item(data.get('item', ''))}"
    elif kind == "item_removed":
        text = f"ушёл {names.item(data.get('item', ''))}"
    elif kind == "phase_changed":
        text = f"фаза: {PHASE_RU.get(data.get('new'), data.get('new'))}"
    elif kind == "game_event":
        text = f"событие {data.get('type')}"
    elif kind in ("hero_picked", "hero_banned"):
        verb = "пик" if kind == "hero_picked" else "бан"
        text = f"{verb} {TEAM_RU.get(data.get('team'), data.get('team'))}: {names.hero(data.get('hero'))}"
    else:
        return None
    return f"{stamp} {text}"


BKB_RU = {"Yes": "да", "No": "нет"}


def _ability_facts(info) -> str:
    if info is None:
        return ""
    stats = ", ".join(x for x in (f"кд {info.cooldown}" if info.cooldown else "", f"мана {info.mana}" if info.mana else "") if x)
    text = f" [{stats}]" if stats else ""
    return text + (f": {info.desc}" if info.desc else "")


def _enemy_line(hero: str, names) -> str:
    bits = []
    ult = names.ultimate(hero)
    if ult:
        bits.append(f"ульта {ult[0]}, пробивает BKB: {BKB_RU.get(ult[1], 'нет данных')}")
    tags = names.tags(hero)
    if tags:
        bits.append("черты: " + ", ".join(tags_ru(tags)))
    return f"- {names.hero(hero)}" + (": " + "; ".join(bits) if bits else "") + "."


def _extra(extra: dict) -> list[str]:
    lines = []
    for key, value in extra.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            value = ", ".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, (list, tuple)):
            value = "; ".join(str(v) for v in value)
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{key}:\n{value}")
            continue
        lines.append(f"{key}: {value}")
    return lines


def build_summary(state: GameState | None, events=(), extra: dict | None = None, names=None, slim: bool = False) -> str:
    if state is None:
        return "Данных от игры пока нет."
    names = names or PlainNames()
    lines = []
    clock = fmt_clock(state.clock) if state.clock is not None else "--:--"
    day = "" if state.daytime is None else (", день" if state.daytime else ", ночь")
    pause = ", пауза" if state.paused else ""
    lines.append(f"Время {clock} ({PHASE_RU.get(state.phase, state.phase)}{day}{pause}). Мы: {TEAM_RU.get(state.team, state.team or '?')}.")

    if state.hero:
        status = "жив" if state.alive else f"мёртв, возрождение через {state.respawn_seconds} с"
        lines.append(f"Герой: {names.hero(state.hero)}, ур. {state.level}, {status}. "
                     f"K/D/A {state.kills}/{state.deaths}/{state.assists}, LH/DN {state.last_hits}/{state.denies}, "
                     f"GPM/XPM {state.gpm}/{state.xpm}. HP {state.health_percent}%, мана {state.mana_percent}%.")
        if state.buyback_cooldown > 0:
            buyback = f"откат {state.buyback_cooldown} с"
        else:
            buyback = "хватает золота" if state.gold >= state.buyback_cost else "не хватает золота"
        lines.append(f"Золото {state.gold} (надёжное {state.gold_reliable}, ненадёжное {state.gold_unreliable}). "
                     f"Выкуп {state.buyback_cost}, {buyback}.")
        lines.append(f"Предметы: {_items(state.inventory, names)}. Рюкзак: {_items(state.backpack, names)}. "
                     f"Тайник: {_items(state.stash, names)}. "
                     f"Нейтралка: {_items([state.neutral], names) if state.neutral else '—'}.")
        abilities = []
        for a in state.abilities:
            if a.name.startswith(HIDDEN_ABILITY_PREFIXES) or "empty" in a.name:
                continue
            if a.cooldown > 0:
                tail = f"откат {int(a.cooldown + 0.999)} с"
            elif a.passive:
                tail = "пассивка"
            else:
                tail = "готово" if a.level and a.can_cast else ""
            abilities.append(f"- {names.ability(state.hero, a.name)} ур.{a.level}" + (f" ({tail})" if tail else "")
                             + ("" if slim else _ability_facts(names.ability_info(state.hero, a.name))))
        lines.append("Способности:\n" + "\n".join(abilities) if abilities else "Способности: —.")

    draft = state.draft
    if draft and (draft.picks["radiant"] or draft.picks["dire"]):
        if state.team in draft.picks:
            other = "dire" if state.team == "radiant" else "radiant"
            allies = [h for h in draft.picks[state.team] if h != state.hero]
            lines.append("Союзники: " + (", ".join(names.hero(h) for h in allies) or "—") + ".")
            enemies = draft.picks[other]
            if enemies and not slim and any(names.ultimate(h) or names.tags(h) for h in enemies):
                lines.append("Враги:\n" + "\n".join(_enemy_line(h, names) for h in enemies))
            else:
                lines.append("Враги: " + (", ".join(names.hero(h) for h in enemies) or "—") + ".")
        else:
            for team in ("radiant", "dire"):
                lines.append(f"{TEAM_RU[team]}: " + (", ".join(names.hero(h) for h in draft.picks[team]) or "—") + ".")
        bans = draft.bans["radiant"] + draft.bans["dire"]
        if bans:
            lines.append("Баны: " + ", ".join(names.hero(h) for h in bans) + ".")

    if extra:
        lines += _extra(extra)

    dicts = [e if isinstance(e, dict) else asdict(e) for e in events if isinstance(e, dict) or is_dataclass(e)]
    recent = [t for t in (_event(e, names) for e in dicts if e.get("kind") != "tick") if t][-MAX_EVENTS:]
    if recent:
        lines.append("Последние события: " + "; ".join(recent) + ".")
    return "\n".join(lines)
