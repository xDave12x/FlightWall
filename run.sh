#!/bin/bash
# Runs the display. The LED driver needs root, so this uses sudo.
#   ./run.sh          real data
#   ./run.sh --mock   sample data (good first test)
DIR="$(cd "$(dirname "$0")" && pwd)"
exec sudo "$DIR/.venv/bin/python" "$DIR/main.py" "$@"
