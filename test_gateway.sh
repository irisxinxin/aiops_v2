#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Config
HTTP_PORT="${HTTP_PORT:-8081}"
QTTY_PORT="${QTTY_PORT:-7682}"

echo "[TEST] Testing Gateway Service with sdn5_cpu.json"

# Check if service is running
if ! pgrep -f "uvicorn gateway.app:app" >/dev/null 2>&1; then
    echo "[TEST] Starting gateway service..."
    bash gateway/start.sh &
    GATEWAY_PID=$!
    echo $GATEWAY_PID > gateway.pid
    sleep 3
else
    echo "[TEST] Gateway service already running"
fi

# Wait for service to be ready
echo "[TEST] Waiting for gateway to be ready..."
for i in {1..30}; do
    if curl -sS --max-time 2 "http://127.0.0.1:${HTTP_PORT}/healthz" >/dev/null 2>&1; then
        echo "[TEST] Gateway is ready"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "[ERROR] Gateway not ready after 30s"
        exit 1
    fi
done

# Test with sdn5_cpu.json
echo "[TEST] Testing /ask endpoint with sdn5_cpu.json..."
curl -X POST "http://127.0.0.1:${HTTP_PORT}/ask" \
    -H "Content-Type: application/json" \
    -d @<(jq -c '{text: "分析这个CPU告警并提供解决方案", alert: .}' sdn5_cpu.json) \
    --max-time 60 | head -20

echo -e "\n[TEST] Gateway test completed successfully"
echo "[TEST] Gateway PID: $(cat gateway.pid 2>/dev/null || echo 'N/A')"
echo "[TEST] To stop: kill \$(cat gateway.pid 2>/dev/null || echo) || pkill -f 'uvicorn gateway.app:app'"
