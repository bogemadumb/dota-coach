"""High-MMR item builds per hero per position -> data/kb/builds/<hero>.json.

Sources: d2pt (dota2protracker.com, 7000+ MMR pubs) and dotabuff (all ranks). Both sit behind Cloudflare,
so pages are loaded by a headed Chromium on a Windows box reachable over ssh (WSL), see tools/builds_browser.py.
The host is DOTA_BUILDS_SSH_HOST (default: home-pc).
Raw pages are cached in data/cache/builds/<source>/, the normalizer reads only the cache.
"""

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dota_coach.config import ROOT  # noqa: E402

CACHE = ROOT / "data" / "cache" / "builds"
CONST_DIR = ROOT / "data" / "cache" / "dotaconstants"
KB_DIR = ROOT / "data" / "kb" / "builds"
HELPER = Path(__file__).with_name("builds_browser.py")

SSH_HOST = os.environ.get("DOTA_BUILDS_SSH_HOST", "home-pc")
REMOTE_WSL = "/mnt/c/dota-builds"
REMOTE_WIN = r"C:\dota-builds"
CMD_EXE = "/mnt/c/Windows/System32/cmd.exe"
RUN_CMD = '@echo off\r\ncd /d C:\\dota-builds\r\n"C:\\Program Files\\Python312\\python.exe" -X utf8 %*\r\n'

MAX_AGE = 20 * 3600
BATCH = 40
DELAY = {"d2pt": 3.0, "dotabuff": 5.0}
MIN_POS_MATCHES = 30
DEFAULT_PATCH = "7.41f"
POSITIONS = ("1", "2", "3", "4", "5")
DOTABUFF_PAGES = {
    "items_week": "https://www.dotabuff.com/heroes/{slug}/items?date=week",
    "items_patch": "https://www.dotabuff.com/heroes/{slug}/items?date=patch_7.41",
    "builds": "https://www.dotabuff.com/heroes/{slug}/builds",
}
MIN_SIT_RATE = 0.03
MIN_FINAL_RATE = 0.03
TOP_NEUTRAL = 8


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


class Consts:
    def __init__(self, directory: Path = CONST_DIR):
        def load(name):
            return json.loads((directory / name).read_text(encoding="utf-8"))

        heroes, items, ability_ids = load("heroes.json"), load("items.json"), load("ability_ids.json")
        self.hero_key = {int(h["id"]): h["name"].removeprefix("npc_dota_hero_") for h in heroes.values()}
        self.hero_name = {self.hero_key[int(h["id"])]: h["localized_name"] for h in heroes.values()}
        self.item_key = {int(i["id"]): k for k, i in items.items() if i.get("id") is not None}
        self.ability_name = {int(i): v for k, v in ability_ids.items() for i in k.split(",")}
        self.dname_key = {}
        for k, i in items.items():
            if i.get("dname"):
                self.dname_key.setdefault(norm_name(i["dname"]), k)
        self.items = items


def norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unescape(name).lower())


def d2pt_page_name(consts: Consts, key: str, mappings: dict | None = None) -> str:
    hid = next(i for i, k in consts.hero_key.items() if k == key)
    entry = ((mappings or {}).get("heroesMapping") or {}).get(str(hid)) or {}
    return quote_plus(entry.get("displayName") or consts.hero_name[key], safe="")


DOTABUFF_SLUG = {"obsidian_destroyer": "outworld-destroyer", "ringmaster": "ringmaster"}


def dotabuff_slug(consts: Consts, key: str) -> str:
    if key in DOTABUFF_SLUG:
        return DOTABUFF_SLUG[key]
    name = consts.hero_name[key].lower().replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def read_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def write_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    tmp.replace(path)


def fresh(path: Path) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < MAX_AGE


class Unmapped:
    def __init__(self):
        self.items: dict[str, int] = {}

    def add(self, what: str) -> None:
        self.items[what] = self.items.get(what, 0) + 1


def item_by_id(consts: Consts, item_id, unm: Unmapped, mapping: dict | None = None):
    if int(item_id) == 0:
        return None
    key = consts.item_key.get(int(item_id))
    if key is None:
        short = ((mapping or {}).get(str(item_id)) or {}).get("shortName") or str(item_id)
        unm.add("d2pt:%s" % short)
    return key


