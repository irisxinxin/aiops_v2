#!/usr/bin/env bash
set -euo pipefail

# One-click deploy/restart for q-gateway

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ---- Tunables (can be overridden by env) ----
INIT_READY_TIMEOUT="${INIT_READY_TIMEOUT:-10}"
WARMUP_SLEEP="${WARMUP_SLEEP:-15}"
Q_OVERALL_TIMEOUT="${Q_OVERALL_TIMEOUT:-30}"
QTTY_HOST="${QTTY_HOST:-127.0.0.1}"
QTTY_PORT="${QTTY_PORT:-7682}"
HTTP_HOST="${HTTP_HOST:-0.0.0.0}"
HTTP_PORT="${HTTP_PORT:-8081}"

echo "[1/7] Disable legacy service if exists (aiops-qproxy.service)"
sudo systemctl disable --now aiops-qproxy.service 2>/dev/null || true

echo "[2/7] Ensure session root and permissions"
mkdir -p q-sessions logs
sudo chown -R ubuntu:ubuntu q-sessions logs || true

echo "[3/7] Ensure Python venv and deps"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -U --disable-pip-version-check fastapi uvicorn[standard] websockets stransi >/dev/null

echo "[4/7] Prekill lingering processes (uvicorn/ttyd)"
# 防御性清理：清掉可能遗留的 uvicorn/ttyd 进程，避免端口占用/多实例
pkill -f "uvicorn.*gateway.app:app" 2>/dev/null || true
pkill -f "ttyd.*q_entry.sh" 2>/dev/null || true

echo "[5/7] Install/Reload systemd unit"
sudo cp gateway/q-gateway.service /etc/systemd/system/
# Rewrite hard-coded repo path in unit to current PROJECT_DIR
sudo sed -i "s|/home/ubuntu/huixin/aiops_v2|${PROJECT_DIR}|g" /etc/systemd/system/q-gateway.service
# Create/Update drop-in override for env tunables
sudo mkdir -p /etc/systemd/system/q-gateway.service.d
sudo tee /etc/systemd/system/q-gateway.service.d/override.conf >/dev/null <<EOF
[Service]
Environment=INIT_READY_TIMEOUT=${INIT_READY_TIMEOUT}
Environment=WARMUP_SLEEP=${WARMUP_SLEEP}
Environment=Q_OVERALL_TIMEOUT=${Q_OVERALL_TIMEOUT}
Environment=QTTY_HOST=${QTTY_HOST}
Environment=QTTY_PORT=${QTTY_PORT}
Environment=HTTP_HOST=${HTTP_HOST}
Environment=HTTP_PORT=${HTTP_PORT}
EOF
sudo systemctl daemon-reload

echo "[6/7] Restart service (CLEAR_SESSIONS=${CLEAR_SESSIONS:-0})"
if [ "${CLEAR_SESSIONS:-0}" = "1" ]; then
  sudo CLEAR_SESSIONS=1 systemctl restart q-gateway
else
  sudo systemctl restart q-gateway
fi

echo "[7/7] Show brief status"
sudo systemctl status q-gateway --no-pager | sed -n '1,12p' || true
echo "Health check"
for i in {1..20}; do
  if curl -sf http://127.0.0.1:8081/healthz >/dev/null; then
    echo "✅ Health OK"
    exit 0
  fi
  echo "Waiting health... ($i/20)" && sleep 1
done

echo "❌ Health check failed"
exit 1


