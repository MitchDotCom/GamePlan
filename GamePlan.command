#!/bin/bash
# Double-click this file (Mac) to set up and open GamePlan. The first run takes a few minutes; later runs open in seconds.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "GamePlan needs Python 3. Install it from https://www.python.org/downloads/ and double-click this file again."
  read -r -p "Press Return to close."
  exit 1
fi
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
echo "Installing GamePlan (first run only)..."
pip install -q -e . || { echo "Install failed. Send the message above to Claude."; read -r -p "Press Return to close."; exit 1; }
echo "Starting GamePlan. The first run also downloads the 2025 season (about 200 MB, 10 to 20 minutes); the two demo games work right away."
exec gameplan --download --open
