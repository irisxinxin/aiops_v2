# Q Gateway Service

## 概述
Q Gateway 是一个基于 FastAPI 的服务，用于处理告警分析请求并通过 Q CLI 提供智能分析结果。

## 功能特性
- ✅ 告警数据分析和根因识别
- ✅ 连接池管理，支持并发请求
- ✅ 流式响应，实时返回分析进度
- ✅ SOP 文档自动匹配和加载
- ✅ 结构化分析结果输出

## 服务状态
- **Gateway API**: http://127.0.0.1:8081
- **健康检查**: http://127.0.0.1:8081/healthz
- **TTYD 终端**: 127.0.0.1:7682

## 快速开始

### 部署与重启（唯一入口：oneclick）
```bash
# 可选：覆盖关键参数（也可直接跳过使用默认值）
export INIT_READY_TIMEOUT=12
export WARMUP_SLEEP=20
export Q_OVERALL_TIMEOUT=45
export QTTY_HOST=127.0.0.1
export QTTY_PORT=7682
export HTTP_HOST=0.0.0.0
export HTTP_PORT=8081

# 一键部署/重启（唯一入口）
bash scripts/oneclick_gateway.sh

# 查看服务状态
sudo systemctl status q-gateway --no-pager

# 查看服务日志
sudo journalctl -u q-gateway -f
```

> 说明：不再推荐直接调用 `gateway/start.sh`/`stop.sh` 或其它旧脚本；请统一使用 `scripts/oneclick_gateway.sh` 管理服务生命周期。

### 测试与日志

```bash
# 健康检查
curl -sf http://127.0.0.1:8081/healthz && echo OK || echo FAIL

# 示例请求（alert 路径，最小字段集）
curl -s -X POST http://127.0.0.1:8081/ask_json \
  -H 'Content-Type: application/json' \
  -d '{"alert":{"service":"sdn5","category":"network","severity":"critical","region":"aps1","title":"sdn5 container CPU usage is too high","metadata":{"group_id":"sdn5_critical"}}}' | jq .

# 查看 systemd 服务日志
sudo journalctl -u q-gateway -f

# 查看 q 会话日志
ls -lh logs/q_*.out | tail -n 5
```

### 测试服务
```bash
# 完整功能测试
./test_complete_api.sh

# 测试 sdn5_cpu.json 分析
python3 test_sdn5.py
```

## API 使用

### 分析告警
```bash
curl -X POST http://localhost:8081/ask \
  -H "Content-Type: application/json" \
  -d '{
    "text": "分析这个CPU告警，给出根因分析和解决建议",
    "alert": {...}  # 告警数据
  }'
```

### 健康检查
```bash
curl http://localhost:8081/healthz
```

## 分析结果格式

服务返回结构化的分析结果，包含：

- **tool_calls**: 执行的工具调用和结果
- **root_cause**: 根因分析
- **evidence**: 支持证据
- **suggested_actions**: 建议措施
- **confidence**: 置信度
- **analysis_summary**: 分析摘要

## 文件结构

```
├── gateway/
│   ├── app.py              # 主应用程序
│   ├── mapping.py          # 告警映射逻辑
│   ├── start.sh           # 启动脚本
│   ├── stop.sh            # 停止脚本
│   ├── q_entry.sh         # Q CLI 入口脚本
│   └── q-gateway.service  # systemd 服务配置
├── api/                   # API 客户端和连接池
├── sop/                   # SOP 文档目录
├── sdn5_cpu.json         # 测试用告警数据
├── test_sdn5.py          # 测试脚本
├── test_complete_api.sh  # 完整测试脚本
└── install_gateway_service.sh  # 服务安装脚本
```

## 环境变量

- `SOP_DIR`: SOP 文档目录 (默认: ./sop)
- `TASK_DOC_PATH`: 任务文档路径 (默认: ./task_instructions.md)
- `QTTY_HOST`: Q CLI 主机 (默认: 127.0.0.1)
- `QTTY_PORT`: Q CLI 端口 (默认: 7682)
- `ALERT_JSON_PRETTY`: 告警 JSON 格式化 (默认: 1)

## 系统服务管理

```bash
# 查看服务状态
sudo systemctl status q-gateway

# 查看服务日志
sudo journalctl -u q-gateway -f

# 重启服务
sudo systemctl restart q-gateway
```

## 故障排除

1. **服务无法启动**: 检查虚拟环境是否激活，依赖是否安装
2. **连接超时**: 检查 Q CLI 是否正常运行，端口是否被占用
3. **分析结果异常**: 检查 SOP 文档和任务指令是否正确配置

## 测试验证

服务已通过 sdn5_cpu.json 测试验证，能够：
- ✅ 正确识别虚假告警
- ✅ 提供详细的根因分析
- ✅ 给出具体的修复建议
- ✅ 返回结构化的分析结果
