#!/bin/bash

echo "=== Multiple sdn5_cpu.json Tests - WebSocket Connection Reuse ==="
echo "Start time: $(date)"
echo ""

# Test payload
PAYLOAD='{
  "text": "分析这个CPU告警，给出根因分析和解决建议",
  "alert": {
    "status": "firing",
    "env": "dev",
    "region": "dev-nbu-aps1",
    "service": "sdn5",
    "category": "cpu",
    "severity": "critical",
    "title": "sdn5 container CPU usage is too high",
    "group_id": "sdn5_critical",
    "window": "5m",
    "duration": "15m",
    "threshold": 0.9,
    "metadata": {
      "alert_name": "sdn5 container CPU usage is too high",
      "alertgroup": "sdn5",
      "alertname": "sdn5 container CPU usage is too high",
      "auto_create_group": false,
      "comparison": ">",
      "container": "omada-device-gateway",
      "datasource_cluster": "dev-nbu-aps1",
      "department": "[ERD|Networking Solutions|Network Services]",
      "duration": "300s",
      "expression": "sum(rate(container_cpu_usage_seconds_total{container!=\"POD\",container!=\"\", container!=\"istio-proxy\", image!=\"\",pod=~\"omada-device-gateway.*\", namespace=~\"sdn5\"}[5m])) by (pod, container) / sum(kube_pod_container_resource_limits{container!=\"POD\",pod=~\"omada-device-gateway.*\", namespace=~\"sdn5\", resource=\"cpu\"} > 0) by (pod, container)>0.9",
      "group_id": "sdn5_critical",
      "pod": "omada-device-gateway-6.0.0189-59ccd49449-98n7b",
      "prometheus": "monitoring/kps-prometheus",
      "service_name": "sdn5",
      "severity": "critical",
      "tel_up": "30m",
      "threshold_value": 0.9,
      "current_value": 0.92
    }
  }
}'

# Function to run a single test
run_test() {
    local test_num=$1
    echo "=== Test #$test_num ==="
    echo "Time: $(date)"
    
    # Check connection pool before test
    echo "Connection pool before test:"
    curl -s http://localhost:8081/healthz | jq '.connection_pool'
    
    echo ""
    echo "Prompt: 分析这个CPU告警，给出根因分析和解决建议"
    echo ""
    
    # Record start time
    start_time=$(date +%s.%N)
    
    # Run the test with timeout and capture key response parts
    echo "Response (key parts):"
    response=$(timeout 45 curl -X POST http://localhost:8081/ask \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        -w "\n\n=== Timing Info ===\nTotal time: %{time_total}s\nConnect time: %{time_connect}s\nResponse time: %{time_starttransfer}s\nHTTP code: %{http_code}\n" \
        2>/dev/null)
    
    # Calculate total time
    end_time=$(date +%s.%N)
    total_time=$(echo "$end_time - $start_time" | bc -l)
    
    # Extract key information from response
    echo "- Checking for historical references..."
    if echo "$response" | grep -q -E "(10\+|previous|historical|analyzed.*times|multiple.*hours)"; then
        echo "  ✅ Found historical context references"
        echo "$response" | grep -o -E "(10\+[^,]*|previous[^,]*|historical[^,]*|analyzed[^,]*times|multiple[^,]*hours)" | head -3
    else
        echo "  ❌ No clear historical references found"
    fi
    
    echo ""
    echo "- Checking for root cause analysis..."
    if echo "$response" | grep -q -E "(false.*positive|chronic|systematic|root_cause)"; then
        echo "  ✅ Root cause analysis present"
        echo "$response" | grep -o -E "(false.*positive[^,]*|chronic[^,]*|systematic[^,]*)" | head -2
    else
        echo "  ❌ No clear root cause found"
    fi
    
    echo ""
    echo "- Extracting timing information..."
    timing_info=$(echo "$response" | grep -A4 "=== Timing Info ===")
    if [ -n "$timing_info" ]; then
        echo "$timing_info"
    else
        echo "  Total execution time: ${total_time}s"
    fi
    
    echo ""
    echo "Connection pool after test:"
    curl -s http://localhost:8081/healthz | jq '.connection_pool'
    
    echo ""
    echo "----------------------------------------"
    echo ""
}

# Run multiple tests
for i in {1..4}; do
    run_test $i
    if [ $i -lt 4 ]; then
        echo "Waiting 5 seconds before next test..."
        sleep 5
    fi
done

echo "=== Summary ==="
echo "End time: $(date)"
echo ""
echo "Expected behavior with WebSocket reuse:"
echo "- First call: Longer latency (connection establishment)"
echo "- Subsequent calls: Shorter latency (connection reuse)"
echo "- Historical context: References to previous analyses"
echo "- Connection pool: Should show 1 active connection throughout"
