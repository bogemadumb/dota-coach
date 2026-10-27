import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fake_claude import Factory, answer, kind_of  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dota_coach.brain import Brain, KnowledgeNames, parse_answer  # noqa: E402
from dota_coach.bus import Bus  # noqa: E402
from dota_coach.config import DEFAULTS  # noqa: E402
from dota_coach.server import Core, create_app  # noqa: E402
from dota_coach.state import GameState  # noqa: E402
from dota_coach.voice import SilentVoice  # noqa: E402
from simulate import Match  # noqa: E402


class Env:
    def __init__(self, factory=None, **cfg) -> None:
        self.cfg = dict(DEFAULTS, **cfg)
        self.bus = Bus()
        self.q = self.bus.subscribe()
        self.hints = []
        self.factory = factory or Factory()
        self.t = 1000.0
        self.clock = 100
        self.brain = Brain(self.cfg, self.bus, self.hints.append, client_factory=self.factory,
                           context_fn=lambda kind=None: "СВОДКА", clock_fn=lambda: self.clock, now_fn=lambda: self.t)

    def topics(self, name):
        out = []
        for topic, payload in list(self.q._queue):
            if topic == name:
                out.append(payload)
        return out


def run(coro):
    return asyncio.run(coro)


def game_state(clock, **kw) -> GameState:
    return GameState(received_at=0, phase=kw.pop("phase", "game"), clock=clock, **kw)


def test_parse_plain_json():
    r = parse_answer('{"say": "бкб", "detail": "почему", "priority": 3, "ttl": 12}', "death")
    assert r == {"say": "бкб", "detail": "почему", "priority": 3, "ttl": 12.0, "plan": ""}


def test_parse_fences_and_chatter():
    text = 'Вот ответ:\n```json\n{"say": "купи бкб", "detail": "d"}\n```\nГотово'
    r = parse_answer(text, "periodic")
    assert r["say"] == "купи бкб" and r["priority"] == 2 and r["ttl"] == 20.0


def test_parse_skips_garbage_braces_and_takes_first_object():
    r = parse_answer('{не json} {"say": "раз"} {"say": "два"}', "periodic")
    assert r["say"] == "раз"


def test_parse_clamps_and_tolerates_types():
    r = parse_answer('{"say": "x", "priority": 9, "ttl": 99999}', "periodic")
    assert r["priority"] == 3 and r["ttl"] == 180.0
    r = parse_answer('{"say": "x", "priority": "высокий", "ttl": "долго", "detail": null}', "periodic")
    assert r["priority"] == 2 and r["ttl"] == 20.0 and r["detail"] == ""


def test_parse_failures():
    assert parse_answer("", "periodic") is None
    assert parse_answer("просто текст", "periodic") is None
    assert parse_answer('{"detail": "нет say"}', "periodic") is None
    assert parse_answer("[1, 2]", "periodic") is None
    assert parse_answer('{"say": ', "periodic") is None


def test_parse_empty_say_and_plan_list():
    assert parse_answer('{"say": ""}', "periodic")["say"] == ""
    r = parse_answer('{"say": "s", "plan": ["a", "b"]}', "plan")
    assert r["plan"] == "a\nb"
    assert parse_answer('{"plan": "только план"}', "plan")["plan"] == "только план"


def test_hint_conversion_and_status():
    env = Env(Factory([answer("ставь бкб", "у зевса много магии", 3, 15)]))
    assert env.brain.request("death", "погиб")
    run(env.brain.drain())
    [hint] = env.hints
    assert (hint.source, hint.category, hint.say, hint.priority, hint.ttl, hint.clock) == ("brain", "brain_death", "ставь бкб", 3, 15.0, 100)
    assert hint.detail == "у зевса много магии" and hint.say_long == hint.detail
    status = env.brain.status()
    assert status["calls"] == 1 and status["last_latency"] is not None and status["last_error"] is None
    assert status["in_flight"] is None and status["pending"] == []
    assert env.topics("brain_status")[-1]["calls"] == 1
    opts = env.factory.options[0]
    assert opts.model == "sonnet" and opts.tools == [] and opts.setting_sources == [] and opts.max_turns == 1
    assert "Dota 2" in opts.system_prompt and "JSON" in opts.system_prompt
    assert env.factory.queries[0].startswith("Тип запроса: death\nпогиб")
    assert "СВОДКА" in env.factory.queries[0]


