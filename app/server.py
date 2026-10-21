#!/usr/bin/env python3
"""Bitunix multi-market dashboard v4. Futures (USDT/USDC/USD) + spot. Pure stdlib.
v4: parallel spot sweep with 24h high/low/vol/chg from kline/history(limit=25);
    last price from last_price (live). Extended TradFi name registry.
v3: names layer; kline sweeper waits for roster.
v2: classification; spot retry/backoff; tolerant code checks."""
import json, threading, time, os
import os
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BIND = ("0.0.0.0", 8124)
FUTURES_REFRESH_SECS = 15
KLINE_SWEEP_SECS = 300
ROSTER_REFRESH_SECS = 1800
KLINE_CONCURRENCY = 8
CLASSIFY_MAX_AGE_SECS = 7 * 86400

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
ICON_CACHE = os.path.join(BASE_DIR, "icons.json")
CG_NAMES_CACHE = os.path.join(BASE_DIR, "cg-names.json")
HARVESTED_NAMES_FILE = os.path.join(BASE_DIR, "tradfi-names.json")

def _load_harvested_names():
    out = {}
    try:
        d = json.load(open(HARVESTED_NAMES_FILE))
        for sym, rec in (d.get("entries") or {}).items():
            if isinstance(rec, dict) and rec.get("status") == "named" and rec.get("name"):
                b = sym[:-4] if sym.upper().endswith("USDT") else sym
                out[b.upper()] = rec["name"]
    except Exception:
        pass
    return out

HARVESTED_NAMES = _load_harvested_names()

def _load_forced_tradfi():
    out = set()
    try:
        d = json.load(open(HARVESTED_NAMES_FILE))
        excl = set(x.upper() for x in (d.get("exclude_crypto") or []))
        for sym in (d.get("entries") or {}).keys():
            b = sym[:-4] if sym.upper().endswith("USDT") else sym
            b = b.upper()
            if b and b not in excl:
                out.add(b)
    except Exception:
        pass
    return out

FORCED_TRADFI = _load_forced_tradfi()

INFO_LINKS_FILE = os.path.join(BASE_DIR, "info-links.json")

def _load_info_links():
    try:
        return {k.upper(): v for k, v in json.load(open(INFO_LINKS_FILE)).items()}
    except Exception:
        return {}

INFO_LINKS = _load_info_links()

CG_IDS_FILE = os.path.join(BASE_DIR, "cg-ids.json")

def _load_cg_ids():
    try:
        d = json.load(open(CG_IDS_FILE))
        return {k.upper(): v["url"] for k, v in d.items()
                if isinstance(v, dict) and v.get("url")}
    except Exception:
        return {}

INFO_CG = _load_cg_ids()

CG_RANKS_FILE = os.path.join(BASE_DIR, "cg-ranks.json")

def _load_cg_ranks():
    try:
        return {k.upper(): v for k, v in json.load(open(CG_RANKS_FILE)).items()}
    except Exception:
        return {}

CG_RANKS = _load_cg_ranks()

def cg_rank(base):
    b = (base or "").upper()
    cands = [b, b[4:] if b.startswith("1000") else "1000" + b]
    for c in cands:
        if c in CG_RANKS:
            return CG_RANKS[c]
    return None

def info_url(base):
    b = (base or "").upper()
    cands = [b, b[4:] if b.startswith("1000") else "1000" + b]
    for c in cands:
        if c in INFO_LINKS:
            return INFO_LINKS[c]
    for c in cands:
        if c in INFO_CG:
            return INFO_CG[c]
    if classify(b) == "TradFi":
        return "https://finance.yahoo.com/quote/" + b + "/"
    return None

FB = "https://fapi.bitunix.com/api/v1/futures/market"
SB = "https://openapi.bitunix.com/api/spot/v1"
CG = "https://api.coingecko.com/api/v3"

state_lock = threading.Lock()
state = {
    "futures": {"meta": [], "tickers": {}, "funding": {}, "refs": {}, "updated": None, "err": None},
    "spot":    {"meta": [], "tickers": {}, "refs": {}, "updated": None, "err": None},
}

