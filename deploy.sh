#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

.venv/bin/pip install -r requirements.txt
sudo -n /usr/bin/systemctl restart blackwolves
