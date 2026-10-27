import asyncio
import json
import re
import sys
from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import factcheck as fc  # noqa: E402
from dota_coach.kb import KB  # noqa: E402


@pytest.fixture(scope="module")
def kb():
    return KB()


@pytest.fixture(scope="module")
def bank(kb):
    return fc.build_questions(kb)


def test_generation_is_deterministic(kb, bank):
    again = fc.build_questions(kb)
    assert json.dumps(bank, sort_keys=True) == json.dumps(again, sort_keys=True)
    assert fc.build_questions(kb, seed=1) != bank


@pytest.mark.skipif(not (ROOT / "data" / "cache" / "official").is_dir(), reason="official datafeed cache not downloaded (tools/update_official.py)")
def test_committed_bank_matches_generator(bank):
    committed = fc.load_bank()
    assert json.dumps(committed, ensure_ascii=False, sort_keys=True) == json.dumps(bank, ensure_ascii=False, sort_keys=True)


def test_bank_shape(bank):
    counts = {c: sum(1 for q in bank if q["category"] == c) for c in fc.CATEGORIES}
    assert counts["items"] == 45 and counts["abilities"] == 45 and counts["heroes"] == 20 and counts["talents"] == 10
    assert counts["mechanics"] >= 30
    assert 140 <= len(bank) <= 170
    assert len({q["id"] for q in bank}) == len(bank)
    for q in bank:
        assert q["answer_type"] in fc.FORMAT_HINT
        assert q["question"].strip() and q["source"]
        assert "tolerance" in q
        if q["answer_type"] == "choice":
            keys = [o["key"] for o in q["options"]]
            assert q["answer"] in keys
            assert all(re.search(re.escape(f"{o['key']} — {o['text']}"), q["question"]) for o in q["options"])
        if q["answer_type"] == "yes_no":
            assert isinstance(q["answer"], bool)
        if q["answer_type"] == "items_set":
            assert isinstance(q["answer"], list) and q["answer"]


def test_machine_fields_are_latin(bank):
    for q in bank:
        assert re.fullmatch(r"[a-z0-9_.]+", q["id"]), q["id"]
        assert all(re.fullmatch(r"[a-z_]+", k) for k in q), q["id"]


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def test_every_kb_gold_is_rederivable(kb, bank):
    checked = 0
    for q in bank:
        ref = q.get("ref")
        if not ref:
            continue
        got = fc.derive(kb, ref)
        if q["subtype"] == "ability_ultimate":
            ult = [kb.ability(k)["name_en"] for k in got]
            assert ult == [q["ultimate"]], q["id"]
            assert next(o["text"] for o in q["options"] if o["key"] == q["answer"]) == q["ultimate"]
        elif q["subtype"] == "talent_level":
            assert str(got) == q["answer"], q["id"]
        else:
            assert same(got, q["answer"]), (q["id"], got, q["answer"])
        checked += 1
    assert checked >= 100


def test_answers_are_not_trivial(bank):
    for sub in ("item_in_shop", "ability_pierce", "item_pierce", "ability_dispel"):
        values = {q["answer"] for q in bank if q["subtype"] == sub}
        assert values == {True, False}, sub


def test_removed_items_are_asked(bank):
    gold = {q["id"]: q["answer"] for q in bank if q["subtype"] == "item_in_shop"}
    assert gold["item_in_shop.eternal_shroud"] is False
    assert gold["item_in_shop.hood_of_defiance"] is False


def test_mechanics_evidence_is_in_sources_and_verified(bank):
    mechanics = [q for q in bank if q["category"] == "mechanics"]
    assert mechanics
    for q in mechanics:
        line = fc.evidence_line(q["file"], q["evidence"])
        assert line, (q["id"], q["evidence"])
        assert fc.UNVERIFIED not in line, q["id"]
        assert q["source"].startswith(f"mechanics_{q['file'].lower()}.md")
        titles = [t for t, _ in fc.split_sections(q["file"])]
        wanted = q["source"].split(", ", 1)[1]
        assert any(t.startswith(wanted.split(".")[0] + ".") for t in titles), q["id"]


def test_mechanics_checks_match_kb(kb, bank):
    checked = 0
    for q in bank:
        check = q.get("check")
        if not check:
            continue
        got = fc.derive(kb, check)
        if isinstance(got, set):
            assert got == {q["answer"]}, q["id"]
        else:
            assert same(got, q["answer"]), (q["id"], got, q["answer"])
        checked += 1
    assert checked >= 8


def test_mechanics_excerpt_contains_keyword_lines(bank):
    q = next(x for x in bank if x["id"] == "mech.mkb_chance")
    text = fc.mechanics_excerpt(q)
    assert "Monkey King Bar" in text and "80%" in text
    for q in bank:
        if q["category"] == "mechanics":
            assert fc.mechanics_excerpt(q).strip()


