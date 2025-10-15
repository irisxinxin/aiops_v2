#!/usr/bin/env bash
set -euo pipefail

# One-click deploy/restart for q-gateway

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "[1/6] Ensure session root and permissions"
sudo mkdir -p /srv/q-sessions
sudo chown -R ubuntu:ubuntu /srv/q-sessions || true

echo "[2/6] Ensure Python venv and deps"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -U --disable-pip-version-check fastapi uvicorn[standard] websockets >/dev/null

echo "[3/6] Install/Reload systemd unit"
sudo cp gateway/q-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload

echo "[4/6] Restart service (CLEAR_SESSIONS=${CLEAR_SESSIONS:-0})"
if [ "${CLEAR_SESSIONS:-0}" = "1" ]; then
  sudo CLEAR_SESSIONS=1 systemctl restart q-gateway
else
  sudo systemctl restart q-gateway
fi

echo "[5/6] Show brief status"
sudo systemctl status q-gateway --no-pager | sed -n '1,12p' || true

echo "[6/6] Health check"
for i in {1..20}; do
  if curl -sf http://127.0.0.1:8081/healthz >/dev/null; then
    echo "✅ Health OK"
    exit 0
  fi
  echo "Waiting health... ($i/20)" && sleep 1
done

echo "❌ Health check failed"
exit 1


