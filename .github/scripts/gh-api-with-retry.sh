#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <gh-api-args...>" >&2
  exit 2
fi

last_status=1
last_error=""

for attempt in 1 2 3 4 5; do
  stdout_file="$(mktemp)"
  stderr_file="$(mktemp)"
  if gh api "$@" >"$stdout_file" 2>"$stderr_file"; then
    cat "$stdout_file"
    rm -f "$stdout_file" "$stderr_file"
    exit 0
  else
    last_status=$?
  fi

  last_error="$(cat "$stderr_file")"
  cat "$stderr_file" >&2
  rm -f "$stdout_file" "$stderr_file"

  if printf '%s\n' "$last_error" | grep -Eiq 'HTTP (401|403|404)'; then
    echo "gh api failed with non-transient status on attempt ${attempt}; not retrying." >&2
    exit "$last_status"
  fi

  if [ "$attempt" -lt 5 ]; then
    sleep_seconds=$((attempt * attempt * 5))
    echo "gh api failed on attempt ${attempt}; retrying in ${sleep_seconds}s..." >&2
    sleep "$sleep_seconds"
  fi
done

echo "gh api failed after 5 attempts." >&2
if [ -n "$last_error" ]; then
  printf '%s\n' "$last_error" >&2
fi
exit "$last_status"
