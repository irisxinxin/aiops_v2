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


