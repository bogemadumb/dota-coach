import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_claude import Factory  # noqa: E402

from dota_coach import kb_context as kc  # noqa: E402
from dota_coach.brain import Brain, KnowledgeNames  # noqa: E402
from dota_coach.bus import Bus  # noqa: E402
from dota_coach.config import DEFAULTS  # noqa: E402
from dota_coach.server import Core  # noqa: E402
from dota_coach.state import Draft, GameState  # noqa: E402
from dota_coach.summary import build_summary  # noqa: E402
from dota_coach.voice import SilentVoice  # noqa: E402

DRAFT_A = ("nevermore", ["crystal_maiden", "mars", "antimage", "lion"], ["puck", "pudge", "slark", "phantom_assassin", "zuus"])
DRAFT_B = ("lion", ["sven", "invoker", "tiny", "dazzle"], ["juggernaut", "lina", "axe", "rubick", "viper"])


def prompt_for(draft):
    hero, allies, enemies = draft
    return kc.system_prompt_for_draft(hero, sorted(allies), sorted(enemies))


def run(coro):
    return asyncio.run(coro)


def make(draft, factory=None, refs=None, **cfg):
    holder = {"draft": draft}
    factory = factory or Factory()
    brain = Brain(dict(DEFAULTS, **cfg), Bus(), lambda hint: None, client_factory=factory,
                  context_fn=lambda kind=None: "СВОДКА", clock_fn=lambda: 100,
                  draft_fn=lambda: holder["draft"], refs_fn=refs)
    return brain, factory, holder


def ask(brain, kind="periodic", note=""):
    brain.request(kind, note)
    run(brain.drain())


def test_first_request_with_known_draft_uses_cards_in_system_prompt():
    brain, factory, _ = make(DRAFT_A)
    ask(brain)
    prompt = factory.options[0].system_prompt
    assert prompt == prompt_for(DRAFT_A)
    assert "# Shadow Fiend [nevermore]" in prompt and "Справочник механик" in prompt
    assert prompt.count("Против него") >= 9
    assert brain.cards_in_prompt is True and len(factory.clients) == 1


def test_no_draft_means_base_prompt_and_no_cards():
    brain, factory, _ = make(None)
    ask(brain)
    assert factory.options[0].system_prompt == kc.base_prompt()
    assert brain.cards_in_prompt is False


def test_session_rebuilt_when_hero_or_draft_changes():
    brain, factory, holder = make(DRAFT_A)
    ask(brain)
    ask(brain)
    assert len(factory.clients) == 1
    holder["draft"] = DRAFT_A[:2] + (["puck", "pudge", "slark", "phantom_assassin", "lina"],)
    ask(brain)
    assert len(factory.clients) == 2 and factory.clients[0].closed
    assert "Lina:" in factory.options[1].system_prompt and "Zeus:" not in factory.options[1].system_prompt
    holder["draft"] = DRAFT_B
    ask(brain)
    assert len(factory.clients) == 3
    assert "# Lion [lion]" in factory.options[2].system_prompt
    assert "# Shadow Fiend" not in factory.options[2].system_prompt


def test_draft_order_does_not_rebuild():
    brain, factory, holder = make(DRAFT_A)
    ask(brain)
    holder["draft"] = (DRAFT_A[0], list(reversed(DRAFT_A[1])), list(reversed(DRAFT_A[2])))
    ask(brain)
    assert len(factory.clients) == 1


def test_draft_appearing_after_base_session_rebuilds_and_carries_plan():
    brain, factory, holder = make(None)
    ask(brain)
    assert factory.options[0].system_prompt == kc.base_prompt()
    brain.plan = "Опасные враги: Пудж"
    holder["draft"] = DRAFT_A
    ask(brain)
    assert len(factory.clients) == 2
    assert factory.options[1].system_prompt == prompt_for(DRAFT_A)
    assert "Опасные враги: Пудж" in factory.queries[-1]


def test_recycling_keeps_the_card_prompt():
    brain, factory, _ = make(DRAFT_A, brain_recycle=2)
    for _ in range(5):
        ask(brain)
    assert len(factory.clients) == 3
    assert {o.system_prompt for o in factory.options} == {prompt_for(DRAFT_A)}


def test_new_match_resets_cards_until_draft_known_again():
    brain, factory, holder = make(DRAFT_A)
    ask(brain)
    brain.reset()
    holder["draft"] = None
    ask(brain)
    assert factory.options[1].system_prompt == kc.base_prompt() and brain.cards_in_prompt is False
    holder["draft"] = DRAFT_B
    ask(brain)
    assert "# Lion [lion]" in factory.options[2].system_prompt


