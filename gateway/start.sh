#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 激活虚拟环境
source .venv/bin/activate

# 停止之前的服务
echo "Stopping previous gateway services..."
pkill -f "uvicorn gateway.app:app" || true
pkill -f "ttyd.*gateway/q_entry.sh" || true
sleep 2

# 清空会话目录（可选）
if [[ "${CLEAR_SESSIONS:-0}" == "1" ]]; then
  echo "Clearing ./q-sessions ..."
  rm -rf ./q-sessions/* || true
fi

# 启动 ttyd 服务 (Q CLI 终端)
echo "Starting ttyd service..."
ttyd --ping-interval 55 -p 7682 --writable --interface 127.0.0.1 bash gateway/q_entry.sh &
TTYD_PID=$!

# 等待 ttyd 启动
sleep 3

# 启动 Gateway API 服务
echo "Starting Gateway API service..."
python3 -m uvicorn gateway.app:app --host 0.0.0.0 --port 8081 --log-level info &
GATEWAY_PID=$!

# 保存 PID
echo $GATEWAY_PID > gateway.pid

echo "Services started:"
echo "  TTYD PID: $TTYD_PID"
echo "  Gateway PID: $GATEWAY_PID"
echo "  Gateway API: http://127.0.0.1:8081"

# 等待服务启动并检查健康状态
for i in {1..10}; do
    if curl -s http://127.0.0.1:8081/healthz > /dev/null; then
        echo "✅ Gateway service is healthy"
        exit 0
    fi
    echo "Waiting for service to start... ($i/10)"
    sleep 2
done

echo "❌ Gateway service health check failed"
exit 1