cls_lock = threading.Lock()
CRYPTO_SET = set()
NAME_MAP = {}
CLS_READY = threading.Event()

CURATED_NAMES = {
    "WLFI": "World Liberty Financial",
    "EPIC": "EPIC Chain",
 "1000PEPE":"Pepe (meme)","1000SHIB":"Shiba Inu (meme)","AAVE":"Aave","ADA":"Cardano",
 "ALGO":"Algorand","ARB":"Arbitrum","ATOM":"Cosmos","AVAX":"Avalanche","BANANA":"Banana Gun","BCH":"Bitcoin Cash",
 "BNB":"BNB","BTC":"Bitcoin","CAKE":"PancakeSwap","DOGE":"Dogecoin","DOGS":"Dogs (TON)","DOT":"Polkadot",
 "ENA":"Ethena","ETC":"Ethereum Classic","ETH":"Ethereum","FIL":"Filecoin",
 "HBAR":"Hedera","HYPE":"Hyperliquid","ICP":"Internet Computer","INJ":"Injective",
 "JUP":"Jupiter","LDO":"Lido DAO","LINK":"Chainlink","LTC":"Litecoin",
 "NEAR":"NEAR Protocol","ONDO":"Ondo Finance","PENDLE":"Pendle",
 "PENGU":"Pudgy Penguins","POL":"Polygon Ecosystem Token","PUMP":"Pump.fun",
 "QNT":"Quant","RENDER":"Render Network","S":"Sonic (ex-Fantom)","SAND":"The Sandbox",
 "SOL":"Solana","STRK":"Starknet","SUI":"Sui","SYN":"Synapse","TAO":"Bittensor",
 "TRUMP":"Official Trump","TRX":"TRON","UNI":"Uniswap","WIF":"dogwifhat",
 "WLD":"Worldcoin","XLM":"Stellar","XRP":"XRP","ZEC":"Zcash",
 "OPENAI":"OpenAI (pre-IPO)","ANTHROPIC":"Anthropic (pre-IPO)",
 "AAPL":"Apple Inc.","ADBE":"Adobe Inc.","AKAM":"Akamai Technologies","ALAB":"Astera Labs",
 "AMD":"Advanced Micro Devices","AMAT":"Applied Materials","AMZN":"Amazon.com Inc.",
 "AVGO":"Broadcom Inc.","BRKB":"Berkshire Hathaway (Cl B)","COIN":"Coinbase Global",
 "CRCL":"Circle Internet Group","CRWD":"CrowdStrike","CSCO":"Cisco Systems",
 "DATAIP":"Data infrastructure listing ?","DIS":"Walt Disney Co.","DJT":"Trump Media & Tech",
 "GOOGL":"Alphabet Inc.","HOOD":"Robinhood Markets","INTC":"Intel Corp.",
 "IONQ":"IonQ Inc.","MARA":"MARA Holdings","META":"Meta Platforms",
 "MRK":"Merck & Co.","MRNA":"Moderna Inc.","MSFT":"Microsoft Corp.",
 "MSTR":"Strategy (ex-MicroStrategy)","NBIS":"Nebius Group","NFLX":"Netflix Inc.",
 "NOK":"Nokia Oyj","NVDA":"NVIDIA Corp.","PATH":"UiPath Inc.","PLTR":"Palantir Technologies",
 "QCOM":"Qualcomm Inc.","RKLB":"Rocket Lab","SMCI":"Super Micro Computer",
 "SNDK":"SanDisk Corp.","TSLA":"Tesla Inc.","TSM":"Taiwan Semiconductor (TSMC)",
 # v4 additions - the 72 formerly-unnamed TradFi tickers
 "AGPU":"Allied Green Technologies ?","BBX":"BBX Capital ?","BEAMX":"Beam (token?) ?","BNLIFE":"?",
 "BWET":"?","BX":"Blackstone Inc.","BZ":"?","CL":"Colgate-Palmolive","CRML":"Critical Metals Corp",
 "CSOPHLS2L":"CSOP 2x HK-listed Semi ETN ?","CSOPSX2L":"CSOP 2x Samsung leveraged ?",
 "CXMT":"ChangXin Memory (CXMT)","EBAY":"eBay Inc.","EDGEX":"EdgeX ?","EWJ":"iShares MSCI Japan ETF",
 "EWZ":"iShares MSCI Brazil ETF","GAMESTOP":"GameStop Corp.","GIGADEV":"?","GTLB":"GitLab Inc.",
 "HAJIMI":"?","HANMI":"Hanmi Semiconductor","HYUNDAI":"Hyundai Motor Co.","INTW":"?",
 "KODEX200":"KODEX 200 ETF (KR)","KSTR":"Korea strategic ETF ?","KUAISHOU":"Kuaishou Technology",
 "LGE":"LG Electronics","LUNA2":"Terra (LUNA 2.0) ?","LYTE":"?","MEITUAN":"Meituan",
 "MINIMAX":"MiniMax AI","MOONSHOT":"Moonshot AI (Kimi)","MUU":"?","MVLL":"Marvell-linked leveraged ?",
 "NATGAS":"Natural Gas (Henry Hub)","NAVER":"Naver Corp.","NIULAI":"?","NVDL":"T-Rex 2X NVIDIA ETF",
 "ONDS":"Ondas Holdings","OURA":"Oura ?","PAYP":"PayPal-linked listing ?","PENGSTOCK":"?",
 "PHAROS":"Pharos Energy ?","POPMART":"Pop Mart International","QNTX":"?","SAMSUNG":"Samsung Electronics",
 "SAMSUNGEM":"Samsung-linked ?","SHAZ":"?","SHEIN":"Shein","SHLD":"?","SKDD":"Semis/Korea leveraged ?",
 "SKHYNIX":"SK Hynix Co.","SKUU":"SK-linked leveraged ?","STXX":"SK-linked leveraged ?",
 "TBT":"ProShares Ultra 20+ Yr Treasury","TENCENT":"Tencent Holdings","TWST":"Twist Bioscience",
 "TXN":"Texas Instruments","TZA":"Direxion Small Cap 3x Bear","UNITREE":"Unitree Robotics",
 "URNM":"Sprott Uranium Miners ETF","USDEX":"?","UVXY":"ProShares Ultra VIX ETF",
 "VKTX":"Viking Therapeutics","XAG":"Silver (spot oz)","XBI":"SPDR S&P Biotech ETF",
 "XIAOMI":"Xiaomi Corp.","XLE":"Energy Select SPDR Fund","ZCSH":"?","ZHIPU":"Zhipu AI (GLM)",
 "ZHONGJI":"Zhongji Innolight ?",
 "QNTX":"Quantinuum",
 "PENGSTOCK":"Penguin Solutions",
}