def test_card_failure_falls_back_to_base_prompt(monkeypatch):
    def boom(*args):
        raise RuntimeError("no cards")

    monkeypatch.setattr(kc, "system_prompt_for_draft", boom)
    brain, factory, _ = make(DRAFT_A)
    ask(brain)
    assert factory.options[0].system_prompt == kc.base_prompt() and brain.cards_in_prompt is False


def test_warm_up_skipped_without_draft_and_done_with_it():
    brain, factory, holder = make(None)
    brain.warm_up()
    run(brain.step())
    assert factory.clients == []
    holder["draft"] = ("nevermore", [], [])
    brain.warm_up()
    run(brain.step())
    assert len(factory.clients) == 1 and factory.clients[0].connected
    assert "# Shadow Fiend [nevermore]" in factory.options[0].system_prompt


def test_refs_added_to_manual_and_items_requests_only():
    seen = []

    def refs(kind, note):
        seen.append(kind)
        return "КАРТОЧКА BKB" if kind in ("manual", "items") else ""

    brain, factory, _ = make(DRAFT_A, refs=refs)
    ask(brain, "manual", "Вопрос игрока: бкб?")
    ask(brain, "periodic")
    assert "=== Справка по предметам" in factory.queries[0] and "КАРТОЧКА BKB" in factory.queries[0]
    assert "Справка по предметам" not in factory.queries[1]
    assert factory.queries[0].startswith("Тип запроса: manual\n")


def test_refs_failure_does_not_break_request():
    def refs(kind, note):
        raise RuntimeError("boom")

    brain, factory, _ = make(DRAFT_A, refs=refs)
    ask(brain, "manual", "вопрос")
    assert brain.calls == 1 and brain.last_error is None and len(factory.queries) == 1


def make_core(hero="nevermore", team="radiant", draft=True):
    core = Core(dict(DEFAULTS, log_raw_gsi=False), voice=SilentVoice(), client_factory=Factory())
    state = GameState(received_at=0, phase="game", clock=840, hero=hero, team=team, level=10)
    if draft:
        state.draft = Draft(picks={"radiant": ["nevermore", "crystal_maiden", "mars", "antimage", "lion"],
                                   "dire": ["puck", "pudge", "slark", "phantom_assassin", "zuus"]})
    core.state = state
    return core


def test_core_draft_info_splits_teams_and_handles_missing_data():
    core = make_core()
    assert core.draft_info() == ("nevermore", ["crystal_maiden", "mars", "antimage", "lion"],
                                 ["puck", "pudge", "slark", "phantom_assassin", "zuus"])
    dire = make_core(hero="pudge", team="dire")
    assert dire.draft_info()[0] == "pudge" and "nevermore" in dire.draft_info()[2]
    assert make_core(draft=False).draft_info() == ("nevermore", [], [])
    core.state = None
    assert core.draft_info() is None
    assert make_core(hero=None).draft_info() is None


def test_core_refs_for_manual_question_and_items_candidates():
    core = make_core()
    text = core.brain_refs("manual", "Вопрос игрока: стоит ли брать мкб против фантомки?")
    assert "Monkey King Bar [monkey_king_bar]" in text
    assert core.brain_refs("periodic", "") == ""
    assert core.brain_refs("manual", "Игрок нажал кнопку «совет сейчас».") == ""

    class Cand:
        def __init__(self, key):
            self.key = key

    core.advice.candidates = [Cand("black_king_bar"), Cand("blink"), Cand("monkey_king_bar"), Cand("satanic")]
    items = core.brain_refs("items", "")
    assert items.count("[black_king_bar]") == 1 and "[blink]" in items and "[monkey_king_bar]" in items
    assert "[satanic]" not in items


def test_core_summary_goes_slim_when_cards_are_in_prompt():
    core = make_core()
    fat = core.brain_context("periodic")
    assert "ульта" in fat
    core.brain.cards_in_prompt = True
    slim = core.brain_context("periodic")
    assert "ульта" not in slim and "Враги: " in slim
    assert len(slim) < len(fat)


def test_build_summary_slim_drops_static_text_but_keeps_state():
    core = make_core()
    state = core.state
    from dota_coach.state import Ability
    state.abilities = [Ability(name="nevermore_requiem", level=2, cooldown=40.0, can_cast=False, passive=False)]
    names = KnowledgeNames()
    fat = build_summary(state, names=names)
    slim = build_summary(state, names=names, slim=True)
    assert "Requiem of Souls ур.2 (откат 40 с)" in slim
    assert "Shadow Fiend gathers up" in fat and "Shadow Fiend gathers up" not in slim
    assert "пробивает BKB" in fat and "пробивает BKB" not in slim
    assert "Союзники: " in slim and "Враги: Puck, Pudge" in slim
