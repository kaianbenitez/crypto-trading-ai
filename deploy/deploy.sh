#!/bin/bash
# Run this once on the VPS after SSH-ing in.
# Supports: Ubuntu (apt) and AlmaLinux/RHEL (dnf)
# Usage: bash deploy/deploy.sh
set -e

PROJECT_DIR="/root/trading-ai"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Detecting OS ==="
if command -v apt-get &>/dev/null; then
    PKG="apt"
    echo "  Ubuntu/Debian detected"
elif command -v dnf &>/dev/null; then
    PKG="dnf"
    echo "  AlmaLinux/RHEL detected"
else
    echo "Unsupported OS"; exit 1
fi

echo "=== Installing system deps ==="
if [ "$PKG" = "apt" ]; then
    apt-get update -qq
    apt-get install -y python3.11 python3.11-venv python3-pip nodejs npm curl
else
    dnf install -y python3.11 python3-pip nodejs npm curl
fi

echo "=== Setting up project ==="
mkdir -p "$PROJECT_DIR"
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='node_modules' --exclude='.next' \
    "$REPO_DIR/" "$PROJECT_DIR/"

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
cp "$PROJECT_DIR/deploy/trading-agent.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/webapi.service"        /etc/systemd/system/
systemctl daemon-reload
systemctl enable trading-agent webapi
systemctl start  trading-agent webapi

echo ""
echo "=== Done ==="
echo "Check status:  systemctl status trading-agent webapi"
echo "Live logs:     journalctl -u trading-agent -f"
echo "Dashboard:     http://$(curl -s ifconfig.me):3000"
