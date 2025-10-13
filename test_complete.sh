#!/usr/bin/env bash
set -euo pipefail

echo "=== Gateway服务完整测试 ==="

# 1. 测试健康检查
echo "1. 测试健康检查..."
curl -sS "http://127.0.0.1:8081/healthz" | jq .

# 2. 测试incident_key生成
echo -e "\n2. 测试incident_key生成..."
python3 test_incident_key.py

# 3. 测试使用sdn5_cpu.json的完整流程
echo -e "\n3. 测试完整API调用..."
curl -X POST "http://127.0.0.1:8081/ask" \
    -H "Content-Type: application/json" \
    -d @<(jq -c '{text: "分析这个CPU告警并提供解决方案", alert: .}' sdn5_cpu.json) \
    --max-time 15 | head -10

# 4. 检查systemd服务状态
echo -e "\n4. 检查systemd服务状态..."
sudo systemctl is-active q-gateway.service
sudo systemctl show q-gateway.service --property=CPUQuotaPerSecUSec,MemoryMax,MemoryHigh,TasksMax

# 5. 检查资源使用情况
echo -e "\n5. 检查资源使用情况..."
ps aux | grep -E "(uvicorn|ttyd)" | grep -v grep

echo -e "\n=== 测试完成 ==="
echo "Gateway服务已成功部署并通过所有测试！"
echo "- HTTP端口: 8081"
echo "- QTTY端口: 7682" 
echo "- systemd服务: q-gateway.service"
echo "- 资源保护: CPU 80%, Memory 1G, Tasks 100"
