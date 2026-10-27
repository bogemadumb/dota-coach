"""Download the official Valve datafeed (dota2.com/datafeed) into data/cache/official/<lang>/. Raw JSON."""

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach.config import ROOT  # noqa: E402

OUT = ROOT / "data" / "cache" / "official"
BASE = "https://www.dota2.com/datafeed/"
LANGS = ("russian", "english")
MAX_AGE = 24 * 3600
RATE = 3.0
WORKERS = 4
PATCH_PREFIX = "7.41"


class Limiter:
    def __init__(self, rate: float):
        self.step = 1.0 / rate
        self.next = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next)
            self.next = at + self.step
        if at > now:
            time.sleep(at - now)


LIMIT = Limiter(RATE)


def fresh(path: Path, force: bool) -> bool:
    return not force and path.exists() and path.stat().st_size > 2 and time.time() - path.stat().st_mtime < MAX_AGE


def valid(doc) -> bool:
    if not isinstance(doc, dict):
        return False
    if "patches" in doc or "patch_number" in doc:
        return True
    return bool(isinstance(doc.get("result"), dict) and doc["result"].get("data"))


def fetch(client: httpx.Client, endpoint: str, params: dict, tries: int = 6) -> bytes:
    delay = 2.0
    err = "?"
    for attempt in range(tries):
        LIMIT.wait()
        wait = delay
        try:
            r = client.get(BASE + endpoint, params=params)
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After") or delay)
                err = f"HTTP {r.status_code}"
            else:
                r.raise_for_status()
                if valid(r.json()):
                    return r.content
                err = "empty or error payload"
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as e:
            err = type(e).__name__
        if attempt < tries - 1:
            time.sleep(wait)
            delay = min(delay * 2, 30)
    raise RuntimeError(f"{endpoint} {params}: {err}")


class Job:
    def __init__(self, endpoint: str, params: dict, path: Path):
        self.endpoint, self.params, self.path = endpoint, params, path


def run_jobs(client: httpx.Client, jobs: list[Job], force: bool, stats: dict, label: str) -> None:
    def one(job: Job):
        if fresh(job.path, force):
            stats["skipped"] += 1
            return
        try:
            body = fetch(client, job.endpoint, job.params)
            job.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = job.path.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(job.path)
            stats["downloaded"] += 1
        except Exception as e:
            stats["failed"].append(f"{job.path.relative_to(OUT)}: {e}")

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, jobs))
    print(f"{label}: {len(jobs)} files", flush=True)


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="ignore the 24h freshness check")
    ap.add_argument("--all-patches", action="store_true", help="patch notes for every patch, not only 7.41*")
    ap.add_argument("--langs", nargs="+", default=list(LANGS))
    args = ap.parse_args()

    stats = {"downloaded": 0, "skipped": 0, "failed": []}
    counts: dict[str, int] = {}
    headers = {"User-Agent": "Mozilla/5.0 dota-coach-kb"}
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
        lists = []
        for lang in args.langs:
            for name in ("herolist", "itemlist", "abilitylist"):
                lists.append(Job(name, {"language": lang}, OUT / lang / f"{name}.json"))
            lists.append(Job("patchnoteslist", {"language": lang}, OUT / lang / "patchnoteslist.json"))
        run_jobs(client, lists, args.force, stats, "lists")

        hero_ids: set[int] = set()
        item_ids: set[int] = set()
        versions: list[str] = []
        for lang in args.langs:
            hl, il, pl = (OUT / lang / f"{n}.json" for n in ("herolist", "itemlist", "patchnoteslist"))
            if hl.exists():
                hero_ids |= {h["id"] for h in read(hl)["result"]["data"]["heroes"]}
            if il.exists():
                item_ids |= {i["id"] for i in read(il)["result"]["data"]["itemabilities"]}
            if pl.exists() and not versions:
                versions = [p["patch_number"] for p in read(pl)["patches"]
                            if args.all_patches or p["patch_number"].startswith(PATCH_PREFIX)]

        jobs = []
        for lang in args.langs:
            for hid in sorted(hero_ids):
                jobs.append(Job("herodata", {"language": lang, "hero_id": hid}, OUT / lang / "heroes" / f"{hid}.json"))
        run_jobs(client, jobs, args.force, stats, "heroes")
        counts["heroes"] = len(hero_ids)

        jobs = []
        for lang in args.langs:
            for iid in sorted(item_ids):
                jobs.append(Job("itemdata", {"language": lang, "item_id": iid}, OUT / lang / "items" / f"{iid}.json"))
        run_jobs(client, jobs, args.force, stats, "items")
        counts["items"] = len(item_ids)

        jobs = []
        for lang in args.langs:
            for v in versions:
                jobs.append(Job("patchnotes", {"language": lang, "version": v}, OUT / lang / "patchnotes" / f"{v}.json"))
        run_jobs(client, jobs, args.force, stats, "patchnotes")
        counts["patches"] = len(versions)

    print(f"ids: {counts}  langs: {args.langs}")
    print(f"downloaded {stats['downloaded']}, skipped fresh {stats['skipped']}, failed {len(stats['failed'])}")
    for line in stats["failed"]:
        print("FAIL", line)
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
