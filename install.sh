#!/usr/bin/env bash
# bitunix-scanner-dashboard :: Docker install (hardened, sealed)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="bitunix-scanner:latest"
NAME="bitunix-scanner"
PORT="${1:-8124}"

command -v docker >/dev/null || { echo "ERROR: docker not found"; exit 1; }

echo "[1/3] building image..."
docker build -t "$IMAGE" "$HERE"

echo "[2/3] replacing old container (if any)..."
docker rm -f "$NAME" 2>/dev/null || true

echo "[3/3] starting hardened container on :$PORT"
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network bridge \
  -p "$PORT":8124 \
  --read-only \
  --tmpfs /tmp:rw,size=16m,noexec \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --memory 512m \
  --cpus 1.0 \
  -u 1000:1000 \
  "$IMAGE"

echo
echo "DONE: http://localhost:$PORT  (logs: docker logs -f $NAME)"
