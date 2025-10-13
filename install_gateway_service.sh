#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "[INSTALL] Installing Q Gateway systemd service..."

# Stop existing service if running
sudo systemctl stop q-gateway || true

# Copy service file
sudo cp gateway/q-gateway.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable q-gateway

echo "[INSTALL] Service installed successfully"
echo "[INSTALL] To start: sudo systemctl start q-gateway"
echo "[INSTALL] To check status: sudo systemctl status q-gateway"
echo "[INSTALL] To view logs: sudo journalctl -u q-gateway -f"
