#!/bin/bash
set -euo pipefail
umask 077
echo "===================================================================="
echo "LAUNCHING AIMAOS SETUP WIZARD"
echo "===================================================================="
cd "$(dirname "$0")"
PY=".venv/bin/python3"
[ -x "$PY" ] || PY="Alix-AI/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"
"$PY" setup.py "$@"
