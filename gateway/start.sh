#!/usr/bin/env bash
set -euo pipefail

# Ports
HTTP_PORT="${HTTP_PORT:-8081}"
QTTY_PORT="${QTTY_PORT:-7682}"

# Clean up ports best-effort
kill_port(){
  local p="$1"
  (ss -ltnp 2>/dev/null | grep ":$p ") || true
  if lsof -iTCP:"$p" -sTCP:LISTEN -t >/dev/null 2>&1; then
    lsof -iTCP:"$p" -sTCP:LISTEN -t | xargs -r kill -9 || true
  fi
}

mkdir -p logs
kill_port "$QTTY_PORT" || true
kill_port "$HTTP_PORT" || true

run_as_ubuntu() {
  local cmd="$1"
  if id -u ubuntu >/dev/null 2>&1; then
    if [ "$(id -un)" != "ubuntu" ] && command -v sudo >/dev/null 2>&1; then
      # 以 ubuntu 身份执行，并设置 HOME
      sudo -u ubuntu -H env HOME=/home/ubuntu bash -lc "$cmd"
      return $?
    fi
  fi
  bash -lc "$cmd"
}

# Start ttyd (loopback only, no auth, heartbeat) as ubuntu when possible
run_as_ubuntu "nohup ttyd --ping-interval 55 -p '$QTTY_PORT' --writable --interface 127.0.0.1 bash gateway/q_entry.sh > ./logs/ttyd.gateway.out 2>&1 & echo \$! > ./logs/ttyd.gateway.pid"

# Start FastAPI app
# Run API as ubuntu when possible
run_as_ubuntu "exec python3 -m uvicorn gateway.app:app --host 0.0.0.0 --port '$HTTP_PORT' --log-level info"


