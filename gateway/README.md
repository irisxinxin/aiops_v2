## Q Gateway（SSE）

功能：
- 解析 `sop_id`（优先级：sop_id > incident_key > alert）
- 构建 Prompt：`TASK` + `SOP(<sop_id>)` + `ALERT JSON` + `USER`
- 每次 HTTP 调用临时连接 ttyd（`q chat --trust-all-tools --resume`），流式返回（SSE）
- 会话按 `sop_id` 隔离（容器内 `/srv/q-sessions/<sop_id>/`）

环境变量：
- `SOP_DIR`（默认 `/app/aiops/sop`）
- `TASK_DOC_PATH`（默认 `/app/aiops/task_instructions.md`）
- `TASK_DOC_BUDGET`（默认 131072 字节）
- `QTTY_PORT`（默认 7682）
- `HTTP_PORT`（默认 8081）

### 部署与重启（oneclick，唯一入口）

强烈建议使用一键脚本作为唯一的部署与重启入口，脚本将自动处理依赖安装、systemd 单元安装/路径修正、环境变量注入（systemd drop-in）与健康检查：

```bash
# 可选：在执行前按需覆盖关键参数（也可不设，使用脚本默认值）
export INIT_READY_TIMEOUT=12
export WARMUP_SLEEP=20
export Q_OVERALL_TIMEOUT=45
export QTTY_HOST=127.0.0.1
export QTTY_PORT=7682
export HTTP_HOST=0.0.0.0
export HTTP_PORT=8081

# 一键部署/重启（唯一入口）
bash scripts/oneclick_gateway.sh

# 查看服务状态与日志
sudo systemctl status q-gateway --no-pager
sudo journalctl -u q-gateway -f
```

脚本能力：
- 禁用并停止旧的 `aiops-qproxy.service`（如存在）
- 准备 `q-sessions` 与 `logs` 目录并授予权限
- 创建/激活 `.venv` 并安装依赖（含 `stransi`）
- 安装 `gateway/q-gateway.service` 到 systemd，并将仓库路径重写为当前目录
- 通过 systemd drop-in `/etc/systemd/system/q-gateway.service.d/override.conf` 注入上述环境变量
- 重载 systemd、重启服务并进行健康检查

### 测试与日志

```bash
# 健康检查
curl -sf http://127.0.0.1:8081/healthz && echo OK || echo FAIL

# 发送示例请求（alert 路径）
curl -s -X POST http://127.0.0.1:8081/ask_json \
  -H 'Content-Type: application/json' \
  -d '{"alert":{"service":"sdn5","category":"network","severity":"critical","region":"aps1","title":"sdn5 container CPU usage is too high","metadata":{"group_id":"sdn5_critical"}}}' | jq .

# 查看服务日志
sudo journalctl -u q-gateway -f

# 查看 q 会话日志（按 sop_id）
ls -lh logs/q_*.out | tail -n 5
tail -n 200 -f logs/q_511470.out
```

### Docker 运行

在工程根（能看到 `aiops/` 与 `gateway/`）执行：

```bash
mkdir -p bin && cp "$(which q)" bin/q
docker build -f gateway/Dockerfile -t q-gateway .
docker run --rm --name q-gateway \
  -p 8081:8081 \
  -v "$PWD/q-sessions:/srv/q-sessions" \
  -v "$PWD/bin/q:/usr/local/bin/q:ro" \
  --memory=512m --cpus="0.75" \
  q-gateway
```

或使用 compose：

```bash
docker compose -f gateway/docker-compose.yml up -d --build
```

### API（SSE）

`POST /ask`，Body（任一字段可选）：`sop_id`、`incident_key`、`alert`、`text`。

示例：

```bash
curl -N -H "Content-Type: application/json" \
  -d '{"incident_key":"omada_network_high_ap_sg","text":"继续：把对账步骤列清单"}' \
  http://127.0.0.1:8081/ask
```

```bash
curl -N -H "Content-Type: application/json" \
  -d '{"alert":{"service":"omada","category":"network","severity":"high","region":"sg"},"text":"继续：复盘根因"}' \
  http://127.0.0.1:8081/ask
```

```bash
curl -N -H "Content-Type: application/json" \
  -d '{"sop_id":"omada-network-high-sg-1a2b3c4d5e","text":"保存：/save ./conv.json -f"}' \
  http://127.0.0.1:8081/ask
```

注意：`text` 以 `/` 开头时（例如 `/save`、`/load`），不拼接 `TASK/SOP/ALERT`，直接透传。


