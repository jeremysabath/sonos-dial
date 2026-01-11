#!/bin/bash
# Deploy sonos-dial to Raspberry Pi

set -e

# Load environment variables from .env if it exists
if [ -f "$(dirname "$0")/.env" ]; then
    set -a
    source "$(dirname "$0")/.env"
    set +a
fi

PI_HOST="${PI_HOST:?Error: PI_HOST not set. Copy .env.example to .env and configure.}"
PI_USER="${PI_USER:?Error: PI_USER not set. Copy .env.example to .env and configure.}"
PI_PATH="${PI_PATH:?Error: PI_PATH not set. Copy .env.example to .env and configure.}"

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
    ./.env \
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
