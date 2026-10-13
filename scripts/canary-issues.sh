#!/bin/sh
# Sync `romledger canary --json` findings to GitHub issues titled "canary: <key>":
# open one per new finding, close the open ones whose finding is gone.
#
# Usage: sh scripts/canary-issues.sh [--dry-run] <findings.json>
#
# Needs gh (authenticated through GH_TOKEN) and jq. --dry-run prints each
# command that would change GitHub instead of running it.
set -eu

_require_tool() {
  _require_tool_name=$1
  if ! command -v "$_require_tool_name" >/dev/null 2>&1; then
    echo "canary-issues: $_require_tool_name is required but not on PATH" >&2
    return 1
  fi
}

_mutate() {
  if [ "$DRY_RUN" -eq 1 ]; then
    _mutate_line=$(printf '%s' "$*" | tr '\n' ' ')
    echo "dry-run: gh $_mutate_line"
    return 0
  fi
  gh "$@"
}

_ensure_label() {
  if [ "$DRY_RUN" -eq 1 ]; then
    _mutate label create "$LABEL" --color "$LABEL_COLOR" --description "$LABEL_DESCRIPTION"
    return 0
  fi
  if _ensure_label_output=$(gh label create "$LABEL" --color "$LABEL_COLOR" \
    --description "$LABEL_DESCRIPTION" 2>&1); then
    return 0
  fi
  case $_ensure_label_output in
    *"already exists"*) return 0 ;;
  esac
  echo "canary-issues: $_ensure_label_output" >&2
  return 1
}

_open_issues() {
  gh issue list --label "$LABEL" --state open --limit 200 --json number,title
}

_finding_keys() {
  jq -r '.[].key' "$1"
}

_issue_body() {
  jq -r --arg key "$2" '.[] | select(.key == $key)
    | "\(.title)\n\n\(.detail)\n\nThe weekly canary found this."' "$1"
}

_has_open_issue() {
  _has_open_issue_count=$(printf '%s' "$1" | jq -r --arg title "$2" \
    '[.[] | select(.title == $title)] | length')
  [ "$_has_open_issue_count" -gt 0 ]
}

_create_new() {
  _create_new_findings=$1
  _create_new_open=$2
  _create_new_keys=$(_finding_keys "$_create_new_findings")
  while IFS= read -r _create_new_key; do
    [ -n "$_create_new_key" ] || continue
    if _has_open_issue "$_create_new_open" "$TITLE_PREFIX$_create_new_key"; then
      continue
    fi
    _create_new_body=$(_issue_body "$_create_new_findings" "$_create_new_key")
    _mutate issue create --label "$LABEL" --title "$TITLE_PREFIX$_create_new_key" \
      --body "$_create_new_body"
  done <<ISSUES
$_create_new_keys
ISSUES
}

_open_numbers_and_keys() {
  printf '%s' "$1" | jq -r --arg prefix "$TITLE_PREFIX" \
    '.[] | select(.title | startswith($prefix)) | "\(.number) \(.title[($prefix | length):])"'
}

_close_resolved() {
  _close_resolved_findings=$1
  _close_resolved_keys=$(_finding_keys "$_close_resolved_findings")
  _close_resolved_open=$(_open_numbers_and_keys "$2")
  while read -r _close_resolved_number _close_resolved_key; do
    [ -n "$_close_resolved_number" ] || continue
    if printf '%s\n' "$_close_resolved_keys" | grep -Fxq -- "$_close_resolved_key"; then
      continue
    fi
    _mutate issue close "$_close_resolved_number" \
      --comment "The canary no longer reports this finding."
  done <<ISSUES
$_close_resolved_open
ISSUES
}

_usage() {
  echo "usage: sh scripts/canary-issues.sh [--dry-run] <findings.json>" >&2
}

main() {
  readonly LABEL=canary
  readonly LABEL_COLOR=FBCA04
  readonly LABEL_DESCRIPTION="Reported by the weekly canary"
  readonly TITLE_PREFIX="canary: "

  _main_dry_run=0
  if [ $# -gt 0 ] && [ "$1" = "--dry-run" ]; then
    _main_dry_run=1
    shift
  fi
  if [ $# -ne 1 ]; then
    _usage
    exit 2
  fi
  readonly DRY_RUN=$_main_dry_run
  _main_findings=$1

  _require_tool gh
  _require_tool jq
  if [ ! -f "$_main_findings" ]; then
    echo "canary-issues: $_main_findings not found" >&2
    exit 2
  fi

  _ensure_label
  _main_open=$(_open_issues)
  _create_new "$_main_findings" "$_main_open"
  _close_resolved "$_main_findings" "$_main_open"
}

main "$@"
