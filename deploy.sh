#!/bin/bash
# Deploy sonos-dial to Raspberry Pi

set -e

PI_HOST="${PI_HOST:-pi-zero.local}"
PI_USER="${PI_USER:-jeremysabath}"
PI_PATH="${PI_PATH:-/home/jeremysabath/sonos-dial}"

echo "Deploying to ${PI_USER}@${PI_HOST}:${PI_PATH}"

# Sync files (excluding venv, pycache, etc.)
rsync -avz --delete \
    --exclude '__pycache__' \
    --exclude '.venv' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude '.DS_Store' \
    ./src/ \
    ./requirements.txt \
    ./sonos-dial.service \
    "${PI_USER}@${PI_HOST}:${PI_PATH}/"

echo "Done! Files synced to Pi."
echo ""
echo "Next steps on the Pi:"
echo "  ssh ${PI_USER}@${PI_HOST}"
echo "  cd ${PI_PATH}"
echo "  python3 -m venv .venv"
echo "  source .venv/bin/activate"
echo "  pip install -r requirements.txt"
echo "  python main.py  # test manually"
