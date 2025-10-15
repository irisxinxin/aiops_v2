#!/usr/bin/env bash
set -euo pipefail

# 获取 sop_id：优先 argv，其次 QUERY_STRING 中的 arg=，最后 default
SOP_ID="${1:-}"
if [ -z "$SOP_ID" ] && [ -n "${QUERY_STRING:-}" ]; then
  ARG_PART="$(printf '%s' "$QUERY_STRING" | tr '&' '\n' | grep -m1 '^arg=')" || true
  SOP_ID="${ARG_PART#arg=}"
fi
SOP_ID="${SOP_ID:-default}"

# 统一使用仓库下的 q-sessions/<sop_id>
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_DIR="${PROJECT_DIR}/q-sessions/${SOP_ID}"
mkdir -p "$SESSION_DIR"
cd "$SESSION_DIR"

# 写入探测，避免只读导致崩溃
touch .q_rw_test || { echo "CWD is read-only: $PWD" >&2; exit 30; }
rm -f .q_rw_test || true

# 选择 Q 可执行文件（可被环境 Q_CMD 覆盖）
Q_CMD="${Q_CMD:-}"
if [ -z "$Q_CMD" ]; then
  if [ -x "/home/ubuntu/.local/bin/q" ]; then
    Q_CMD="/home/ubuntu/.local/bin/q"
  elif [ -x "/usr/local/bin/q" ]; then
    Q_CMD="/usr/local/bin/q"
  elif command -v q >/dev/null 2>&1; then
    Q_CMD="$(command -v q)"
  else
    echo "[ERROR] Amazon Q CLI (q) not found. Set Q_CMD or install q." >&2
    exit 1
  fi
fi

# 会话日志目录（便于线上排障）
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
echo "[q_entry] sop_id=$SOP_ID session_dir=$SESSION_DIR q_cmd=$Q_CMD" >> "$LOG_DIR/q_entry.log"

# 启动会话（工具信任，自动续会话）并记录日志
exec "$Q_CMD" chat --trust-all-tools --resume >>"$LOG_DIR/q_${SOP_ID}.out" 2>&1

