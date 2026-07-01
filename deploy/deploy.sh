#!/bin/bash
# Run this once on the IONOS VPS after SSH-ing in.
# Usage: bash deploy/deploy.sh
set -e

PROJECT_DIR="/home/ubuntu/trading-ai"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Installing system deps ==="
sudo apt-get update -qq
sudo apt-get install -y python3.11 python3.11-venv python3-pip nodejs npm

echo "=== Copying project files ==="
sudo mkdir -p "$PROJECT_DIR"
sudo rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='node_modules' --exclude='.next' \
    "$REPO_DIR/" "$PROJECT_DIR/"
sudo chown -R ubuntu:ubuntu "$PROJECT_DIR"

echo "=== Python virtualenv + deps ==="
cd "$PROJECT_DIR"
python3.11 -m venv venv
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q

echo "=== Next.js frontend build ==="
cd "$PROJECT_DIR/web"
npm install --silent
npm run build

echo "=== Systemd services ==="
sudo cp "$PROJECT_DIR/deploy/trading-agent.service" /etc/systemd/system/
sudo cp "$PROJECT_DIR/deploy/webapi.service"        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading-agent webapi
sudo systemctl start  trading-agent webapi

echo ""
echo "=== Done ==="
echo "Check status:  sudo systemctl status trading-agent webapi"
echo "Live logs:     sudo journalctl -u trading-agent -f"
echo "Dashboard:     http://$(curl -s ifconfig.me):3000"
