import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_cards as bc  # noqa: E402

from dota_coach import kb as kbmod  # noqa: E402
from dota_coach import kb_context as kc  # noqa: E402

KB = kbmod.default()
CARDS = ROOT / "data" / "kb" / "cards"
RULES = yaml.safe_load((ROOT / "data" / "kb" / "item_rules.yaml").read_text(encoding="utf-8"))
RULE_FIELDS = {"melee_only", "ranged_only", "ranged_penalty", "melee_penalty", "works_on_illusions", "unique_group",
               "pierces_debuff_immunity", "dispel", "dispellable_by", "blocked_for_heroes", "removed", "why", "note", "src"}
SAMPLE = ("nevermore", ["crystal_maiden", "mars", "antimage", "lion"], ["puck", "pudge", "slark", "phantom_assassin", "zuus"])


@pytest.fixture(scope="module")
def ctx():
    return bc.Ctx()


def test_cards_exist_for_all_heroes():
    heroes = KB.heroes()
    assert len(heroes) == 127
    for key in heroes:
        full, short = CARDS / f"{key}.md", CARDS / f"{key}.short.md"
        assert full.exists() and short.exists(), key
        assert full.read_text(encoding="utf-8").startswith("# "), key
        assert "Способности" in full.read_text(encoding="utf-8") and "Таланты" in full.read_text(encoding="utf-8"), key


def test_card_sizes_within_budget():
    full = [kc.estimate_tokens((CARDS / f"{k}.md").read_text(encoding="utf-8")) for k in KB.heroes()]
    short = [kc.estimate_tokens((CARDS / f"{k}.short.md").read_text(encoding="utf-8")) for k in KB.heroes()]
    assert max(short) <= 250
    assert 1500 <= sum(full) / len(full) <= 3100
    assert max(full) <= 4500


def test_placeholder_never_leaks_without_note():
    leaked = 0
    for key in KB.heroes():
        text = (CARDS / f"{key}.md").read_text(encoding="utf-8")
        if "[?]" in text.replace(bc.PLACEHOLDER_NOTE, ""):
            leaked += 1
            assert bc.PLACEHOLDER_NOTE in text, key
        else:
            assert bc.PLACEHOLDER_NOTE not in text, key
        assert "[?]" not in (CARDS / f"{key}.short.md").read_text(encoding="utf-8"), key
    assert leaked > 0


def test_card_header_has_attribute_numbers():
    text = (CARDS / "nevermore.md").read_text(encoding="utf-8")
    assert "Основной атрибут: ловкость" in text and "Дальний бой" in text
    assert "ловкость (основной) +1 урона, +1 скор. атаки, +0.167 брони (3.6/ур. = +3.6 урона/ур.)" in text
    assert "сила +22 HP, +0.1 реген HP" in text and "+0.1% сопр. магии" in text and "Ур.1:" in text and "Ур.25" in text
    bane = (CARDS / "bane.md").read_text(encoding="utf-8")
    assert "Универсал" in bane and "+0.45 урона" in bane


def test_card_marks_bkb_pierce_and_survivorship():
    text = (CARDS / "nevermore.md").read_text(encoding="utf-8")
    assert "Requiem of Souls — ульт" in text and "НЕ пробивает БКБ" in text
    assert "Presence of the Dark Lord — пассив, ПРОБИВАЕТ БКБ" in text
    assert text.count("Поздние предметы выглядят лучше") == 1
    assert "Herald–Guardian" in text and "Δ" in text
    assert "Против кого тяжело" in text


def test_short_card_contents():
    text = (CARDS / "phantom_assassin.short.md").read_text(encoding="utf-8")
    assert text.startswith("Phantom Assassin:") and "ближний бой" in text and "Ульт Coup de Grace: ПРОБИВАЕТ БКБ" in text
    assert "Против него" in text and "MKB" in text and "Черты:" in text


