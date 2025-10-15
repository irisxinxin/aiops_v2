#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Stopping gateway services..."

# 停止 Gateway API 服务
if [ -f gateway.pid ]; then
    GATEWAY_PID=$(cat gateway.pid)
    if kill -0 "$GATEWAY_PID" 2>/dev/null; then
        echo "Stopping Gateway API (PID: $GATEWAY_PID)..."
        kill "$GATEWAY_PID"
        sleep 2
    fi
    rm -f gateway.pid
fi

# 停止所有相关进程
pkill -f "uvicorn gateway.app:app" || true
pkill -f "ttyd.*gateway/q_entry.sh" || true

echo "✅ Gateway services stopped"
