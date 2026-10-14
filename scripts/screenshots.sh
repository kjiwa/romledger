#!/bin/sh
# Regenerates docs/images/*.png from a fictional library.
set -eu

readonly PLAYWRIGHT="playwright==1.64.0"

main() {
  _main_root=$(cd "$(dirname "$0")/.." && pwd)
  cd "$_main_root"
  uvx --from "$PLAYWRIGHT" playwright install chromium
  uv run --no-project --with "$PLAYWRIGHT" --with-editable . \
    python scripts/demo_library.py docs/images
}

main "$@"