def pct(x, nd=4):
    return None if x is None else round(float(x), nd)


def norm_d2pt_position(node: dict, consts: Consts, mappings: dict, unm: Unmapped) -> dict | None:
    builds = node.get("buildData") or []
    if not builds:
        return None
    build = sorted(builds, key=lambda b: -(b.get("num_matches") or 0))[0]
    bd = build["build_data"]
    im = (mappings or {}).get("itemsMapping") or {}

    def key_of(item_id):
        return item_by_id(consts, item_id, unm, im)

    def timed(entry):
        k = key_of(entry["raw_item_id"])
        if k is None:
            return None
        copy = int(str(entry.get("key", "")).split("::")[-1] or 1)
        out = {"item": k, "count": entry["count"], "pick_rate": pct(entry.get("pr")),
               "winrate": pct(entry.get("win_rate")), "avg_time_min": round(entry["avg_minute"], 1),
               "std_time_min": round(entry.get("std_minute") or 0, 1)}
        if copy > 1:
            out["copy"] = copy
        return out

    core = [e for e in map(timed, bd.get("anchor_items") or []) if e]
    core_ids = {(e["item"], e.get("copy", 1)) for e in core}
    matches = build["num_matches"]
    situational = []
    for entry in bd.get("items_mid_late") or []:
        e = timed(entry)
        if e and (e["item"], e.get("copy", 1)) not in core_ids and (e["pick_rate"] or 0) >= MIN_SIT_RATE:
            situational.append(e)

    starting = []
    for ids, st in (bd.get("starting_items_new") or [])[:5]:
        keys = [key_of(i) for i in ids]
        if None in keys:
            continue
        starting.append({"items": keys, "count": st["count"], "winrate": pct(st["win_rate"]),
                         "lane_advantage": st.get("lane_advantage")})

    final = []
    for e in bd.get("sixslot") or []:
        k = key_of(e["item_id"])
        if k and e["pick_rate"] >= MIN_FINAL_RATE:
            final.append({"item": k, "count": e["num_matches"], "pick_rate": pct(e["pick_rate"])})
    final.sort(key=lambda x: -x["pick_rate"])

    lategame = {}
    for bucket, ids in (bd.get("anchor_lategame_inventories") or {}).items():
        keys = [key_of(i) for i in ids]
        lategame[bucket] = [k for k in keys if k]

    def ability(aid):
        return consts.ability_name.get(int(aid)) or next(
            (a["name"] for a in bd.get("abilities") or [] if a["ability_id"] == aid), str(aid))

    skill = [{"order": [ability(a) for a in seq], "count": st["count"], "winrate": pct(st["win_rate"]),
              "pick_rate": pct(st["pr"])} for seq, st in (bd.get("abilities_new") or [])]

    talents = []
    for t in bd.get("talents") or []:
        side = lambda s: {"name": s["name"], "display": s["displayName"], "count": s["count"],  # noqa: E731
                          "pick_rate": pct(s["pick_rate"]), "winrate": pct(s["win_rate"])}
        talents.append({"level": t["lvl"], "left": side(t["left"]), "right": side(t["right"]),
                        "chosen": "left" if t["choice"] == "lt" else "right"})

    neutral = {}
    for tier_idx, table in (bd.get("neutral_stats") or {}).items():
        rows = []
        for item_id, st in table.items():
            k = key_of(item_id)
            if k:
                rows.append({"item": k, "count": st["count"], "winrate": pct(st["win_rate"]),
                             "pick_rate": pct(st["pick_rate"])})
        rows.sort(key=lambda r: -r["count"])
        neutral[str(int(tier_idx) + 1)] = rows[:TOP_NEUTRAL]

    enchant = {}
    for tier_idx, table in (bd.get("enhancement_stats") or {}).items():
        rows = []
        for item_id, st in table.items():
            k = key_of(item_id)
            if k:
                rows.append({"item": k, "count": st["count"], "winrate": pct(st["win_rate"]),
                             "pick_rate": pct(st["pick_rate"])})
        rows.sort(key=lambda r: -r["count"])
        enchant[str(int(tier_idx) + 1)] = rows[:TOP_NEUTRAL]

    facets = []
    names = {f["hero_variant"]: f["name"] for f in (node.get("facetData") or {}).get("facets") or []}
    for st in (node.get("facetData") or {}).get("stats") or []:
        n = int(st["num_matches"])
        facets.append({"id": st["hero_variant"], "name": names.get(st["hero_variant"]), "matches": n,
                       "winrate": pct(int(st["num_wins"]) / n) if n else None})
    real = [f for f in facets if f["id"] != 0]
    facet = max(real, key=lambda f: f["matches"]) if real else (facets[0] if facets else None)

    return {
        "matches": matches,
        "winrate": pct(build["num_wins"] / matches) if matches else None,
        "facet_id": build.get("facet_id"),
        "build_id": build.get("build_id"),
        "starting": starting,
        "core": core,
        "situational": situational,
        "final_inventory": final,
        "lategame_inventory": lategame,
        "skill_build": skill,
        "talents": talents,
        "neutral": neutral,
        "enchantments": enchant,
        "facet": facet,
        "facets": facets,
    }