def get_json(url, timeout=30, log=False):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bitunix-dashboard/4.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        if log:
            print("fetch fail %s : %r" % (url, e), flush=True)
        return None

def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def classify(base):
    b = (base or "").upper()
    if not b:
        return "Crypto"
    if b in FORCED_TRADFI:
        return "TradFi"
    if not CLS_READY.is_set():
        return "Crypto"
    with cls_lock:
        if b in CRYPTO_SET:
            return "Crypto"
        if b.startswith("1000") and b[4:] in CRYPTO_SET:
            return "Crypto"
    return "TradFi"

def lookup_name(base):
    b = (base or "").upper()
    if b in HARVESTED_NAMES:
        return HARVESTED_NAMES[b]
    if b in CURATED_NAMES:
        return CURATED_NAMES[b]
    if b.startswith("1000") and b[4:] in CURATED_NAMES:
        return CURATED_NAMES[b[4:]]
    with cls_lock:
        n = NAME_MAP.get(b) or (b.startswith("1000") and NAME_MAP.get(b[4:])) or None
    if n:
        return n
    return b + (" ?" if classify(b) == "TradFi" else "")

def load_icon_cache():
    try:
        if (time.time() - os.path.getmtime(ICON_CACHE)) < 7 * 86400:
            return json.load(open(ICON_CACHE))
    except Exception:
        pass
    return {}