def test_empty_say_is_not_submitted():
    env = Env(Factory(['{"say": ""}']))
    env.brain.request("periodic")
    run(env.brain.drain())
    assert env.hints == [] and env.brain.calls == 1 and env.brain.last_error is None


def test_bad_answer_logged_and_dropped():
    env = Env(Factory(["извините, не могу"]))
    env.brain.request("periodic")
    run(env.brain.drain())
    assert env.hints == [] and env.brain.last_error == "bad answer"
    env.brain.request("periodic")
    run(env.brain.drain())
    assert len(env.hints) == 1 and env.brain.last_error is None


def test_plan_published_with_card_and_voice_hint():
    env = Env(Factory([answer("береги пудж-хук", "d", 2, 30, plan="Опасные враги:\n- Пудж")]))
    env.brain.request("plan")
    run(env.brain.drain())
    assert env.topics("plan")[-1] == "Опасные враги:\n- Пудж"
    assert env.brain.plan.startswith("Опасные")
    assert env.hints[0].category == "brain_plan"
    assert env.brain.status()["has_plan"] is True


def test_plan_requested_once_per_match_and_retried_after_failure():
    env = Env(Factory(["мусор", "мусор", "мусор", answer("x", plan="P")]))
    assert env.brain.request("plan") is True
    assert env.brain.request("plan") is False
    run(env.brain.drain())
    assert env.brain.plan == ""
    assert env.brain.request("plan") is True
    run(env.brain.drain())
    assert env.brain.request("plan") is True
    run(env.brain.drain())
    assert env.brain.request("plan") is False
    assert env.brain.calls == 3
    env2 = Env(Factory([answer("x", plan="P")]))
    env2.brain.request("plan")
    run(env2.brain.drain())
    assert env2.brain.request("plan") is False
    env2.brain.reset()
    assert env2.brain.request("plan") is True


def test_same_kind_replaced_by_newer():
    env = Env()
    env.brain.request("death", "первая")
    env.brain.request("death", "вторая")
    assert list(env.brain.pending) == ["death"]
    run(env.brain.drain())
    assert len(env.factory.queries) == 1 and "вторая" in env.factory.queries[0]


def test_priority_order_plan_first():
    env = Env()
    for kind in ("periodic", "item_bought", "death", "manual", "plan"):
        env.brain.request(kind)
    run(env.brain.drain())
    assert env.factory.kinds == ["plan", "manual", "death", "item_bought", "periodic"]


def test_unknown_kind_and_disabled():
    env = Env()
    assert env.brain.request("nonsense") is False
    env.cfg["brain_enabled"] = False
    assert env.brain.request("death") is False
    assert run(env.brain.step()) is False
    assert env.factory.queries == []


def test_disable_clears_pending():
    env = Env()
    env.brain.request("death")
    env.cfg["brain_enabled"] = False
    env.brain.set_enabled()
    assert env.brain.pending == {} and env.topics("brain_status")[-1]["enabled"] is False


def test_stale_requests_dropped_by_ttl():
    env = Env()
    env.brain.request("periodic")
    env.brain.request("death")
    env.t += 21
    run(env.brain.drain())
    assert env.factory.kinds == ["death"]
    env.brain.request("fight")
    env.t += 7
    run(env.brain.drain())
    assert env.factory.kinds == ["death"]


def test_one_in_flight_at_a_time():
    env = Env(Factory(delay=0.02))

    async def go():
        runner = asyncio.create_task(env.brain.run())
        for kind in ("periodic", "death", "manual"):
            env.brain.request(kind)
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.2)
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)
        await env.brain.close()

    run(go())
    assert env.factory.max_active == 1
    assert len(env.factory.queries) == 3


def test_in_flight_reported_during_call():
    gate = asyncio.Event()
    env = Env(Factory(gate=gate))

    async def go():
        env.brain.request("death")
        task = asyncio.create_task(env.brain.step())
        await asyncio.sleep(0.01)
        assert env.brain.status()["in_flight"] == "death"
        gate.set()
        await task

    run(go())
    assert env.brain.status()["in_flight"] is None


def test_budget_stops_calls():
    env = Env(brain_max_calls=2)
    for _ in range(4):
        env.brain.request("periodic")
        run(env.brain.drain())
    assert len(env.factory.queries) == 2 and env.brain.status()["calls"] == 2
    assert env.brain.pending == {}


