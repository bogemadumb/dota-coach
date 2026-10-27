import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from . import gsi_fields
from .arbiter import MODES, Arbiter
from .brain import Brain, KnowledgeNames
from .bus import Bus
from . import kb_context
from .config import ROOT
from .events import EventDetector
from .items import ROLE_SETTINGS, Advice, ItemAdvisor, ItemsTrigger
from .match_picture import MatchPicture
from .state import GameState
from .summary import build_summary
from .timers import TIMINGS_PATH, Timers
from .voice import Voice

log = logging.getLogger(__name__)

PANEL = Path(__file__).parent / "panel" / "index.html"
LOG_DIR = ROOT / "logs"
VOICE_STYLES = ("commands", "coach")
TRIGGER_RE = re.compile(r"^[a-z0-9_]{1,40}$")
KEY_ITEMS = {
    "item_blink", "item_overwhelming_blink", "item_swift_blink", "item_arcane_blink", "item_black_king_bar",
    "item_aeon_disk", "item_sphere", "item_lotus_orb", "item_force_staff", "item_cyclone", "item_glimmer_cape",
    "item_ghost", "item_manta", "item_orchid", "item_bloodthorn", "item_blade_mail", "item_sheepstick",
}
KEY_ITEM_COST = 2000
PICTURE_KINDS = {"plan", "death", "items", "periodic", "item_bought"}
ADVICE_REFRESH = 3
DEATH_GOLD = 1000


