#!/bin/bash

echo "=== Stopping all services ==="
sudo systemctl stop q-proxy.service 2>/dev/null || true
pkill -f "uvicorn.*app:app" 2>/dev/null || true
pkill -f "ttyd.*q_entry.sh" 2>/dev/null || true
pkill -f fast_proxy.py 2>/dev/null || true
sleep 3

echo "=== Verifying clean state ==="
REMAINING=$(ps aux | grep -E "(uvicorn.*app:app|ttyd.*q_entry)" | grep -v grep | wc -l)
if [ $REMAINING -gt 0 ]; then
    echo "⚠️  Warning: $REMAINING processes still running"
    ps aux | grep -E "(uvicorn.*app:app|ttyd.*q_entry)" | grep -v grep
fi

echo "=== Starting services ==="
./gateway/start.sh
sleep 3

# Start fast proxy
python3 fast_proxy.py &
sleep 2

echo "=== Service status ==="
curl -s http://127.0.0.1:8081/healthz > /dev/null && echo "✅ Gateway: healthy" || echo "❌ Gateway: failed"
curl -s http://127.0.0.1:8083/healthz > /dev/null && echo "✅ Fast Proxy: healthy" || echo "❌ Fast Proxy: failed"

echo "=== Process verification ==="
GATEWAY_COUNT=$(ps aux | grep "uvicorn.*app:app" | grep -v grep | wc -l)
echo "Gateway processes: $GATEWAY_COUNT (should be 1)"

echo "=== Services ready ==="
echo "Gateway API: http://127.0.0.1:8081"
echo "Fast HTTP Proxy: http://127.0.0.1:8083 (recommended)"
echo ""
echo "Test with: curl -X POST http://127.0.0.1:8083/ask -H 'Content-Type: application/json' -d '{...}'"
