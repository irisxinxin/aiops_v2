#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 激活虚拟环境
source .venv/bin/activate

# 启动 ttyd 服务 (后台)
echo "Starting ttyd service..."
ttyd --ping-interval 55 -p 7682 --writable --interface 127.0.0.1 bash gateway/q_entry.sh &
TTYD_PID=$!

# 等待 ttyd 启动
sleep 3

# 启动 Gateway API 服务 (前台，systemd管理)
echo "Starting Gateway API service..."
exec python3 -m uvicorn gateway.app:app --host 0.0.0.0 --port 8081 --log-level info