class Core:
    def __init__(self, cfg: dict, voice=None, timings_path: Path = TIMINGS_PATH, client_factory=None) -> None:
        self.cfg = cfg
        self.bus = Bus()
        self.timers = Timers(timings_path)
        self.arbiter = Arbiter(cfg, self.bus, voice if voice is not None else Voice(cfg), self.clock)
        self.detector = EventDetector()
        self.names = KnowledgeNames()
        self.picture = MatchPicture(self.names)
        self.advisor = ItemAdvisor(self.names, self.picture)
        self.items_trigger = ItemsTrigger()
        self.advice = Advice()
        self.advice_at: int | None = None
        self.brain = Brain(cfg, self.bus, self.arbiter.submit, client_factory=client_factory,
                           context_fn=self.brain_context, clock_fn=self.clock,
                           draft_fn=self.draft_info, refs_fn=self.brain_refs)
        self.state: GameState | None = None
        self.recent_events: list[dict] = []
        self._raw_log = None

    def clock(self) -> int | None:
        return self.state.clock if self.state else None

    def brain_context(self, kind: str | None = None) -> str:
        extra = {}
        if kind in PICTURE_KINDS:
            extra["Картина матча"] = self.picture.to_text(self.clock(), tags=False)
            extra["Покупки"] = self.refresh_items(force=True).to_text()
        return build_summary(self.state, self.recent_events, extra=extra, names=self.names, slim=self.brain.cards_in_prompt)

    def draft_info(self) -> tuple[str, list[str], list[str]] | None:
        state = self.state
        if not state or not state.hero:
            return None
        picks = state.draft.picks if state.draft else {}
        if state.team not in picks:
            return state.hero, [], []
        other = "dire" if state.team == "radiant" else "radiant"
        allies = [h for h in picks[state.team] if h != state.hero]
        return state.hero, allies, list(picks[other])

    def brain_refs(self, kind: str, note: str) -> str:
        if kind == "manual":
            return kb_context.item_cards_for_text(note)
        if kind == "items":
            return kb_context.item_cards_for_keys([c.key for c in self.advice.candidates[:kb_context.MAX_ITEM_CARDS]])
        return ""

    def refresh_items(self, force: bool = False) -> Advice:
        clock = self.clock()
        if not force and clock is not None and self.advice_at is not None and 0 <= clock - self.advice_at < ADVICE_REFRESH:
            return self.advice
        advice = self.advisor.compute(self.state, self.cfg.get("role", "auto"))
        changed = advice.signature() != self.advice.signature()
        self.advice, self.advice_at = advice, clock
        if changed:
            self.bus.publish("items", self.items_payload())
        return advice

    def items_payload(self) -> dict:
        return self.advice.to_dict()

    def see_items(self, hero: str, items: list[str], source: str, clock: int | None = None, **kwargs) -> list[str]:
        """Entry point for scout / realtime / screen readers."""
        clock = self.clock() if clock is None else clock
        new = self.picture.update_seen(hero, items, source, clock, **kwargs)
        pic = self.picture.heroes.get(gsi_fields.hero_short(hero))
        if pic and pic.team and pic.team != self.picture.team:
            key_new = [k for k in new if self.is_key_item("item_" + k)]
            if key_new:
                self.items_trigger.mark(clock)
                shown = ", ".join(self.names.item(k) for k in key_new)
                self.brain.request("items", f"У врага {pic.name} впервые замечен ключевой предмет: {shown}.")
        self.refresh_items(force=True)
        return new

    def is_key_item(self, name: str) -> bool:
        if name in KEY_ITEMS:
            return True
        info = self.names.item_info(name)
        return bool(info and info.cost >= KEY_ITEM_COST and info.components
                    and info.neutral_tier is None and not info.is_recipe)

    def brain_event(self, event, state: GameState, replay: bool) -> None:
        if replay:
            return
        if event.kind == "phase_changed" and event.data.get("new") == "pregame" and event.data.get("old") in ("draft", "strategy"):
            self.brain.request("plan")
        elif state.phase not in ("pregame", "game"):
            return
        elif event.kind == "hero_died":
            note = f"Игрок погиб, возрождение через {event.data.get('respawn_seconds', '?')} с."
            if state.gold >= DEATH_GOLD:
                note += f" Золото {state.gold} можно потратить на покупку."
            self.items_trigger.mark(event.clock)
            self.brain.request("death", note)
        elif event.kind == "item_added" and self.is_key_item(event.data.get("item", "")):
            name = self.names.item(event.data["item"])
            self.brain.request("item_bought", f"Игрок получил ключевой предмет: {name}.")

    def mark(self, trigger: str, clock: int) -> int:
        return self.timers.mark(trigger, clock)

    def settings(self) -> dict:
        return {
            "mode": self.cfg.get("mode", "normal"),
            "voice_style": self.cfg.get("voice_style", "commands"),
            "voice_enabled": bool(self.cfg.get("voice_enabled", True)),
            "brain_enabled": bool(self.cfg.get("brain_enabled", True)),
            "role": self.cfg.get("role", "auto"),
        }

    def update_settings(self, patch: dict) -> str | None:
        valid = {
            "mode": lambda v: isinstance(v, str) and v in MODES,
            "voice_style": lambda v: isinstance(v, str) and v in VOICE_STYLES,
            "voice_enabled": lambda v: isinstance(v, bool),
            "brain_enabled": lambda v: isinstance(v, bool),
            "role": lambda v: isinstance(v, str) and v in ROLE_SETTINGS,
        }
        for key, value in patch.items():
            if key not in valid:
                return f"unknown setting: {key}"
            if not valid[key](value):
                return f"bad value for {key}"
        self.cfg.update(patch)
        if patch.get("voice_enabled") is False:
            self.arbiter.queue.clear()
            self.arbiter.voice.interrupt()
        if "brain_enabled" in patch:
            self.brain.set_enabled()
        if "role" in patch:
            self.refresh_items(force=True)
        self.bus.publish("settings", self.settings())
        return None

    def ingest(self, payload: dict) -> None:
        if self.cfg.get("log_raw_gsi"):
            self._log_raw(payload)
        state = gsi_fields.parse(payload)
        prev = self.state
        if state.draft is None and prev and prev.draft and prev.match_id == state.match_id:
            state.draft = prev.draft
        events = self.detector.feed(state)
        self.state = state
        self.picture.update_state(state)
        self.bus.publish("state", state)
        replay = any(e.kind == "match_started" for e in events)
        for event in events:
            if event.kind == "match_started":
                self.recent_events = []
                self.timers.reset()
                self.arbiter.reset()
                self.brain.reset()
                self.brain.warm_up()
                self.picture.reset()
                self.picture.update_state(state)
                self.advisor.reset()
                self.items_trigger.reset()
                self.advice, self.advice_at = Advice(), None
            elif event.kind == "tick":
                self._tick(event.clock, state)
            elif event.kind == "game_event" and event.data.get("type") == "roshan_killed" and not replay:
                if event.clock is not None:
                    self.mark("roshan_killed", event.clock)
            self.brain_event(event, state, replay)
            if event.kind != "tick":
                self.recent_events = (self.recent_events + [asdict(event)])[-50:]
            self.bus.publish("event", event)

    def _tick(self, clock: int | None, state: GameState) -> None:
        if clock is None:
            return
        self.brain.tick(state)
        advice = self.refresh_items()
        reason = self.items_trigger.check(state, advice, self.brain.last_request_clock)
        if reason:
            self.brain.request("items", reason)
        if not self.brain.plan_requested and state.hero and state.draft and len(state.draft.picks["radiant"]) + len(state.draft.picks["dire"]) >= 10:
            self.brain.request("plan")
        try:
            for hint in self.timers.check(clock, state):
                self.arbiter.submit(hint)
        except Exception:
            log.exception("timers failed at clock %s", clock)

    def _log_raw(self, payload: dict) -> None:
        if self._raw_log is None:
            LOG_DIR.mkdir(exist_ok=True)
            name = time.strftime("gsi-%Y%m%d-%H%M%S.jsonl")
            self._raw_log = open(LOG_DIR / name, "a", encoding="utf-8")
        self._raw_log.write(json.dumps({"t": time.time(), "payload": payload}, ensure_ascii=False) + "\n")
        self._raw_log.flush()