def test_budget_resets_on_new_match():
    env = Env(brain_max_calls=1)
    env.brain.request("periodic")
    run(env.brain.drain())
    env.brain.reset()
    env.brain.request("periodic")
    run(env.brain.drain())
    assert len(env.factory.queries) == 2


def test_recycle_carries_memory():
    env = Env(Factory([answer("совет про линию", "детали"), answer("второй"), answer("третий"), answer("четвёртый")]), brain_recycle=2)
    env.brain.plan = "ПЛАН: играть от пуджа"
    env.brain.plan_requested = True
    for kind in ("death", "periodic", "periodic", "death"):
        env.brain.request(kind)
        run(env.brain.drain())
    assert len(env.factory.clients) == 2
    assert env.factory.clients[0].closed and not env.factory.clients[1].closed
    assert all("Память матча" not in q for q in env.factory.queries[:2])
    third = env.factory.queries[2]
    assert "Память матча" in third and "ПЛАН: играть от пуджа" in third and "совет про линию" in third
    assert "Память матча" not in env.factory.queries[3]


def test_new_match_starts_fresh_session_without_memory():
    env = Env(brain_recycle=50)
    env.brain.request("death")
    run(env.brain.drain())
    env.brain.plan = "СТАРЫЙ ПЛАН"
    env.brain.reset()
    env.brain.request("periodic")
    run(env.brain.drain())
    assert len(env.factory.clients) == 2 and env.factory.clients[0].closed
    assert "СТАРЫЙ ПЛАН" not in env.factory.queries[1] and "Память матча" not in env.factory.queries[1]
    assert env.brain.plan == "" and env.topics("plan")[-1] == ""


def test_reset_during_flight_discards_old_answer():
    gate = asyncio.Event()
    env = Env(Factory(gate=gate))

    async def go():
        env.brain.request("death")
        task = asyncio.create_task(env.brain.step())
        await asyncio.sleep(0.01)
        env.brain.reset()
        gate.set()
        await task

    run(go())
    assert env.hints == []


def test_client_error_recovers_with_new_session():
    env = Env(Factory([RuntimeError("boom"), answer("снова")]))
    env.brain.plan = "ПЛАН"
    env.brain.request("periodic")
    run(env.brain.drain())
    assert "boom" in env.brain.last_error and env.hints == []
    assert env.factory.clients[0].closed
    env.brain.request("periodic")
    run(env.brain.drain())
    assert len(env.factory.clients) == 2 and env.brain.last_error is None
    assert "ПЛАН" in env.factory.queries[1]


def test_timeout_counts_as_error():
    env = Env(Factory(delay=1), brain_timeout=0.05)
    env.brain.request("periodic")
    run(env.brain.drain())
    assert env.brain.last_error and env.brain.status()["in_flight"] is None


def test_latencies_keep_last_50():
    env = Env()
    for _ in range(55):
        env.brain.request("periodic")
        run(env.brain.drain())
    assert len(env.brain.status()["latencies"]) == 50 and env.brain.calls == 55


def periodic_fires(env, mode, start, stop, **state_kw):
    env.cfg["mode"] = mode
    fired = []
    for clock in range(start, stop + 1):
        env.brain.tick(game_state(clock, **state_kw))
        if "periodic" in env.brain.pending:
            env.brain.pending.pop("periodic")
            fired.append(clock)
    return fired


@pytest.mark.parametrize("mode,interval", [("quiet", 120), ("normal", 60), ("chatty", 30)])
def test_periodic_cadence_per_mode(mode, interval):
    env = Env()
    assert periodic_fires(env, mode, 0, 400) == list(range(interval, 401, interval))


def test_no_periodic_when_dead_paused_or_not_in_game():
    env = Env()
    assert periodic_fires(env, "chatty", 0, 300, alive=False) == []
    assert periodic_fires(env, "chatty", 0, 300, paused=True) == []
    assert periodic_fires(env, "chatty", 0, 300, phase="pregame") == []
    assert periodic_fires(env, "chatty", 0, 300, phase="draft") == []


def test_periodic_timer_restarts_after_death():
    env = Env()
    env.cfg["mode"] = "normal"
    fired = []
    for clock in range(0, 200):
        env.brain.tick(game_state(clock, alive=not (100 <= clock < 130)))
        if env.brain.pending.pop("periodic", None):
            fired.append(clock)
    assert fired == [60, 189]


