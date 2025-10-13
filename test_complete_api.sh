#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Config
HTTP_PORT="${HTTP_PORT:-8081}"
QTTY_PORT="${QTTY_PORT:-7682}"

echo "[TEST] Complete API Test with sdn5_cpu.json"

# Check if service is running
if ! curl -sS --max-time 2 "http://127.0.0.1:${HTTP_PORT}/healthz" >/dev/null 2>&1; then
    echo "[ERROR] Gateway service not running. Please start it first."
    exit 1
fi

echo "[TEST] Gateway service is running"

# Show connection pool status
echo "[TEST] Connection pool status:"
curl -s "http://127.0.0.1:${HTTP_PORT}/healthz" | jq .connection_pool

# Test with sdn5_cpu.json and capture full response
echo "[TEST] Testing /ask endpoint with sdn5_cpu.json..."
echo "[TEST] Request payload:"
jq -c '{text: "分析这个CPU告警并提供解决方案", alert: .}' sdn5_cpu.json

echo -e "\n[TEST] API Response (first 50 lines):"
timeout 60 curl -X POST "http://127.0.0.1:${HTTP_PORT}/ask" \
    -H "Content-Type: application/json" \
    -d "$(jq -c '{text: "分析这个CPU告警并提供解决方案", alert: .}' sdn5_cpu.json)" \
    2>/dev/null | head -50

echo -e "\n[TEST] Connection pool status after request:"
curl -s "http://127.0.0.1:${HTTP_PORT}/healthz" | jq .connection_pool

echo -e "\n[TEST] Complete API test finished"