def normalize_d2pt(nodes: dict[str, dict], consts: Consts, mappings: dict, unm: Unmapped, fetched_at: str) -> dict:
    positions, stats, scope, updated, patch = {}, {}, {}, None, None
    for pos, node in sorted(nodes.items()):
        patch = patch or node.get("patchversion")
        for hs in node.get("heroStats") or []:
            if hs.get("position") in {"pos %s" % p for p in POSITIONS}:
                stats[hs["position"][4:]] = {
                    "matches": hs["matches"], "winrate": pct(hs["wins"] / hs["matches"]) if hs["matches"] else None,
                    "role_pick_share": pct(hs.get("role_pick_share")), "d2pt_rating": hs.get("d2pt_rating")}
        entry = norm_d2pt_position(node, consts, mappings, unm)
        if entry is None:
            continue
        positions[pos] = entry
        b = sorted(node["buildData"], key=lambda b: -(b.get("num_matches") or 0))[0]
        scope = b.get("data_scope") or scope
        updated = b.get("updated_at") or updated
    return {
        "fetched_at": fetched_at,
        "mmr": "7000+",
        "kind": "pubs",
        "patch": patch,
        "window_days": scope.get("configured_window_days"),
        "patch_versions": scope.get("patch_versions"),
        "data_updated_at": updated,
        "position_stats_8d": stats,
        "positions": positions,
    }


ROW_RE = re.compile(r'<tr[^>]*data-link-to="/items/[^"]*"[^>]*>(.*?)</tr>', re.S)
CELL_RE = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)


def parse_dotabuff_items(html: str) -> list[dict]:
    rows = []
    for m in ROW_RE.finditer(html):
        cells = CELL_RE.findall(m.group(1))
        name, count, winrate = None, None, None
        for attrs, _ in cells:
            val = re.search(r'data-value="([^"]*)"', attrs)
            if not val:
                continue
            if "cell-xlarge" in attrs:
                name = unescape(val.group(1))
            elif "sorted" in attrs:
                count = int(float(val.group(1)))
            elif name is not None and count is not None and winrate is None:
                winrate = float(val.group(1)) / 100
        if name and count is not None and winrate is not None:
            rows.append({"name": name, "count": count, "winrate": round(winrate, 4)})
    return rows


def parse_dotabuff_priorities(html: str) -> list[dict]:
    out = []
    for block in html.split('<div class="ability-priority">')[1:]:
        block = block.split('<div class="ability-priority">')[0]
        names = [unescape(x) for x in re.findall(r'alt="([^"]+)"', block)]
        keys = re.findall(r'<div class="hotkey">\s*([^<\s]+)\s*</div>', block)
        br = re.search(r"([\d.]+)%</span>\s*Build Rate", block)
        wr = re.search(r"([\d.]+)%</span>\s*Win Rate", block)
        if names and br and wr:
            out.append({"order": names, "hotkeys": keys, "build_rate": round(float(br.group(1)) / 100, 4),
                        "winrate": round(float(wr.group(1)) / 100, 4)})
    return out


