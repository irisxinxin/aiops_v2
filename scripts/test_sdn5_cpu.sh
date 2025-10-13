#!/usr/bin/env bash
set -euo pipefail

# Simple end-to-end test script for sdn5_cpu.json
# - Starts ttyd (no-auth, writable) on port 7682 with ping interval 25
# - Starts the Python proxy
# - Waits until ready
# - Posts sdn5_cpu.json to /call and prints the response

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

# ------- Config (env-overridable) -------
export Q_HOST="${Q_HOST:-127.0.0.1}"
export Q_PORT="${Q_PORT:-7682}"
export Q_USER="${Q_USER:-}"
export Q_PASS="${Q_PASS:-}"

export POOL_SIZE="${POOL_SIZE:-1}"
export READY_NEED="${READY_NEED:-0}"
export WARMUP_DELAY_MS="${WARMUP_DELAY_MS:-500}"

export HTTP_HOST="${HTTP_HOST:-127.0.0.1}"
export HTTP_PORT="${HTTP_PORT:-8080}"
export REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-300}"

# Relative paths
export SOP_DIR="${SOP_DIR:-./sop}"
export SOP_JSONL_DIR="${SOP_JSONL_DIR:-./sop}"
export SOP_JSONL_FILE="${SOP_JSONL_FILE:-sdn5_sop_full.jsonl}"
export TASK_INSTR_PATH="${TASK_INSTR_PATH:-./task_instructions.md}"
export CONV_DIR="${CONV_DIR:-./conversations}"

mkdir -p "$CONV_DIR"

# ------- Start ttyd (no-auth, writable) -------
if ! pgrep -f "ttyd .* -p ${Q_PORT}" >/dev/null 2>&1; then
  echo "[TEST] Starting ttyd (no-auth, writable) on :${Q_PORT} ..."
  nohup ttyd --ping-interval 25 -p ${Q_PORT} --writable q > ttyd.log 2>&1 & echo $! > ttyd.pid
  sleep 1
else
  echo "[TEST] ttyd already running on :${Q_PORT}"
fi

# ------- Start proxy -------
if ! pgrep -f "python .*qproxy_pool.py" >/dev/null 2>&1; then
  echo "[TEST] Starting qproxy_pool.py on ${HTTP_HOST}:${HTTP_PORT} ..."
  nohup python qproxy_pool.py > qproxy_test.log 2>&1 & echo $! > qproxy_test.pid
  sleep 1
else
  echo "[TEST] qproxy_pool.py already running"
fi

# ------- Wait until ready -------
echo "[TEST] Waiting proxy ready ..."
for i in {1..60}; do
  st=$(curl -sS --max-time 2 "http://${HTTP_HOST}:${HTTP_PORT}/readyz" || true)
  if [ "$st" = "ok" ]; then
    echo "[TEST] Proxy ready"
    break
  fi
  sleep 1
  if [ $i -eq 60 ]; then
    echo "[WARN] Proxy not ready after 60s, continue anyway"
  fi
done

# ------- Call with sdn5_cpu.json -------
echo "[TEST] Posting sdn5_cpu.json to /call ..."
if command -v jq >/dev/null 2>&1; then
  jq -c '{alert:.}' ./sdn5_cpu.json \
  | curl -sS -X POST "http://${HTTP_HOST}:${HTTP_PORT}/call" -H 'Content-Type: application/json' --data-binary @- | tee /dev/stderr
else
  python - <<'PY' | curl -sS -X POST "http://${HTTP_HOST}:${HTTP_PORT}/call" -H 'Content-Type: application/json' --data-binary @- | tee /dev/stderr
import json
print(json.dumps({"alert": json.load(open("sdn5_cpu.json","r"))}, ensure_ascii=False))
PY
fi

echo "[TEST] Done. PIDs: ttyd=$(cat ttyd.pid 2>/dev/null || echo -), qproxy=$(cat qproxy_test.pid 2>/dev/null || echo -)"
echo "[TEST] Stop with: kill \
  \$(cat qproxy_test.pid 2>/dev/null || echo) || true; \
  kill \
  \$(cat ttyd.pid 2>/dev/null || echo) || true"


