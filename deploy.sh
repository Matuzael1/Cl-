#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

python3 -m venv .venv || true
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

sudo cp systemd/blackwoves.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart blackwoves
sudo nginx -t
sudo systemctl reload nginx
