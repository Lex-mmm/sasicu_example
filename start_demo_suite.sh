#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/env/bin/python3"
if [ ! -x "$PY" ]; then
  echo "Venv python not found at $PY" >&2
  echo "Create it or run: python3 -m venv env && ./env/bin/pip install -r requirements.txt" >&2
  exit 1
fi
exec "$PY" "$HERE/sdc_demo_suite.py" "$@"
