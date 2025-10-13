#!/usr/bin/env bash
set -euo pipefail

SOP_ID="${1:-}"
if [ -z "$SOP_ID" ]; then
  echo "Usage: $0 <sop_id>" >&2
  exit 1
fi

SESSION_DIR="/srv/q-sessions/${SOP_ID}"
mkdir -p "$SESSION_DIR"
cd "$SESSION_DIR"

# 选择 Q 可执行文件（优先环境变量，其次常见路径，最后 PATH）
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

# 进入会话（可保存/加载，带工具信任）
exec "$Q_CMD" chat --trust-all-tools --resume


