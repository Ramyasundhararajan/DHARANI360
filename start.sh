#!/usr/bin/env bash
# DHARANI 360 launcher for macOS / Linux
set -e
cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "Python 3 was not found on this computer. Please install it from https://www.python.org/downloads/ and run this script again."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Setting up DHARANI 360 for the first time - this only happens once..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "Starting DHARANI 360..."
echo "Open this address in your browser: http://127.0.0.1:5000"
echo "Press Ctrl+C to stop."
echo ""

( sleep 1.5 && (open http://127.0.0.1:5000 2>/dev/null || xdg-open http://127.0.0.1:5000 2>/dev/null || true) ) &
python3 app.py
