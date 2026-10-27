import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import fetch_builds as fb  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "builds"
KB = ROOT / "data" / "kb" / "builds"


@pytest.fixture(scope="module")
def consts():
    return fb.Consts()


@pytest.fixture()
def d2pt_raw():
    return json.loads((FIX / "d2pt_nevermore_pos1.json").read_text(encoding="utf-8"))


def test_hero_and_item_mapping(consts):
    assert consts.hero_key[11] == "nevermore"
    assert consts.hero_name["nevermore"] == "Shadow Fiend"
    assert consts.item_key[36] == "magic_wand"
    assert consts.item_key[1] == "blink"
    assert consts.ability_name[5059] == "nevermore_shadowraze1"
    assert fb.norm_name("Aghanim&#39;s Scepter") == fb.norm_name("Aghanim's Scepter")
    assert consts.dname_key[fb.norm_name("Black King Bar")] == "black_king_bar"


def test_page_names(consts):
    assert fb.d2pt_page_name(consts, "nevermore") == "Shadow+Fiend"
    assert fb.d2pt_page_name(consts, "furion") == "Nature%27s+Prophet"
    assert fb.dotabuff_slug(consts, "furion") == "natures-prophet"
    assert fb.dotabuff_slug(consts, "antimage") == "anti-mage"


def test_d2pt_page_name_prefers_site_display_name(consts):
    mappings = {"heroesMapping": {"76": {"displayName": "Outworld Destroyer"}, "131": {"displayName": "Ringmaster"}}}
    assert consts.hero_name["obsidian_destroyer"] != "Outworld Destroyer"
    assert fb.d2pt_page_name(consts, "obsidian_destroyer", mappings) == "Outworld+Destroyer"
    assert fb.d2pt_page_name(consts, "ringmaster", mappings) == "Ringmaster"
    assert fb.dotabuff_slug(consts, "obsidian_destroyer") == "outworld-destroyer"


def test_empty_slot_id_is_not_logged(consts):
    unm = fb.Unmapped()
    assert fb.item_by_id(consts, 0, unm) is None
    assert unm.items == {}


def test_d2pt_position_normalizer(consts, d2pt_raw):
    unm = fb.Unmapped()
    pos = fb.norm_d2pt_position(d2pt_raw["node"], consts, d2pt_raw["mappings"], unm)
    assert unm.items == {}
    assert pos["matches"] == 4436
    assert pos["winrate"] == pytest.approx(1718 / 4436, abs=1e-4)
    assert pos["starting"][0]["items"] == ["magic_wand", "faerie_fire", "faerie_fire"]
    core = pos["core"]
    assert [e["item"] for e in core][:3] == ["magic_wand", "falcon_blade", "power_treads"]
    assert core[0]["avg_time_min"] == pytest.approx(-0.7, abs=0.05)
    assert all(set(e) >= {"item", "count", "pick_rate", "winrate", "avg_time_min"} for e in core)
    assert all(k in consts.items for e in core + pos["situational"] for k in [e["item"]])
    sit = {e["item"] for e in pos["situational"]}
    assert "black_king_bar" in sit and not sit & {e["item"] for e in core}
    assert all(e["pick_rate"] >= fb.MIN_SIT_RATE for e in pos["situational"])
    sk = pos["skill_build"][0]
    assert len(sk["order"]) == 10 and sk["order"][0] == "nevermore_shadowraze1"
    assert [t["level"] for t in pos["talents"]] == [10, 15, 20, 25]
    assert pos["talents"][0]["chosen"] in ("left", "right")
    assert pos["neutral"]["1"][0]["item"] in consts.items
    assert pos["facet"]["name"] == "No Facet"
    assert set(pos["lategame_inventory"]) == {"30+", "45+", "55+"}


