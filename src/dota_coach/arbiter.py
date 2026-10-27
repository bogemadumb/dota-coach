import asyncio
import logging
import time
from dataclasses import asdict

from .bus import Bus
from .hints import Hint

log = logging.getLogger(__name__)

MODES = {
    "quiet": {"min_priority": 3, "gap": 20.0},
    "normal": {"min_priority": 2, "gap": 6.0},
    "chatty": {"min_priority": 1, "gap": 2.0},
}


class Arbiter:
    def __init__(self, cfg: dict, bus: Bus, voice, clock_fn) -> None:
        self.cfg = cfg
        self.bus = bus
        self.voice = voice
        self.clock_fn = clock_fn
        self.queue: list[Hint] = []
        self.seen: set[str] = set()
        self.last_spoken_at = float("-inf")
        self.speaking: Hint | None = None
        self.wake = asyncio.Event()
        self.spoken: list[Hint] = []

    @property
    def mode(self) -> dict:
        return MODES.get(self.cfg.get("mode", "normal"), MODES["normal"])

    def reset(self) -> None:
        self.queue.clear()
        self.seen.clear()

    def submit(self, hint: Hint) -> None:
        if hint.id in self.seen:
            return
        self.seen.add(hint.id)
        self.bus.publish("hint", asdict(hint))
        if not self.cfg.get("voice_enabled", True) or hint.priority < self.mode["min_priority"]:
            return
        self.queue = [h for h in self.queue if h.category != hint.category or not hint.category or h.priority > hint.priority]
        self.queue.append(hint)
        self.queue.sort(key=lambda h: -h.priority)
        self.wake.set()
        if hint.priority >= 3 and self.speaking and self.speaking.priority < 3:
            self.voice.interrupt()

    def _fresh(self, hint: Hint) -> bool:
        now = self.clock_fn()
        return now is None or hint.clock is None or now - hint.clock <= hint.ttl

    def next_hint(self) -> Hint | None:
        if not self.cfg.get("voice_enabled", True):
            self.queue.clear()
            return None
        self.queue = [h for h in self.queue if self._fresh(h)]
        if not self.queue:
            return None
        hint = self.queue[0]
        if hint.priority < 3 and time.monotonic() - self.last_spoken_at < self.mode["gap"]:
            return None
        return self.queue.pop(0)

    async def run(self) -> None:
        while True:
            hint = self.next_hint()
            if hint is None:
                self.wake.clear()
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
                continue
            text = hint.say_long if self.cfg.get("voice_style") == "coach" and hint.say_long else hint.say
            self.spoken.append(hint)
            self.speaking = hint
            try:
                await self.voice.speak(text)
            except Exception:
                log.exception("voice failed")
            finally:
                self.speaking = None
            self.last_spoken_at = time.monotonic()