def atomic_json_dump(obj, path):
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w"))
    os.replace(tmp, path)

ICON_EMOJI = {
 "BTC":"\u20bf","ETH":"\u039e","SOL":"\u25ce","XRP":"\u2715","ADA":"\u20b3","DOT":"\u25cf","DOGE":"\u00d0","BNB":"\U0001f7e1",
 "AVAX":"\u2744\ufe0f","LINK":"\U0001f517","UNI":"\U0001f984","LTC":"\u0141","ETC":"\u26a1","BCH":"\u0243","ATOM":"\u2316",
 "SUI":"\U0001f4a7","ARB":"\u25c8","INJ":"\U0001f530","TAO":"\U0001f9ec","JUP":"\U0001fa90","TRX":"\u25b2","STRK":"\u03a9",
 "1000PEPE":"\U0001f438","1000SHIB":"\U0001f415","WIF":"\U0001f415","WLD":"\U0001f30d","XLM":"\u2b50","ZEC":"\U0001f512",
}

def row_icon(base, icons):
    return icons.get(base) or ICON_EMOJI.get(base) or ("\U0001f4c8" if classify(base) == "TradFi" else "\U0001fa99")

def build_futures_meta(pairs, icons):
    meta = []
    for p in pairs:
        if p.get("symbolStatus") != "OPEN" or p.get("quote") not in ("USDT", "USDC", "USD"):
            continue
        base = p.get("base", "")
        meta.append({
            "key": p["symbol"], "symbol": p["symbol"], "base": base, "quote": p["quote"],
            "pair": base + "/" + p["quote"], "name": lookup_name(base), "info_url": info_url(base), "rank": cg_rank(base),
            "category": classify(base),
            "img": icons.get(base), "icon": row_icon(base, icons),
            "max_lev": p.get("maxLeverage"),
        })
    return meta

def build_spot_meta(rows, icons):
    meta = []
    for r in rows:
        if r.get("isOpen") != 1:
            continue
        base = (r.get("base") or "").upper()
        meta.append({
            "key": r["symbol"].upper(), "symbol": r["symbol"].upper(), "base": base,
            "quote": r.get("quote", ""), "pair": r["symbol"].upper(),
            "name": lookup_name(base), "info_url": info_url(base), "rank": cg_rank(base), "category": classify(base),
            "img": icons.get(base), "icon": row_icon(base, icons), "max_lev": None,
        })
    return meta

def classification_thread():
    global CRYPTO_SET, NAME_MAP
    while True:
        try:
            resp = get_json(f"{SB}/common/coin_pair/list", timeout=90, log=True)
            spot_bases, icons = set(), {}
            if resp and resp.get("code") in (0, "0"):
                for r in resp.get("data") or []:
                    b = (r.get("base") or "").upper()
                    if b:
                        spot_bases.add(b)
                    if b and r.get("baseIcon"):
                        icons[b] = r["baseIcon"]
            if not spot_bases:
                print("classification: spot roster unavailable, retry in 30s", flush=True)
                time.sleep(30)
                continue
            atomic_json_dump(icons, ICON_CACHE)
            names = None
            try:
                if (time.time() - os.path.getmtime(CG_NAMES_CACHE)) < CLASSIFY_MAX_AGE_SECS:
                    names = json.load(open(CG_NAMES_CACHE))
            except Exception:
                pass
            if names is None:
                cgr = get_json(f"{CG}/coins/list?include_platform=false", timeout=120, log=True)
                if cgr and isinstance(cgr, list):
                    names = {}
                    for c in cgr:
                        s = str(c.get("symbol", "")).upper()
                        nm = str(c.get("name", "")).strip()
                        if s and nm:
                            names.setdefault(s, nm)
                    atomic_json_dump(names, CG_NAMES_CACHE)
                else:
                    print("classification: coingecko unavailable, retry in 60s", flush=True)
                    time.sleep(60)
                    continue
            combined = spot_bases | set(names.keys())
            with cls_lock:
                CRYPTO_SET = combined
                NAME_MAP = names
                CLS_READY.set()
            print("classification ready: %d spot bases, %d cg names" % (len(spot_bases), len(names)), flush=True)
            time.sleep(CLASSIFY_MAX_AGE_SECS)
        except Exception as e:
            print("classification thread error: %r" % e, flush=True)
            time.sleep(60)

