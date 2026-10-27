import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import factcheck as fc  # noqa: E402


@pytest.mark.skipif(not (ROOT / "data" / "cache" / "official").is_dir(), reason="official datafeed cache not downloaded (tools/update_official.py)")
def test_bank_b_is_reproducible_and_independent_of_bank_a():
    kb = fc.KB()
    a = fc.load_bank(fc.QUESTIONS_PATH)
    b = fc.load_bank(fc.QUESTIONS_B_PATH)
    assert fc.build_questions(kb, fc.SEED_B, bank="b") == b
    assert fc.EXCL == {"items": set(), "heroes": set(), "abilities": set()}
    ua, ub = fc.used_entities(a), fc.used_entities([q for q in b if q["category"] != "mechanics"])
    assert all(not (ua[k] & ub[k]) for k in ua)
    assert not ({q["id"] for q in a} & {q["id"] for q in b})
    assert 150 <= len(b) <= 160
    counts = {c: sum(1 for q in b if q["category"] == c) for c in fc.CATEGORIES}
    assert counts["items"] == 45 and counts["abilities"] == 45 and counts["heroes"] == 20 and counts["talents"] == 10


def test_bank_b_mechanics_have_evidence_in_the_files():
    for q in fc.load_bank(fc.QUESTIONS_B_PATH):
        if q["category"] == "mechanics":
            assert fc.evidence_line(q["file"], q["evidence"]), q["id"]


def test_results_paths_keep_bank_a_names():
    assert fc.results_path("cards", "2026-10-01").name == "results_cards_2026-10-01.json"
    assert fc.results_path("cards", "2026-10-01", bank="b").name == "results_b_cards_2026-10-01.json"
