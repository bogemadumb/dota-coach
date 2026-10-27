import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from dota_coach import gsi_fields  # noqa: E402
from dota_coach.state import Draft, Event, GameState, Item  # noqa: E402
from dota_coach.summary import PlainNames, build_summary  # noqa: E402
from simulate import DIRE, RADIANT, Match  # noqa: E402


def mid_game(clock=840) -> GameState:
    match = Match("t", seed=3)
    for c in range(-90, clock + 1):
        match.advance(c)
    state = gsi_fields.parse(match.payload("game", clock, 0))
    state.draft = Draft(picks={"radiant": list(RADIANT), "dire": list(DIRE)}, bans={"radiant": ["axe"], "dire": []})
    return state


def test_none_state():
    assert "нет" in build_summary(None)


def test_core_fields_present():
    state = mid_game()
    text = build_summary(state)
    assert "Время 14:00 (игра" in text
    assert "Мы: Radiant" in text
    assert f"Герой: Nevermore, ур. {state.level}" in text
    assert f"K/D/A {state.kills}/{state.deaths}/{state.assists}" in text
    assert f"LH/DN {state.last_hits}/{state.denies}" in text
    assert f"GPM/XPM {state.gpm}/{state.xpm}" in text
    assert f"Золото {state.gold} (надёжное {state.gold_reliable}, ненадёжное {state.gold_unreliable})" in text
    assert "Выкуп" in text
    assert "Нейтралка: Arcane Ring" in text
    assert "Nevermore Shadowraze1 ур." in text or "Shadowraze1" in text
    assert "Союзники: Crystal Maiden, Mars, Antimage, Lion." in text
    assert "Враги: Puck, Pudge, Slark, Phantom Assassin, Zuus." in text
    assert "Баны: Axe." in text


def test_own_hero_not_in_allies_and_enemies_follow_team():
    state = mid_game()
    state.team = "dire"
    state.hero = "puck"
    text = build_summary(state)
    allies = text.split("Союзники: ")[1].split(".")[0]
    enemies = text.split("Враги: ")[1].split(".")[0]
    assert "Puck" not in allies and "Pudge" in allies
    assert "Nevermore" in enemies


def test_dead_hero_cooldowns_and_stash():
    state = mid_game()
    state.alive, state.respawn_seconds, state.buyback_cooldown = False, 33, 200
    state.stash = [Item("item_tango", "stash0", charges=3)]
    state.abilities[5].cooldown = 61.2
    text = build_summary(state)
    assert "мёртв, возрождение через 33 с" in text
    assert "откат 200 с" in text
    assert "Tango x3" in text
    assert "откат 62 с" in text


def test_events_last_eight_without_ticks():
    events = [{"kind": "tick", "clock": 1, "data": {}}] + [
        {"kind": "level_up", "clock": 100 + i, "data": {"level": i}} for i in range(12)
    ] + [{"kind": "match_started", "clock": 0, "data": {}}]
    text = build_summary(mid_game(), events)
    line = [ln for ln in text.splitlines() if ln.startswith("Последние события")][0]
    assert line.count("уровень") == 8
    assert "уровень 11" in line and "уровень 3;" not in line
    assert "tick" not in line and "match_started" not in line


def test_events_accept_dataclasses_and_game_events():
    events = [Event("hero_died", 500, {"respawn_seconds": 30}), Event("game_event", 520, {"type": "roshan_killed"})]
    text = build_summary(mid_game(), events)
    assert "8:20 игрок погиб, возрождение 30 с" in text
    assert "8:40 событие roshan_killed" in text


def test_extra_lines():
    text = build_summary(mid_game(), extra={"Картина матча": ["Puck: Blink", "Zuus: Aether Lens"], "Карта": {"Pudge": "пропал 25 с"}, "Пусто": []})
    assert "Картина матча: Puck: Blink; Zuus: Aether Lens" in text
    assert "Карта: Pudge: пропал 25 с" in text
    assert "Пусто" not in text


def test_custom_names_used():
    class N(PlainNames):
        def hero(self, key):
            return f"H<{key}>"

        def item(self, key):
            return f"I<{key}>"

    text = build_summary(mid_game(), names=N())
    assert "H<nevermore>" in text and "I<item_bottle>" in text


