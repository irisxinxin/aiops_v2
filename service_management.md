# Q Gateway 服务管理指南

## Systemd 服务操作顺序

### 1. 停止现有服务
```bash
# 停止 systemd 服务（如果已安装）
sudo systemctl stop q-gateway

# 停止手动启动的服务
./gateway/stop.sh

# 确认所有进程已停止
ps aux | grep -E "(gateway|uvicorn|ttyd)" | grep -v grep
```

### 2. 启动服务（手动方式推荐）
```bash
# 手动启动（推荐，更稳定）
./gateway/start.sh

# 或安装为 systemd 服务
./install_gateway_service.sh
```

### 3. 验证服务健康
```bash
curl -s http://localhost:8081/healthz | jq .
```

## 测试 API 调用

### sdn5_cpu.json 测试的 curl 命令
```bash
curl -X POST http://localhost:8081/ask \
  -H "Content-Type: application/json" \
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
```

## 测试结果验证

### ✅ 测试成功完成 (2025-10-14 01:56)

**性能指标:**
- **总用时**: 35.43 秒
- **连接时间**: 0.0003 秒
- **响应开始时间**: 11.37 秒
- **HTTP 状态码**: 200

**响应质量验证:**
- ✅ **根因分析**: 识别为慢性虚假告警 (Chronic false positive alert)
- ✅ **预检数据**: 基于10+次历史分析，CPU使用率一致显示7-8%
- ✅ **归因分析**: 
  - 告警声称: 92% CPU使用率
  - 实际使用: 7-8% (VictoriaMetrics数据)
  - 根因: Prometheus监控系统基础设施故障
- ✅ **建议措施**: 
  - 紧急禁用告警规则
  - 升级到监控基础设施团队
  - 实施紧急监控使用VictoriaMetrics
  - 建立监控系统健康验证程序
- ✅ **置信度**: 1.0 (100%置信度)

**历史会话复用验证:**
- ✅ **连接池状态**: 1/2 活跃连接
- ✅ **会话复用**: 相同sop_id请求复用现有连接
- ✅ **历史上下文**: 分析中引用了"10+次历史分析"，确认使用了conversation resume

## 完整测试流程

### 步骤 1: 停止现有服务
```bash
sudo systemctl stop q-gateway || echo "Service not running"
./gateway/stop.sh
```

### 步骤 2: 启动服务
```bash
./gateway/start.sh
```

### 步骤 3: 验证服务健康
```bash
curl -s http://localhost:8081/healthz | jq .
```

### 步骤 4: 执行 sdn5_cpu 测试
```bash
# 使用计时的curl测试
./test_curl_sdn5.sh

# 或使用Python测试脚本
python3 test_sdn5.py
```

### 步骤 5: 检查历史会话复用
```bash
curl -s http://localhost:8081/healthz | jq '.connection_pool'
```

## 预期结果

### 健康检查响应
```json
{
  "ok": true,
  "sop_dir": "/home/ubuntu/huixin/aiops_v2/sop",
  "task_doc": "/home/ubuntu/huixin/aiops_v2/task_instructions.md",
  "qtty": {
    "host": "127.0.0.1",
    "port": 7682
  },
  "connection_pool": {
    "active_connections": 1,
    "max_connections": 2
  }
}
```

### 分析结果包含
- ✅ **tool_calls**: VictoriaMetrics 查询结果
- ✅ **root_cause**: 慢性虚假告警识别
- ✅ **evidence**: 历史分析模式和实际vs声称的CPU使用率
- ✅ **suggested_actions**: 紧急和长期修复建议
- ✅ **confidence**: 1.0 (100%置信度)
- ✅ **analysis_summary**: 关键监控基础设施故障分析

### 连接复用验证
- ✅ 相同 sop_id 请求会复用现有连接
- ✅ 连接池状态显示活跃连接数
- ✅ 历史会话自动恢复 (resume conversation)
- ✅ 分析中引用历史上下文 ("10+次历史分析")