def test_mismatch_section_never_contains_d2pt_core(ctx):
    names = {ctx.item_name(k): k for k in RULES["items"]}
    checked = 0
    for key in KB.heroes():
        text = (CARDS / f"{key}.md").read_text(encoding="utf-8")
        section = text.split("## Что не подходит", 1)[1].split("\n## ", 1)[0]
        builds = bc.load_json(ROOT / "data" / "kb" / "builds" / f"{key}.json")
        core = set()
        for pos in bc.d2pt_positions(builds).values():
            core |= {e["item"] for e in pos["core"]}
        for line in section.splitlines()[1:]:
            if not line.startswith("- "):
                continue
            item = names[line[2:].split(":", 1)[0]]
            checked += 1
            assert item not in core, (key, item)
            assert item in RULES["items"]
    assert checked > 100


def test_mismatch_reasons_follow_attack_type(ctx):
    sf = (CARDS / "nevermore.md").read_text(encoding="utf-8").split("## Что не подходит", 1)[1].split("\n## ", 1)[0]
    assert "Battle Fury" in sf and "Echo Sabre" in sf
    jug = (CARDS / "juggernaut.md").read_text(encoding="utf-8").split("## Что не подходит", 1)[1].split("\n## ", 1)[0]
    assert "Battle Fury" not in jug and "Dragon Lance" in jug
    sb = (CARDS / "spirit_breaker.md").read_text(encoding="utf-8").split("## Что не подходит", 1)[1].split("\n## ", 1)[0]
    assert "Skull Basher: у этого героя Bash с предмета не срабатывает" in sb


def test_item_rules_keys_exist_in_kb():
    items = KB.index["items"]
    heroes = KB.index["heroes"]
    for key, rule in RULES["items"].items():
        assert key in items, key
        assert set(rule) <= RULE_FIELDS, (key, set(rule) - RULE_FIELDS)
        for hero in rule.get("blocked_for_heroes", []):
            assert hero in heroes, (key, hero)
        if rule.get("unique_group"):
            assert key in RULES["groups"][rule["unique_group"]]["items"], key
        if "ranged_penalty" in rule:
            assert set(rule["ranged_penalty"]) == {"melee", "ranged", "what"}
        why = rule.get("why", {})
        assert set(why) <= {"melee_only", "ranged_only", "ranged_penalty", "melee_penalty", "illusions", "blocked"}, key
    for name, group in RULES["groups"].items():
        for key in group["items"]:
            assert key in items, (name, key)
            if key in RULES["items"] and RULES["items"][key].get("unique_group"):
                assert RULES["items"][key]["unique_group"] in {n for n, g in RULES["groups"].items() if key in g["items"]}, (name, key)
    for hero in RULES["illusion_heroes"]:
        assert hero in heroes


def test_item_rules_consistent_with_official_texts():
    for key, rule in RULES["items"].items():
        item = KB.item(key)
        if rule.get("removed"):
            assert item["shop"]["purchasable"] is False, key
        if "pierces_debuff_immunity" in rule and isinstance(item["bkb_pierce"], bool):
            assert rule["pierces_debuff_immunity"] == item["bkb_pierce"], key
        if "dispellable_by" in rule and item["dispellable"] is not None:
            assert rule["dispellable_by"] == item["dispellable"], key
        if "ranged_penalty" in rule and key in ("basher", "abyssal_blade"):
            text = " ".join(s["text"] for s in item["sections_ru"])
            assert "25% в ближнем бою, 10% — в дальнем" in text, key
    assert RULES["items"]["basher"]["ranged_penalty"] == {"melee": 25, "ranged": 10, "what": "шанс Bash, %"}
    assert RULES["items"]["bfury"]["melee_only"] is True
    assert RULES["items"]["diffusal_blade"]["works_on_illusions"] is False
    assert RULES["items"]["silver_edge"]["pierces_debuff_immunity"] is False
    assert RULES["items"]["abyssal_blade"]["pierces_debuff_immunity"] is True
    assert RULES["items"]["aeon_disk"]["dispel"] == "strong"