def parse_dotabuff_talents(html: str) -> list[dict]:
    out = []
    for row in re.findall(r'<tr class="talent-data-row">(.*?)</tr>', html, re.S):
        level = re.search(r'talent-level[^>]*>\s*<div>\s*(\d+)', row)
        cells = []
        for cell in row.split('<td class="talent-cell">')[1:]:
            name = re.search(r'talent-name-inner">\s*(.*?)\s*</span>', cell, re.S)
            pick = re.search(r"([\d.]+)% Pick Rate", cell)
            win = re.search(r"Win Rate:\s*([\d.]+)%", cell)
            if name and pick:
                cells.append({"name": unescape(name.group(1)), "pick_rate": round(float(pick.group(1)) / 100, 4),
                              "winrate": round(float(win.group(1)) / 100, 4) if win else None})
        if level and len(cells) == 2:
            out.append({"level": int(level.group(1)), "left": cells[0], "right": cells[1]})
    return out


def normalize_dotabuff(pages: dict[str, str], consts: Consts, unm: Unmapped, fetched_at: str) -> dict:
    windows = {}
    for page, label in (("items_week", "week"), ("items_patch", "patch_7.41")):
        if page not in pages:
            continue
        rows = []
        for r in parse_dotabuff_items(pages[page]):
            if r["name"].startswith("Recipe:"):
                continue
            dagon = re.fullmatch(r"Dagon \(level (\d)\)", r["name"])
            k = ("dagon_%s" % dagon.group(1)) if dagon else consts.dname_key.get(norm_name(r["name"]))
            if k is None or k not in consts.items:
                unm.add("dotabuff:%s" % r["name"])
                continue
            rows.append({"item": k, "count": r["count"], "winrate": r["winrate"]})
        windows[label] = rows
    html = pages.get("builds", "")
    return {
        "fetched_at": fetched_at,
        "mmr": "all",
        "kind": "ranked_all_brackets",
        "windows": windows,
        "skill_priorities": parse_dotabuff_priorities(html),
        "talents": parse_dotabuff_talents(html),
        "positions": {},
    }


def hero_file(key: str) -> Path:
    return KB_DIR / ("%s.json" % key)


def write_kb(key: str, hero_id: int, source: str, data: dict, patch: str | None) -> None:
    path = hero_file(key)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["hero"] = key
    doc["hero_id"] = hero_id
    doc["patch"] = patch or doc.get("patch") or DEFAULT_PATCH
    doc.setdefault("sources", {})[source] = data
    KB_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def d2pt_path(key: str, pos: str) -> Path:
    return CACHE / "d2pt" / ("%s__pos%s.json.gz" % (key, pos))


def load_d2pt_nodes(key: str) -> dict[str, dict]:
    nodes = {}
    for pos in POSITIONS:
        p = d2pt_path(key, pos)
        if p.exists():
            nodes[pos] = read_gz(p)["data"]["node"]
    return nodes


