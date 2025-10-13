#!/usr/bin/env bash
set -euo pipefail

# 从 URL 参数获取 sop_id (ttyd 会将 ?arg=value 作为第一个参数传递)
# 如果没有参数，使用 default
SOP_ID="${1:-default}"

SESSION_DIR="/home/ubuntu/huixin/aiops_v2/q-sessions/${SOP_ID}"
mkdir -p "$SESSION_DIR"
cd "$SESSION_DIR"

# 选择 Q 可执行文件
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