def test_grade_number():
    assert fc.grade_number(37.5, 37.5)
    assert fc.grade_number("37,5%", 37.5)
    assert fc.grade_number("≈ 9 секунд", 9)
    assert fc.grade_number("1 600", 1600)
    assert fc.grade_number("−10", -10)
    assert fc.grade_number("0.45", 0.45, 0.005)
    assert fc.grade_number(37.4, 37.5, 0.1)
    assert not fc.grade_number(37.3, 37.5, 0.1)
    assert not fc.grade_number("около десяти", 10)
    assert not fc.grade_number(None, 10)
    assert not fc.grade_number(True, 1)
    assert not fc.grade_number("9/8/7", 8)


def test_grade_yes_no_russian():
    for yes in ("да", "Да.", "ДА, пробивает", True, "yes"):
        assert fc.grade_yes_no(yes, True), yes
        assert not fc.grade_yes_no(yes, False), yes
    for no in ("нет", "Нет, не пробивает", "НЕТ!", False, "no"):
        assert fc.grade_yes_no(no, False), no
        assert not fc.grade_yes_no(no, True), no
    for junk in ("не уверен", "", None, "возможно", 5):
        assert not fc.grade_yes_no(junk, True)
        assert not fc.grade_yes_no(junk, False)


def test_grade_choice():
    opts = [{"key": "A", "text": "первое"}, {"key": "B", "text": "второе"}, {"key": "C", "text": "третье"}]
    assert fc.grade_choice("B", "B", opts)
    assert fc.grade_choice(" b. ", "B", opts)
    assert fc.grade_choice("B) второе", "B", opts)
    assert fc.grade_choice("второе", "B", opts)
    assert not fc.grade_choice("A", "B", opts)
    assert not fc.grade_choice("", "B", opts)
    assert not fc.grade_choice(None, "B", opts)
    attr = [{"key": "str", "text": "сила"}, {"key": "agi", "text": "ловкость"}, {"key": "all", "text": "универсал"}]
    assert fc.grade_choice("agi", "agi", attr)
    assert fc.grade_choice("Ловкость", "agi", attr)
    assert not fc.grade_choice("str", "agi", attr)
    levels = [{"key": k, "text": f"ряд {k} уровня"} for k in ("10", "15", "20", "25")]
    assert fc.grade_choice(20, "20", levels)
    assert not fc.grade_choice("25", "20", levels)


def test_grade_items_set_with_aliases(kb):
    gold = ["mithril_hammer", "ogre_axe"]
    assert fc.grade_items_set(kb, ["Mithril Hammer", "Ogre Axe"], gold)
    assert fc.grade_items_set(kb, ["Ogre Axe", "Mithril Hammer", "Black King Bar Recipe"], gold)
    assert fc.grade_items_set(kb, "Mithril Hammer, Ogre Axe, рецепт", gold)
    assert fc.grade_items_set(kb, ["ogre_axe", "mithril_hammer"], gold)
    assert not fc.grade_items_set(kb, ["Ogre Axe"], gold)
    assert not fc.grade_items_set(kb, ["Ogre Axe", "Mithril Hammer", "Belt of Strength"], gold)
    assert not fc.grade_items_set(kb, ["Ogre Axe", "Несуществующий предмет"], gold)
    assert not fc.grade_items_set(kb, None, gold)
    assert fc.resolve_item(kb, "бкб") == "black_king_bar"
    assert fc.resolve_item(kb, "BKB") == "black_king_bar"
    assert fc.resolve_item(kb, "мкб") == "monkey_king_bar"
    assert fc.grade_items_set(kb, ["БКБ"], ["black_king_bar"])


def test_grade_text_key():
    assert fc.grade_text_key("To Hell and Back", "To Hell and Back")
    assert fc.grade_text_key("Врождённая: to hell and back (Lion)", "To Hell and Back")
    assert fc.grade_text_key("Predator", "Predator", ["viper_predator"])
    assert fc.grade_text_key("viper_predator", "Predator", ["viper_predator"])
    assert not fc.grade_text_key("Poison Attack", "Predator")
    assert not fc.grade_text_key(None, "Predator")
    assert not fc.grade_text_key("", "Predator")


def test_grade_dispatch(kb, bank):
    for q in bank:
        gold = q["answer"]
        if q["answer_type"] == "items_set":
            gold = [kb.item(k)["name_en"] for k in gold]
        assert fc.grade(kb, q, gold), q["id"]


