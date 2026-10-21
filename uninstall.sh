#!/usr/bin/env bash
# bitunix-scanner-dashboard :: uninstall (detects Docker or bare-metal install)
set -euo pipefail

echo "[1/3] stopping + removing Docker container/image (if present)..."
docker rm -f bitunix-scanner 2>/dev/null && echo "  removed container" || echo "  no container"
docker rmi bitunix-scanner:latest 2>/dev/null && echo "  removed image" || echo "  no image"

echo "[2/3] removing systemd unit (if present)..."
if systemctl list-unit-files | grep -q '^bitunix-scanner.service'; then
  systemctl disable --now bitunix-scanner
  rm -f /etc/systemd/system/bitunix-scanner.service
  systemctl daemon-reload
  echo "  unit removed"
else
  echo "  no unit"
fi

echo "[3/3] removing install directory (if present)..."
for d in /opt/bitunix-scanner-dashboard /opt/bitunix-dashboard; do
  [ -d "$d" ] && rm -rf "$d" && echo "  removed $d"
done

echo "DONE."
