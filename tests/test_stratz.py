import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import fetch_stratz as fs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "data" / "cache" / "stratz" / "schema.json"

HERO_KEYS = {11: "nevermore", 1: "antimage", 2: "axe"}
ITEM_KEYS = {1: "blink", 108: "ultimate_scepter", 29: "boots", 63: "power_treads", 44: "tango"}

STATS = [
    {"heroId": 11, "week": 2960, "position": "POSITION_2", "bracketBasicIds": "HERALD_GUARDIAN", "matchCount": 1000, "winCount": 480},
    {"heroId": 11, "week": 2960, "position": "POSITION_1", "bracketBasicIds": "HERALD_GUARDIAN", "matchCount": 49, "winCount": 20},
    {"heroId": 11, "week": 2960, "position": "POSITION_5", "bracketBasicIds": "HERALD_GUARDIAN", "matchCount": 300, "winCount": 150},
    {"heroId": 1, "week": 2960, "position": "POSITION_2", "bracketBasicIds": "HERALD_GUARDIAN", "matchCount": 3000, "winCount": 1500},
    {"heroId": 11, "week": 2960, "position": "POSITION_2", "bracketBasicIds": "DIVINE_IMMORTAL", "matchCount": 500, "winCount": 200},
    {"heroId": 11, "week": 2960, "position": "UNKNOWN", "bracketBasicIds": "DIVINE_IMMORTAL", "matchCount": 999, "winCount": 1},
]

RAW_LOW = {
    "f2": [
        {"itemId": 1, "instance": 0, "time": 15, "matchCount": 200, "winCount": 100},
        {"itemId": 1, "instance": 0, "time": 17, "matchCount": 100, "winCount": 60},
        {"itemId": 1, "instance": 1, "time": 30, "matchCount": 5, "winCount": 5},
        {"itemId": 108, "instance": 0, "time": 30, "matchCount": 50, "winCount": 40},
        {"itemId": 99999, "instance": 0, "time": 10, "matchCount": 70, "winCount": 30},
    ],
    "s2": [
        {"itemId": 44, "instance": 0, "wasGiven": False, "matchCount": 900, "winCount": 450},
        {"itemId": 44, "instance": 1, "wasGiven": True, "matchCount": 10, "winCount": 5},
    ],
    "b2": [{"itemId": 63, "instance": 0, "timeAverage": 540.0, "matchCount": 400, "winCount": 200}],
    "n2": [],
    "f5": [], "s5": [], "b5": [], "n5": [],
    "mu": {"advantage": [{"heroId": 11, "with": [
        {"heroId2": 1, "matchCount": 100, "winCount": 55, "synergy": 3.456},
        {"heroId2": 2, "matchCount": 10, "winCount": 9, "synergy": 20.0},
    ], "vs": [
        {"heroId2": 2, "matchCount": 80, "winCount": 30, "synergy": -4.0},
        {"heroId2": 1, "matchCount": 90, "winCount": 50, "synergy": 5.0},
    ]}]},
}


def build():
    index = fs.stat_index(STATS)
    return fs.normalize_hero(
        "nevermore", 11, "7.41f", 2960, "2026-10-01T00:00:00Z", index,
        {"low": RAW_LOW}, HERO_KEYS, ITEM_KEYS,
    )


def test_stat_index_ignores_non_positions():
    index = fs.stat_index(STATS)
    assert index["by_hero"][(11, "HERALD_GUARDIAN", 2)] == (1000, 480)
    assert index["totals"][("HERALD_GUARDIAN", 2)] == 4000
    assert index["hero_totals"][(11, "HERALD_GUARDIAN")] == 1349
    assert not any(k[2] not in range(1, 6) for k in index["by_hero"])


def test_qualifying_positions_threshold():
    index = fs.stat_index(STATS)
    assert fs.qualifying_positions(index, 11, "low") == [2, 5]
    assert fs.qualifying_positions(index, 11, "high") == [2]
    assert fs.qualifying_positions(index, 11, "mid") == []


def test_normalize_position_block():
    out = build()
    assert (out["hero"], out["patch"], out["week"]) == ("nevermore", "7.41f", 2960)
    positions = out["brackets"]["low"]["positions"]
    assert set(positions) == {"2", "5"}
    p2 = positions["2"]
    assert p2["matches"] == 1000 and p2["winrate"] == 0.48
    assert p2["pick_share"] == 0.25
    assert p2["pos_share"] == round(1000 / 1349, 4)


