#!/bin/sh
# Runs the unpacked extension in Chromium against a fictional library. With a directory argument
# it also writes the popup screenshots there.
set -eu

readonly PLAYWRIGHT="playwright==1.64.0"

main() {
  _main_root=$(cd "$(dirname "$0")/.." && pwd)
  cd "$_main_root"
  uvx --from "$PLAYWRIGHT" playwright install chromium
  uv run --no-project --with "$PLAYWRIGHT" --with-editable . \
    python scripts/extension_check.py "$@"
}

main "$@"
