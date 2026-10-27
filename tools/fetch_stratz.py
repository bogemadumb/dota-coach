"""Fetch per-hero item/matchup stats from STRATZ GraphQL into data/kb/builds_stratz/<hero>.json."""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach.config import ROOT  # noqa: E402

CACHE = ROOT / "data" / "cache" / "stratz"
RAW = CACHE / "raw"
OUT = ROOT / "data" / "kb" / "builds_stratz"
CONST = ROOT / "data" / "cache" / "dotaconstants"

URL = "https://api.stratz.com/graphql"
KEYCHAIN_SERVICE = "stratz_api_token"
KEYCHAIN_ACCOUNT = "dimasimonik"

BRACKETS = {"low": "HERALD_GUARDIAN", "mid": "CRUSADER_ARCHON", "high": "DIVINE_IMMORTAL"}
POSITIONS = (1, 2, 3, 4, 5)
MIN_MATCHES = 50
TOP_ITEMS = 25
MIN_ITEM_MATCHES = 5
MIN_ITEM_SHARE = 0.01
MIN_MATCHUP = 50
WEEK_SECONDS = 7 * 24 * 3600
MIN_INTERVAL = 0.5
HOUR_FLOOR = 200
DEFAULT_MAX_AGE_H = 12.0


def load_keys() -> tuple[dict[int, str], dict[int, str]]:
    heroes = json.loads((CONST / "heroes.json").read_text())
    item_ids = json.loads((CONST / "item_ids.json").read_text())
    hero_keys = {int(i): h["name"].removeprefix("npc_dota_hero_") for i, h in heroes.items()}
    item_keys = {int(i): k for i, k in item_ids.items()}
    return hero_keys, item_keys


def get_token() -> str:
    out = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
        capture_output=True, text=True,
    )
    token = out.stdout.strip()
    if out.returncode != 0 or not token:
        raise SystemExit("STRATZ token not found in Keychain")
    return token


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(
            timeout=180,
            headers={
                "Authorization": f"Bearer {get_token()}",
                "User-Agent": "STRATZ_API",
                "Content-Type": "application/json",
            },
        )
        self.requests = 0
        self.last = 0.0

    @staticmethod
    def _num(headers, name: str) -> int | None:
        value = headers.get(name)
        return int(value) if value and value.isdigit() else None

    def _throttle(self) -> None:
        wait = MIN_INTERVAL - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)

    def _after(self, headers) -> None:
        hour = self._num(headers, "x-ratelimit-remaining-hour")
        minute = self._num(headers, "x-ratelimit-remaining-minute")
        day = self._num(headers, "x-ratelimit-remaining-day")
        if day is not None and day < 300:
            raise SystemExit("daily STRATZ budget nearly exhausted, stopping")
        if hour is not None and hour < HOUR_FLOOR:
            print(f"  hour budget low ({hour}), sleeping 5 min", flush=True)
            time.sleep(300)
        elif minute is not None and minute < 8:
            time.sleep(30)

    def query(self, text: str) -> dict:
        delay = 5.0
        for attempt in range(6):
            self._throttle()
            self.last = time.monotonic()
            try:
                resp = self.http.post(URL, json={"query": text})
            except httpx.HTTPError as exc:
                print(f"  network error {type(exc).__name__}, retry in {delay:.0f}s", flush=True)
                time.sleep(delay)
                delay *= 2
                continue
            self.requests += 1
            if resp.status_code in (429, 502, 503, 504):
                wait = float(resp.headers.get("retry-after", delay))
                print(f"  http {resp.status_code}, retry in {wait:.0f}s", flush=True)
                time.sleep(max(wait, delay))
                delay *= 2
                continue
            resp.raise_for_status()
            self._after(resp.headers)
            data = resp.json()
            if data.get("errors"):
                raise RuntimeError(json.dumps(data["errors"])[:500])
            return data["data"]
        raise RuntimeError("STRATZ request failed after retries")


def pos_enum(p: int) -> str:
    return f"POSITION_{p}"