def futures_roster():
    resp = get_json(f"{FB}/trading_pairs", log=True)
    return (resp.get("data") or []) if resp and resp.get("code") in (0, "0") else []

def futures_plane_thread():
    while True:
        try:
            icons = load_icon_cache()
            meta = build_futures_meta(futures_roster(), icons)
            tresp = get_json(f"{FB}/tickers")
            fres = get_json(f"{FB}/funding_rate/batch")
            tickers, funding = {}, {}
            if tresp and tresp.get("code") in (0, "0"):
                for t in tresp.get("data") or []:
                    tickers[t["symbol"]] = t
            if fres and fres.get("code") in (0, "0"):
                for f in fres.get("data") or []:
                    funding[f["symbol"]] = f
            if not meta or not tickers:
                print("futures plane: incomplete fetch, retry in 15s", flush=True)
                time.sleep(15)
                continue
            with state_lock:
                st = state["futures"]
                st["meta"] = meta
                st["tickers"] = tickers
                st["funding"] = funding
                st["updated"] = int(time.time())
                st["err"] = None
        except Exception as e:
            with state_lock:
                state["futures"]["err"] = str(e)
        time.sleep(FUTURES_REFRESH_SECS)

def futures_roster_thread():
    while True:
        time.sleep(ROSTER_REFRESH_SECS)
        try:
            meta = build_futures_meta(futures_roster(), load_icon_cache())
            keep = {m["key"] for m in meta}
            with state_lock:
                st = state["futures"]
                st["meta"] = meta
                for k in list(st["tickers"]):
                    if k not in keep:
                        st["tickers"].pop(k, None)
                        st["refs"].pop(k, None)
            print("futures roster refresh: %d contracts" % len(meta), flush=True)
        except Exception as e:
            print("futures roster refresh failed: %r" % e, flush=True)

def kline_worker(sym, sem, results):
    try:
        resp = get_json(f"{FB}/kline?symbol=%s&interval=1h&limit=100" % sym)
        if resp and resp.get("code") in (0, "0"):
            parsed = []
            for c in resp.get("data") or []:
                cl = fnum(c.get("close"))
                if cl is not None:
                    parsed.append((int(c.get("time", 0)), cl))
            parsed.sort()
            if len(parsed) >= 2:
                refs = {"1": parsed[-1][1]}
                if len(parsed) >= 6: refs["6"] = parsed[-6][1]
                if len(parsed) >= 24: refs["24"] = parsed[-24][1]
                results[sym] = refs
    except Exception:
        pass
    finally:
        sem.release()

def kline_sweeper_thread():
    sem = threading.Semaphore(KLINE_CONCURRENCY)
    while True:
        with state_lock:
            syms = [m["key"] for m in state["futures"]["meta"]]
        if not syms:
            time.sleep(15)
            continue
        results = {}
        for sym in syms:
            sem.acquire()
            threading.Thread(target=kline_worker, args=(sym, sem, results), daemon=True).start()
            time.sleep(0.1)
        while sem._value < KLINE_CONCURRENCY:
            time.sleep(0.5)
        with state_lock:
            state["futures"]["refs"].update(results)
        print("kline sweep: %d ok of %d" % (len(results), len(syms)), flush=True)
        time.sleep(KLINE_SWEEP_SECS)

