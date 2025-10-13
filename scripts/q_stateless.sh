#!/usr/bin/env bash
set -euo pipefail
if [ -t 0 ]; then
  # Interactive mode - read from stdin
  while IFS= read -r line; do
    q chat --no-interactive --trust-all-tools -- "$line" || true
  done
else
  # Non-interactive mode - read all input at once
  input=$(cat)
  if [ -n "$input" ]; then
    q chat --no-interactive --trust-all-tools -- "$input" || true
  fi
fi
