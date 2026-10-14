#!/bin/sh
# Builds the image for this machine, starts it on a scratch library and queries the API.
set -eu

readonly IMAGE="romledger:check"
readonly TOKEN="image-check-token-0123456789"

_main_work=""

_cleanup() {
  docker rm -f romledger-check >/dev/null 2>&1 || true
  if [ -n "$_main_work" ]; then
    rm -rf "$_main_work"
  fi
}

_wait_for_api() {
  _wait_for_api_url="$1"
  _wait_for_api_tries=0
  while ! curl -fsS -H "Authorization: Bearer $TOKEN" "$_wait_for_api_url" >/dev/null 2>&1; do
    _wait_for_api_tries=$((_wait_for_api_tries + 1))
    if [ "$_wait_for_api_tries" -ge 30 ]; then
      docker logs romledger-check >&2
      echo "the API did not answer at $_wait_for_api_url" >&2
      exit 1
    fi
    sleep 1
  done
}

main() {
  for _main_tool in docker curl; do
    if ! command -v "$_main_tool" >/dev/null 2>&1; then
      echo "$_main_tool is required but not installed" >&2
      exit 1
    fi
  done
  _main_root=$(cd "$(dirname "$0")/.." && pwd)
  _main_work=$(mktemp -d)
  trap _cleanup EXIT
  mkdir "$_main_work/config" "$_main_work/library" "$_main_work/library/roms" \
    "$_main_work/library/inbox"
  printf '[library]\nroms = "/library/roms"\ninboxes = ["/library/inbox"]\n\n[platforms.nes]\n' \
    >"$_main_work/config/config.toml"
  chmod -R a+rX "$_main_work"
  chmod -R a+rwX "$_main_work/library"

  docker build -t "$IMAGE" "$_main_root"
  docker run --rm "$IMAGE" --version
  docker run --rm --entrypoint igir "$IMAGE" --help >/dev/null
  docker run -d --name romledger-check -e "ROMLEDGER_TOKEN=$TOKEN" \
    -v "$_main_work/config:/config:ro" -v "$_main_work/library:/library" \
    -p 127.0.0.1::8730 "$IMAGE" >/dev/null
  _main_address=$(docker port romledger-check 8730/tcp | head -n 1)
  _wait_for_api "http://$_main_address/api/platforms"
  curl -fsS -H "Authorization: Bearer $TOKEN" "http://$_main_address/api/platforms"
  echo
}

main "$@"
