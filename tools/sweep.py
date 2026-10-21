#!/usr/bin/env python3
"""Bitunix TradFi sweep: harvest instrument names + reachability in one pass.
Visits https://www.bitunix.com/contract-trade/<SYM>USDT for each ticker.
Line 0 of .chart-header-container = symbol (redirect to BTCUSDT => geoblocked).
Line 1 = official instrument name.
Output: sweep-results.json with egress vantage recorded.
Usage: python3 sweep.py [--show] [tickersfile]"""
import json, re, sys, time, urllib.request
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import WebDriverException

URL = "https://www.bitunix.com/contract-trade/{}USDT"
VANTAGE = "https://ipinfo.io/json"

def norm_base(sym):
    """Normalize a rendered symbol: drop parentheticals (ASCII/CJK), trailing USDT, punctuation."""
    s = re.sub(r"[（(].*?[)）]", "", str(sym)).strip().upper()
    if s.endswith("USDT"):
        s = s[:-4]
    return re.sub(r"[^A-Z0-9]", "", s)


def vantage():
    try:
        with urllib.request.urlopen(VANTAGE, timeout=8) as r:
            j = json.loads(r.read())
        return {"ip": j.get("ip"), "country": j.get("country"), "city": j.get("city")}
    except Exception as e:
        return {"error": str(e)[:100]}

def load_tickers(path):
    txt = Path(path).read_text()
    return [t for t in txt.split() if t and not t.startswith("#")]

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show = "--show" in sys.argv
    tickers_file = args[0] if args else "tradfi-tickers.txt"
    syms = load_tickers(tickers_file)
    print("sweep: %d tickers from %s" % (len(syms), tickers_file))

    van = vantage()
    print("egress: %s (%s, %s)" % (van.get("ip"), van.get("country"), van.get("city")))

    opts = webdriver.FirefoxOptions()
    opts.page_load_strategy = "eager"   # don't wait for full load event
    if not show:
        opts.add_argument("-headless")
    driver = webdriver.Firefox(options=opts)
    driver.set_page_load_timeout(25)
    results = {"vantage": van, "generated": int(time.time()), "entries": {}}
    try:
        for i, sym in enumerate(syms, 1):
            key, rec = sym + "USDT", {"name": None, "status": "nodata"}
            try:
                try:
                    driver.get(URL.format(sym))
                except WebDriverException:
                    pass  # eager strategy: DOM still renders, waiter handles the rest
                WebDriverWait(driver, 20).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, ".chart-header-container"))
                lines = [l.strip() for l in driver.find_element(
                    By.CSS_SELECTOR, ".chart-header-container").get_attribute("innerText").split("\n") if l.strip()]
                if not lines:
                    rec["status"] = "nodata"
                else:
                    landed = lines[0]
                    rec["landed_on"] = landed
                    nb, want = norm_base(landed), norm_base(key)
                    if nb == want:
                        rec.update(status="ok",
                                   name=(lines[1] if len(lines) >= 2 else None),
                                   rendered_symbol=landed)
                    elif nb == "BTC":
                        rec["status"] = "geoblocked"
                    else:
                        rec["status"] = "renamed"
            except Exception as e:
                rec.update(status="error", err=str(e)[:200])
            results["entries"][key] = rec
            print("[%d/%d] %-16s %-11s %s" % (i, len(syms), key, rec["status"], rec["name"] or ""), flush=True)
            time.sleep(2)
    finally:
        driver.quit()
    out = Path("sweep-results-%s.json" % (van.get("country") or "xx"))
    out.write_text(json.dumps(results, indent=2))
    ent = results["entries"]
    print("done: %d ok, %d geoblocked, %d other -> %s" %
          (sum(r["status"]=="ok" for r in ent.values()),
           sum(r["status"]=="geoblocked" for r in ent.values()),
           sum(r["status"] not in ("ok","geoblocked") for r in ent.values()), out))

if __name__ == "__main__":
    main()
