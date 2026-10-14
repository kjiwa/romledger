#!/bin/sh
# Regenerates docs/images/demo.gif from a fictional library. Needs vhs (with ttyd and ffmpeg).
set -eu

readonly PLAYWRIGHT="playwright==1.64.0"

main() {
  if ! command -v vhs >/dev/null 2>&1; then
    echo "vhs is required but not installed: https://github.com/charmbracelet/vhs" >&2
    exit 1
  fi
  _main_root=$(cd "$(dirname "$0")/.." && pwd)
  cd "$_main_root"
  _main_work=$(mktemp -d)
  trap 'rm -rf "$_main_work"' EXIT
  uv run --no-project --with "$PLAYWRIGHT" --with-editable . \
    python scripts/demo_library.py --library "$_main_work/library"
  ROMLEDGER_CONFIG="$_main_work/library/config.toml"
  ROMLEDGER_DATA="$_main_work/library/data"
  export ROMLEDGER_CONFIG ROMLEDGER_DATA
  uv run --no-project --with-editable . vhs docs/demo.tape
}

main "$@"