def test_periodic_not_when_disabled_or_already_in_flight():
    env = Env()
    env.cfg["brain_enabled"] = False
    assert periodic_fires(env, "chatty", 0, 100) == []
    env.cfg["brain_enabled"] = True
    env.brain.in_flight = "periodic"
    assert periodic_fires(env, "chatty", 0, 100) == []


def test_knowledge_names_fallback_without_knowledge():
    names = KnowledgeNames()
    names.kn = None
    assert names.hero("nevermore") == "Nevermore" and names.item("item_black_king_bar") == "Black King Bar"
    assert names.ability("nevermore", "nevermore_requiem") == "Nevermore Requiem"
    assert names.item_info("item_blink") is None


def test_knowledge_names_real():
    names = KnowledgeNames()
    if names.kn is None:
        pytest.skip("no knowledge cache")
    assert names.hero("nevermore") == "Shadow Fiend"
    assert names.item("item_blink") == "Blink Dagger"


def wiring(**cfg_over):
    factory = Factory()
    cfg = dict(DEFAULTS, gsi_token="t", log_raw_gsi=False, **cfg_over)
    core = Core(cfg, voice=SilentVoice(), client_factory=factory)
    return core, factory, TestClient(create_app(cfg, core))


def wait_idle(core, factory=None, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if not core.brain.pending and core.brain.in_flight is None:
            return
        time.sleep(0.01)
    raise AssertionError("brain did not go idle")


def feed_draft(client, match):
    for step in range(11):
        client.post("/gsi", json=match.payload("draft", -150 + step, step))
    for s in range(10):
        client.post("/gsi", json=match.payload("strategy", -100 + s, 0))


def feed_game(client, match, start, stop, phase=None):
    for clock in range(start, stop + 1):
        match.advance(clock)
        client.post("/gsi", json=match.payload(phase or ("pregame" if clock < 0 else "game"), clock, 0))


def test_wiring_plan_once_per_match_then_new_match_again():
    core, factory, client = wiring()
    with client:
        match = Match("t", seed=1)
        feed_draft(client, match)
        feed_game(client, match, -90, -80)
        wait_idle(core)
        assert factory.kinds == ["plan"]
        feed_game(client, match, -79, 30)
        wait_idle(core)
        assert factory.kinds.count("plan") == 1
        match2 = Match("t", seed=2)
        feed_draft(client, match2)
        feed_game(client, match2, -90, -85)
        wait_idle(core)
        assert factory.kinds.count("plan") == 2
        assert len(factory.clients) == 2


def test_wiring_plan_hint_card_and_websocket():
    core, factory, client = wiring()
    factory.replies = [answer("береги пудж-хук", "d", 2, 30, plan="Опасные враги:\n- Пудж")]
    with client:
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello" and hello["plan"] == "" and hello["brain"]["max_calls"] == 120
            match = Match("t", seed=1)
            feed_draft(client, match)
            feed_game(client, match, -90, -85)
            wait_idle(core)
            seen = {}
            for _ in range(200):
                msg = ws.receive_json()
                seen[msg["type"]] = msg
                if "plan" in seen and seen["plan"]["plan"] and "hint" in seen and seen["hint"]["hint"]["source"] == "brain":
                    break
            assert seen["plan"]["plan"] == "Опасные враги:\n- Пудж"
            assert seen["hint"]["hint"]["category"] == "brain_plan"
            assert "brain_status" in seen
        assert client.get("/api/brain").json()["plan"].startswith("Опасные")


def test_wiring_death_and_key_item_and_periodic():
    core, factory, client = wiring(mode="chatty")
    with client:
        match = Match("t", seed=1)
        feed_draft(client, match)
        feed_game(client, match, -90, 0)
        wait_idle(core)
        for clock in range(1, 1000):
            match.advance(clock)
            client.post("/gsi", json=match.payload("game", clock, 0))
            if clock % 15 == 0:
                wait_idle(core)
            names = [i.name for i in core.state.inventory + core.state.backpack]
            if "item_blink" in names and "death" in factory.kinds and "item_bought" in factory.kinds:
                break
        wait_idle(core)
    assert "death" in factory.kinds and "item_bought" in factory.kinds and "periodic" in factory.kinds
    bought = [q for q in factory.queries if kind_of(q) == "item_bought"]
    assert any("Blink Dagger" in q or "Black King Bar" in q for q in bought)
    assert not any("Power Treads" in q.split("\n")[1] for q in bought)


def test_key_item_rule():
    core, _, _ = wiring()
    assert core.is_key_item("item_blink") and core.is_key_item("item_black_king_bar")
    assert core.is_key_item("item_satanic")
    assert not core.is_key_item("item_tango") and not core.is_key_item("item_magic_wand")
    assert not core.is_key_item("item_power_treads") and not core.is_key_item("item_reaver")
    assert not core.is_key_item("item_unknown_thing")


def test_wiring_ask_endpoint():
    core, factory, client = wiring()
    assert client.post("/api/brain/ask", json={}).status_code == 400
    with client:
        feed_game(client, Match("t", seed=1), -90, 5)
        r = client.post("/api/brain/ask", json={"question": "что купить?"})
        assert r.status_code == 200 and r.json() == {"ok": True}
        wait_idle(core)
        manual = [q for q in factory.queries if kind_of(q) == "manual"]
        assert len(manual) == 1 and "Вопрос игрока: что купить?" in manual[0]
        assert client.post("/api/brain/ask", json={"question": 5}).status_code == 400
        assert client.post("/api/brain/ask").status_code == 200
        wait_idle(core)
        assert "кнопку" in [q for q in factory.queries if kind_of(q) == "manual"][-1]
        status = client.get("/api/brain").json()
        assert status["calls"] == len(factory.queries) and status["enabled"] is True and "plan" in status


def test_wiring_toggle_brain_at_runtime():
    core, factory, client = wiring()
    with client:
        feed_game(client, Match("t", seed=1), -90, 5)
        r = client.post("/api/settings", json={"brain_enabled": False})
        assert r.status_code == 200 and r.json()["brain_enabled"] is False
        assert client.post("/api/brain/ask", json={}).status_code == 400
        assert client.get("/api/brain").json()["enabled"] is False
        assert client.post("/api/settings", json={"brain_enabled": "no"}).status_code == 400
        client.post("/api/settings", json={"brain_enabled": True})
        assert client.post("/api/brain/ask", json={}).status_code == 200
        wait_idle(core)
    assert factory.kinds == ["manual"]


def test_wiring_disabled_brain_makes_no_calls():
    core, factory, client = wiring(brain_enabled=False)
    with client:
        match = Match("t", seed=1)
        feed_draft(client, match)
        feed_game(client, match, -90, 500)
    assert factory.queries == []


def advised_block(query: str) -> str:
    if "=== Уже советовал" not in query:
        return ""
    return query.split("=== Уже советовал", 1)[1].split("=== Сводка", 1)[0]


def test_every_request_carries_advised_block_with_last_five_and_clock():
    phrases = ["альфа прячься за деревьями", "бета бери руну", "гамма стакай лагеря", "дельта жди пуджа у башни",
               "эпсилон купи дасты", "дзета иди на рошана", "эта дави линию"]
    replies = [answer(p) for p in phrases]
    env = Env(Factory(replies))
    for i in range(7):
        env.clock = 100 + i * 60
        env.brain.request("periodic")
        run(env.brain.drain())
    assert advised_block(env.factory.queries[0]) == ""
    second = advised_block(env.factory.queries[1])
    assert "1:40 альфа прячься за деревьями" in second and "бета" not in second
    last = advised_block(env.factory.queries[6])
    assert "альфа" not in last and "эта дави" not in last
    assert all(w in last for w in ("бета", "гамма", "дельта", "эпсилон", "дзета")) and last.count("\n") >= 5
    assert "6:40 дзета иди на рошана" in last
    assert len(env.brain.advices) == 5


def test_advised_block_is_not_only_after_recycle():
    env = Env(Factory([answer("раз два"), answer("три четыре")]), brain_recycle=50)
    env.brain.request("death")
    run(env.brain.drain())
    env.brain.request("items")
    run(env.brain.drain())
    assert len(env.factory.clients) == 1
    assert "раз два" in advised_block(env.factory.queries[1])
    assert "Память матча" not in env.factory.queries[1]


def test_system_prompt_forbids_repetition_and_defines_items_kind():
    env = Env()
    env.brain.request("periodic")
    run(env.brain.drain())
    prompt = env.factory.options[0].system_prompt
    assert "Уже советовал" in prompt and "не повторяй" in prompt.lower()
    assert "items —" in prompt and "дальше X, потом Y" in prompt
    assert "максимум 15 строк" in prompt
    assert "главнее твоей памяти" in prompt


def test_duplicate_say_dropped_normalized_and_logged(caplog):
    env = Env(Factory([answer("Купи БКБ сейчас!"), answer("купи  бкб, сейчас"), answer("Ставь дасты против фантомки")]))
    with caplog.at_level("INFO"):
        for _ in range(3):
            env.brain.request("periodic")
            run(env.brain.drain())
    assert [h.say for h in env.hints] == ["Купи БКБ сейчас!", "Ставь дасты против фантомки"]
    assert env.brain.duplicates == 1 and env.brain.status()["duplicates"] == 1
    assert any("duplicate" in r.message for r in caplog.records)
    assert len(env.brain.advices) == 2


def test_duplicate_threshold_similar_but_different_passes():
    env = Env(Factory([answer("Дальше бкб потом блинк"), answer("Бери мкб против фантомки")]))
    for _ in range(2):
        env.brain.request("items")
        run(env.brain.drain())
    assert len(env.hints) == 2 and env.brain.duplicates == 0


def test_duplicate_checked_against_last_five_only():
    says = ["совет первый про линию", "жми руну", "стакай лагерь", "иди на башню", "купи дасты", "забери рошана",
            "совет первый про линию"]
    env = Env(Factory([answer(s) for s in says]))
    for _ in says:
        env.brain.request("periodic")
        run(env.brain.drain())
    assert len(env.hints) == 7 and env.brain.duplicates == 0


def test_manual_answer_never_dropped_as_duplicate():
    env = Env(Factory([answer("держи линию"), answer("держи линию")]))
    env.brain.request("periodic")
    run(env.brain.drain())
    env.brain.request("manual", "вопрос")
    run(env.brain.drain())
    assert len(env.hints) == 2 and env.brain.duplicates == 0


def test_duplicates_reset_on_new_match():
    env = Env(Factory([answer("держи линию"), answer("держи линию")]))
    env.brain.request("periodic")
    run(env.brain.drain())
    env.brain.reset()
    env.brain.request("periodic")
    run(env.brain.drain())
    assert len(env.hints) == 2


def test_context_function_receives_request_kind():
    seen = []
    env = Env()
    env.brain.context_fn = lambda kind=None: seen.append(kind) or "СВОДКА"
    for kind in ("death", "items", "periodic"):
        env.brain.request(kind)
    run(env.brain.drain())
    assert seen == ["death", "items", "periodic"]


def test_items_kind_priority_and_ttl():
    env = Env()
    for kind in ("periodic", "item_bought", "items", "death"):
        env.brain.request(kind)
    run(env.brain.drain())
    assert env.factory.kinds == ["death", "items", "item_bought", "periodic"]
    env.brain.request("items")
    env.t += 31
    run(env.brain.drain())
    assert env.factory.kinds.count("items") == 1


def test_warm_up_connects_without_query():
    env = Env()

    async def go():
        runner = asyncio.create_task(env.brain.run())
        env.brain.warm_up()
        await asyncio.sleep(0.05)
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)

    run(go())
    assert len(env.factory.clients) == 1 and env.factory.clients[0].connected
    assert env.factory.queries == [] and env.brain.calls == 0
    env.brain.request("periodic")
    run(env.brain.drain())
    assert len(env.factory.clients) == 1


def test_warm_up_skipped_when_disabled_and_failure_is_harmless():
    env = Env(brain_enabled=False)
    env.brain.warm_up()
    assert env.brain.warm_pending is False

    class Broken(Factory):
        def __call__(self, options):
            client = super().__call__(options)

            async def boom():
                raise RuntimeError("no network")

            client.connect = boom
            return client

    env2 = Env(Broken())
    env2.brain.warm_up()
    run(env2.brain.step())
    assert env2.brain.client is None and env2.brain.warm_pending is False


def test_wiring_match_start_warms_session_before_first_request():
    core, factory, client = wiring()
    with client:
        client.post("/gsi", json=Match("t", seed=1).payload("pregame", -90, 0))
        end = time.time() + 3
        while time.time() < end and not factory.clients:
            time.sleep(0.01)
        assert len(factory.clients) == 1 and factory.clients[0].connected and factory.queries == []
        assert client.get("/api/brain").json()["calls"] == 0
