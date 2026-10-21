#!/usr/bin/env python3
"""Browse every coin info_url served by the dashboard, capture name/desc
from the destination page itself. Page = new truth. Resume-safe via
link-audit.json. Log: per-ticker lines + end summary lists."""
import json, sys, time, urllib.request
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

DASH = "http://20.20.20.21:8124/api/data"
OUT = "link-audit.json"

delay = 3.0
if "--delay" in sys.argv:
    delay = float(sys.argv[sys.argv.index("--delay")+1])

d = json.load(urllib.request.urlopen(DASH, timeout=30))
uniq = {}
for sec in ("futures", "spot"):
    for r in d[sec]["meta"]:
        uniq.setdefault(r["base"], r)
targets = {b: r for b, r in uniq.items() if r.get("info_url") and r.get("category") != "TradFi"}

audit = {}
try:
    audit = json.load(open(OUT))
except Exception:
    pass
todo = [(b, r) for b, r in sorted(targets.items()) if b not in audit]
print("audit targets: %d (%d already done, resuming)" % (len(todo), len(audit)), flush=True)

BLOCK_HINTS = ("not available", "access denied", "restricted", "region", "404", "not found", "page not")
opts = webdriver.FirefoxOptions()
opts.page_load_strategy = "eager"
opts.add_argument("-headless")
driver = webdriver.Firefox(options=opts)
driver.set_page_load_timeout(30)

def grab(sel, attr=None):
    try:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if not els:
            return None
        return (els[0].get_attribute(attr) or els[0].text or "").strip()
    except Exception:
        return None

try:
    for i, (b, r) in enumerate(todo, 1):
        rec = {"url": r["info_url"], "expected": r.get("name") or "?"}
        try:
            try:
                driver.get(r["info_url"])
            except WebDriverException:
                pass
            time.sleep(delay)
            rec["page_title"] = (driver.title or "").strip()[:200]
            rec["og_title"] = grab('meta[property="og:title"]', "content")
            rec["desc"] = (grab('meta[name="description"]', "content") or grab('meta[property="og:description"]', "content"))
            rec["h1"] = grab("h1")
            blob = " ".join(filter(None, [rec["page_title"], rec["og_title"]])).lower()
            if any(h in blob for h in BLOCK_HINTS):
                rec["status"] = "suspect-block-or-dead"
            elif (rec["page_title"] or rec["og_title"]):
                rec["status"] = "ok"
            else:
                rec["status"] = "thin-no-title"
        except Exception as e:
            rec["status"] = "error"
            rec["error"] = str(e)[:120]
        audit[b] = rec
        name_bit = rec.get("og_title") or rec.get("page_title") or "(NO TITLE)"
        desc_bit = (rec.get("desc") or "")[:110]
        print("[%d/%d] %-12s %-22s | %s | %s" % (i, len(todo), b, rec["status"], name_bit[:60], desc_bit), flush=True)
        if i % 10 == 0 or i == len(todo):
            json.dump(audit, open(OUT, "w"), indent=1)
finally:
    json.dump(audit, open(OUT, "w"), indent=1)
    driver.quit()
    oks = sorted(b for b, r in audit.items() if r["status"] == "ok")
    thin = sorted(b for b, r in audit.items() if r["status"] == "thin-no-title")
    blocked = sorted(b for b, r in audit.items() if r["status"] == "suspect-block-or-dead")
    errs = sorted(b for b, r in audit.items() if r["status"] == "error")
    print("\n===== SUMMARY =====", flush=True)
    print("fetched with name+desc: %d" % len(oks), flush=True)
    print("--- THIN / NO DESCRIPTION (%d) ---" % len(thin), flush=True)
    for b in thin: print("  %s -> %s" % (b, audit[b]["url"]), flush=True)
    print("--- SUSPECT BLOCK/DEAD (%d) ---" % len(blocked), flush=True)
    for b in blocked: print("  %s -> %s" % (b, audit[b]["url"]), flush=True)
    print("--- ERRORS (%d) ---" % len(errs), flush=True)
    for b in errs: print("  %s: %s" % (b, audit[b].get("error")), flush=True)
    print("saved %d records -> %s" % (len(audit), OUT), flush=True)