def snapshot(state: GameState | None) -> dict | None:
    if state is None:
        return None
    data = asdict(state)
    data.pop("game_events", None)
    return data


def create_app(cfg: dict, core: Core | None = None) -> FastAPI:
    core = core or Core(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(core.arbiter.run())
        brain_task = asyncio.create_task(core.brain.run())
        try:
            yield
        finally:
            for t in (task, brain_task):
                t.cancel()
                with suppress(asyncio.CancelledError):
                    await t
            await core.brain.close()
            core.arbiter.voice.interrupt()

    app = FastAPI(lifespan=lifespan)
    app.state.core = core

    @app.post("/gsi")
    async def gsi(request: Request):
        payload = await request.json()
        if gsi_fields.auth_token(payload) != cfg["gsi_token"]:
            return JSONResponse({"ok": False}, status_code=403)
        core.ingest(payload)
        return {"ok": True}

    @app.get("/")
    async def panel():
        return FileResponse(PANEL)

    @app.get("/api/state")
    async def api_state():
        return {"state": snapshot(core.state), "events": core.recent_events}

    @app.post("/api/mark/{trigger}")
    async def api_mark(trigger: str):
        clock = core.clock()
        if clock is None:
            return JSONResponse({"ok": False, "error": "no clock"}, status_code=400)
        if not TRIGGER_RE.match(trigger):
            return JSONResponse({"ok": False, "error": "bad trigger"}, status_code=400)
        rules = core.mark(trigger, clock)
        return {"ok": True, "trigger": trigger, "clock": clock, "rules": rules}

    @app.get("/api/settings")
    async def api_settings():
        return core.settings()

    @app.post("/api/settings")
    async def api_settings_update(request: Request):
        try:
            patch = await request.json()
        except ValueError:
            patch = None
        if not isinstance(patch, dict):
            return JSONResponse({"ok": False, "error": "expected object"}, status_code=400)
        error = core.update_settings(patch)
        if error:
            return JSONResponse({"ok": False, "error": error}, status_code=400)
        return core.settings()

    @app.get("/api/items")
    async def api_items():
        core.refresh_items(force=True)
        return core.items_payload()

    @app.get("/api/brain")
    async def api_brain():
        return {**core.brain.status(), "plan": core.brain.plan}

    @app.post("/api/brain/ask")
    async def api_brain_ask(request: Request):
        try:
            body = await request.json()
        except ValueError:
            body = {}
        question = body.get("question") if isinstance(body, dict) else None
        if question is not None and not isinstance(question, str):
            return JSONResponse({"ok": False, "error": "bad question"}, status_code=400)
        if not core.brain.enabled:
            return JSONResponse({"ok": False, "error": "brain disabled"}, status_code=400)
        if core.state is None:
            return JSONResponse({"ok": False, "error": "no game state"}, status_code=400)
        note = f"Вопрос игрока: {question.strip()[:500]}" if question and question.strip() else "Игрок нажал кнопку «совет сейчас»."
        core.brain.request("manual", note)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        q = core.bus.subscribe()
        try:
            await socket.send_json({"type": "hello", "state": snapshot(core.state), "events": core.recent_events, "settings": core.settings(), "plan": core.brain.plan, "brain": core.brain.status(), "items": core.items_payload()})
            while True:
                topic, payload = await q.get()
                if topic == "state":
                    while not q.empty() and q._queue[0][0] == "state":
                        topic, payload = q.get_nowait()
                    await socket.send_json({"type": "state", "state": snapshot(payload)})
                elif topic == "event" and payload.kind != "tick":
                    await socket.send_json({"type": "event", "event": asdict(payload)})
                elif topic == "hint":
                    await socket.send_json({"type": "hint", "hint": payload})
                elif topic == "settings":
                    await socket.send_json({"type": "settings", "settings": payload})
                elif topic == "plan":
                    await socket.send_json({"type": "plan", "plan": payload})
                elif topic == "items":
                    await socket.send_json({"type": "items", "items": payload})
                elif topic == "brain_status":
                    await socket.send_json({"type": "brain_status", "brain": payload})
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            pass
        finally:
            core.bus.unsubscribe(q)

    return app