def stats_query() -> str:
    brackets = ",".join(BRACKETS.values())
    return (
        "{heroStats{stats(bracketBasicIds:[%s],groupByPosition:true,groupByBracket:true,minTime:0,maxTime:0)"
        "{heroId week position bracketBasicIds matchCount winCount}}}" % brackets
    )


def hero_bracket_query(hero_id: int, bracket: str, positions: list[int]) -> str:
    b = BRACKETS[bracket]
    parts = []
    for p in positions:
        args = f"heroId:{hero_id},bracketBasicIds:[{b}],positionIds:[{pos_enum(p)}]"
        parts.append(f"f{p}:itemFullPurchase({args},matchLimit:0){{itemId instance time matchCount winCount}}")
        parts.append(f"s{p}:itemStartingPurchase({args}){{itemId instance wasGiven matchCount winCount}}")
        parts.append(f"b{p}:itemBootPurchase({args}){{itemId instance timeAverage matchCount winCount}}")
        parts.append(f"n{p}:itemNeutral({args}){{itemId matchCount winCount equippedMatchCount equippedMatchWinCount}}")
    parts.append(
        f"mu:heroVsHeroMatchup(heroId:{hero_id},bracketBasicIds:[{b}])"
        "{advantage{heroId with{heroId2 matchCount winCount synergy} vs{heroId2 matchCount winCount synergy}}}"
    )
    return "{heroStats{" + " ".join(parts) + "}}"


def pct(wins: int, matches: int) -> float:
    return round(wins / matches, 4) if matches else 0.0


def agg_core(rows: list[dict], item_keys: dict[int, str], pos_matches: int) -> list[dict]:
    acc: dict[int, list[float]] = {}
    for r in rows:
        if r.get("instance") != 0 or not r.get("matchCount"):
            continue
        a = acc.setdefault(r["itemId"], [0, 0, 0.0])
        a[0] += r["matchCount"]
        a[1] += r.get("winCount") or 0
        a[2] += r["matchCount"] * (r.get("time") or 0)
    out = []
    floor = max(MIN_ITEM_MATCHES, MIN_ITEM_SHARE * pos_matches)
    for item_id, (m, w, t) in acc.items():
        key = item_keys.get(item_id)
        if key is None or m < floor:
            continue
        out.append({
            "item": key, "matches": int(m), "winrate": pct(w, m),
            "buy_rate": round(m / pos_matches, 4) if pos_matches else 0.0,
            "avg_time_min": round(t / m, 1),
        })
    out.sort(key=lambda x: -x["matches"])
    return out[:TOP_ITEMS]


def agg_starting(rows: list[dict], item_keys: dict[int, str]) -> list[dict]:
    out = []
    for r in rows:
        key = item_keys.get(r["itemId"])
        if key is None or not r.get("matchCount"):
            continue
        out.append({
            "item": key, "copies": r["instance"] + 1, "given": bool(r.get("wasGiven")),
            "matches": r["matchCount"], "winrate": pct(r.get("winCount") or 0, r["matchCount"]),
        })
    out.sort(key=lambda x: -x["matches"])
    return out[:TOP_ITEMS]


def agg_boots(rows: list[dict], item_keys: dict[int, str]) -> list[dict]:
    out = []
    for r in rows:
        key = item_keys.get(r["itemId"])
        if key is None or r.get("instance") != 0 or not r.get("matchCount"):
            continue
        out.append({
            "item": key, "matches": r["matchCount"],
            "winrate": pct(r.get("winCount") or 0, r["matchCount"]),
            "avg_time_min": round((r.get("timeAverage") or 0) / 60, 1),
        })
    out.sort(key=lambda x: -x["matches"])
    return out


def agg_neutral(rows: list[dict], item_keys: dict[int, str]) -> list[dict]:
    out = []
    for r in rows:
        key = item_keys.get(r.get("itemId"))
        if key is None or not r.get("matchCount"):
            continue
        eq = r.get("equippedMatchCount") or 0
        out.append({
            "item": key, "matches": r["matchCount"], "winrate": pct(r.get("winCount") or 0, r["matchCount"]),
            "equipped_matches": eq, "equipped_winrate": pct(r.get("equippedMatchWinCount") or 0, eq),
        })
    out.sort(key=lambda x: -x["matches"])
    return out[:TOP_ITEMS]


