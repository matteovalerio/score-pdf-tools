#!/usr/bin/env bash
# wedding·lifeboat — start script
set -e
cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing dependencies…"
pip install -q -r requirements.txt

echo
echo "  wedding·lifeboat is running →  http://localhost:8000"
echo "  (Ctrl+C to stop)"
echo
exec uvicorn app:app --host 0.0.0.0 --port 8000
