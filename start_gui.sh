#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use the project virtual environment python
"$DIR/env/bin/python3" "$DIR/sdc_monitor_control.py" "$@"