@pytest.mark.parametrize("needle", [
    "0.45", "9/8/7", "80%", "−70%", "−50%", "Shiva", "+0.1%", "38.5%", "63.4%", "25% у ближних, 10% у дальних",
    "10/15/20/25/27/28/29/30", "Madstone", "с 0:00", "Tormentor", "Diffusal Blade и Disperser", "НЕ сжигают ману",
    "Bloodthorn", "критического удара у Bloodthorn нет", "ДВУХ", "Debuff Immunity", "Break",
    "−85%", "Spirit Vessel", "Eye of Skadi", "Aeon Disk", "Грани (facets) убраны в 7.41",
])
def test_digest_contains_key_facts(needle):
    assert needle in kc.digest()


def test_digest_states_shivas_no_longer_reduces_healing():
    text = kc.digest()
    assert "Shiva's Guard лечение НЕ снижает с 7.41" in text
    assert "9/8/7 с" in text and "4-го уровня нет с 7.41" in text


def test_digest_size_and_no_placeholders():
    assert kc.estimate_tokens(kc.digest()) <= 3300
    assert "[?]" not in kc.digest()


def test_system_prompt_for_sample_draft_under_budget():
    hero, allies, enemies = SAMPLE
    prompt = kc.system_prompt_for_draft(hero, allies, enemies)
    assert prompt.startswith(kc.base_prompt().strip()[:60])
    assert kc.digest()[:80] in prompt
    assert "# Shadow Fiend [nevermore]" in prompt
    for ref in allies + enemies:
        short = (CARDS / f"{ref}.short.md").read_text(encoding="utf-8").strip()
        assert short in prompt, ref
    assert (CARDS / "puck.md").read_text(encoding="utf-8")[:200] not in prompt
    assert kc.estimate_tokens(prompt) <= 15000


def test_system_prompt_without_hero_cards_falls_back_to_digest():
    prompt = kc.system_prompt_for_draft("не_герой", [], [])
    assert kc.digest()[:80] in prompt and "Карточка героя игрока" not in prompt


def test_system_prompt_accepts_names_and_aliases():
    a = kc.system_prompt_for_draft("npc_dota_hero_nevermore", ["Crystal Maiden"], ["zuus"])
    assert "# Shadow Fiend [nevermore]" in a and "Crystal Maiden:" in a and "Zeus:" in a


def test_prompt_rules_say_data_beats_memory():
    text = kc.base_prompt()
    assert "главнее твоей памяти" in text and "не уверен" in text and "только из справочника" in text


def test_context_for_question_digest_hero_and_items():
    text = kc.context_for_question("Дифузал сжигает ману иллюзиям?", hero="phantom_lancer")
    assert kc.digest()[:80] in text
    assert "# Phantom Lancer [phantom_lancer]" in text
    assert "Diffusal Blade [diffusal_blade]" in text


def test_context_for_question_finds_heroes_and_items_by_alias():
    text = kc.context_for_question("Пробивает ли ульта Зевс бкб и нужен ли мкб против фантомки?")
    assert "Black King Bar [black_king_bar]" in text and "Monkey King Bar [monkey_king_bar]" in text
    assert "=== Официальные данные героя zuus" in text


def test_item_cards_for_text_limits_and_skips_noise():
    assert kc.item_cards_for_text("Что слышно? Как дела сегодня?") == ""
    many = kc.item_cards_for_text("бкб, мкб, блинк, скади, радиан, манта")
    heads = [b.split("\n")[0] for b in many.split("\n\n") if "зол." in b.split("\n")[0]]
    assert len(heads) == 3


def test_hero_card_fallback_when_card_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(kc, "CARDS_DIR", tmp_path)
    kc._card.cache_clear()
    try:
        assert "Shadow Fiend" in kc.hero_card("nevermore")
    finally:
        kc._card.cache_clear()


@pytest.mark.skipif(not (ROOT / "data" / "kb" / "builds").is_dir(), reason="data/kb/builds not generated (tools/fetch_builds.py)")
@pytest.mark.parametrize("key", ["nevermore", "lion", "invoker", "bane", "spirit_breaker", "phantom_lancer"])
def test_cards_match_the_generator(ctx, key):
    assert (CARDS / f"{key}.md").read_text(encoding="utf-8") == bc.full_card(ctx, key)
    assert (CARDS / f"{key}.short.md").read_text(encoding="utf-8") == bc.short_card(ctx, key)


