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

# 进入会话（可保存/加载，带工具信任）
exec q chat --trust-all-tools --resume


