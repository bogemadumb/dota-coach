"""Download the local knowledge cache: dotaconstants, OpenDota per-hero stats, item/hero icons."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach.config import ROOT  # noqa: E402

CACHE = ROOT / "data" / "cache"
CONST_DIR = CACHE / "dotaconstants"
OD_DIR = CACHE / "opendota"
ICON_DIR = CACHE / "icons"

CONST_BASE = "https://cdn.jsdelivr.net/gh/odota/dotaconstants@master/build/"
CONST_FALLBACK = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/"
CONST_FILES = [
    "heroes", "items", "item_ids", "abilities", "ability_ids", "hero_abilities",
    "patch", "aghs_desc", "neutral_abilities",
]
OD_BASE = "https://api.opendota.com/api"
ICON_BASE = "https://cdn.cloudflare.steamstatic.com"
MAX_AGE = 24 * 3600
OD_INTERVAL = 1.0

_last_od = 0.0


def fresh(path: Path, force: bool) -> bool:
    return not force and path.exists() and time.time() - path.stat().st_mtime < MAX_AGE


def get(client: httpx.Client, url: str, tries: int = 6) -> httpx.Response:
    delay = 2.0
    for attempt in range(tries):
        try:
            r = client.get(url)
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After") or delay)
                err = f"HTTP {r.status_code}"
            else:
                r.raise_for_status()
                return r
        except (httpx.TransportError, httpx.TimeoutException) as e:
            wait, err = delay, type(e).__name__
        if attempt == tries - 1:
            raise RuntimeError(f"{url}: {err}")
        time.sleep(wait)
        delay = min(delay * 2, 30)
    raise RuntimeError(url)


def get_opendota(client: httpx.Client, path: str):
    global _last_od
    pause = OD_INTERVAL - (time.monotonic() - _last_od)
    if pause > 0:
        time.sleep(pause)
    try:
        return get(client, OD_BASE + path).json()
    finally:
        _last_od = time.monotonic()


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def update_dotaconstants(client: httpx.Client, force: bool) -> tuple[int, int, list[str]]:
    ok = skipped = 0
    fails: list[str] = []
    for name in CONST_FILES:
        path = CONST_DIR / f"{name}.json"
        if fresh(path, force):
            skipped += 1
            continue
        try:
            try:
                r = get(client, f"{CONST_BASE}{name}.json")
            except RuntimeError:
                r = get(client, f"{CONST_FALLBACK}{name}.json")
            json.loads(r.content)
            write_atomic(path, r.content)
            ok += 1
        except Exception as e:
            fails.append(f"dotaconstants/{name}: {e}")
    return ok, skipped, fails


def load_const(name: str):
    return json.loads((CONST_DIR / f"{name}.json").read_text(encoding="utf-8"))


def update_opendota(client: httpx.Client, force: bool) -> tuple[int, int, list[str]]:
    ok = skipped = 0
    fails: list[str] = []
    jobs = [("hero_stats.json", "/heroStats")]
    for hid in sorted(int(h) for h in load_const("heroes")):
        jobs.append((f"hero_{hid}_item_popularity.json", f"/heroes/{hid}/itemPopularity"))
        jobs.append((f"hero_{hid}_matchups.json", f"/heroes/{hid}/matchups"))
    for filename, api in jobs:
        path = OD_DIR / filename
        if fresh(path, force):
            skipped += 1
            continue
        try:
            data = get_opendota(client, api)
            payload = {"fetched_at": datetime.now(timezone.utc).isoformat(), "data": data}
            write_atomic(path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            ok += 1
        except Exception as e:
            fails.append(f"opendota{api}: {e}")
    return ok, skipped, fails


def icon_jobs() -> list[tuple[Path, str]]:
    jobs = []
    for key, item in load_const("items").items():
        if item.get("img"):
            jobs.append((ICON_DIR / "items" / f"{key}.png", item["img"]))
    for hero in load_const("heroes").values():
        short = hero["name"].removeprefix("npc_dota_hero_")
        if hero.get("icon"):
            jobs.append((ICON_DIR / "heroes" / f"{short}_icon.png", hero["icon"]))
        if hero.get("img"):
            jobs.append((ICON_DIR / "heroes" / f"{short}_portrait.png", hero["img"]))
    return jobs


def update_icons(client: httpx.Client, force: bool) -> tuple[int, int, list[str]]:
    ok = skipped = 0
    fails: list[str] = []
    for path, rel in icon_jobs():
        if not force and path.exists() and path.stat().st_size > 0:
            skipped += 1
            continue
        url = ICON_BASE + rel.split("?")[0]
        try:
            write_atomic(path, get(client, url).content)
            ok += 1
        except Exception as e:
            fails.append(f"icon {path.name}: {e}")
    return ok, skipped, fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=["dotaconstants", "opendota", "icons"])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    steps = {"dotaconstants": update_dotaconstants, "opendota": update_opendota, "icons": update_icons}
    todo = [args.only] if args.only else list(steps)
    all_fails: list[str] = []
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "dota-coach/0.1"}) as client:
        for name in todo:
            if name != "dotaconstants" and not (CONST_DIR / "heroes.json").exists():
                print("dotaconstants missing, fetching first")
                steps["dotaconstants"](client, False)
            ok, skipped, fails = steps[name](client, args.force)
            print(f"{name}: downloaded {ok}, fresh/skipped {skipped}, failed {len(fails)}", flush=True)
            all_fails += fails
    for f in all_fails:
        print("FAIL", f)
    return 1 if all_fails else 0


if __name__ == "__main__":
    sys.exit(main())
