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

# Start ttyd (loopback only, no auth, heartbeat)
nohup ttyd --ping-interval 55 -p "$QTTY_PORT" --writable --interface 127.0.0.1 q \
  > ./logs/ttyd.gateway.out 2>&1 & echo $! > ./logs/ttyd.gateway.pid

# Start FastAPI app
exec python3 -m uvicorn gateway.app:app --host 0.0.0.0 --port "$HTTP_PORT" --log-level info


