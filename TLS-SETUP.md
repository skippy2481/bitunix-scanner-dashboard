# Bitunix Scanner Dashboard — Build Guide

A self-hosted multi-market scanner for **Bitunix** spot and futures with
crypto/TradFi classification, curated info links, CoinGecko rank badges,
and geoblock awareness. Runs on anything with Python 3.10+.

## Quick Deploy

### Option A: Docker (recommended)

    git clone https://github.com/skippy2481/bitunix-scanner-dashboard /opt/bitunix-scanner-dashboard
    cd /opt/bitunix-scanner-dashboard
    ./install.sh 8124              # runs on http://localhost:8124
    ./install.sh <PORT>            # custom port if needed

Logs: `docker logs -f bitunix-scanner`

### Option B: Bare Metal

    sudo ./install-bare.sh                    # installs to /opt, port 8124
    sudo ./install-bare.sh /srv/scanner 8125  # custom directory + port

Check status: `systemctl status bitunix-scanner`
View logs: `journalctl -u bitunix-scanner -f`

---

## TLS Setup (HTTPS on Raw IP, No Domain Required)

Serve the dashboard over HTTPS using only a raw server IP — no domain name required.
Uses Let's Encrypt IP-address certificates (available since January 2026).

### Requirements

- Server with public IPv4 address
- Ports 80 and 443 reachable from the internet
- Ubuntu 24.04 (tested)

### Step 1 — Install nginx and Certbot

    apt-get update && apt-get install -y nginx pipx
    pipx install certbot
    certbot --version    # must be >= 5.3

    ufw allow 80/tcp
    ufw allow 443/tcp

### Step 2 — Configure nginx

Create `/etc/nginx/sites-available/bitunix-scanner`:

    server {
        listen 443 ssl http2;
        listen [::]:443 ssl;
        server_name <YOUR_SERVER_IP>;

        ssl_certificate     /etc/letsencrypt/live/<YOUR_SERVER_IP>/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/<YOUR_SERVER_IP>/privkey.pem;

        location / {
            proxy_pass http://127.0.0.1:8124;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }
    }

    server {
        listen 80;
        listen [::]:80;
        server_name <YOUR_SERVER_IP>;

        location /.well-known/acme-challenge/ {
            root /var/www/html;
        }

        location / {
            return 301 https://$host$request_uri;
        }
    }

Enable and test:

    rm -f /etc/nginx/sites-enabled/default
    ln -sf /etc/nginx/sites-available/bitunix-scanner /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx

NOTE: nginx 1.24 does NOT support standalone `http2 on;` directive.
Use `listen 443 ssl http2;` as shown above.

### Step 3 — Obtain IP Certificate

    certbot certonly --webroot -w /var/www/html \
      --ip-address <YOUR_SERVER_IP> \
      --preferred-profile shortlived \
      --register-unsafely-without-email --agree-tos \
      --non-interactive

Certificate appears at `/etc/letsencrypt/live/<YOUR_SERVER_IP>/`.

NOTE: IP certificates use the `shortlived` profile (~6 day lifetime).
Automation is mandatory.

### Step 4 — Automatic Renewal

Certbot via pipx has no built-in renewal timer. Create one:

`/etc/systemd/system/certbot-renew.service`:

    [Unit]
    Description=Certbot renewal
    [Service]
    Type=oneshot
    ExecStart=/root/.local/bin/certbot renew --quiet

`/etc/systemd/system/certbot-renew.timer`:

    [Unit]
    Description=Run certbot renewal twice daily
    [Timer]
    OnCalendar=*-*-* 06,18:00:00
    RandomizedDelaySec=30m
    Persistent=true
    [Install]
    WantedBy=timers.target

Renewal deploy hook (`/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`):

    #!/bin/sh
    systemctl reload nginx

Activate:

    chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
    systemctl daemon-reload
    systemctl enable --now certbot-renew.timer

### Step 5 — Bind Container to Loopback

With nginx fronting the dashboard, bind the container to localhost only:

    docker rm -f bitunix-scanner
    docker run -d \
      --name bitunix-scanner \
      --restart unless-stopped \
      --network bridge \
      -p 127.0.0.1:8124:8124 \
      --read-only \
      --tmpfs /tmp:rw,size=16m,noexec \
      --cap-drop ALL \
      --security-opt no-new-privileges \
      --memory 512m \
      --cpus 1.0 \
      -u 1000:1000 \
      bitunix-scanner:latest

This ensures the dashboard is only accessible via nginx (TLS), not directly.

### Verification

From outside the server:

    curl -s -o /dev/null -w "%{http_code} %{ssl_verify_result}\n" https://<YOUR_SERVER_IP>/
    # Expected: 200 0

    curl -s -o /dev/null -w "%{http_code}\n" http://<YOUR_SERVER_IP>/
    # Expected: 301

Check renewal timer:

    systemctl is-active certbot-renew.timer
    certbot certificates

---

## Updating

    cd /opt/bitunix-scanner-dashboard
    git pull
    ./install.sh 8124           # Docker path (recreates container)
    # or
    systemctl restart bitunix-scanner   # Bare-metal path

## Data Refresh

    python3 tools/cg-rank-harvest.py    # CoinGecko rank re-harvest
    python3 tools/sweep.py              # region availability check

After data edits: rebuild container or restart service.

## Uninstall

    sudo ./uninstall.sh                 # handles both paths

---

## Disclaimer

This is an unofficial, community-built scanner dashboard. Not affiliated with
or endorsed by Bitunix. Trademarks belong to their respective owners.

Data is sourced from public endpoints and may be delayed or incomplete.
Verify on the exchange before acting. Instrument availability varies by
jurisdiction — check local laws and exchange terms for your region.
Use at your own risk.
