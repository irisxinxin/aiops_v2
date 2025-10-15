#!/bin/bash

echo "=== Complete Gateway Service Test ==="
echo "Time: $(date)"
echo

# 1. 重启服务
echo "Step 1: Restarting gateway service..."
./restart_gateway.sh

if [ $? -ne 0 ]; then
    echo "❌ Failed to restart gateway service"
    exit 1
fi

echo "✅ Gateway service restarted successfully"
echo

# 2. 等待服务完全启动
echo "Step 2: Waiting for service to be fully ready..."
sleep 5

# 验证服务状态
for i in {1..10}; do
    if curl -s http://127.0.0.1:8081/healthz > /dev/null 2>&1; then
        echo "✅ Service is ready!"
        break
    fi
    echo "Waiting... ($i/10)"
    sleep 2
done

# 3. 运行详细测试
echo "Step 3: Running detailed sdn5_cpu tests..."
python3 test_sdn5_detailed.py

echo
echo "=== Test Complete ==="
echo "Check the generated log file for detailed results."