def load_mappings() -> dict:
    p = CACHE / "d2pt" / "_mappings.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def normalize_hero(key: str, consts: Consts, unm: Unmapped, sources: set[str]) -> list[str]:
    done = []
    hid = next(i for i, k in consts.hero_key.items() if k == key)
    if "d2pt" in sources:
        nodes = load_d2pt_nodes(key)
        if nodes:
            any_path = next(d2pt_path(key, p) for p in nodes)
            fetched = datetime.fromtimestamp(any_path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            patch = next(iter(nodes.values())).get("patchversion")
            write_kb(key, hid, "d2pt", normalize_d2pt(nodes, consts, load_mappings(), unm, fetched), patch)
            done.append("d2pt")
    if "dotabuff" in sources:
        pages, stamps = {}, []
        for page in DOTABUFF_PAGES:
            p = CACHE / "dotabuff" / ("%s__%s.json.gz" % (key, page))
            if p.exists():
                rec = read_gz(p)
                pages[page] = rec["html"]
                stamps.append(rec["fetched_at"])
        if pages:
            write_kb(key, hid, "dotabuff", normalize_dotabuff(pages, consts, unm, min(stamps)), None)
            done.append("dotabuff")
    return done


def push(local_bytes: bytes, remote_path: str) -> None:
    subprocess.run(["ssh", SSH_HOST, "cat > %s" % remote_path], input=local_bytes, check=True, timeout=60)


def run_remote(jobs: list[dict], delay: float, on_result) -> int:
    stamp = "%d_%d" % (time.time(), os.getpid())
    subprocess.run(["ssh", SSH_HOST, "mkdir -p %s" % REMOTE_WSL], check=True, timeout=30)
    push(HELPER.read_bytes(), "%s/builds_browser.py" % REMOTE_WSL)
    push(RUN_CMD.encode(), "%s/run_browser.cmd" % REMOTE_WSL)
    jobs_name = "jobs_%s.jsonl" % stamp
    push(("\n".join(json.dumps(j) for j in jobs) + "\n").encode(), "%s/%s" % (REMOTE_WSL, jobs_name))
    remote = ("cd %s && PYTHONIOENCODING=utf-8 %s /c '%s\\run_browser.cmd builds_browser.py %s\\%s %s\\profile_%s %s'"
              % (REMOTE_WSL, CMD_EXE, REMOTE_WIN, REMOTE_WIN, jobs_name, REMOTE_WIN, stamp, delay))
    proc = subprocess.Popen(["ssh", SSH_HOST, remote], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8")
    watchdog = threading.Timer(len(jobs) * 150 + 300, proc.kill)
    watchdog.start()
    threading.Thread(target=lambda: [log("remote: " + line.rstrip()) for line in proc.stderr], daemon=True).start()
    got = 0
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                on_result(json.loads(line))
                got += 1
            except json.JSONDecodeError:
                log("bad line from remote: %r" % line[:80])
        proc.wait()
    finally:
        watchdog.cancel()
        subprocess.run(["ssh", SSH_HOST, "rm -f %s/%s" % (REMOTE_WSL, jobs_name)], timeout=30)
    return got


def run_batches(jobs: list[dict], delay: float, handler, retry: bool = True) -> list[dict]:
    failed = []
    for i in range(0, len(jobs), BATCH):
        chunk = jobs[i:i + BATCH]
        seen = set()

        ids = {j["id"] for j in chunk}

        def on_result(res, seen=seen, ids=ids):
            if res["id"] not in ids:
                log("ignoring foreign result %s" % res["id"])
                return
            seen.add(res["id"])
            if not handler(res):
                failed.append({"id": res["id"], "url": res["url"], "error": res.get("error") or "invalid_data"})

        try:
            run_remote(chunk, delay, on_result)
        except Exception as e:  # noqa: BLE001
            log("batch failed: %r" % (e,))
        for j in chunk:
            if j["id"] not in seen:
                failed.append({"id": j["id"], "url": j["url"], "error": "no_result"})
        log("batch %d-%d done, failed so far %d" % (i + 1, i + len(chunk), len(failed)))
    if failed and retry:
        log("retrying %d failed jobs after a pause" % len(failed))
        time.sleep(60)
        by_id = {j["id"]: j for j in jobs}
        failed = run_batches([by_id[f["id"]] for f in failed], delay * 2, handler, retry=False)
    return failed


def fetch_d2pt(keys: list[str], consts: Consts, force: bool) -> list[dict]:
    fetched_now: set[tuple[str, str]] = set()

    def make_handler(expected):
        def handler(res):
            if not res["ok"]:
                return False
            data = res["data"]
            node = data["node"]
            key, kind = expected[res["id"]]
            if node.get("heroId") != next(i for i, k in consts.hero_key.items() if k == key):
                return False
            pos = str(node.get("position", ""))[4:]
            if pos not in POSITIONS:
                return False
            if data.get("mappings") and data["mappings"].get("itemsMapping"):
                (CACHE / "d2pt").mkdir(parents=True, exist_ok=True)
                (CACHE / "d2pt" / "_mappings.json").write_text(json.dumps(data["mappings"], ensure_ascii=False))
            write_gz(d2pt_path(key, pos), {"id": res["id"], "url": res["url"], "fetched_at": now_iso(), "data": {"node": node}})
            fetched_now.add((key, pos))
            return True
        return handler

    def url(key, pos=None):
        base = "https://dota2protracker.com/hero/%s?section=builds" % d2pt_page_name(consts, key, mappings)
        return base + ("&role=pos+%s" % pos if pos else "")

    failed = []
    mappings = load_mappings()
    phase1, expected = [], {}
    for key in keys:
        have = [p for p in POSITIONS if fresh(d2pt_path(key, p))]
        if force or not have:
            jid = "%s__default" % key
            phase1.append({"id": jid, "url": url(key), "kind": "d2pt"})
            expected[jid] = (key, "default")
    if phase1:
        log("d2pt phase 1: %d default pages" % len(phase1))
        failed += run_batches(phase1, DELAY["d2pt"], make_handler(expected))

    phase2, expected2 = [], {}
    for key in keys:
        nodes = load_d2pt_nodes(key)
        if not nodes:
            continue
        stats = next(iter(nodes.values())).get("heroStats") or []
        for hs in stats:
            pos = str(hs.get("position", ""))[4:]
            if pos in POSITIONS and hs.get("matches", 0) >= MIN_POS_MATCHES:
                if (key, pos) in fetched_now or (not force and fresh(d2pt_path(key, pos))):
                    continue
                jid = "%s__pos%s" % (key, pos)
                phase2.append({"id": jid, "url": url(key, pos), "kind": "d2pt"})
                expected2[jid] = (key, pos)
    if phase2:
        log("d2pt phase 2: %d position pages" % len(phase2))
        failed += run_batches(phase2, DELAY["d2pt"], make_handler(expected2))
    return failed


def fetch_dotabuff(keys: list[str], consts: Consts, force: bool) -> list[dict]:
    jobs, expected = [], {}
    for key in keys:
        slug = dotabuff_slug(consts, key)
        for page, tmpl in DOTABUFF_PAGES.items():
            path = CACHE / "dotabuff" / ("%s__%s.json.gz" % (key, page))
            if force or not fresh(path):
                jid = "%s__%s" % (key, page)
                jobs.append({"id": jid, "url": tmpl.format(slug=slug), "kind": "html"})
                expected[jid] = (key, page)

    def handler(res):
        if not res["ok"] or "dotabuff" not in res["title"].lower():
            return False
        key, page = expected[res["id"]]
        html = res["data"]
        marker = "<table" if page.startswith("items") else "ability-priority"
        if marker not in html:
            return False
        write_gz(CACHE / "dotabuff" / ("%s__%s.json.gz" % (key, page)),
                 {"id": res["id"], "url": res["url"], "fetched_at": now_iso(), "html": html})
        return True

    if not jobs:
        return []
    log("dotabuff: %d pages" % len(jobs))
    return run_batches(jobs, DELAY["dotabuff"], handler)


def coverage(keys: list[str]) -> dict:
    cov = {}
    for key in keys:
        p = hero_file(key)
        if not p.exists():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        for src, data in doc.get("sources", {}).items():
            c = cov.setdefault(src, {"heroes": 0, "positions": 0})
            has = [p_ for p_, d in data.get("positions", {}).items() if d.get("core")]
            if has or data.get("windows"):
                c["heroes"] += 1
            c["positions"] += len(has)
    return cov


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["d2pt", "dotabuff", "all"], default="all")
    ap.add_argument("--hero", help="short hero key, e.g. nevermore")
    ap.add_argument("--force", action="store_true", help="ignore cache freshness")
    ap.add_argument("--normalize-only", action="store_true", help="no network, rebuild data/kb/builds from cache")
    args = ap.parse_args()

    consts = Consts()
    keys = sorted(consts.hero_name)
    if args.hero:
        if args.hero not in consts.hero_name:
            print("unknown hero key: %s" % args.hero, file=sys.stderr)
            return 2
        keys = [args.hero]
    sources = {"d2pt", "dotabuff"} if args.source == "all" else {args.source}

    failed = []
    if not args.normalize_only:
        if "d2pt" in sources:
            failed += [dict(f, source="d2pt") for f in fetch_d2pt(keys, consts, args.force)]
        if "dotabuff" in sources:
            failed += [dict(f, source="dotabuff") for f in fetch_dotabuff(keys, consts, args.force)]

    unm = Unmapped()
    for key in keys:
        normalize_hero(key, consts, unm, sources)

    report = {"at": now_iso(), "failed": failed, "unmapped": unm.items, "coverage": coverage(keys)}
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"failed": len(failed), "unmapped": len(unm.items), "coverage": report["coverage"]}))
    for f in failed:
        print("FAILED %s %s %s" % (f["source"], f["id"], f["error"]), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
