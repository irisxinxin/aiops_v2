#!/bin/bash

echo "=== Quick sdn5_cpu Tests - Connection Reuse Analysis ==="
echo ""

# Function to run a quick test
run_quick_test() {
    local test_num=$1
    echo "=== Test #$test_num - $(date) ==="
    
    # Check connection pool
    pool_status=$(curl -s http://localhost:8081/healthz | jq -r '.connection_pool | "Active: \(.active_connections)/\(.max_connections)"')
    echo "Connection pool: $pool_status"
    
    # Run test with shorter timeout
    start_time=$(date +%s.%N)
    
    response=$(timeout 30 curl -X POST http://localhost:8081/ask \
        -H "Content-Type: application/json" \
        -d '{
          "text": "快速分析这个sdn5 CPU告警",
          "alert": {
            "status": "firing",
            "service": "sdn5",
            "category": "cpu",
            "severity": "critical",
            "title": "sdn5 container CPU usage is too high",
            "metadata": {
              "current_value": 0.92,
              "threshold_value": 0.9
            }
          }
        }' \
        -w "TIMING: Total:%{time_total}s Connect:%{time_connect}s Response:%{time_starttransfer}s HTTP:%{http_code}" \
        2>/dev/null)
    
    end_time=$(date +%s.%N)
    total_time=$(echo "$end_time - $start_time" | bc -l)
    
    # Extract key info
    if echo "$response" | grep -q "TIMING:"; then
        timing=$(echo "$response" | grep "TIMING:" | tail -1)
        echo "$timing"
    else
        echo "TIMING: Total:${total_time}s (timeout or error)"
    fi
    
    # Check for historical context
    if echo "$response" | grep -q -E "(历史|previous|之前|多次|historical|analyzed.*times)"; then
        echo "✅ Historical context found"
        echo "$response" | grep -o -E "(历史[^,，。]*|previous[^,]*|之前[^,，。]*|多次[^,，。]*|historical[^,]*)" | head -2
    else
        echo "❌ No historical context"
    fi
    
    # Check for analysis completion
    if echo "$response" | grep -q -E "(root_cause|根因|false.*positive|虚假)"; then
        echo "✅ Analysis completed"
    else
        echo "❌ Analysis incomplete or timeout"
    fi
    
    echo ""
}

# Run 3 quick tests
for i in {1..3}; do
    run_quick_test $i
    sleep 2
done

echo "=== Connection Reuse Summary ==="
echo "Expected pattern:"
echo "- All tests should use the same WebSocket connection"
echo "- Connection pool should remain at 1/2 throughout"
echo "- Later tests may reference historical context"
echo "- Response times should be similar (connection reuse working)"
