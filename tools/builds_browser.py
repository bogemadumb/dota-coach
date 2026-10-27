"""Runs on the home PC (Windows, headed Chromium via playwright): loads pages that Cloudflare blocks for plain HTTP.

Usage: python builds_browser.py JOBS.jsonl PROFILE_DIR DELAY_SEC
Job line: {"id": "...", "url": "...", "kind": "d2pt" | "html"}
Result line on stdout: {"id", "url", "ok", "status", "title", "error", "data"}
d2pt: data = SvelteKit hero node (node 0 mappings only on the first d2pt result); html: data = page HTML.
"""

import json
import os
import random
import shutil
import sys
import time

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", r"C:\playwright-browsers")
from playwright.sync_api import sync_playwright  # noqa: E402

CHALLENGE = ("Один момент", "Just a moment", "Attention Required")
BLOCK_TYPES = {"image", "media", "font"}
BLOCK_HOSTS = ("googletagmanager", "google-analytics", "clarity.ms", "doubleclick", "googlesyndication",
               "adnxs", "pubwise", "facebook", "amazon-adsystem", "criteo", "rubiconproject", "ads.")

JS_SVELTE = """() => {
  const sc = [...document.scripts].find(s => s.textContent.includes('kit.start'));
  if (!sc) return null;
  const t = sc.textContent;
  const i = t.indexOf('data: [');
  const j = t.indexOf('form:', i);
  if (i < 0 || j < 0) return null;
  const s = t.slice(i + 6, j).trim().replace(/,\\s*$/, '');
  return JSON.stringify((0, eval)('(' + s + ')'));
}"""


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


def emit(obj):
    try:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except OSError:
        os._exit(1)


def open_context(p, profile):
    shutil.rmtree(profile, ignore_errors=True)
    ctx = p.chromium.launch_persistent_context(
        profile, headless=False, viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"], ignore_default_args=["--enable-automation"])

    def route(r):
        req = r.request
        if req.resource_type in BLOCK_TYPES or any(h in req.url for h in BLOCK_HOSTS):
            r.abort()
        else:
            r.continue_()

    ctx.route("**/*", route)
    return ctx


def load(page, job, timeout=30):
    status = None
    try:
        resp = page.goto(job["url"], wait_until="domcontentloaded", timeout=60000)
        status = resp.status if resp else None
    except Exception as e:
        return {"ok": False, "status": None, "title": "", "error": "goto: %s" % type(e).__name__, "data": None}
    end = time.time() + timeout
    title = ""
    while time.time() < end:
        try:
            title = page.title()
        except Exception:
            title = ""
        if title and not any(c in title for c in CHALLENGE):
            if job["kind"] == "html":
                time.sleep(1.0)
                return {"ok": True, "status": status, "title": title, "error": None, "data": page.content()}
            try:
                raw = page.evaluate(JS_SVELTE)
            except Exception as e:
                raw = None
                log("evaluate failed on %s: %s" % (job["id"], str(e)[:200]))
            if raw:
                return {"ok": True, "status": status, "title": title, "error": None, "data": json.loads(raw)}
        time.sleep(1.5)
    return {"ok": False, "status": status, "title": title, "error": "challenge_or_no_data", "data": None}


def main():
    jobs_path, profile, delay = sys.argv[1], sys.argv[2], float(sys.argv[3])
    jobs = [json.loads(line) for line in open(jobs_path, encoding="utf-8") if line.strip()]
    first_d2pt = True
    with sync_playwright() as p:
        ctx = open_context(p, profile)
        page = ctx.new_page()
        rotations = 0
        for n, job in enumerate(jobs):
            if n:
                time.sleep(delay + random.random())
            res = load(page, job)
            if not res["ok"] and res["error"] == "challenge_or_no_data":
                log("challenge on %s, rotating profile" % job["id"])
                ctx.close()
                time.sleep(20)
                rotations += 1
                ctx = open_context(p, profile)
                page = ctx.new_page()
                res = load(page, job)
            if res["ok"] and job["kind"] == "d2pt":
                data = res["data"]
                node0 = data[0]["data"] if data else {}
                node1 = data[1]["data"] if len(data) > 1 else {}
                res["data"] = {"node": node1}
                if first_d2pt:
                    res["data"]["mappings"] = {"itemsMapping": node0.get("itemsMapping"),
                                               "heroesMapping": node0.get("heroesMapping"),
                                               "config": node0.get("config")}
                    first_d2pt = False
            emit({"id": job["id"], "url": job["url"], **res})
            log("%d/%d %s ok=%s %s" % (n + 1, len(jobs), job["id"], res["ok"], res["error"] or ""))
        ctx.close()
    shutil.rmtree(profile, ignore_errors=True)
    log("done, rotations=%d" % rotations)


if __name__ == "__main__":
    main()