def test_item_cards_show_bkb_pierce_for_passive_items():
    for key in ("desolator", "blight_stone", "basher", "assault"):
        text = KB.item_text(key)
        assert "пробивает БКБ" in text, key
    assert "не пробивает БКБ" in KB.item_text("pavise")
    assert "пробивает БКБ" not in KB.item_text("black_king_bar")


def test_every_official_bool_pierce_is_in_item_rules():
    for key, row in KB.index["items"].items():
        if row["status"] != "shop":
            continue
        pierce = KB.item(key)["bkb_pierce"]
        if isinstance(pierce, bool):
            assert RULES["items"].get(key, {}).get("pierces_debuff_immunity") is pierce, key


def test_item_status_split_removed_vs_special():
    rows = KB.index["items"]
    statuses = {r["status"] for r in rows.values()}
    assert "removed_or_special" not in statuses and {"removed", "special", "shop"} <= statuses
    for key, row in rows.items():
        item = KB.item(key)
        assert item["shop"]["status"] == row["status"]
        if row["status"] in ("removed", "special"):
            assert item["shop"]["purchasable"] is False, key
        if row["status"] == "removed":
            assert item["shop"]["basis"] in ("patchnotes", "retired_neutral", "legacy_neutral_id_block"), key
    assert rows["aegis"]["status"] == "special" and rows["roshans_banner"]["status"] == "special"
    assert rows["famango"]["status"] == "special" and rows["tier1_token"]["status"] == "special"
    assert rows["eternal_shroud"]["status"] == "removed" and KB.item("eternal_shroud")["shop"]["removed_in"] == "7.41"
    assert rows["hood_of_defiance"]["status"] == "removed" and KB.item("hood_of_defiance")["shop"]["removed_in"] == "7.33"
    assert rows["force_boots"]["status"] == "removed"
    for key in ("wraith_pact", "quarterstaff", "tome_of_knowledge", "infused_raindrop", "black_king_bar"):
        assert rows[key]["status"] in ("shop", "free_stock"), key
    assert "убран из игры" in KB.item_text("eternal_shroud") and "(7.41)" in KB.item_text("eternal_shroud")


def test_infused_raindrop_is_purchasable_and_not_removed_in_rules():
    assert KB.item("infused_raindrop")["shop"]["purchasable"] is True
    assert not RULES["items"].get("infused_raindrop", {}).get("removed")


def test_removed_rules_match_kb_status():
    for key, rule in RULES["items"].items():
        if rule.get("removed"):
            assert KB.item(key)["shop"]["status"] == "removed", key
    shop_removed = [k for k, r in KB.index["items"].items() if r["status"] == "removed" and r["cost"] > 0]
    assert all(KB.item(k)["shop"]["basis"] == "patchnotes" for k in shop_removed)


def test_hero_tag_bkb_pierce_is_official_base_minus_documented_exclusions():
    doc = yaml.safe_load((ROOT / "data" / "hero_tags.yaml").read_text(encoding="utf-8"))
    tags, exclude = doc["heroes"], doc["bkb_pierce_ult_exclude"]
    for key, reason in exclude.items():
        assert key in tags and len(reason.split()) >= 3, key
        assert "bkb_pierce_ult" not in tags[key]["tags"], key
        assert kbmod.threatens_through_bkb(KB.hero(key)), f"{key} is excluded without need"
    for key in KB.heroes():
        assert ("bkb_pierce_ult" in tags[key]["tags"]) == kbmod.threatens_through_bkb(KB.hero(key), exclude), key
    for key in ("phantom_assassin", "drow_ranger", "ursa", "dragon_knight", "morphling", "rubick", "windrunner",
                "enchantress", "spectre", "dark_seer", "riki"):
        assert "bkb_pierce_ult" not in tags[key]["tags"], key
    for key in ("vengefulspirit", "shadow_demon", "nyx_assassin", "tusk", "elder_titan", "earth_spirit", "phoenix",
                "grimstroke", "death_prophet", "bounty_hunter", "void_spirit", "dawnbreaker", "kez", "pudge", "faceless_void"):
        assert "bkb_pierce_ult" in tags[key]["tags"], key