def agg_matchups(block: dict | None, hero_keys: dict[int, str]) -> dict:
    result = {"vs": [], "with": []}
    entries = (block or {}).get("advantage") or []
    if not entries:
        return result
    for side in ("vs", "with"):
        rows = []
        for r in entries[0].get(side) or []:
            key = hero_keys.get(r["heroId2"])
            if key is None or (r.get("matchCount") or 0) < MIN_MATCHUP:
                continue
            rows.append({
                "hero": key, "matches": r["matchCount"],
                "winrate": pct(r.get("winCount") or 0, r["matchCount"]),
                "advantage": round(r.get("synergy") or 0, 2),
            })
        rows.sort(key=lambda x: -x["advantage"])
        result[side] = rows
    return result


def stat_index(stat_rows: list[dict]) -> dict:
    """(hero_id, bracket_enum, position_int) -> (matches, wins); also totals per (bracket, position)."""
    by_hero: dict[tuple, tuple[int, int]] = {}
    totals: dict[tuple, int] = {}
    hero_totals: dict[tuple, int] = {}
    for r in stat_rows:
        pos = str(r.get("position") or "")
        if not pos.startswith("POSITION_"):
            continue
        p = int(pos[-1])
        m = r.get("matchCount") or 0
        by_hero[(r["heroId"], r["bracketBasicIds"], p)] = (m, r.get("winCount") or 0)
        totals[(r["bracketBasicIds"], p)] = totals.get((r["bracketBasicIds"], p), 0) + m
        hero_totals[(r["heroId"], r["bracketBasicIds"])] = hero_totals.get((r["heroId"], r["bracketBasicIds"]), 0) + m
    return {"by_hero": by_hero, "totals": totals, "hero_totals": hero_totals}


def qualifying_positions(index: dict, hero_id: int, bracket: str) -> list[int]:
    b = BRACKETS[bracket]
    return [p for p in POSITIONS if index["by_hero"].get((hero_id, b, p), (0, 0))[0] >= MIN_MATCHES]


def normalize_hero(
    hero_key: str, hero_id: int, patch: str, week: int, fetched_at: str, index: dict,
    raw_by_bracket: dict[str, dict], hero_keys: dict[int, str], item_keys: dict[int, str],
) -> dict:
    brackets: dict = {}
    matchups: dict = {}
    for bracket, raw in raw_by_bracket.items():
        enum = BRACKETS[bracket]
        positions: dict = {}
        hero_total = index["hero_totals"].get((hero_id, enum), 0)
        for p in POSITIONS:
            m, w = index["by_hero"].get((hero_id, enum, p), (0, 0))
            if m < MIN_MATCHES:
                continue
            total = index["totals"].get((enum, p), 0)
            entry = {
                "matches": m, "winrate": pct(w, m),
                "pick_share": round(m / total, 4) if total else 0.0,
                "pos_share": round(m / hero_total, 4) if hero_total else 0.0,
                "starting": agg_starting(raw.get(f"s{p}") or [], item_keys),
                "core": agg_core(raw.get(f"f{p}") or [], item_keys, m),
                "boots": agg_boots(raw.get(f"b{p}") or [], item_keys),
            }
            neutral = agg_neutral(raw.get(f"n{p}") or [], item_keys)
            if neutral:
                entry["neutral"] = neutral
            positions[str(p)] = entry
        brackets[bracket] = {"positions": positions}
        matchups[bracket] = agg_matchups(raw.get("mu"), hero_keys)
    return {
        "hero": hero_key, "patch": patch, "week": week, "fetched_at": fetched_at,
        "source": "stratz", "brackets": brackets, "matchups": matchups,
    }


def is_fresh(path: Path, max_age_h: float) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < max_age_h * 3600


def load_json(path: Path):
    return json.loads(path.read_text())


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(path)


