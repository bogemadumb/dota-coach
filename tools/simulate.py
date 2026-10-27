"""Fake Dota 2 match: sends GSI-shaped JSON to the coach server, one payload per game second."""

import argparse
import random
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach.config import load  # noqa: E402

RADIANT = ["nevermore", "crystal_maiden", "mars", "antimage", "lion"]
DIRE = ["puck", "pudge", "slark", "phantom_assassin", "zuus"]
CORE_BUYS = [
    (-88, "item_tango", 90), (-87, "item_branches", 50), (-86, "item_branches", 50),
    (-85, "item_faerie_fire", 65), (None, "item_bottle", 675), (None, "item_magic_wand", 450),
    (None, "item_power_treads", 1400), (None, "item_blink", 2250), (None, "item_black_king_bar", 4050),
    (None, "item_satanic", 5050),
]
SUPPORT_BUYS = [
    (-88, "item_tango", 90), (-87, "item_branches", 50), (-86, "item_branches", 50),
    (-85, "item_ward_sentry", 50), (None, "item_magic_wand", 450), (None, "item_arcane_boots", 1500),
    (None, "item_glimmer_cape", 2150), (None, "item_force_staff", 2200), (None, "item_blink", 2250),
    (None, "item_ultimate_scepter", 4200),
]
CONSUMED = {"item_faerie_fire": 160, "item_tango": 200}
COSTS = {name: cost for _, name, cost in CORE_BUYS + SUPPORT_BUYS}
MAIN_SLOTS = 6
HEROES = {
    "nevermore": {
        "id": 11, "buys": CORE_BUYS, "last_hit_rate": 0.09, "income": 2.0,
        "abilities": [
            ("nevermore_shadowraze1", 10, False), ("nevermore_shadowraze2", 10, False), ("nevermore_shadowraze3", 10, False),
            ("nevermore_necromastery", 0, False), ("nevermore_dark_lord", 0, False), ("nevermore_requiem", 120, True),
        ],
    },
    "lion": {
        "id": 26, "buys": SUPPORT_BUYS, "last_hit_rate": 0.012, "income": 1.7,
        "abilities": [
            ("lion_impale", 12, False), ("lion_voodoo", 14, False), ("lion_mana_drain", 6, False),
            ("lion_to_hell_and_back", 0, False), ("lion_finger_of_death", 110, True),
        ],
    },
}
GAME_STATE = {
    "draft": "DOTA_GAMERULES_STATE_HERO_SELECTION",
    "strategy": "DOTA_GAMERULES_STATE_STRATEGY_TIME",
    "pregame": "DOTA_GAMERULES_STATE_PRE_GAME",
    "game": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
    "post": "DOTA_GAMERULES_STATE_POST_GAME",
}