def test_core_aggregates_minutes_and_drops_unknown_and_extra_copies():
    core = build()["brackets"]["low"]["positions"]["2"]["core"]
    assert [c["item"] for c in core] == ["blink", "ultimate_scepter"]
    blink = core[0]
    assert blink["matches"] == 300
    assert blink["winrate"] == round(160 / 300, 4)
    assert blink["avg_time_min"] == round((200 * 15 + 100 * 17) / 300, 1)
    assert blink["buy_rate"] == 0.3


def test_starting_boots_and_empty_neutral():
    p2 = build()["brackets"]["low"]["positions"]["2"]
    assert p2["starting"][0] == {"item": "tango", "copies": 1, "given": False, "matches": 900, "winrate": 0.5}
    assert p2["starting"][1]["given"] is True and p2["starting"][1]["copies"] == 2
    assert p2["boots"] == [{"item": "power_treads", "matches": 400, "winrate": 0.5, "avg_time_min": 9.0}]
    assert "neutral" not in p2


def test_matchups_sorted_filtered_and_rounded():
    mu = build()["matchups"]["low"]
    assert [m["hero"] for m in mu["with"]] == ["antimage"]
    assert mu["with"][0]["advantage"] == 3.46
    assert [m["hero"] for m in mu["vs"]] == ["antimage", "axe"]
    assert mu["vs"][1]["advantage"] == -4.0


def test_top_items_cap():
    keys = {i: f"item{i}" for i in range(1, 60)}
    rows = [{"itemId": i, "instance": 0, "time": 10, "matchCount": 100 + i, "winCount": 50} for i in range(1, 60)]
    core = fs.agg_core(rows, keys, 1000)
    assert len(core) == fs.TOP_ITEMS
    assert core[0]["matches"] == 159


def test_normalized_output_is_json_serialisable():
    json.dumps(build())


def test_query_builders_are_well_formed():
    q = fs.hero_bracket_query(11, "high", [1, 2])
    assert q.count("{") == q.count("}")
    assert "DIVINE_IMMORTAL" in q and "POSITION_2" in q and "POSITION_3" not in q
    assert "minTime:0,maxTime:0" in fs.stats_query()


def _schema_types():
    data = json.loads(SCHEMA.read_text())["data"]["__schema"]["types"]
    return {t["name"]: t for t in data}


def _named(t):
    while t.get("ofType"):
        t = t["ofType"]
    return t["name"]


def test_schema_has_every_field_and_argument_we_query():
    types = _schema_types()
    fields = {f["name"]: f for f in types["HeroStatsQuery"]["fields"]}
    text = fs.hero_bracket_query(11, "low", [2]) + fs.stats_query()
    used = re.findall(r":(\w+)\(([^)]*)\)\{([^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*)\}", text)
    names = {u[0] for u in used}
    assert names == {"itemFullPurchase", "itemStartingPurchase", "itemBootPurchase", "itemNeutral", "heroVsHeroMatchup"}
    for name, args, body in used:
        field = fields[name]
        schema_args = {a["name"] for a in field["args"]}
        for arg in re.findall(r"(\w+):", args):
            assert arg in schema_args, (name, arg)
        item_type = types[_named(field["type"])]
        top_fields = {f["name"] for f in item_type["fields"]}
        flat = body
        while re.search(r"\{[^{}]*\}", flat):
            flat = re.sub(r"\{[^{}]*\}", "", flat)
        for word in flat.split():
            assert word in top_fields, (name, word)
    stats = fields["stats"]
    stats_args = {a["name"] for a in stats["args"]}
    assert {"bracketBasicIds", "groupByPosition", "groupByBracket", "minTime", "maxTime"} <= stats_args
    stats_fields = {f["name"] for f in types[_named(stats["type"])]["fields"]}
    assert {"heroId", "week", "position", "bracketBasicIds", "matchCount", "winCount"} <= stats_fields


def test_bracket_enums_exist_in_schema():
    types = _schema_types()
    values = {e["name"] for e in types["RankBracketBasicEnum"]["enumValues"]}
    assert set(fs.BRACKETS.values()) <= values
    positions = {e["name"] for e in types["MatchPlayerPositionType"]["enumValues"]}
    assert {f"POSITION_{p}" for p in fs.POSITIONS} <= positions