def test_mechanics_a_marks_eternal_shroud_removed():
    text = (ROOT / "data" / "kb" / "mechanics_a.md").read_text(encoding="utf-8")
    assert "Pipe/Glimmer/Eternal Shroud полезны" not in text
    assert "Eternal Shroud (20% + 3.5% за стак) **убран из игры в 7.41**" in text
    assert "Eternal Shroud убран в 7.41" in text


def test_digest_has_wisdom_shrine_and_stack_penalty():
    text = kc.digest()
    assert "Wisdom Shrine" in text and "200/500/800" in text
    assert "Стак нейтрального лагеря снижает награду на 20% (с 7.39e)" in text


def test_skill_order_is_unambiguous_on_all_cards(ctx):
    import re
    for key in KB.heroes():
        text = (CARDS / f"{key}.md").read_text(encoding="utf-8")
        match = re.search(r"Прокачка по уровням[^:]*: (.*)\.\n", text)
        assert match, key
        labels = bc.ability_labels(KB.hero(key))
        assert len(set(labels.values())) == len(labels), key
        items = re.findall(r"(\d+) (.+?)(?:, (?=\d+ )|$)", match.group(1))
        assert [int(n) for n, _ in items] == list(range(1, len(items) + 1)), key
        for _, label in items:
            assert (label in labels.values() or label == "талант") and "_" not in label, (key, label)
    sf = (CARDS / "nevermore.md").read_text(encoding="utf-8")
    assert "6 Requiem" in sf and "1 Shadowraze, 2 Presence" in sf


def test_compact_cards_keep_all_special_values():
    mars = (CARDS / "mars.md").read_text(encoding="utf-8")
    assert "дальность применения 900/1000/1100/1200" in mars
    lion = (CARDS / "lion.md").read_text(encoding="utf-8")
    assert "доп. урон в ближнем бою 20/30/40" in lion


def test_question_context_uses_full_official_text_for_named_heroes():
    text = kc.context_for_question("Какая дальность у Spear of Mars на 3 уровне, и что у Finger of Death Лиона?")
    assert "Официальные данные героя mars" in text and "Официальные данные героя lion" in text
    assert "900/1000/1100/1200" in text
    own = kc.context_for_question("Сколько урона у ульты?", hero="lion")
    assert "Карточка героя lion (сводка и сборки)" in own and "Официальные данные героя lion" in own


def test_prompt_demands_evidence_for_interactions():
    text = kc.base_prompt()
    assert "взаимодействии способностей и предметов" in text and "(не уверен)" in text