class Match:
    def __init__(self, token: str, seed: int, hero: str = "nevermore") -> None:
        self.profile = HEROES[hero]
        self.hero = hero
        self.abilities = self.profile["abilities"]
        self.rng = random.Random(seed)
        self.token = token
        self.match_id = str(self.rng.randint(8_000_000_000, 8_999_999_999))
        self.gold = 600.0
        self.items: list[str] = []
        self.buy_index = 0
        self.cooldowns = {name: 0.0 for name, _, _ in self.abilities}
        self.alive = True
        self.respawn = 0
        self.deaths = 0
        self.kills = 0
        self.last_hits = 0
        self.events: list[dict] = []

    def draft(self, step: int) -> dict:
        order = [(t, i) for i in range(5) for t in ("team2", "team3")]
        picked = order[: min(step, len(order))]
        data = {"activeteam": 2 if step % 2 == 0 else 3, "pick": True, "team2": {"home_team": True}, "team3": {"home_team": False}}
        for team, i in picked:
            heroes = RADIANT if team == "team2" else DIRE
            data[team][f"pick{i}_class"] = heroes[i]
            data[team][f"pick{i}_id"] = 0
        return data

    def advance(self, clock: int) -> None:
        if clock >= 0 and self.alive:
            self.gold += self.profile["income"] + clock / 60 * 0.2
            if self.rng.random() < self.profile["last_hit_rate"] + min(clock / 20000, 0.03):
                self.last_hits += 1
                self.gold += 45
        if clock == 430 and self.alive:
            self.alive, self.respawn, self.deaths = False, 22, self.deaths + 1
            self.gold *= 0.85
        elif clock == 1020 and self.alive:
            self.alive, self.respawn, self.deaths = False, 41, self.deaths + 1
        if not self.alive:
            self.respawn -= 1
            if self.respawn <= 0:
                self.alive = True
        if clock in (300, 610, 900, 1300):
            self.kills += 1
            self.gold += 250
        buys = self.profile["buys"]
        while self.buy_index < len(buys):
            at, item, cost = buys[self.buy_index]
            ready = clock >= at if at is not None else self.gold >= cost
            if not ready or self.gold < cost:
                break
            self.gold -= cost
            if len(self.items) >= MAIN_SLOTS:
                self.items.remove(min(self.items, key=lambda n: (COSTS.get(n, 0), n != "item_branches")))
            self.items.append(item)
            self.buy_index += 1
        for item, at in CONSUMED.items():
            if clock == at and item in self.items:
                self.items.remove(item)
        for name, cd, ult in self.abilities:
            self.cooldowns[name] = max(0.0, self.cooldowns[name] - 1)
            if cd and self.alive and self.cooldowns[name] == 0 and clock > 0 and self.rng.random() < (0.02 if ult else 0.15):
                self.cooldowns[name] = cd
        if clock == 1110:
            self.events.append({"game_time": 1200, "event_type": "roshan_killed", "team": "dire"})

    def payload(self, phase: str, clock: int, step: int) -> dict:
        level = 1 if clock < 0 else min(30, 1 + clock // 70)
        items = {f"slot{i}": {"name": "empty"} for i in range(9)}
        for i, name in enumerate(self.items[:9]):
            items[f"slot{i}"] = {"name": name, "can_cast": True, "cooldown": 0, "passive": False}
        items["neutral0"] = {"name": "item_arcane_ring" if clock >= 420 else "empty"}
        items["teleport0"] = {"name": "item_tpscroll", "charges": 1, "cooldown": 0}
        abilities = {}
        for i, (name, _, ult) in enumerate(self.abilities):
            lvl = 0 if clock < 0 else min(3 if ult else 4, max(0, (level - (6 if ult else i)) // (5 if ult else 2) + (1 if level > (6 if ult else i) else 0)))
            abilities[f"ability{i}"] = {
                "name": name, "level": lvl, "can_cast": lvl > 0 and self.cooldowns[name] == 0,
                "passive": name.endswith(("necromastery", "dark_lord")), "ability_active": True,
                "cooldown": int(self.cooldowns[name]), "ultimate": ult,
            }
        gold = int(self.gold)
        data = {
            "provider": {"name": "Dota 2", "appid": 570, "version": 47, "timestamp": int(time.time())},
            "map": {
                "name": "start", "matchid": self.match_id, "game_time": clock + 90, "clock_time": clock,
                "daytime": (clock // 300) % 2 == 0 if clock >= 0 else True, "nightstalker_night": False,
                "game_state": GAME_STATE[phase], "paused": False, "win_team": "none",
                "radiant_score": self.kills + 3, "dire_score": self.deaths + 4,
            },
            "player": {
                "steamid": "76561198000000000", "name": "sim", "activity": "playing", "kills": self.kills,
                "deaths": self.deaths, "assists": self.kills // 2, "last_hits": self.last_hits, "denies": self.last_hits // 8,
                "team_name": "radiant", "gold": gold, "gold_reliable": gold // 4, "gold_unreliable": gold - gold // 4,
                "gpm": int((gold + 2000) / max(clock / 60, 1)) if clock > 0 else 0, "xpm": 400 if clock > 0 else 0,
            },
            "hero": {
                "id": self.profile["id"], "name": f"npc_dota_hero_{self.hero}", "level": level, "alive": self.alive,
                "respawn_seconds": max(self.respawn, 0) if not self.alive else 0, "buyback_cost": 200 + clock,
                "buyback_cooldown": 0, "health_percent": 100 if self.alive else 0, "mana_percent": 80,
                "xpos": -1500 + self.rng.randint(-200, 200), "ypos": -1200 + self.rng.randint(-200, 200),
            },
            "abilities": abilities,
            "items": items,
            "auth": {"token": self.token},
        }
        if phase == "draft":
            data["draft"] = self.draft(step)
            data["hero"] = {}
            data["abilities"] = {}
            data["items"] = {}
        if self.events:
            data["events"] = list(self.events)
        return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speed", type=float, default=10.0, help="game seconds per real second")
    parser.add_argument("--minutes", type=int, default=25)
    parser.add_argument("--start", type=int, default=None, help="skip to this clock second")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--hero", choices=sorted(HEROES), default="nevermore", help="own hero: core or support profile")
    args = parser.parse_args()

    cfg = load()
    url = f"http://{cfg['host']}:{cfg['port']}/gsi"
    match = Match(cfg["gsi_token"], args.seed, args.hero)
    timeline = [("draft", -150 + s, s) for s in range(0, 11)] + [("strategy", -100 + s, 0) for s in range(10)]
    timeline += [("pregame", c, 0) for c in range(-90, 0)] + [("game", c, 0) for c in range(0, args.minutes * 60 + 1)]
    timeline += [("post", args.minutes * 60, 0)]
    delay = 1 / args.speed
    with httpx.Client(timeout=2) as client:
        for phase, clock, step in timeline:
            if phase in ("pregame", "game"):
                match.advance(clock)
            if args.start is not None and clock < args.start and phase != "draft":
                continue
            client.post(url, json=match.payload(phase, clock, step))
            time.sleep(delay)


if __name__ == "__main__":
    main()
