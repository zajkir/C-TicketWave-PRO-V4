#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
if [ "${CTW_HOST:-127.0.0.1}" = "127.0.0.1" ]; then
  export CTW_ALLOW_LOCAL_SETUP=1
fi
exec .venv/bin/python -m uvicorn app:app --host "${CTW_HOST:-127.0.0.1}" --port "${CTW_PORT:-8765}"
