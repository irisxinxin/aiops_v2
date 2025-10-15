#!/bin/bash

echo "=== Testing sdn5_cpu.json with curl ==="
echo "Start time: $(date)"
echo ""

# 记录开始时间
start_time=$(date +%s.%N)

# 执行 curl 请求
curl -X POST http://localhost:8081/ask \
  -H "Content-Type: application/json" \
  -w "\n\n=== Timing Info ===\nTotal time: %{time_total}s\nConnect time: %{time_connect}s\nResponse time: %{time_starttransfer}s\nHTTP code: %{http_code}\n" \
  -d @- << 'EOF'
{
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
}
EOF

# 计算总用时
end_time=$(date +%s.%N)
total_time=$(echo "$end_time - $start_time" | bc -l)

echo ""
echo "=== Test Complete ==="
echo "End time: $(date)"
echo "Total execution time: ${total_time}s"