# ---------- v4: parallel spot sweep with 24h stats ----------
def spot_stats_worker(sym, sem):
    try:
        kp = get_json(f"{SB}/market/kline/history?symbol=%s&interval=60&limit=25" % sym, timeout=15)
        if not (kp and kp.get("code") in (0, "0")):
            return
        rows = kp.get("data") or []
        if not rows:
            return
        rows.sort(key=lambda c: str(c.get("ts", "")))  # ISO8601 UTC sorts chronologically
        closes = [c for c in (fnum(r.get("close")) for r in rows) if c is not None]
        refs = {}
        if len(closes) >= 2:  refs["1"] = closes[-1]
        if len(closes) >= 6:  refs["6"] = closes[-6]
        if len(closes) >= 24: refs["24"] = closes[-24]
        lp = get_json(f"{SB}/market/last_price?symbol=%s" % sym, timeout=15)
        live = fnum(lp.get("data")) if lp and lp.get("code") in (0, "0") else None
        last = live if live else fnum(rows[-1].get("close"))
        if not last:
            return
        highs = [fnum(c.get("high")) for c in rows]
        lows = [fnum(c.get("low")) for c in rows]
        highs = [h for h in highs if h is not None]
        lows = [l for l in lows if l is not None]
        qvol = 0.0
        for c in rows:
            v, cl = fnum(c.get("volume")), fnum(c.get("close"))
            if v and cl:
                qvol += v * cl
        ref24 = fnum(rows[-24].get("close")) if len(rows) >= 24 else None
        chg24 = ((last / ref24) - 1) * 100 if ref24 else None
        with state_lock:
            state["spot"]["tickers"][sym] = {
                "lastPrice": str(last),
                "high": str(max(highs)) if highs else None,
                "low": str(min(lows)) if lows else None,
                "quoteVol": str(round(qvol, 2)),
                "chg24": round(chg24, 2) if chg24 is not None else None,
            }
            state["spot"]["updated"] = int(time.time())
            if refs:
                state["spot"]["refs"][sym] = refs
    except Exception:
        pass
    finally:
        sem.release()

def spot_plane_thread():
    sem = threading.Semaphore(KLINE_CONCURRENCY)
    while True:
        try:
            icons = load_icon_cache()
            resp = get_json(f"{SB}/common/coin_pair/list", timeout=90, log=True)
            if not (resp and resp.get("code") in (0, "0") and resp.get("data")):
                with state_lock:
                    state["spot"]["err"] = "spot roster fetch failed (see journal)"
                print("spot plane: roster fetch failed, retry in 15s", flush=True)
                time.sleep(15)
                continue
            meta = build_spot_meta(resp["data"], icons)
            with state_lock:
                state["spot"]["meta"] = meta
                state["spot"]["err"] = None
                syms = [m["key"] for m in meta]
            for sym in syms:
                sem.acquire()
                threading.Thread(target=spot_stats_worker, args=(sym, sem), daemon=True).start()
                time.sleep(0.05)
            while sem._value < KLINE_CONCURRENCY:
                time.sleep(0.5)
            print("spot sweep pass complete: %d symbols" % len(syms), flush=True)
        except Exception as e:
            with state_lock:
                state["spot"]["err"] = str(e)
            time.sleep(30)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/data":
            with state_lock:
                body = json.dumps(state).encode()
            ctype = "application/json"
        elif self.path == "/tradfi-blocked.json":
            try:
                body = open(os.path.join(os.path.dirname(INDEX_PATH), "tradfi-blocked.json"), "rb").read()
            except OSError:
                body = b'{"blocked":[]}'
            ctype = "application/json"
        else:
            try:
                body = open(INDEX_PATH, "rb").read()
            except OSError:
                body = b"<h1>index.html missing</h1>"
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    for fn in (classification_thread, futures_plane_thread, futures_roster_thread,
               kline_sweeper_thread, spot_plane_thread):
        threading.Thread(target=fn, daemon=True).start()
    print("bitunix dashboard v4 listening on %s:%d" % BIND, flush=True)
    ThreadingHTTPServer(BIND, H).serve_forever()
