#!/usr/bin/env python3
"""
Audit diff tool for bitunix-scanner-dashboard.
- Compares live /api/data against a baseline TSV (defaults to Oct 21 baseline).
- Reports: new listings, delisted, missing info links, missing names, category counts.
Usage: python3 audit-diff.py [--baseline PATH]
"""
import argparse, json, sys, os
from urllib.request import urlopen
from urllib.error import URLError

BASE_API = os.environ.get("BITUNIX_BASE_URL", "http://127.0.0.1:8124")

def load_baseline(path=None):
    if not path:
        path = "/opt/bitunix-scanner-dashboard/runtime/audit-links-20261104.tsv"
    if not os.path.exists(path):
        print("[WARN] baseline not found: %s" % path, file=sys.stderr)
        return set()
    s = set()
    with open(path) as f:
        hdr = f.readline()
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if parts and parts[0]:
                s.add(parts[0].upper())
    return s

def fetch_api():
    try:
        raw = urlopen(BASE_API+"/api/data", timeout=20).read().decode("utf-8")
        return json.loads(raw)
    except Exception as e:
        print("[ERR] api fetch failed: %r" % e, file=sys.stderr)
        sys.exit(1)

def audit_plane(meta, old_bases, plane):
    if not meta:
        return
    rows = meta if isinstance(meta,list) else list(meta.values())[0] if isinstance(meta,dict) else []
    bases = {str(m.get("base","")).upper() for m in rows}
    new = sorted(bases - old_bases)
    gone = sorted(old_bases - bases)
    nolink = [m for m in rows if not (m.get("info_url") or "").strip()]
    noname = [m for m in rows if not (m.get("name") or "").strip()]
    cats = {}
    for m in rows:
        cats[m.get("category") or "NONE"] = cats.get(m.get("category") or "NONE",0)+1
    print("[%s] NEW since baseline (%d): %s" % (plane.upper(), len(new), new))
    print("[%s] GONE since baseline (%d): %s" % (plane.upper(), len(gone), gone))
    print("[%s] rows=%d  no info_url=%d  no name=%d" % (plane, len(rows), len(nolink), len(noname)))
    print("[%s] categories: %s" % (plane, cats))
    if nolink:
        print("  sample missing links:", [(m['key'],m.get('category')) for m in nolink[:15]])
    if noname:
        print("  missing names:", [m['key'] for m in noname[:15]])
    print()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=None)
    args = ap.parse_args()
    old = load_baseline(args.baseline)
    d = fetch_api()
    for plane in ("futures",):  # spot has no baseline TSV
        st = d.get(plane, {})
        meta = st.get("meta") or st.get("meta_rows") or st.get("rows") or None
        audit_plane(meta, old, plane)

if __name__ == "__main__":
    main()
