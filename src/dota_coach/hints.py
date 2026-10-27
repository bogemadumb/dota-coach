from dataclasses import dataclass


@dataclass
class Hint:
    id: str
    source: str
    priority: int
    say: str
    clock: int | None
    detail: str = ""
    say_long: str = ""
    ttl: float = 15.0
    category: str = ""
