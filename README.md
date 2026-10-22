# Bitunix Scanner Dashboard

![screenshot](web-server.png)

A fast, self-hosted multi-market scanner for **Bitunix** spot and futures —
with crypto/TradFi classification, curated info links to canonical asset
pages, CoinGecko market-cap rank badges, and US geoblock awareness baked in.

Monitor ~1,300 instruments across both markets in one page: live prices, 24h
change, funding rates, category filters, favorites, and sortable/resizable
columns. Every crypto row links to its verified CoinGecko or CoinMarketCap
page; every stock row links to its Yahoo Finance quote. Runs on anything with
Python 3 — a Raspberry Pi, an Orange Pi, or a $10 VPS.

## Features

- Live spot + futures scanning (~1,300 instruments) with a single toggle
- Crypto / TradFi classification, with leveraged-ETF, pre-IPO, and tokenized-stock handling
- Curated info links: CoinGecko / CoinMarketCap coin pages, Yahoo Finance quotes
- CoinGecko market-cap rank badges (#1, #53...) on crypto rows
- Funding rates and 24h change per instrument, sortable and resizable columns
- **Portable favorites:** star instruments, then Export your favorites to a JSON
  file and Import it on any new browser or machine to restore them instantly
- Category filters, search, and US-geoblock awareness for TradFi rows

> ⚠️ **Unofficial project** — not affiliated with, endorsed by, or connected
> to Bitunix. See the full disclaimer at the bottom.

## Install — Option 1: Docker (recommended)

Sealed, hardened container: read-only filesystem, all capabilities dropped,
non-root user, no-new-privileges. One command:

    ./install.sh              # builds image, runs on http://localhost:8124
    ./install.sh 9000         # or pick any host port

Logs: `docker logs -f bitunix-scanner` · Uninstall (either path): `sudo ./uninstall.sh`

## Install — Option 2: Bare metal (no Docker required)

For minimal systems or if you prefer systemd over containers:

    sudo ./install-bare.sh                       # installs to /opt, port 8124
    sudo ./install-bare.sh /srv/scanner 8125     # custom directory + port

Installs a `bitunix-scanner` systemd unit (auto-start, restart-on-failure):

    systemctl status bitunix-scanner      # check it
    journalctl -u bitunix-scanner -f      # logs

Both paths boot automatically (container restart-policy / systemd).

Requirements: Python 3.10+ (stdlib only, no pip packages).

## Quick start on a fresh server (public deploy)

    # as root, on any Ubuntu/Debian box with docker + ufw:
    ufw allow 22/tcp && ufw enable          # deny-by-default firewall
    ufw allow 8124/tcp                      # dashboard port
    systemctl is-enabled docker || systemctl enable docker
    git clone https://github.com/skippy2481/bitunix-scanner-dashboard /opt/bitunix-scanner-dashboard
    cd /opt/bitunix-scanner-dashboard
    ./install.sh 8124                       # builds + runs hardened container

Then browse to http://<server-ip>:8124. Want HTTPS on the bare IP with no domain? See **TLS-SETUP.md**. Uninstall later with `sudo ./uninstall.sh`.

## How it works

**Polling model.** The server runs background threads per market, so
upstream is polled server-side and browsers just fetch one consolidated
snapshot from `/api/data`:

- **Futures plane** — refreshes every **15 seconds** (batch tickers,
  funding rates, meta). Incomplete fetches retry after 15s.
- **Spot plane** — runs a continuous sweep: per-symbol stat workers under
  a concurrency semaphore, one pass at a time (a full pass is the
  interval; watch the journal for "spot sweep pass complete").
- **Roster** — instrument lists refresh every **30 minutes**, so new
  listings appear automatically.
- **Reference prices** (1h/6h/24h) — kline sweep every **5 minutes**.
- **Classifier caches** — CoinGecko names/icons refresh weekly.

**Classification.** Each base symbol is classified Crypto/TradFi from a
stack: forced-TradFi registry (`tradfi-names.json`) first, then
CoinGecko-derived sets, with 1000-prefixed symbols normalized. Info links
resolve from `info-links.json` (hand-curated), then CoinGecko IDs, then
Yahoo Finance for TradFi.

**Rank badges.** Crypto rows carry a CoinGecko market-cap rank from
`cg-ranks.json` (harvested via `tools/cg-rank-harvest.py`).

**Persistence.** Favorites live in your browser's localStorage — nothing
is stored server-side. Export/Import buttons move them between browsers.

## Repository layout

| Path | Contents |
|------|----------|
| `app/` | `server.py` + `index.html` — the dashboard itself |
| `data/` | Curated registries: info links, TradFi names, CG ranks, icons, blocklist |
| `tools/` | Maintenance scripts (rank harvest, availability sweeps) |
| `tools/client/` | Host-side browser auditor (Selenium/Firefox, never containerized) |

## Keeping data fresh

- Re-harvest CoinGecko ranks: `python3 tools/cg-rank-harvest.py`
- Verify instrument availability from your region: `python3 tools/sweep.py`
- After data edits: rebuild container (`./install.sh`) or restart the service.

## Disclaimer

This is an **unofficial, community-built** scanner dashboard. It is not
affiliated with, endorsed by, or connected to Bitunix in any way. Bitunix,
product names, and trademarks belong to their respective owners.

Data is sourced from public endpoints and may be delayed, incomplete, or
inaccurate — verify on the exchange before acting on anything displayed.
**Instrument availability varies by jurisdiction:** Bitunix restricts
access to some instruments by region, so assets shown here may not be
tradable or even viewable where you live. Nothing in this tool indicates
what you personally may access or trade — check your local laws and the
exchange's terms for your jurisdiction. Use at your own risk.
