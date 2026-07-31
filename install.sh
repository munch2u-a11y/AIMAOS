#!/usr/bin/env bash
set -euo pipefail
umask 077

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "AIMAOS requires Python 3.11 or newer."
  exit 1
fi

python3 -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.lock
.venv/bin/python3 doctor.py
.venv/bin/python3 setup.py "$@"

echo
echo "Installation complete. Start AIMAOS with: ./Launch AIMAOS.sh"
