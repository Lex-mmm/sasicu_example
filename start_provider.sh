#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use the project virtual environment python
"$DIR/env/bin/python3" "$DIR/provider_MDT.py" "$@"
