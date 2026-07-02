#!/bin/bash
# Run this once on the VPS after SSH-ing in.
# Target: Ubuntu 24.04 on IONOS. Also keeps basic AlmaLinux/RHEL support.
# Usage: bash deploy/deploy.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "$PROJECT_DIR" != "/root/trading-ai" ]; then
    echo "This deployment expects the repo at /root/trading-ai."
    echo "Run: git clone https://github.com/kaianbenitez/crypto-trading-ai.git /root/trading-ai"
    echo "Then: cd /root/trading-ai && bash deploy/deploy.sh"
    exit 1
fi

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
    apt-get install -y ca-certificates curl gnupg python3 python3-venv python3-pip rsync

    if ! command -v node &>/dev/null || ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' 2>/dev/null; then
        install -d -m 0755 /etc/apt/keyrings
        curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
            | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
        echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
            > /etc/apt/sources.list.d/nodesource.list
        apt-get update -qq
        apt-get install -y nodejs
    fi
else
    dnf install -y python3 python3-pip nodejs npm curl rsync
fi

echo "=== Runtime versions ==="
python3 --version
node --version
npm --version

echo "=== Python virtualenv + deps ==="
cd "$PROJECT_DIR"
python3 -m venv venv
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q

echo "=== Next.js frontend build ==="
cd "$PROJECT_DIR/web"
npm ci --silent
npm run build

echo "=== Systemd services ==="
cp "$PROJECT_DIR/deploy/trading-agent.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/webapi.service"        /etc/systemd/system/
cp "$PROJECT_DIR/deploy/dashboard.service"     /etc/systemd/system/
systemctl daemon-reload
systemctl enable trading-agent webapi dashboard
systemctl restart dashboard

if [ -f "$PROJECT_DIR/.env" ]; then
    systemctl restart webapi trading-agent
else
    echo "WARNING: $PROJECT_DIR/.env is missing. Create it, then run:"
    echo "  systemctl restart webapi trading-agent"
fi

echo ""
echo "=== Done ==="
echo "Check status:  systemctl status trading-agent webapi dashboard"
echo "Live logs:     journalctl -u trading-agent -f"
echo "Dashboard:     http://$(curl -s ifconfig.me):3000"