def test_unmapped_item_is_logged_and_dropped(consts, d2pt_raw):
    raw = copy.deepcopy(d2pt_raw)
    bd = raw["node"]["buildData"][0]["build_data"]
    bogus = dict(bd["anchor_items"][0], raw_item_id=999999, key="999999::1")
    bd["anchor_items"].append(bogus)
    unm = fb.Unmapped()
    pos = fb.norm_d2pt_position(raw["node"], consts, raw["mappings"], unm)
    assert unm.items == {"d2pt:999999": 1}
    assert len(pos["core"]) == len(d2pt_raw["node"]["buildData"][0]["build_data"]["anchor_items"])


def test_position_without_builds_is_skipped(consts, d2pt_raw):
    node = dict(d2pt_raw["node"], buildData=[])
    assert fb.norm_d2pt_position(node, consts, d2pt_raw["mappings"], fb.Unmapped()) is None


def test_normalize_d2pt_source(consts, d2pt_raw):
    src = fb.normalize_d2pt({"1": d2pt_raw["node"]}, consts, d2pt_raw["mappings"], fb.Unmapped(), "2026-10-01T00:00:00Z")
    assert src["mmr"] == "7000+" and src["patch"] == "7.41f" and src["window_days"] == 14
    assert set(src["positions"]) == {"1"}
    assert src["position_stats_8d"]["1"]["matches"] == 1712


def test_dotabuff_items_parser():
    rows = fb.parse_dotabuff_items((FIX / "dotabuff_items.html").read_text(encoding="utf-8"))
    names = [r["name"] for r in rows]
    assert names[:2] == ["Alert", "Power Treads"]
    assert "Black King Bar" in names and "Recipe: Daedalus" in names
    first = rows[0]
    assert isinstance(first["count"], int) and 0 < first["winrate"] < 1


def test_dotabuff_normalizer(consts):
    pages = {"items_week": (FIX / "dotabuff_items.html").read_text(encoding="utf-8"),
             "builds": (FIX / "dotabuff_builds.html").read_text(encoding="utf-8")}
    unm = fb.Unmapped()
    src = fb.normalize_dotabuff(pages, consts, unm, "2026-10-01T00:00:00Z")
    items = [r["item"] for r in src["windows"]["week"]]
    assert "power_treads" in items and "black_king_bar" in items and "dagon_2" in items
    assert not any(i.startswith("recipe") for i in items)
    assert unm.items == {}
    assert src["mmr"] == "all" and src["positions"] == {}
    assert src["skill_priorities"] and src["skill_priorities"][0]["hotkeys"]
    assert all(0 < p["build_rate"] <= 1 for p in src["skill_priorities"])
    assert src["talents"] and {"level", "left", "right"} <= set(src["talents"][0])


def test_write_kb_merges_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "KB_DIR", tmp_path)
    fb.write_kb("nevermore", 11, "d2pt", {"x": 1}, "7.41f")
    fb.write_kb("nevermore", 11, "dotabuff", {"y": 2}, None)
    doc = json.loads((tmp_path / "nevermore.json").read_text(encoding="utf-8"))
    assert doc["hero"] == "nevermore" and doc["hero_id"] == 11 and doc["patch"] == "7.41f"
    assert doc["sources"] == {"d2pt": {"x": 1}, "dotabuff": {"y": 2}}


def _kb_files():
    return sorted(KB.glob("*.json")) if KB.exists() else []


@pytest.mark.skipif(not _kb_files(), reason="data/kb/builds not generated")
def test_generated_files_schema(consts):
    valid_items = set(consts.items)
    for path in _kb_files():
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["hero"] == path.stem and doc["hero"] in consts.hero_name
        assert doc["patch"] and set(doc["sources"]) <= {"d2pt", "dotabuff"}
        for pos, entry in doc["sources"].get("d2pt", {}).get("positions", {}).items():
            assert pos in fb.POSITIONS
            assert entry["matches"] > 0 and 0 <= entry["winrate"] <= 1
            for e in entry["core"] + entry["situational"]:
                assert e["item"] in valid_items, (path.name, e["item"])
        for window in doc["sources"].get("dotabuff", {}).get("windows", {}).values():
            assert all(r["item"] in valid_items for r in window), path.name
