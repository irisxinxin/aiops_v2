#!/usr/bin/env bash
set -euo pipefail

# This script starts ttyd (wrapping the local `q` CLI) and the Python Q proxy
# with a warmed WebSocket connection pool. It uses ONLY relative paths so the
# whole folder can be copied to any remote server and run as-is.

# Resolve repository root (the script lives in ./scripts)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

# ---- Config (env-overridable) ----
export Q_HOST="${Q_HOST:-127.0.0.1}"
export Q_PORT="${Q_PORT:-7682}"
export Q_USER="${Q_USER:-demo}"
export Q_PASS="${Q_PASS:-password123}"

export POOL_SIZE="${POOL_SIZE:-1}"
export READY_NEED="${READY_NEED:-1}"

export HTTP_HOST="${HTTP_HOST:-0.0.0.0}"
export HTTP_PORT="${HTTP_PORT:-8080}"

# Relative paths (kept as defaults in qproxy_pool.py)
export SOP_DIR="${SOP_DIR:-./sop}"
export SOP_JSONL_DIR="${SOP_JSONL_DIR:-./sop}"
export SOP_JSONL_FILE="${SOP_JSONL_FILE:-sdn5_sop_full.jsonl}"
export TASK_INSTR_PATH="${TASK_INSTR_PATH:-./task_instructions.md}"
export CONV_DIR="${CONV_DIR:-./conversations}"

# Optional prompt shaping
export QPROXY_TASK_DOC_BUDGET="${QPROXY_TASK_DOC_BUDGET:-2048}"
export QPROXY_ALERT_JSON_PRETTY="${QPROXY_ALERT_JSON_PRETTY:-0}"

# ---- Prepare folders ----
mkdir -p "$CONV_DIR" "$SOP_DIR" ./logs

# ---- Python venv + deps ----
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -U pip >/dev/null
python -m pip install fastapi "uvicorn[standard]" "git+https://github.com/aleck31/terminal-api-for-qcli@master"

# ---- Check ttyd availability ----
if ! command -v ttyd >/dev/null 2>&1; then
  echo "[ERROR] ttyd not found. Please install ttyd (e.g., brew install ttyd or apt install ttyd)." >&2
  exit 1
fi

# ---- Start ttyd (if not listening) ----
is_port_open() {
  # Try nc; fallback to bash /dev/tcp
  if command -v nc >/dev/null 2>&1; then
    nc -z "$Q_HOST" "$Q_PORT" >/dev/null 2>&1
  else
    (echo > /dev/tcp/$Q_HOST/$Q_PORT) >/dev/null 2>&1 || return 1
  fi
}

if ! is_port_open; then
  echo "[INFO] Starting ttyd on :$Q_PORT ..."
  nohup ttyd --ping-interval 25 -p "$Q_PORT" -c "$Q_USER:$Q_PASS" q \
    > ./logs/ttyd.out 2>&1 & echo $! > ./logs/ttyd.pid
  sleep 1
else
  echo "[INFO] ttyd already listening on :$Q_PORT, skipping start"
fi

# ---- Start Python Q proxy ----
echo "[INFO] Starting Q proxy on ${HTTP_HOST}:${HTTP_PORT} ..."
nohup python qproxy_pool.py > ./logs/qproxy.out 2>&1 & echo $! > ./logs/qproxy.pid

cat <<EOF
[OK] Processes started.
    ttyd PID:   
      - \
        \$(test -f ./logs/ttyd.pid && cat ./logs/ttyd.pid || echo "(external or no pid)")
    qproxy PID: \
      - \
        \$(cat ./logs/qproxy.pid)

Health checks:
  curl -sS http://127.0.0.1:${HTTP_PORT}/healthz
  curl -sS http://127.0.0.1:${HTTP_PORT}/readyz

Test with local alert JSON:
  jq -c '{alert:.}' ./sdn5_cpu.json | curl -sS -X POST 'http://127.0.0.1:${HTTP_PORT}/call' -H 'Content-Type: application/json' --data-binary @-

Stop:
  kill \$(cat ./logs/qproxy.pid 2>/dev/null || echo) || true
  kill \$(cat ./logs/ttyd.pid 2>/dev/null || echo) || true
EOF


