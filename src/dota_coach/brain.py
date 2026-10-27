"""Claude as the coach: one persistent SDK session, one request in flight, JSON answers turned into Hints."""

import asyncio
import json
import logging
import re
import statistics
import time
from collections import deque
from difflib import SequenceMatcher
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, TextBlock

from . import kb_context
from .hints import Hint
from .state import GameState
from .timers import fmt_clock

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "brain_system.md"
PERIODIC_INTERVALS = {"quiet": 120, "normal": 60, "chatty": 30}
PRIORITY = {"plan": 0, "manual": 1, "fight": 2, "death": 3, "items": 4, "item_bought": 5, "periodic": 6}
REQUEST_TTL = {"plan": 180.0, "manual": 60.0, "fight": 6.0, "death": 25.0, "items": 30.0, "item_bought": 40.0,
               "periodic": 20.0}
FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)
WORD_RE = re.compile(r"[^\w\s]")
MEMORY_ADVICES = 5
DUPLICATE_RATIO = 0.8
WARMUP_TIMEOUT = 15.0


def normalize_say(text: str) -> str:
    return " ".join(WORD_RE.sub(" ", text.lower()).split())


@dataclass
class Request:
    kind: str
    note: str
    clock: int | None
    created: float
    ttl: float


class KnowledgeNames:
    """Display names from knowledge.py; every lookup falls back to a prettified key."""

    def __init__(self) -> None:
        try:
            from . import knowledge
            self.kn = knowledge.default()
        except Exception:
            log.warning("knowledge unavailable, using plain names")
            self.kn = None
        self.abilities: dict[str, dict] = {}

    def hero(self, key: str | None) -> str:
        if self.kn and key:
            try:
                return self.kn.hero(key).name
            except Exception:
                pass
        from .summary import pretty
        return pretty(key)

    def item_info(self, key: str):
        if not self.kn:
            return None
        try:
            return self.kn.item(key)
        except Exception:
            return None

    def item(self, key: str) -> str:
        info = self.item_info(key)
        if info:
            return info.name
        from .summary import pretty
        return pretty(key)

    def ability_info(self, hero_key: str | None, key: str):
        if self.kn and hero_key:
            if hero_key not in self.abilities:
                try:
                    self.abilities[hero_key] = {a.key: a for a in self.kn.hero(hero_key).abilities}
                except Exception:
                    self.abilities[hero_key] = {}
            return self.abilities[hero_key].get(key)
        return None

    def ability(self, hero_key: str | None, key: str) -> str:
        info = self.ability_info(hero_key, key)
        if info:
            return info.name
        from .summary import pretty
        return pretty(key)

    def ultimate(self, hero_key: str | None):
        """(name, bkbpierce 'Yes'/'No'/None) of the hero's ultimate, or None."""
        if self.kn and hero_key:
            try:
                ult = self.kn.hero(hero_key).ultimate
            except Exception:
                return None
            if ult:
                return ult.name, ult.bkb_pierce if isinstance(ult.bkb_pierce, str) else None
        return None

    def tags(self, hero_key: str | None) -> list[str]:
        from .match_picture import load_hero_tags
        key = hero_key
        if self.kn and hero_key:
            try:
                key = self.kn.hero(hero_key).key
            except Exception:
                pass
        return list(load_hero_tags().get(key or "", []))


