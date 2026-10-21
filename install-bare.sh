#!/usr/bin/env bash
# bitunix-scanner-dashboard :: bare-metal install (no Docker)
# usage: ./install-bare.sh [TARGET_DIR] [PORT]   (defaults: /opt/bitunix-scanner-dashboard 8124)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-/opt/bitunix-scanner-dashboard}"
PORT="${2:-8124}"

command -v python3 >/dev/null || { echo "ERROR: python3 not found"; exit 1; }

if [ "$(id -u)" -ne 0 ]; then echo "ERROR: run as root (sudo) for ${TARGET}"; exit 1; fi

echo "[1/2] installing to ${TARGET}..."
mkdir -p "$TARGET"
cp "$HERE"/app/server.py "$HERE"/app/index.html "$TARGET"/
cp "$HERE"/data/*.json "$HERE"/data/*.tsv "$TARGET"/ 2>/dev/null || cp "$HERE"/data/*.json "$TARGET"/
python3 -m py_compile "$TARGET/server.py" && echo "  syntax OK"

echo "[2/2] installing systemd unit (port ${PORT})..."
cat > /etc/systemd/system/bitunix-scanner.service <<UNIT
[Unit]
Description=Bitunix Scanner Dashboard
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 ${TARGET}/server.py
Restart=on-failure
RestartSec=5
WorkingDirectory=${TARGET}

[Install]
WantedBy=multi-user.target
UNIT
# patch port if not default
[ "$PORT" != "8124" ] && sed -i "s/server.py/server.py --port ${PORT}/" /etc/systemd/system/bitunix-scanner.service || true

systemctl daemon-reload
systemctl enable --now bitunix-scanner
sleep 2
systemctl is-active bitunix-scanner && echo "DONE: service active"
