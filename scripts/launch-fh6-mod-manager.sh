#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_ICON="$APP_DIR/resources/icons/fh6-mod-manager.png"

if [ "${1:-}" = "--print-icon" ]; then
  printf '%s\n' "$APP_ICON"
  exit 0
fi

cd "$APP_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import PySide6" >/dev/null 2>&1; then
  pip install -r requirements.txt
fi

python -m app.main