def parse_answer(text: str, kind: str) -> dict | None:
    text = FENCE_RE.sub("", text or "")
    decoder = json.JSONDecoder()
    obj = None
    pos = text.find("{")
    while pos != -1:
        try:
            candidate, _ = decoder.raw_decode(text, pos)
        except ValueError:
            pos = text.find("{", pos + 1)
            continue
        if isinstance(candidate, dict):
            obj = candidate
            break
        pos = text.find("{", pos + 1)
    if obj is None or not ("say" in obj or (kind == "plan" and "plan" in obj)):
        return None
    say = obj.get("say")
    detail = obj.get("detail")
    plan = obj.get("plan")
    if isinstance(plan, list):
        plan = "\n".join(str(line) for line in plan)
    try:
        priority = min(3, max(1, int(obj.get("priority", 2))))
    except (TypeError, ValueError):
        priority = 2
    try:
        ttl = min(180.0, max(3.0, float(obj.get("ttl", 20))))
    except (TypeError, ValueError):
        ttl = 20.0
    return {
        "say": say.strip() if isinstance(say, str) else "",
        "detail": detail.strip() if isinstance(detail, str) else "",
        "priority": priority,
        "ttl": ttl,
        "plan": plan.strip() if isinstance(plan, str) else "",
    }


def default_client_factory(options: ClaudeAgentOptions):
    return ClaudeSDKClient(options=options)


