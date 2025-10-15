#!/usr/bin/env bash
set -euo pipefail

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

echo "Starting ttyd service..."
ttyd --interface "${QTTY_HOST:-127.0.0.1}" \
     --port "${QTTY_PORT:-7682}" \
     --url-arg \
     --writable \
     --ping-interval "${QTTY_PING:-55}" \
     bash gateway/q_entry.sh &

sleep "${WARMUP_SLEEP:-15}" || true
echo "Starting Gateway API service..."
exec uvicorn gateway.app:app --host "${HTTP_HOST:-0.0.0.0}" --port "${HTTP_PORT:-8081}" --log-level info
