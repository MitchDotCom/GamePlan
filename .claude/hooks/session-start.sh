#!/bin/bash
# Installs the Python dependencies for Claude Code on the web sessions. Idempotent and non-interactive.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
python3 -m pip install --quiet -e '.[dev]'
# browser smoke test for the viewer (chromium is preinstalled in the web environment)
python3 -m pip install --quiet playwright
echo 'export PYTHONPATH="'"$CLAUDE_PROJECT_DIR"'/src${PYTHONPATH:+:$PYTHONPATH}"' >> "${CLAUDE_ENV_FILE:-/dev/null}"