ALIAS_CASES = {
    "item": {
        "диффузал": "diffusal_blade", "дифузал": "diffusal_blade", "мкб": "monkey_king_bar", "мкбшка": "monkey_king_bar",
        "бладторн": "bloodthorn", "сатаник": "satanic", "хекс": "sheepstick", "гинь": "sheepstick", "сайт": "sheepstick",
        "бкб": "black_king_bar", "бкбшка": "black_king_bar", "аганим": "ultimate_scepter", "аг": "ultimate_scepter",
        "шард": "aghanims_shard", "линка": "sphere", "линкен": "sphere", "еул": "cyclone", "эул": "cyclone", "еулс": "cyclone",
        "форс": "force_staff", "глиммер": "glimmer_cape", "блейдмейл": "blade_mail", "манта": "manta", "абисал": "abyssal_blade",
        "абиссал": "abyssal_blade", "баттлфюри": "bfury", "бф": "bfury", "радик": "radiance", "радианс": "radiance",
        "мидас": "hand_of_midas", "дагон": "dagon", "мек": "mekansm", "мекасм": "mekansm", "гривсы": "guardian_greaves",
        "пайп": "pipe", "вессел": "spirit_vessel", "вессель": "spirit_vessel", "скади": "skadi", "шива": "shivas_guard",
        "бабочка": "butterfly", "баттерфляй": "butterfly", "даедалус": "greater_crit", "дедалус": "greater_crit",
        "крит": "greater_crit", "десо": "desolator", "дезолятор": "desolator", "сильвер": "silver_edge",
        "сильвер эдж": "silver_edge", "нулик": "nullifier", "нуллифаер": "nullifier", "аеон": "aeon_disk",
        "рефрешер": "refresher", "октарин": "octarine_core", "кая": "kaya", "яша": "yasha", "санга": "sange",
        "s&y": "sange_and_yasha", "сноу": "sange_and_yasha",
    },
    "hero": {
        "фантомка": "phantom_assassin", "па": "phantom_assassin", "сф": "nevermore", "невер": "nevermore", "пудж": "pudge",
        "зевс": "zuus", "пак": "puck", "сларк": "slark", "войд": "faceless_void", "фв": "faceless_void",
        "инвокер": "invoker", "инвок": "invoker", "тинкер": "tinker", "антимаг": "antimage", "ам": "antimage",
        "шторм": "storm_spirit", "эмбер": "ember_spirit", "лина": "lina", "лион": "lion", "кристалка": "crystal_maiden",
        "цм": "crystal_maiden", "вивер": "weaver", "медуза": "medusa", "дуза": "medusa", "хускар": "huskar",
        "бристл": "bristleback", "спектра": "spectre", "нага": "naga_siren", "пл": "phantom_lancer", "лансер": "phantom_lancer",
        "тб": "terrorblade", "террорблейд": "terrorblade", "ск": "sand_king", "скелет": "skeleton_king", "вк": "skeleton_king",
        "джагер": "juggernaut", "джагг": "juggernaut", "урса": "ursa", "троль": "troll_warlord", "тролль": "troll_warlord",
        "слардар": "slardar", "акс": "axe", "марс": "mars", "тайд": "tidehunter", "тайдхантер": "tidehunter",
        "энигма": "enigma", "магнус": "magnataur", "дарк сир": "dark_seer", "феникс": "phoenix", "фаер": "phoenix",
        "рики": "riki", "бх": "bounty_hunter", "баунти": "bounty_hunter", "клинкз": "clinkz", "снайпер": "sniper",
        "снайп": "sniper", "дроу": "drow_ranger", "грави": "gyrocopter", "гиро": "gyrocopter",
    },
}


@pytest.mark.parametrize("kind", ["item", "hero"])
def test_aliases_resolve_to_intended_keys(kind):
    for text, key in ALIAS_CASES[kind].items():
        hits = KB.search(text, kind=kind, limit=1)
        assert hits and hits[0]["key"] == key and hits[0]["score"] >= 95, (text, hits)


def test_aliases_have_no_collisions_and_valid_keys():
    import collections
    data = yaml.safe_load((ROOT / "data" / "kb" / "aliases.yaml").read_text(encoding="utf-8"))
    for section, kind in (("heroes", "hero"), ("items", "item")):
        valid = set(KB.index[section])
        owners = collections.defaultdict(set)
        for key, names in data[section].items():
            assert key in valid, (section, key)
            for name in names:
                owners[kbmod.norm(name)].add(key)
        clashes = {n: v for n, v in owners.items() if len(v) > 1}
        assert not clashes, clashes
        families = collections.defaultdict(set)
        for nm, kd, key, via in KB._names:
            if kd == kind and via != "alias":
                families[nm].add(key.rsplit("_", 1)[0] if key.rsplit("_", 1)[-1].isdigit() else key)
        for norm_name, keys in owners.items():
            other = families.get(norm_name, set()) - {k.rsplit("_", 1)[0] if k.rsplit("_", 1)[-1].isdigit() else k for k in keys}
            assert not other, (norm_name, keys, other)
