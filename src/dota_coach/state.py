from dataclasses import dataclass, field


@dataclass
class Item:
    name: str
    slot: str
    charges: int | None = None
    cooldown: float = 0.0
    can_cast: bool = False


@dataclass
class Ability:
    name: str
    level: int = 0
    cooldown: float = 0.0
    can_cast: bool = False
    ultimate: bool = False
    passive: bool = False


@dataclass
class Draft:
    active_team: str | None = None
    is_pick: bool = False
    picks: dict[str, list[str]] = field(default_factory=lambda: {"radiant": [], "dire": []})
    bans: dict[str, list[str]] = field(default_factory=lambda: {"radiant": [], "dire": []})


@dataclass
class GameState:
    received_at: float
    match_id: str | None = None
    phase: str = "unknown"
    clock: int | None = None
    daytime: bool | None = None
    paused: bool = False
    team: str | None = None
    gold: int = 0
    gold_reliable: int = 0
    gold_unreliable: int = 0
    gpm: int = 0
    xpm: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    last_hits: int = 0
    denies: int = 0
    hero: str | None = None
    hero_id: int | None = None
    level: int = 0
    alive: bool = True
    respawn_seconds: int = 0
    buyback_cost: int = 0
    buyback_cooldown: int = 0
    health_percent: int = 100
    mana_percent: int = 100
    xpos: int | None = None
    ypos: int | None = None
    abilities: list[Ability] = field(default_factory=list)
    inventory: list[Item] = field(default_factory=list)
    backpack: list[Item] = field(default_factory=list)
    stash: list[Item] = field(default_factory=list)
    neutral: Item | None = None
    teleport: Item | None = None
    draft: Draft | None = None
    game_events: list[dict] = field(default_factory=list)

    def item_names(self) -> list[str]:
        items = self.inventory + self.backpack + self.stash
        if self.neutral:
            items.append(self.neutral)
        return [i.name for i in items]


@dataclass
class Event:
    kind: str
    clock: int | None
    data: dict = field(default_factory=dict)
