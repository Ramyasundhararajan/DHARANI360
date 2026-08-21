#!/usr/bin/env bash
# Boot script for the Render demo.
# The free plan has no permanent disk, so every start begins with an empty
# instance/ folder. Rather than showing an empty system, seed it: create the
# tables, create the team, then load the sample records.
set -e

echo "==> Preparing the demo database"
python bootstrap.py || echo "    bootstrap reported a problem; continuing"

if [ -f demo_data.py ]; then
  echo "==> Loading demo records"
  python demo_data.py || echo "    demo data reported a problem; continuing"
fi

if [ -f setup_samples.py ]; then
  echo "==> Loading sample chat and call activity"
  python setup_samples.py || echo "    samples reported a problem; continuing"
fi

echo "==> Starting DHARANI 360 on port ${PORT:-5000}"
# One worker, several threads: SQLite is happy with threads in one process
# and unhappy with several processes writing at once.
exec gunicorn app:app \
  --bind "0.0.0.0:${PORT:-5000}" \
  --workers 1 --threads 8 --timeout 120 \
  --access-logfile - --error-logfile -
