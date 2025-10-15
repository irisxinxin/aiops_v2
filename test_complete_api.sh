#!/bin/bash

set -e

echo "=== Q Gateway API Complete Test ==="
echo ""

# 检查服务状态
echo "1. Checking service health..."
if curl -s http://127.0.0.1:8081/healthz > /dev/null; then
    echo "✅ Gateway service is healthy"
    curl -s http://127.0.0.1:8081/healthz | python3 -m json.tool
else
    echo "❌ Gateway service is not responding"
    exit 1
fi

echo ""
echo "2. Testing sdn5_cpu.json analysis..."

# 测试 sdn5_cpu.json
python3 test_sdn5.py

echo ""
echo "=== Test Complete ==="