def current_version(client: Client | None, force: bool, max_age_h: float) -> dict:
    path = RAW / "game_versions.json"
    if client is not None and (force or not is_fresh(path, max_age_h)):
        data = client.query("{constants{gameVersions{id name asOfDateTime}}}")
        save_json(path, data["constants"]["gameVersions"])
    versions = load_json(path)
    now = time.time()
    return max((v for v in versions if v["asOfDateTime"] <= now), key=lambda v: v["asOfDateTime"])


def load_stats(client: Client | None, force: bool, max_age_h: float) -> list[dict]:
    path = RAW / "stats_all.json"
    if client is not None and (force or not is_fresh(path, max_age_h)):
        save_json(path, client.query(stats_query())["heroStats"]["stats"])
    return load_json(path)


def resolve_heroes(names: list[str] | None, hero_keys: dict[int, str]) -> list[tuple[int, str]]:
    all_heroes = sorted(hero_keys.items(), key=lambda kv: kv[1])
    if not names:
        return all_heroes
    wanted = {n.strip() for chunk in names for n in chunk.split(",") if n.strip()}
    picked = [(i, k) for i, k in all_heroes if k in wanted or str(i) in wanted]
    missing = wanted - {k for _, k in picked} - {str(i) for i, _ in picked}
    if missing:
        raise SystemExit(f"unknown heroes: {sorted(missing)}")
    return picked


def run(args: argparse.Namespace) -> int:
    hero_keys, item_keys = load_keys()
    heroes = resolve_heroes(args.hero, hero_keys)
    brackets = args.bracket or list(BRACKETS)
    client = None if args.offline else Client()

    version = current_version(client, args.force, args.max_age_h)
    stat_rows = load_stats(client, args.force, args.max_age_h)
    week = max(r["week"] for r in stat_rows)
    if week * WEEK_SECONDS < version["asOfDateTime"]:
        print(f"WARNING: stats week {week} starts before patch {version['name']}", flush=True)
    index = stat_index(stat_rows)
    print(f"patch {version['name']} (id {version['id']}), stats week {week}, heroes {len(heroes)}", flush=True)

    fetched = skipped = failed = 0
    failures: list[str] = []
    started = time.time()
    for n, (hero_id, key) in enumerate(heroes, 1):
        try:
            for bracket in brackets:
                path = RAW / f"{key}_{bracket}.json"
                if client is not None and (args.force or not is_fresh(path, args.max_age_h)):
                    positions = qualifying_positions(index, hero_id, bracket)
                    data = client.query(hero_bracket_query(hero_id, bracket, positions))["heroStats"]
                    data["_positions"] = positions
                    data["_week"] = week
                    save_json(path, data)
                    fetched += 1
                else:
                    skipped += 1
            raw_by_bracket = {b: load_json(RAW / f"{key}_{b}.json") for b in BRACKETS if (RAW / f"{key}_{b}.json").exists()}
            result = normalize_hero(
                key, hero_id, version["name"], week,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                index, raw_by_bracket, hero_keys, item_keys,
            )
            save_json(OUT / f"{key}.json", result)
        except (RuntimeError, httpx.HTTPError) as exc:
            failed += 1
            failures.append(f"{key}: {exc}")
            print(f"  FAIL {key}: {exc}", flush=True)
        if n % 10 == 0 or n == len(heroes):
            print(f"[{n}/{len(heroes)}] requests={client.requests if client else 0} {time.time() - started:.0f}s", flush=True)

    print(f"done: heroes={len(heroes)} bracket-requests fetched={fetched} cached={skipped} failed={failed} "
          f"http requests={client.requests if client else 0}")
    for line in failures:
        print("  ", line)
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hero", action="append", help="short hero key or id, repeatable / comma separated")
    ap.add_argument("--bracket", action="append", choices=list(BRACKETS))
    ap.add_argument("--force", action="store_true", help="refetch even if the raw cache is fresh")
    ap.add_argument("--offline", action="store_true", help="rebuild output from the raw cache only")
    ap.add_argument("--max-age-h", type=float, default=DEFAULT_MAX_AGE_H)
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
