"""Rule-based timing hints. No model calls: everything here must be exact to the second."""

import logging
from pathlib import Path

import yaml

from .config import ROOT
from .hints import Hint

TIMINGS_PATH = ROOT / "data" / "timings.yaml"
log = logging.getLogger(__name__)


WINDOW = 3


def fmt_clock(seconds: int) -> str:
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    return f"{sign}{seconds // 60}:{seconds % 60:02d}"


class Timers:
    def __init__(self, path: Path = TIMINGS_PATH) -> None:
        data: dict = {}
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            log.warning("timings file not found: %s, running without timers", path)
        self.patch = data.get("patch")
        self.schedule: list[dict] = data.get("schedule") or []
        self.relative: dict[str, list[dict]] = data.get("relative") or {}
        self.pending: list[tuple[int, dict, str]] = []
        self.fired: set[str] = set()
        self.last_clock: int | None = None

    def reset(self) -> None:
        self.pending.clear()
        self.fired.clear()
        self.last_clock = None

    def mark(self, trigger: str, clock: int) -> int:
        self.pending = [p for p in self.pending if not p[2].startswith(f"{trigger}@")]
        for rule in self.relative.get(trigger, []):
            self.pending.append((clock + int(rule["after"]), rule, f"{trigger}@{clock}"))
        return len(self.relative.get(trigger, []))

    def _occurrences(self, rule: dict, clock: int) -> list[int]:
        if "times" in rule:
            return [int(t) for t in rule["times"]]
        first, interval = int(rule["first"]), int(rule["interval"])
        until = int(rule.get("until", 10_000))
        horizon = clock + int(rule.get("lead", 0))
        k = (horizon - first) // interval
        out = []
        while k >= 0 and first + interval * k > horizon - WINDOW:
            if first + interval * k <= until:
                out.append(first + interval * k)
            k -= 1
        return out

    def check(self, clock: int, state=None) -> list[Hint]:
        if self.last_clock is not None and clock < self.last_clock:
            self.fired.clear()
            self.pending.clear()
        self.last_clock = clock
        hints: list[Hint] = []
        for rule in self.schedule:
            if not self._applies(rule, state):
                continue
            for at in self._occurrences(rule, clock):
                hints += self._fire(rule, at, clock, rule["id"])
        for at, rule, key in self.pending:
            if not self._applies(rule, state):
                continue
            hints += self._fire(rule, at, clock, f"{rule['id']}:{key}")
        return hints

    def _applies(self, rule: dict, state) -> bool:
        if state is None:
            return True
        need = rule.get("when")
        if need == "night" and state.daytime is not False:
            return False
        if need == "day" and state.daytime is not True:
            return False
        return True

    def _fire(self, rule: dict, at: int, clock: int, key: str) -> list[Hint]:
        lead = int(rule.get("lead", 0))
        fire_at = at - lead
        if not (fire_at <= clock < fire_at + WINDOW):
            return []
        hint_id = f"{key}@{at}"
        if hint_id in self.fired:
            return []
        self.fired.add(hint_id)
        values = {"lead": lead, "at": fmt_clock(at)}
        return [Hint(
            id=hint_id,
            source="timers",
            priority=int(rule.get("priority", 2)),
            say=rule["say"].format(**values),
            say_long=rule.get("say_long", "").format(**values),
            detail=rule.get("detail", "").format(**values),
            clock=clock,
            ttl=float(rule.get("ttl", max(lead, 5))),
            category=rule.get("category", rule["id"]),
        )]