class Brain:
    def __init__(self, cfg: dict, bus, submit_hint, client_factory=None, context_fn=None, clock_fn=None,
                 now_fn=time.monotonic, draft_fn=None, refs_fn=None) -> None:
        self.cfg = cfg
        self.bus = bus
        self.submit_hint = submit_hint
        self.client_factory = client_factory or default_client_factory
        self.context_fn = context_fn or (lambda kind=None: "")
        self.clock_fn = clock_fn or (lambda: None)
        self.draft_fn = draft_fn or (lambda: None)
        self.warm_needs_draft = draft_fn is not None
        self.refs_fn = refs_fn or (lambda kind, note: "")
        self.now = now_fn
        self.pending: dict[str, Request] = {}
        self.wake = asyncio.Event()
        self.client = None
        self.generation = 0
        self.latencies: deque[float] = deque(maxlen=50)
        self.advices: deque[tuple[str, str]] = deque(maxlen=MEMORY_ADVICES)
        self.duplicates = 0
        self.last_request_clock: int | None = None
        self.warm_pending = False
        self.last_error: str | None = None
        self.in_flight: str | None = None
        self.last_periodic: int | None = None
        self.stale_session = False
        self.session_draft: tuple | None = None
        self.cards_in_prompt = False
        self.last_usage: dict | None = None
        self._clear_match()

    def _clear_match(self) -> None:
        self.calls = 0
        self.plan = ""
        self.plan_requested = False
        self.plan_failures = 0
        self.session_requests = 0
        self.carry = False
        self.session_draft = None
        self.cards_in_prompt = False
        self.advices.clear()
        self.duplicates = 0
        self.last_request_clock = None
        self.last_periodic = None

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("brain_enabled", True))

    @property
    def max_calls(self) -> int:
        return int(self.cfg.get("brain_max_calls", 120))

    def status(self) -> dict:
        lat = list(self.latencies)
        return {
            "enabled": self.enabled,
            "calls": self.calls,
            "max_calls": self.max_calls,
            "model": self.cfg.get("brain_model"),
            "last_latency": round(lat[-1], 2) if lat else None,
            "median_latency": round(statistics.median(lat), 2) if lat else None,
            "latencies": [round(x, 2) for x in lat],
            "last_error": self.last_error,
            "in_flight": self.in_flight,
            "pending": sorted(self.pending, key=PRIORITY.get),
            "has_plan": bool(self.plan),
            "duplicates": self.duplicates,
        }

    def publish_status(self) -> None:
        self.bus.publish("brain_status", self.status())

    def reset(self) -> None:
        self.generation += 1
        self.pending.clear()
        self._clear_match()
        self.last_error = None
        self.stale_session = True
        self.bus.publish("plan", "")
        self.publish_status()

    def set_enabled(self) -> None:
        if not self.enabled:
            self.pending.clear()
        self.publish_status()

    def request(self, kind: str, note: str = "") -> bool:
        if kind not in PRIORITY or not self.enabled:
            return False
        if kind == "plan":
            if self.plan_requested:
                return False
            self.plan_requested = True
        self.last_request_clock = self.clock_fn()
        self.pending[kind] = Request(kind, note, self.last_request_clock, self.now(), REQUEST_TTL[kind])
        self.wake.set()
        return True

    def warm_up(self) -> None:
        if self.enabled:
            self.warm_pending = True
            self.wake.set()

    async def _warm(self) -> None:
        self.warm_pending = False
        if self.warm_needs_draft and self._draft_key() is None:
            return
        try:
            await asyncio.wait_for(self._ensure_session(), timeout=WARMUP_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("brain warm-up failed", exc_info=True)
            await self._drop_client()

    def tick(self, state: GameState) -> None:
        clock = state.clock
        if clock is None or not self.enabled:
            return
        if state.phase != "game" or not state.alive or state.paused:
            self.last_periodic = clock
            return
        if self.last_periodic is None or clock < self.last_periodic:
            self.last_periodic = clock
            return
        interval = PERIODIC_INTERVALS.get(self.cfg.get("mode", "normal"), PERIODIC_INTERVALS["normal"])
        if clock - self.last_periodic >= interval and self.in_flight != "periodic":
            self.last_periodic = clock
            self.request("periodic")

    def _next(self) -> Request | None:
        while self.pending:
            kind = min(self.pending, key=PRIORITY.get)
            req = self.pending.pop(kind)
            if self.now() - req.created > req.ttl:
                log.info("brain request %s expired before sending", kind)
                if kind == "plan":
                    self.plan_requested = False
                continue
            return req
        return None

    async def step(self) -> bool:
        if not self.enabled:
            self.pending.clear()
            return False
        if self.calls >= self.max_calls:
            if self.pending:
                self.pending.clear()
                self.publish_status()
            return False
        req = self._next()
        if req is None:
            if self.warm_pending:
                await self._warm()
            return False
        self.warm_pending = False
        await self._process(req)
        return True

    async def drain(self) -> None:
        while await self.step():
            pass

    async def run(self) -> None:
        while True:
            if not await self.step():
                self.wake.clear()
                await self.wake.wait()

    def _memory(self) -> str:
        return "План на матч:\n" + self.plan if self.plan else ""

    def _advised(self) -> str:
        if not self.advices:
            return ""
        lines = "\n".join(f"{stamp} {say}" for stamp, say in self.advices)
        return "=== Уже советовал (не повторяй, пока ситуация не изменилась) ===\n" + lines

    def is_duplicate(self, say: str) -> bool:
        norm = normalize_say(say)
        return any(SequenceMatcher(None, norm, normalize_say(old)).ratio() >= DUPLICATE_RATIO
                   for _, old in self.advices)

    def _prompt(self, req: Request, memory: str) -> str:
        parts = [f"Тип запроса: {req.kind}"]
        if req.note:
            parts.append(req.note)
        if memory:
            parts.append("=== Память матча ===\n" + memory)
        advised = self._advised()
        if advised:
            parts.append(advised)
        parts.append("=== Сводка ===\n" + self.context_fn(req.kind))
        refs = self._refs(req)
        if refs:
            parts.append("=== Справка по предметам (официальные карточки, главнее памяти) ===\n" + refs)
        parts.append("Ответь одним JSON-объектом.")
        return "\n".join(parts)

    def _refs(self, req: Request) -> str:
        try:
            return self.refs_fn(req.kind, req.note) or ""
        except Exception:
            log.warning("brain refs failed", exc_info=True)
            return ""

    def _draft_key(self) -> tuple | None:
        try:
            info = self.draft_fn()
        except Exception:
            log.warning("brain draft lookup failed", exc_info=True)
            return None
        if not info or not info[0]:
            return None
        hero, allies, enemies = info
        return hero, tuple(sorted(allies)), tuple(sorted(enemies))

    def _system_prompt(self) -> str:
        self.cards_in_prompt = False
        if self.session_draft is not None:
            try:
                prompt = kb_context.system_prompt_for_draft(*self.session_draft)
                self.cards_in_prompt = True
                return prompt
            except Exception:
                log.warning("system prompt with cards failed, using the base one", exc_info=True)
        return PROMPT_PATH.read_text(encoding="utf-8")

    def _options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt(),
            model=self.cfg["brain_model"],
            tools=[],
            setting_sources=[],
            max_turns=1,
        )

    async def _drop_client(self) -> None:
        client, self.client = self.client, None
        if client is None:
            return
        try:
            await asyncio.wait_for(client.disconnect(), timeout=5)
        except Exception:
            log.warning("brain client disconnect failed", exc_info=True)

    async def close(self) -> None:
        await self._drop_client()

    async def _ensure_session(self) -> None:
        recycle = int(self.cfg.get("brain_recycle", 20))
        draft = self._draft_key()
        redraft = draft is not None and draft != self.session_draft
        if self.client is not None and (self.stale_session or redraft or self.session_requests >= recycle):
            await self._drop_client()
            self.carry = not self.stale_session
        self.stale_session = False
        if self.client is None:
            self.session_requests = 0
            if draft is not None:
                self.session_draft = draft
            client = self.client_factory(self._options())
            await client.connect()
            self.client = client

    async def _ask(self, req: Request) -> str:
        await self._ensure_session()
        memory = self._memory() if self.carry else ""
        self.carry = False
        await self.client.query(self._prompt(req, memory))
        text = ""
        async for msg in self.client.receive_response():
            if isinstance(msg, AssistantMessage):
                if msg.error:
                    raise RuntimeError(f"api error: {msg.error}")
                text += "".join(b.text for b in msg.content if isinstance(b, TextBlock))
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    raise RuntimeError(msg.result or msg.subtype)
                self.last_usage = msg.usage
                break
        self.session_requests += 1
        return text

    async def _process(self, req: Request) -> None:
        generation = self.generation
        self.calls += 1
        self.in_flight = req.kind
        self.publish_status()
        started = time.perf_counter()
        text, error = "", None
        try:
            text = await asyncio.wait_for(self._ask(req), timeout=float(self.cfg.get("brain_timeout", 30)))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            log.warning("brain call %s failed: %s", req.kind, error)
            await self._drop_client()
            self.carry = True
        self.in_flight = None
        if generation != self.generation:
            return
        self.latencies.append(time.perf_counter() - started)
        answer = None
        if error is None:
            answer = parse_answer(text, req.kind)
            if answer is None:
                error = "bad answer"
                log.warning("brain answer not parsed (%s): %r", req.kind, text[:300])
        self.last_error = error
        if answer is None:
            if req.kind == "plan" and not self.plan and self.plan_failures < 2:
                self.plan_failures += 1
                self.plan_requested = False
            self.publish_status()
            return
        self._deliver(req, answer)
        self.publish_status()

    def _deliver(self, req: Request, answer: dict) -> None:
        if req.kind == "plan":
            plan = answer["plan"] or answer["detail"]
            if plan:
                self.plan = plan
                self.bus.publish("plan", plan)
            else:
                self.last_error = "plan missing"
                if self.plan_failures < 2:
                    self.plan_failures += 1
                    self.plan_requested = False
        if not answer["say"]:
            return
        if req.kind != "manual" and self.is_duplicate(answer["say"]):
            self.duplicates += 1
            log.info("brain duplicate dropped (%s): %r", req.kind, answer["say"])
            return
        detail = answer["detail"]
        self.advices.append((fmt_clock(req.clock) if req.clock is not None else "--:--", answer["say"]))
        self.submit_hint(Hint(
            id=f"brain_{req.kind}_{self.calls}",
            source="brain",
            priority=3 if req.kind == "manual" else answer["priority"],
            say=answer["say"],
            clock=req.clock,
            detail=detail,
            say_long=detail if 0 < len(detail) <= 220 else "",
            ttl=answer["ttl"],
            category=f"brain_{req.kind}",
        ))
