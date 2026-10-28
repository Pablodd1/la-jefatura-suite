#!/usr/bin/env bash
# ==============================================================================
# La Jefatura Suite — 1-Command Hostinger VPS (Ubuntu 22.04 / 24.04) Installer
#
# Usage on your Hostinger KVM VPS (as root):
#   bash deploy/install_hostinger_vps.sh ceo.yourdomain.com
#
# What it does:
#   1. Installs Python 3, venv, ffmpeg, and Caddy (automatic Let's Encrypt HTTPS).
#   2. Clones or updates /opt/la-jefatura-suite and installs Python dependencies.
#   3. Creates /opt/la-jefatura-suite/.env from .env.example if not present.
#   4. Registers and starts systemd service `lajefatura.service` (auto-restarts 24/7).
#   5. Configures Caddy reverse proxy on port 80/443 -> 127.0.0.1:8931 with auto SSL.
# ==============================================================================
set -euo pipefail

DOMAIN="${1:-}"
APP_DIR="/opt/la-jefatura-suite"
REPO_URL="https://github.com/Pablodd1/la-jefatura-suite.git"

echo "==> [1/5] Installing system packages (Python 3, ffmpeg, git, Caddy)..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip ffmpeg git curl debian-keyring debian-archive-keyring apt-transport-https

if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

echo "==> [2/5] Setting up repository at ${APP_DIR}..."
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" pull origin master
else
  git clone "${REPO_URL}" "${APP_DIR}"
fi

mkdir -p "${APP_DIR}/data" "${APP_DIR}/data/camera_reports"

echo "==> [3/5] Creating Python virtual environment and installing requirements..."
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [ ! -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
  echo "    Created ${APP_DIR}/.env from template. Edit it with: nano ${APP_DIR}/.env"
fi

echo "==> [4/5] Configuring systemd service (lajefatura.service)..."
cat >/etc/systemd/system/lajefatura.service <<EOF
[Unit]
Description=La Jefatura Suite — CEO Mission Control & AI Super Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PYTHONIOENCODING=utf-8
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/scripts/demo_server.py 8931
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable lajefatura.service
systemctl restart lajefatura.service

echo "==> [5/5] Configuring HTTPS reverse proxy (Caddy)..."
if [ -n "${DOMAIN}" ]; then
  cat >/etc/caddy/Caddyfile <<EOF
${DOMAIN} {
    encode gzip
    reverse_proxy 127.0.0.1:8931
}
EOF
  systemctl enable caddy
  systemctl restart caddy
  echo "=============================================================================="
  echo "✅ LA JEFATURA SUITE DEPLOYED SUCCESSFULLY!"
  echo "   Public HTTPS URL: https://${DOMAIN}/?key=mc-demo-2026-x9f4"
  echo "   Website Deck URL: https://${DOMAIN}/website?key=mc-demo-2026-x9f4"
  echo "   Meta Webhook URL: https://${DOMAIN}/api/whatsapp/webhook"
  echo "   Edit variables  : nano ${APP_DIR}/.env && systemctl restart lajefatura"
  echo "=============================================================================="
else
  echo "=============================================================================="
  echo "✅ LA JEFATURA SERVICE RUNNING ON 127.0.0.1:8931"
  echo "   To enable automatic HTTPS on your Hostinger domain, re-run with domain:"
  echo "   bash ${APP_DIR}/deploy/install_hostinger_vps.sh ceo.yourdomain.com"
  echo "=============================================================================="
fi
