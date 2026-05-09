#!/usr/bin/env bash
# Always uses this folder's venv so uvicorn matches `pip install -r requirements.txt`.
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Create the venv first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
exec .venv/bin/python -m uvicorn main:app --reload "$@"
