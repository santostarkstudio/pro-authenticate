#!/bin/sh
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null
. .venv/bin/activate
pip install -q -r backend/requirements.txt
python scripts/run_local.py "$@"
