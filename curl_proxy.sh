#!/bin/bash

# Curl-friendly proxy for Q Gateway
# Usage: ./curl_proxy.sh '{"text": "...", "alert": {...}}'

if [ $# -eq 0 ]; then
    echo "Usage: $0 '<json_request>'"
    echo "Example: $0 '{\"text\": \"分析告警\", \"alert\": {...}}'"
    exit 1
fi

# Create temp file
TEMP_FILE=$(mktemp)
echo "$1" > "$TEMP_FILE"

# Process request and cleanup
python3 simple_proxy.py "$TEMP_FILE"
rm -f "$TEMP_FILE"
