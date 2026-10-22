#!/usr/bin/env bash
# One-time setup on the cloud VM. Run from inside the uploaded ctn-bot folder:
#   bash deploy/setup_vm.sh
# Installs Python packages, then runs bot.py as a systemd service that starts on boot
# and restarts itself if it crashes. Safe to re-run after uploading new code.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR=$(pwd)

for f in .env accounts.json bot.py; do
    [ -f "$f" ] || { echo "missing $f: upload it into $DIR first"; exit 1; }
done
grep -q '^DRY_RUN=0' .env || echo "WARNING: .env doesn't say DRY_RUN=0, so the bot will NOT post"

sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

sudo tee /etc/systemd/system/ctn-bot.service >/dev/null <<EOF
[Unit]
Description=CTN 2026 team bot
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python bot.py
Restart=always
RestartSec=20
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable ctn-bot
sudo systemctl restart ctn-bot
sleep 8
systemctl --no-pager status ctn-bot | head -12
echo
echo "Live logs:   journalctl -u ctn-bot -f"
echo "Restart:     sudo systemctl restart ctn-bot"
echo "Stop:        sudo systemctl stop ctn-bot"
