import json

import pytest
import yaml

from dota_coach.knowledge import CACHE_DIR

DATA = CACHE_DIR.parent
HEROES_JSON = CACHE_DIR / "dotaconstants" / "heroes.json"
TAGS_FILE = DATA / "hero_tags.yaml"
COUNTERS_FILE = DATA / "counters.yaml"


def _load():
    return yaml.safe_load(TAGS_FILE.read_text(encoding="utf-8"))


def test_yaml_parses():
    doc = _load()
    assert doc["patch"] == "7.41f"
    assert isinstance(doc["heroes"], dict)


def test_only_allowed_tags_and_counts():
    allowed = set(yaml.safe_load(COUNTERS_FILE.read_text(encoding="utf-8"))["tags"])
    for key, entry in _load()["heroes"].items():
        tags = entry["tags"]
        assert 1 <= len(tags) <= 4, key
        assert len(set(tags)) == len(tags), key
        assert set(tags) <= allowed, (key, set(tags) - allowed)
        assert len(entry["note"].split()) <= 8, key


def test_keys_sorted():
    keys = list(_load()["heroes"])
    assert keys == sorted(keys)


def test_every_cached_hero_present():
    if not HEROES_JSON.exists():
        pytest.skip("dotaconstants cache absent")
    cached = {h["name"].removeprefix("npc_dota_hero_") for h in json.loads(HEROES_JSON.read_text()).values()}
    present = set(_load()["heroes"])
    assert cached - present == set()
    assert present - cached == set()
