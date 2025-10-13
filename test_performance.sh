#!/bin/bash
set -euo pipefail

# Performance testing script for Q proxy optimization
# Tests single curl requests and measures response times

ENDPOINT="${ENDPOINT:-http://127.0.0.1:8080/call}"
TARGET_TIME="${TARGET_TIME:-10}"  # Target response time in seconds
MAX_ITERATIONS="${MAX_ITERATIONS:-50}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-2}"

# Test payload (simplified)
TEST_PAYLOAD='{
  "alert": {
    "service": "sdn5",
    "category": "cpu",
    "severity": "high",
    "region": "us-east-1",
    "metadata": {
      "alert_name": "cpu_high",
      "group_id": "test123"
    },
    "data": {
      "cpu_usage": 85.5,
      "threshold": 80.0,
      "timestamp": "2025-10-13T09:00:00Z"
    }
  },
  "prompt": "Analyze this CPU alert quickly"
}'

echo "=== Q Proxy Performance Test ==="
echo "Target: ${TARGET_TIME}s response time"
echo "Endpoint: ${ENDPOINT}"
echo "Max iterations: ${MAX_ITERATIONS}"
echo ""

success_count=0
total_time=0
min_time=999
max_time=0
iteration=0

while [ $iteration -lt $MAX_ITERATIONS ]; do
    iteration=$((iteration + 1))
    echo -n "Test $iteration: "
    
    start_time=$(date +%s.%N)
    
    # Make the request
    response=$(curl -s -w "%{http_code}|%{time_total}" \
        -H "Content-Type: application/json" \
        -d "$TEST_PAYLOAD" \
        "$ENDPOINT" 2>/dev/null || echo "000|999")
    
    end_time=$(date +%s.%N)
    
    # Parse response
    http_code=$(echo "$response" | tail -c 10 | cut -d'|' -f1)
    curl_time=$(echo "$response" | tail -c 10 | cut -d'|' -f2)
    actual_time=$(echo "$end_time - $start_time" | bc -l)
    
    # Use curl time if available, otherwise actual time
    if [[ "$curl_time" =~ ^[0-9]+\.?[0-9]*$ ]]; then
        response_time=$curl_time
    else
        response_time=$actual_time
    fi
    
    # Check if successful
    if [ "$http_code" = "200" ]; then
        success_count=$((success_count + 1))
        total_time=$(echo "$total_time + $response_time" | bc -l)
        
        # Update min/max
        if (( $(echo "$response_time < $min_time" | bc -l) )); then
            min_time=$response_time
        fi
        if (( $(echo "$response_time > $max_time" | bc -l) )); then
            max_time=$response_time
        fi
        
        # Check if within target
        if (( $(echo "$response_time <= $TARGET_TIME" | bc -l) )); then
            echo "✓ ${response_time}s (GOOD)"
        else
            echo "⚠ ${response_time}s (SLOW)"
        fi
    else
        echo "✗ HTTP $http_code (${response_time}s)"
    fi
    
    # Show running stats every 10 iterations
    if [ $((iteration % 10)) -eq 0 ] && [ $success_count -gt 0 ]; then
        avg_time=$(echo "scale=2; $total_time / $success_count" | bc -l)
        success_rate=$(echo "scale=1; $success_count * 100 / $iteration" | bc -l)
        echo "  Stats: Success rate: ${success_rate}%, Avg: ${avg_time}s, Min: ${min_time}s, Max: ${max_time}s"
    fi
    
    # Early exit if consistently fast
    if [ $iteration -ge 20 ] && [ $success_count -ge 18 ]; then
        avg_time=$(echo "scale=2; $total_time / $success_count" | bc -l)
        if (( $(echo "$avg_time <= $TARGET_TIME" | bc -l) )); then
            echo ""
            echo "🎉 OPTIMIZATION SUCCESS! Consistently fast responses."
            break
        fi
    fi
    
    sleep $SLEEP_BETWEEN
done

echo ""
echo "=== Final Results ==="
if [ $success_count -gt 0 ]; then
    avg_time=$(echo "scale=2; $total_time / $success_count" | bc -l)
    success_rate=$(echo "scale=1; $success_count * 100 / $iteration" | bc -l)
    
    echo "Total tests: $iteration"
    echo "Successful: $success_count (${success_rate}%)"
    echo "Average response time: ${avg_time}s"
    echo "Min response time: ${min_time}s"
    echo "Max response time: ${max_time}s"
    echo "Target: ${TARGET_TIME}s"
    
    if (( $(echo "$avg_time <= $TARGET_TIME" | bc -l) )); then
        echo "🎯 TARGET ACHIEVED!"
    else
        echo "❌ Target not met. Need further optimization."
    fi
else
    echo "❌ No successful requests. Check service status."
fi
