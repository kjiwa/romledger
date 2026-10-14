# shellcheck shell=sh
# Sourced by gh-cut from the repository root.

_release_lock_version() {
  awk '
    $0 == "name = \"romledger\"" { found = 1; next }
    found && /^version = / { gsub(/version = "|"/, ""); print; exit }
  ' uv.lock
}

release_version() {
  _release_version_pyproject=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n1)
  _release_version_manifest=$(sed -n 's/^  "version": "\(.*\)",$/\1/p' extension/manifest.json)
  _release_version_lock=$(_release_lock_version)
  if [ "$_release_version_pyproject" != "$_release_version_manifest" ] ||
    [ "$_release_version_pyproject" != "$_release_version_lock" ]; then
    echo "pyproject.toml ($_release_version_pyproject), extension/manifest.json ($_release_version_manifest) and uv.lock ($_release_version_lock) disagree" >&2
    return 1
  fi
  echo "$_release_version_pyproject"
}

release_bump() {
  _release_bump_version="$1"
  sed 's/^version = ".*"$/version = "'"$_release_bump_version"'"/' pyproject.toml >pyproject.toml.new
  mv pyproject.toml.new pyproject.toml
  sed 's/^  "version": ".*",$/  "version": "'"$_release_bump_version"'",/' extension/manifest.json >extension/manifest.json.new
  mv extension/manifest.json.new extension/manifest.json
  uv lock
  release_version >/dev/null
}

release_checks() {
  uv run ruff check
  uv run ruff format --check
  uv run mypy
  uv run pytest -q
}
