#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Installing Q Gateway systemd service..."

# 停止现有服务
sudo systemctl stop q-gateway || true

# 复制服务文件
sudo cp gateway/q-gateway.service /etc/systemd/system/

# 重新加载 systemd
sudo systemctl daemon-reload

# 启用服务
sudo systemctl enable q-gateway

# 启动服务
sudo systemctl start q-gateway

# 检查状态
sleep 5
sudo systemctl status q-gateway --no-pager

echo ""
echo "✅ Q Gateway service installed and started"
echo "   Service status: sudo systemctl status q-gateway"
echo "   Service logs: sudo journalctl -u q-gateway -f"
echo "   Gateway API: http://127.0.0.1:8081/healthz"
