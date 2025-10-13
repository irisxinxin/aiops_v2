#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../logs"
PID_FILE="${LOG_DIR}/ttyd.pid"
LOG_FILE="${LOG_DIR}/ttyd.out"

mkdir -p "$LOG_DIR"

# Kill existing ttyd if running
if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping existing ttyd (PID: $OLD_PID)"
        kill "$OLD_PID"
        sleep 2
    fi
    rm -f "$PID_FILE"
fi

# Start ttyd with q_stateless.sh
echo "Starting ttyd with q_stateless.sh..."
nohup ttyd -p 7681 -W "${SCRIPT_DIR}/q_stateless.sh" > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "ttyd started with PID: $(cat "$PID_FILE")"
echo "Access at: http://localhost:7681"
echo "Logs: $LOG_FILE"
