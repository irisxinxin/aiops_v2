# Gateway服务测试总结

## 修复的Bug

### 1. mapping.py中的incident_key生成bug
- **问题**: 没有从metadata中获取alertname和group_id
- **修复**: 优先从metadata获取更准确的信息
- **代码位置**: `/home/ubuntu/huixin/aiops_v2/gateway/mapping.py`

### 2. app.py中的incident_key回写bug  
- **问题**: 生成的incident_key没有存回payload供后续使用
- **修复**: 将生成的incident_key存回payload
- **代码位置**: `/home/ubuntu/huixin/aiops_v2/gateway/app.py`

## 添加的systemd保护

### 资源限制配置
- **CPU限制**: 80% (CPUQuota=80%)
- **内存限制**: 最大1G (MemoryMax=1G)
- **内存高水位**: 800M (MemoryHigh=800M)  
- **任务数限制**: 100 (TasksMax=100)

### 服务配置文件
- **位置**: `/etc/systemd/system/q-gateway.service`
- **状态**: 已启用并运行
- **自动重启**: 5秒重启间隔

## 测试结果

### 1. 健康检查 ✅
```json
{
  "ok": true,
  "sop_dir": "/home/ubuntu/huixin/aiops_v2/sop",
  "task_doc": "/home/ubuntu/huixin/aiops_v2/task_instructions.md",
  "qtty": {
    "host": "127.0.0.1",
    "port": 7682
  }
}
```

### 2. incident_key生成测试 ✅
- **生成的incident_key**: `sdn5_cpu_critical_dev-nbu-aps1_sdn5 container CPU usage is too high_sdn5_critical-4d5bc8b4cd`
- **生成的sop_id**: `sdn5_cpu_critical_dev-nbu-aps1_sdn5-container-cpu-usage-is-too-high_sdn5_critical-4d5bc8b4cd`
- **resolve_sop_id功能**: 正常工作

### 3. API调用测试 ✅
- **端点**: `POST /ask`
- **输入**: sdn5_cpu.json作为alert参数
- **输出**: 正常的SSE流式响应
- **响应时间**: < 15秒

### 4. systemd服务状态 ✅
- **服务状态**: active (running)
- **资源限制**: 已生效
  - CPUQuotaPerSecUSec=800ms
  - MemoryMax=1073741824 (1G)
  - MemoryHigh=838860800 (800M)
  - TasksMax=100

## 服务信息

- **HTTP端口**: 8081
- **QTTY端口**: 7682
- **工作目录**: `/home/ubuntu/huixin/aiops_v2`
- **虚拟环境**: `.venv`
- **日志目录**: `logs/`

## 使用方法

### 启动/停止服务
```bash
sudo systemctl start q-gateway.service
sudo systemctl stop q-gateway.service
sudo systemctl restart q-gateway.service
```

### 查看服务状态
```bash
sudo systemctl status q-gateway.service
```

### 测试API
```bash
curl -X POST "http://127.0.0.1:8081/ask" \
    -H "Content-Type: application/json" \
    -d '{"text": "分析这个CPU告警", "alert": {...}}'
```

## 测试脚本

- `test_gateway.sh`: 基础gateway测试
- `test_incident_key.py`: incident_key生成测试  
- `test_complete.sh`: 完整功能测试

所有测试均通过 ✅
