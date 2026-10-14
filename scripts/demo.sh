#!/bin/sh
# Regenerates docs/images/demo.gif from a fictional library.
set -eu

readonly PLAYWRIGHT="playwright==1.64.0"

main() {
  _main_root=$(cd "$(dirname "$0")/.." && pwd)
  cd "$_main_root"
  _main_work=$(mktemp -d)
  trap 'rm -rf "$_main_work"' EXIT
  uv run --no-project --with "$PLAYWRIGHT" --with-editable . \
    python scripts/demo_library.py --library "$_main_work" \
    >"$_main_work/config-path"
  ROMLEDGER_CONFIG=$(cat "$_main_work/config-path")
  ROMLEDGER_DATA="$_main_work/data"
  export ROMLEDGER_CONFIG ROMLEDGER_DATA
  uv run --no-project --with-editable . vhs docs/demo.tape
}

main "$@"
