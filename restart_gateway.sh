#!/bin/bash

echo "=== Restarting Q Gateway Service ==="

# 停止所有相关服务
echo "Stopping all gateway services..."
sudo systemctl stop q-gateway 2>/dev/null || true
pkill -f "python.*app.py" 2>/dev/null || true
pkill -f "uvicorn.*app:app" 2>/dev/null || true
pkill -f "ttyd.*q_entry.sh" 2>/dev/null || true
sleep 2

# 检查虚拟环境
echo "Checking virtual environment..."
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install fastapi uvicorn requests
else
    source .venv/bin/activate
fi

# 启动服务
echo "Starting gateway service..."
./gateway/start.sh &

# 等待服务就绪
echo "Waiting for service to be ready..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:8081/healthz > /dev/null 2>&1; then
        echo "✅ Gateway service is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 1
done

echo "Gateway service restarted successfully"