def test_size_stays_small():
    state = mid_game()
    state.stash = [Item(f"item_x{i}", f"stash{i}") for i in range(6)]
    events = [{"kind": "item_added", "clock": 800 + i, "data": {"item": "item_blink"}} for i in range(30)]
    text = build_summary(state, events, extra={"Картина матча": ["x" * 80] * 10})
    assert len(text) < 4500


def test_pregame_and_no_hero():
    state = GameState(received_at=0, phase="draft", clock=-120)
    text = build_summary(state)
    assert "Время -2:00 (пики" in text and "Герой" not in text


def real_names():
    import pytest

    from dota_coach.brain import KnowledgeNames
    names = KnowledgeNames()
    if names.kn is None:
        pytest.skip("no knowledge cache")
    return names


def test_own_abilities_carry_short_descriptions_and_costs():
    text = build_summary(mid_game(), names=real_names())
    block = text.split("Способности:\n")[1].split("\nСоюзники")[0].splitlines()
    assert len(block) == 6 and all(line.startswith("- ") for line in block)
    raze = next(ln for ln in block if ln.startswith("- Shadowraze"))
    assert "[кд 9, мана 75]" in raze and "Shadow Fiend razes the ground" in raze
    requiem = next(ln for ln in block if "Requiem of Souls" in ln)
    assert "кд 120/110/100" in requiem and "мана 150/175/200" in requiem
    for line in block:
        desc = line.split(": ", 1)[1] if ": " in line else ""
        assert len(desc) <= 125


def test_enemy_lines_have_ultimate_bkb_flag_and_russian_tags():
    text = build_summary(mid_game(), names=real_names())
    enemies = text.split("Враги:\n")[1].split("\nБаны")[0].splitlines()
    by_name = {ln.split(":")[0].lstrip("- "): ln for ln in enemies}
    assert set(by_name) == {"Puck", "Pudge", "Slark", "Phantom Assassin", "Zeus"}
    assert "ульта Dismember, пробивает BKB: да" in by_name["Pudge"]
    assert "ульта Thundergod's Wrath, пробивает BKB: нет" in by_name["Zeus"]
    assert "ульта Dream Coil, пробивает BKB: нет" in by_name["Puck"]
    assert "уклонение" in by_name["Phantom Assassin"] and "черты:" in by_name["Phantom Assassin"]
    assert "evasion" not in text


def test_plain_names_keep_one_line_enemies():
    assert "Враги: Puck, Pudge, Slark, Phantom Assassin, Zuus." in build_summary(mid_game())


def estimate_tokens(text: str) -> float:
    cyr = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch in "ёЁ")
    return cyr / 2.5 + (len(text) - cyr) / 4


def test_full_draft_summary_with_picture_and_candidates_fits_budget():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dota_coach.config import DEFAULTS
    from dota_coach.server import Core
    from dota_coach.voice import SilentVoice

    real_names()
    core = Core(dict(DEFAULTS, log_raw_gsi=False), voice=SilentVoice())
    match = Match("t", seed=3)
    for step in range(11):
        core.ingest(match.payload("draft", -150 + step, step))
    for clock in range(-90, 841):
        match.advance(clock)
        core.ingest(match.payload("pregame" if clock < 0 else "game", clock, 0))
    core.see_items("phantom_assassin", ["item_desolator", "item_power_treads", "item_black_king_bar"], "scout", 800)
    core.see_items("pudge", ["item_blink", "item_arcane_boots"], "scout", 700)
    core.see_items("lion", ["item_force_staff"], "scout", 600)
    for kind in ("plan", "death", "items", "periodic", "item_bought"):
        text = core.brain_context(kind)
        assert "Картина матча:" in text and "Покупки:" in text and "Способности:\n" in text
        assert estimate_tokens(text) < 2500, (kind, estimate_tokens(text))
    heavy = core.brain_context("plan")
    assert estimate_tokens(heavy) < 2000
    assert len(core.picture.heroes) == 10
    manual = core.brain_context("manual")
    assert "Покупки:" not in manual and estimate_tokens(manual) < estimate_tokens(heavy)


def test_extra_multiline_value():
    text = build_summary(mid_game(), extra={"Картина": "a\nb"})
    assert "Картина:\na\nb" in text
