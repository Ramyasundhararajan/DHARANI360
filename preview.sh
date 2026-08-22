#!/usr/bin/env bash
# DHARANI 360 - open a preview with sample data.
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then exec .venv/bin/python preview.py "$@"; fi
exec python3 preview.py "$@"
