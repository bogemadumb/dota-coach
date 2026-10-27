import asyncio

from dota_coach.arbiter import Arbiter
from dota_coach.bus import Bus
from dota_coach.hints import Hint
from dota_coach.voice import SilentVoice


def make(mode="normal", style="commands", enabled=True, now=100):
    cfg = {"mode": mode, "voice_style": style, "voice_enabled": enabled}
    bus = Bus()
    voice = SilentVoice()
    clock = {"now": now}
    arb = Arbiter(cfg, bus, voice, lambda: clock["now"])
    return arb, bus, voice, clock, bus.subscribe()


def hint(id="a", priority=2, clock=100, ttl=15.0, category="", say="коротко", say_long="", **kw):
    return Hint(id=id, source="timers", priority=priority, say=say, say_long=say_long, clock=clock, ttl=ttl, category=category, **kw)


def published(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


async def speak_until(arb, voice, count, timeout=2.0):
    task = asyncio.create_task(arb.run())
    try:
        async with asyncio.timeout(timeout):
            while len(voice.spoken) < count:
                await asyncio.sleep(0.01)
    except TimeoutError:
        pass
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_dedupe_by_id():
    arb, _, _, _, q = make()
    arb.submit(hint("x"))
    arb.submit(hint("x"))
    assert len(arb.queue) == 1
    assert len(published(q)) == 1


def test_reset_allows_same_id_again():
    arb, *_ = make()
    arb.submit(hint("x"))
    arb.reset()
    assert arb.queue == []
    arb.submit(hint("x"))
    assert len(arb.queue) == 1


def test_mode_min_priority_filtering_still_publishes():
    for mode, queued in (("quiet", ["p3"]), ("normal", ["p3", "p2"]), ("chatty", ["p3", "p2", "p1"])):
        arb, _, _, _, q = make(mode=mode)
        for p in (1, 2, 3):
            arb.submit(hint(f"p{p}", priority=p, category=f"c{p}"))
        assert [h.id for h in arb.queue] == queued, mode
        assert len(published(q)) == 3, mode


def test_stale_hint_dropped():
    arb, _, _, clock, _ = make()
    arb.submit(hint("old", clock=100, ttl=5))
    clock["now"] = 106
    assert arb.next_hint() is None
    assert arb.queue == []


def test_fresh_hint_returned_at_ttl_edge():
    arb, _, _, clock, _ = make()
    arb.submit(hint("edge", clock=100, ttl=5))
    clock["now"] = 105
    assert arb.next_hint().id == "edge"


def test_gap_holds_normal_but_not_urgent():
    arb, *_ = make()
    arb.last_spoken_at = __import__("time").monotonic()
    arb.submit(hint("n", priority=2))
    assert arb.next_hint() is None
    arb.submit(hint("u", priority=3, category="u"))
    assert arb.next_hint().id == "u"
    assert arb.next_hint() is None


def test_first_hint_not_delayed_by_gap():
    arb, *_ = make(mode="quiet")
    arb.submit(hint("u", priority=3))
    assert arb.next_hint().id == "u"


def test_higher_priority_first():
    arb, *_ = make(mode="chatty")
    arb.submit(hint("low", priority=1, category="a"))
    arb.submit(hint("high", priority=3, category="b"))
    assert arb.next_hint().id == "high"


def test_same_category_replaces_older_lower_priority():
    arb, *_ = make()
    arb.submit(hint("r1", priority=2, category="rune"))
    arb.submit(hint("r2", priority=2, category="rune"))
    assert [h.id for h in arb.queue] == ["r2"]


def test_style_commands_speaks_short():
    arb, _, voice, *_ = make(style="commands")
    arb.submit(hint("a", say="руна", say_long="руна силы через десять секунд"))
    asyncio.run(speak_until(arb, voice, 1))
    assert voice.spoken == ["руна"]


def test_style_coach_speaks_long_and_falls_back():
    arb, _, voice, *_ = make(style="coach")
    arb.submit(hint("a", priority=3, say="руна", say_long="руна силы через десять секунд"))
    arb.submit(hint("b", priority=3, category="b", say="стак"))
    asyncio.run(speak_until(arb, voice, 2))
    assert voice.spoken == ["руна силы через десять секунд", "стак"]


def test_voice_disabled_publishes_but_stays_silent():
    arb, _, voice, _, q = make(enabled=False)
    arb.submit(hint("a", priority=3))
    assert [t for t, _ in published(q)] == ["hint"]
    assert arb.queue == []
    asyncio.run(speak_until(arb, voice, 1, timeout=0.3))
    assert voice.spoken == []


def test_voice_disabled_at_runtime_drains_queue():
    arb, _, voice, *_ = make()
    arb.submit(hint("a", priority=3))
    arb.cfg["voice_enabled"] = False
    asyncio.run(speak_until(arb, voice, 1, timeout=0.3))
    assert voice.spoken == [] and arb.queue == []


def test_hint_payload_has_panel_fields():
    arb, _, _, _, q = make()
    arb.submit(hint("a", detail="почему"))
    (topic, payload), = published(q)
    assert topic == "hint" and payload["say"] == "коротко" and payload["detail"] == "почему"


class SlowVoice(SilentVoice):
    def __init__(self):
        super().__init__()
        self.interrupted = 0

    async def speak(self, text):
        self.spoken.append(text)
        await asyncio.sleep(0.2)

    def interrupt(self):
        self.interrupted += 1


def test_urgent_interrupts_current_speech_only_if_lower():
    async def scenario():
        arb, *_ = make(mode="chatty")
        voice = SlowVoice()
        arb.voice = voice
        arb.submit(hint("n", priority=2, category="n"))
        task = asyncio.create_task(arb.run())
        await asyncio.sleep(0.1)
        arb.submit(hint("u", priority=3, category="u"))
        await asyncio.sleep(0.45)
        task.cancel()
        return voice

    voice = asyncio.run(scenario())
    assert voice.interrupted == 1
    assert voice.spoken == ["коротко", "коротко"]


def test_speech_failure_does_not_kill_loop():
    class Broken(SilentVoice):
        async def speak(self, text):
            self.spoken.append(text)
            raise RuntimeError("no audio")

    arb, *_ = make()
    voice = Broken()
    arb.voice = voice
    arb.submit(hint("a", priority=3, category="a"))
    arb.submit(hint("b", priority=3, category="b"))
    asyncio.run(speak_until(arb, voice, 2))
    assert len(voice.spoken) == 2
