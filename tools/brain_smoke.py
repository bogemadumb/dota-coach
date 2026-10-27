"""Live smoke test: Shadow Fiend vs PA/Slark/Puck/Pudge/Zeus with the card system prompt, REAL Claude calls through Brain (6 calls)."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dota_coach.config import DEFAULTS  # noqa: E402
from dota_coach.kb_context import estimate_tokens  # noqa: E402
from dota_coach.server import Core  # noqa: E402
from dota_coach.voice import SilentVoice  # noqa: E402
from simulate import COSTS, Match  # noqa: E402

TARGET_CLOCK = 840


def build_core(hero: str = "nevermore") -> tuple[Core, Match]:
    cfg = dict(DEFAULTS, log_raw_gsi=False)
    core = Core(cfg, voice=SilentVoice())
    match = Match(cfg["gsi_token"], seed=7, hero=hero)
    cfg["gsi_token"] = match.token
    for step in range(11):
        core.ingest(match.payload("draft", -150 + step, step))
    for s in range(10):
        core.ingest(match.payload("strategy", -100 + s, 0))
    for clock in range(-90, TARGET_CLOCK + 1):
        match.advance(clock)
        core.ingest(match.payload("pregame" if clock < 0 else "game", clock, 0))
    core.brain.pending.clear()
    core.brain.plan_requested = False
    return core, match


def request_sizes(core: Core, kind: str, note: str = "") -> str:
    """Estimated tokens of the per-request text without cards in the prompt (old) and with them (new)."""
    from dota_coach.brain import Request
    req = Request(kind, note, core.clock(), 0.0, 60.0)
    keep, refs = core.brain.cards_in_prompt, core.brain.refs_fn
    try:
        core.brain.cards_in_prompt, core.brain.refs_fn = False, lambda kind, note: ""
        old = estimate_tokens(core.brain._prompt(req, ""))
        core.brain.cards_in_prompt, core.brain.refs_fn = True, refs
        new = estimate_tokens(core.brain._prompt(req, ""))
    finally:
        core.brain.cards_in_prompt, core.brain.refs_fn = keep, refs
    return f"request size est. tokens: before {old}, after {new}"


async def call(core: Core, label: str, inbox) -> None:
    before = len(core.brain.latencies)
    await core.brain.drain()
    status = core.brain.status()
    latency = core.brain.latencies[-1] if len(core.brain.latencies) > before else None
    print(f"--- {label}: latency={latency:.2f}s error={status['last_error']}" if latency is not None else f"--- {label}: no call")
    print(f"    usage={core.brain.last_usage} cards_in_prompt={core.brain.cards_in_prompt}")
    hints = []
    while not inbox.empty():
        topic, payload = inbox.get_nowait()
        if topic == "hint" and payload["source"] == "brain":
            hints.append(payload)
    for h in hints:
        print(json.dumps({k: h[k] for k in ("say", "detail", "priority", "ttl")}, ensure_ascii=False, indent=2))
    if not hints:
        print("(no hint submitted)")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hero", default="nevermore", choices=["nevermore", "lion"])
    args = parser.parse_args()
    core, match = build_core(args.hero)
    inbox = core.bus.subscribe()
    try:
        print(request_sizes(core, "plan"))
        print(request_sizes(core, "periodic"))
        core.brain.request("plan")
        await call(core, "plan", inbox)
        from dota_coach import kb_context
        draft = core.draft_info()
        print("system prompt est. tokens:", estimate_tokens(kb_context.system_prompt_for_draft(*draft)))
        print("plan card:\n" + core.brain.plan + "\n")

        core.brain.request("periodic")
        await call(core, "periodic", inbox)

        match.alive, match.respawn = False, 35
        match.deaths += 1
        match.advance(TARGET_CLOCK + 1)
        match.alive, match.respawn = False, 35
        core.ingest(match.payload("game", TARGET_CLOCK + 1, 0))
        print("pending after death:", sorted(core.brain.pending))
        await call(core, "death", inbox)

        match.alive = True
        match.advance(TARGET_CLOCK + 40)
        core.ingest(match.payload("game", TARGET_CLOCK + 40, 0))
        core.brain.pending.clear()
        core.see_items("phantom_assassin", ["item_desolator", "item_power_treads", "item_black_king_bar"], "scout")
        core.see_items("pudge", ["item_blink", "item_arcane_boots"], "scout")
        print("pending after scout:", sorted(core.brain.pending), core.brain.pending.get("items") and core.brain.pending["items"].note)
        print("=== items request: what the model receives ===")
        print(core.brain._prompt(core.brain.pending["items"], ""))
        print()
        await call(core, "items (enemy key item seen)", inbox)

        match.items.remove(min(match.items, key=lambda n: COSTS.get(n, 0)))
        match.items.append("item_sheepstick")
        match.advance(TARGET_CLOCK + 80)
        core.ingest(match.payload("game", TARGET_CLOCK + 80, 0))
        core.brain.pending.pop("periodic", None)
        print("pending after purchase:", sorted(core.brain.pending), core.brain.pending.get("item_bought") and core.brain.pending["item_bought"].note)
        await call(core, "item_bought", inbox)

        core.brain.pending.clear()
        question = "Пробивает ли ульта Пуджа БКБ и режет ли Шива лечение у Сларка?"
        core.brain.request("manual", f"Вопрос игрока: {question}")
        print("=== manual refs: what the model receives ===")
        print(core.brain.refs_fn("manual", question)[:1500])
        await call(core, "manual (facts: Pudge ult vs BKB, Shiva vs healing)", inbox)

        print("advised block at the end:\n" + core.brain._advised())
        print("status:", json.dumps(core.brain.status(), ensure_ascii=False))
    finally:
        await core.brain.close()


if __name__ == "__main__":
    asyncio.run(main())
