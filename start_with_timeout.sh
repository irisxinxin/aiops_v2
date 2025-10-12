#!/bin/bash
cd /home/ubuntu/huixin/aiops_v2
source .venv/bin/activate

# 设置超时启动qproxy
timeout 60s python qproxy_pool.py &
QPROXY_PID=$!

# 等待启动
sleep 5

# 检查健康状态
if curl -s http://127.0.0.1:8080/healthz > /dev/null; then
    echo "✓ QProxy started successfully on port 8080"
    echo "PID: $QPROXY_PID"
    
    # 测试调用
    echo "Testing with sample alert..."
    jq -c '{alert:.}' ./sdn5_cpu.json | curl -sS -X POST 'http://127.0.0.1:8080/call' -H 'Content-Type: application/json' --data-binary @- | head -200
else
    echo "✗ QProxy failed to start"
    kill $QPROXY_PID 2>/dev/null
    exit 1
fi
