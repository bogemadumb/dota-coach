"""The only module that knows GSI field names. If the real client sends something else, fix it here."""

import time

from .state import Ability, Draft, GameState, Item

PHASES = {
    "DOTA_GAMERULES_STATE_INIT": "loading",
    "DOTA_GAMERULES_STATE_WAIT_FOR_PLAYERS_TO_LOAD": "loading",
    "DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD": "loading",
    "DOTA_GAMERULES_STATE_CUSTOM_GAME_SETUP": "loading",
    "DOTA_GAMERULES_STATE_PLAYER_DRAFT": "draft",
    "DOTA_GAMERULES_STATE_HERO_SELECTION": "draft",
    "DOTA_GAMERULES_STATE_STRATEGY_TIME": "strategy",
    "DOTA_GAMERULES_STATE_TEAM_SHOWCASE": "strategy",
    "DOTA_GAMERULES_STATE_PRE_GAME": "pregame",
    "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS": "game",
    "DOTA_GAMERULES_STATE_POST_GAME": "post",
    "DOTA_GAMERULES_STATE_DISCONNECT": "post",
}

TEAMS = {"team2": "radiant", "team3": "dire", 2: "radiant", 3: "dire"}
HERO_PREFIX = "npc_dota_hero_"


def hero_short(name: str | None) -> str | None:
    if not name:
        return None
    return name[len(HERO_PREFIX):] if name.startswith(HERO_PREFIX) else name


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _item(slot: str, raw: dict) -> Item | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not name or name == "empty":
        return None
    return Item(
        name=name,
        slot=slot,
        charges=raw.get("charges"),
        cooldown=float(raw.get("cooldown") or 0),
        can_cast=bool(raw.get("can_cast")),
    )


def _items(raw: dict, prefix: str) -> list[Item]:
    keys = sorted((k for k in raw if k.startswith(prefix)), key=lambda k: _int(k[len(prefix):]))
    found = (_item(k, raw[k]) for k in keys)
    return [i for i in found if i]


def _draft(raw: dict) -> Draft | None:
    if not isinstance(raw, dict) or not raw:
        return None
    draft = Draft(active_team=TEAMS.get(raw.get("activeteam")), is_pick=bool(raw.get("pick")))
    for key, team in (("team2", "radiant"), ("team3", "dire")):
        side = raw.get(key) or {}
        for kind, target in (("pick", draft.picks), ("ban", draft.bans)):
            names = []
            for i in range(10):
                cls = side.get(f"{kind}{i}_class")
                if cls:
                    names.append(hero_short(cls))
            target[team] = names
    return draft


def parse(payload: dict, received_at: float | None = None) -> GameState:
    m = payload.get("map") or {}
    p = payload.get("player") or {}
    h = payload.get("hero") or {}
    items = payload.get("items") or {}
    abilities = payload.get("abilities") or {}

    state = GameState(received_at=received_at if received_at is not None else time.time())
    state.match_id = str(m["matchid"]) if m.get("matchid") else None
    state.phase = PHASES.get(m.get("game_state"), "unknown")
    state.clock = _int(m["clock_time"]) if "clock_time" in m else None
    state.daytime = m.get("daytime")
    state.paused = bool(m.get("paused"))

    state.team = p.get("team_name") or None
    state.gold = _int(p.get("gold"))
    state.gold_reliable = _int(p.get("gold_reliable"))
    state.gold_unreliable = _int(p.get("gold_unreliable"))
    state.gpm = _int(p.get("gpm"))
    state.xpm = _int(p.get("xpm"))
    state.kills = _int(p.get("kills"))
    state.deaths = _int(p.get("deaths"))
    state.assists = _int(p.get("assists"))
    state.last_hits = _int(p.get("last_hits"))
    state.denies = _int(p.get("denies"))

    state.hero = hero_short(h.get("name"))
    state.hero_id = _int(h["id"]) if "id" in h else None
    state.level = _int(h.get("level"))
    state.alive = bool(h.get("alive", True))
    state.respawn_seconds = _int(h.get("respawn_seconds"))
    state.buyback_cost = _int(h.get("buyback_cost"))
    state.buyback_cooldown = _int(h.get("buyback_cooldown"))
    state.health_percent = _int(h.get("health_percent"), 100)
    state.mana_percent = _int(h.get("mana_percent"), 100)
    state.xpos = _int(h["xpos"]) if "xpos" in h else None
    state.ypos = _int(h["ypos"]) if "ypos" in h else None

    for key in sorted(abilities, key=lambda k: _int(k.removeprefix("ability"))):
        a = abilities[key]
        if isinstance(a, dict) and a.get("name"):
            state.abilities.append(Ability(
                name=a["name"],
                level=_int(a.get("level")),
                cooldown=float(a.get("cooldown") or 0),
                can_cast=bool(a.get("can_cast")),
                ultimate=bool(a.get("ultimate")),
                passive=bool(a.get("passive")),
            ))

    inv = _items(items, "slot")
    state.inventory = [i for i in inv if _int(i.slot[4:]) < 6]
    state.backpack = [i for i in inv if _int(i.slot[4:]) >= 6]
    state.stash = _items(items, "stash")
    state.neutral = _item("neutral0", items.get("neutral0"))
    state.teleport = _item("teleport0", items.get("teleport0"))

    state.draft = _draft(payload.get("draft"))
    events = payload.get("events")
    state.game_events = events if isinstance(events, list) else []
    return state


def auth_token(payload: dict) -> str | None:
    return (payload.get("auth") or {}).get("token")