def test_parse_answers_variants():
    plain = '[{"id": "a", "answer": 5}, {"id": "b", "answer": "да"}]'
    assert fc.parse_answers(plain) == {"a": 5, "b": "да"}
    assert fc.parse_answers("```json\n" + plain + "\n```") == {"a": 5, "b": "да"}
    assert fc.parse_answers("Вот ответы:\n" + plain + "\nГотово.") == {"a": 5, "b": "да"}
    assert fc.parse_answers('{"a": 5, "b": "нет"}') == {"a": 5, "b": "нет"}
    assert fc.parse_answers('{"answers": [{"id": "a", "answer": 1}]}') == {"a": 1}
    broken = '[{"id": "a", "answer": 5}, {"id": "b", "answer": "да"},'
    assert fc.parse_answers(broken) == {"a": 5, "b": "да"}
    assert fc.parse_answers('[{"id": 7, "answer": 1}]') == {"7": 1}
    assert fc.parse_answers("не знаю") == {}
    assert fc.parse_answers("") == {}
    assert fc.parse_answers(None) == {}
    assert fc.parse_answers('[{"id": "a", "answer": ["x", "y"]}]') == {"a": ["x", "y"]}


def test_interleave_covers_categories(bank):
    part = fc.interleave(bank, 12)
    assert len(part) == 12
    assert {q["category"] for q in part} == set(fc.CATEGORIES)
    assert fc.interleave(bank, None) == bank
    assert [q["id"] for q in part] == [q["id"] for q in bank if q["id"] in {p["id"] for p in part}]


def test_batches_bare_and_cards_split(bank):
    batches = fc.make_batches(bank, "bare")
    assert all(len(g) <= 10 for g, _ in batches)
    assert sum(len(g) for g, _ in batches) == len(bank)
    assert all(ctx == "" for _, ctx in batches)
    huge = "я" * (fc.CONTEXT_TOKEN_LIMIT * 3)

    def provide(q):
        return huge + q["id"]

    split = fc.make_batches(bank[:10], "cards", provide)
    assert len(split) == 10 and all(len(g) == 1 for g, _ in split)
    small = fc.make_batches(bank[:10], "cards", lambda q: "справка " + q["subtype"])
    assert len(small) == 1 and small[0][1].count("справка") <= 10


def test_union_context_dedupes_blocks(bank):
    qs = bank[:3]
    text = fc.union_context(qs, lambda q: "общий блок\n\nсвой " + q["id"])
    assert text.count("общий блок") == 1
    assert all(q["id"] in text for q in qs)


def test_prompt_lists_ids_and_context(bank):
    prompt = fc.build_prompt(bank[:3], "карточка героя")
    assert "карточка героя" in prompt
    assert all(f"[{q['id']}]" in prompt for q in bank[:3])
    assert "JSON-массив" in prompt
    assert "карточка" not in fc.build_prompt(bank[:3])


class FakeClient:
    def __init__(self, factory):
        self.factory = factory
        self.last = ""

    async def connect(self):
        self.factory.connected += 1

    async def disconnect(self):
        self.factory.closed += 1

    async def query(self, text):
        self.last = text
        self.factory.queries.append(text)

    async def receive_response(self):
        await asyncio.sleep(0)
        reply = self.factory.reply(self.last, self.factory.queries.count(self.last))
        if isinstance(reply, Exception):
            raise reply
        yield AssistantMessage(content=[TextBlock(text=reply)], model="fake")
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id="fake")


class FakeFactory:
    def __init__(self, reply):
        self.reply = reply
        self.queries = []
        self.options = []
        self.connected = 0
        self.closed = 0

    def __call__(self, options):
        self.options.append(options)
        return FakeClient(self)


def ids_in(prompt: str) -> list[str]:
    return re.findall(r"\[([a-z0-9_.]+)\]", prompt)


def perfect(bank, kb):
    gold = {}
    for q in bank:
        value = q["answer"]
        if q["answer_type"] == "items_set":
            value = [kb.item(k)["name_en"] for k in value]
        elif q["answer_type"] == "yes_no":
            value = "да" if value else "нет"
        gold[q["id"]] = value

    def reply(prompt, nth):
        return json.dumps([{"id": i, "answer": gold[i]} for i in ids_in(prompt) if i in gold], ensure_ascii=False)

    return reply


def test_run_mode_bare_with_fake_client(kb, bank):
    sample = fc.interleave(bank, 25)
    factory = FakeFactory(perfect(bank, kb))
    res = asyncio.run(fc.run_mode(kb, sample, "bare", "sonnet", factory, concurrency=3))
    assert res["questions"] == 25 and res["correct"] == 25
    assert res["calls"] == res["batches"] == 3
    assert factory.connected == factory.closed == 3
    assert all(o.tools == [] and o.setting_sources == [] and o.model == "sonnet" for o in factory.options)
    assert all(o.system_prompt == fc.SYSTEM_BARE for o in factory.options)
    assert all("Справочник" not in q for q in factory.queries)


