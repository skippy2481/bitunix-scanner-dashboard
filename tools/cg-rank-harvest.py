#!/usr/bin/env python3
# Harvest CoinGecko market-cap ranks via /coins/markets (250/page).
# Matches roster bases via cg-ids.json (primary) or symbol (fallback).
import json, time, urllib.request, urllib.parse

API = "https://api.coingecko.com/api/v3/coins/markets"

ids  = json.load(open("cg-ids.json"))
roster = set()
payload = json.load(open("/tmp/payload.json"))
for sec in ("futures","spot"):
    for r in payload[sec]["meta"]:
        if r.get("category") == "Crypto":
            b = r.get("base","")
            roster.add(b[4:] if b.startswith("1000") else b)

by_id = {}
pages = []
for page in range(1, 9):
    url = API + "?" + urllib.parse.urlencode(
        {"vs_currency":"usd","order":"market_cap_desc","per_page":250,"page":page})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                rows = json.load(resp)
            pages.extend(rows); print(f"page {page}: {len(rows)} rows")
            break
        except Exception as e:
            print(f"page {page} attempt {attempt}: {e}"); time.sleep(20)
    time.sleep(3)

id_to_rank = {r["id"]: r["market_cap_rank"] for r in pages if r.get("market_cap_rank")}
sym_to_rank = {}
for r in pages:
    if r.get("market_cap_rank") and r.get("symbol"):
        sym_to_rank.setdefault(r["symbol"].upper(), r["market_cap_rank"])

ranks = {}
for b in roster:
    ent = ids.get(b)
    if ent and ent["id"] in id_to_rank:
        ranks[b] = id_to_rank[ent["id"]]
    elif b in sym_to_rank:
        ranks[b] = sym_to_rank[b]

json.dump(ranks, open("cg-ranks.json","w"), indent=1, sort_keys=True)
print(f"\nroster bases: {len(roster)}, ranked: {len(ranks)} "
      f"({100*len(ranks)/max(len(roster),1):.1f}%)")