def test_run_mode_cards_puts_context_into_message(kb, bank):
    sample = [q for q in bank if q["id"] in ("item_cost.arcane_boots", "mech.mkb_chance", "hero_attr.razor")]
    factory = FakeFactory(perfect(bank, kb))
    res = asyncio.run(fc.run_mode(kb, sample, "cards", "sonnet", factory, concurrency=1))
    assert res["correct"] == len(sample)
    assert res["context_source"] in ("fallback", "kb_context")
    prompt = factory.queries[0]
    assert "Справочник по патчу 7.41f" in prompt
    assert all(o.system_prompt == fc.SYSTEM_CARDS for o in factory.options)


def test_run_mode_retries_garbage_then_succeeds(kb, bank):
    sample = fc.interleave(bank, 10)
    good = perfect(bank, kb)

    def reply(prompt, nth):
        return "Извини, вот текст без JSON" if nth == 1 and "Вопросы:" in prompt else good(prompt, nth)

    factory = FakeFactory(reply)
    res = asyncio.run(fc.run_mode(kb, sample, "bare", "sonnet", factory, concurrency=1))
    assert res["correct"] == 10
    assert res["calls"] == 2 and res["batches"] == 1


def test_run_mode_partial_answers_and_wrong_ones(kb, bank):
    sample = fc.interleave(bank, 10)
    good = perfect(bank, kb)
    dropped = sample[0]["id"]
    wrong = sample[1]["id"]

    def reply(prompt, nth):
        rows = json.loads(good(prompt, nth))
        out = []
        for r in rows:
            if r["id"] == dropped:
                continue
            if r["id"] == wrong:
                r["answer"] = "заведомо неверно"
            out.append(r)
        return json.dumps(out, ensure_ascii=False)

    factory = FakeFactory(reply)
    res = asyncio.run(fc.run_mode(kb, sample, "bare", "sonnet", factory, concurrency=1))
    by_id = {r["id"]: r for r in res["results"]}
    assert res["calls"] == 3
    assert not by_id[dropped]["answered"] and not by_id[dropped]["correct"]
    assert by_id[wrong]["answered"] and not by_id[wrong]["correct"]
    assert res["correct"] == 8


def test_run_mode_survives_client_errors(kb, bank):
    sample = fc.interleave(bank, 10)
    good = perfect(bank, kb)

    def reply(prompt, nth):
        return RuntimeError("boom") if nth == 1 else good(prompt, nth)

    factory = FakeFactory(reply)
    res = asyncio.run(fc.run_mode(kb, sample, "bare", "sonnet", factory, concurrency=1))
    assert res["correct"] == 10 and res["calls"] == 2
    assert res["errors"] and "boom" in res["errors"][0]


def test_report_lists_wrong_answers_and_doubtful_gold(kb, bank):
    sample = fc.interleave(bank, 10)
    good = perfect(bank, kb)
    target = sample[0]["id"]

    def broken(prompt, nth):
        rows = json.loads(good(prompt, nth))
        for r in rows:
            if r["id"] == target:
                r["answer"] = "мимо"
        return json.dumps(rows, ensure_ascii=False)

    bare = asyncio.run(fc.run_mode(kb, sample, "bare", "sonnet", FakeFactory(broken), concurrency=1))
    cards = asyncio.run(fc.run_mode(kb, sample, "cards", "sonnet", FakeFactory(broken), concurrency=1))
    report = fc.build_report({"bare": bare, "cards": cards}, "2026-10-01")
    assert "| items |" in report and "| ВСЕГО |" in report
    assert report.count(f"`{target}`") == 3
    assert "кандидаты на сомнительный эталон" in report
    assert "Доля ошибок, cards (" in report and "): 10.0%" in report
    assert "без ответа (null): 0" in report


def test_cli_build_writes_same_bank(tmp_path, kb, bank):
    path = tmp_path / "questions.json"
    fc.write_bank(path, kb)
    assert fc.load_bank(path) == json.loads(json.dumps(bank))


def test_forced_fallback_context_ignores_kb_context(kb, bank):
    source, provide = fc.context_provider(kb, "fallback")
    assert source == "fallback"
    q = next(x for x in bank if x["id"] == "item_cost.arcane_boots")
    assert "Arcane Boots" in provide(q)


def test_report_has_fallback_column(kb, bank):
    sample = fc.interleave(bank, 10)
    good = perfect(bank, kb)
    run = asyncio.run(fc.run_mode(kb, sample, "cards", "sonnet", FakeFactory(good), concurrency=1, context="fallback"))
    assert run["context_source"] == "fallback"
    bare = asyncio.run(fc.run_mode(kb, sample, "bare", "sonnet", FakeFactory(good), concurrency=1))
    report = fc.build_report({"bare": bare, "cards_fallback": run}, "2026-10-01")
    assert "| bare | cards_fallback |" in report
