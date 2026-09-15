#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <variable-name> <value>" >&2
  exit 2
fi

name="$1"
value="$2"
max_attempts=5

if [[ ! "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "invalid GitHub Actions variable name: $name" >&2
  exit 2
fi

is_transient_gh_failure() {
  local log_file="$1"
  grep -Eiq 'HTTP (429|5[0-9]{2})|status([^0-9]| code[^0-9]*)(429|5[0-9]{2})|ECONNRESET|ECONNABORTED|ETIMEDOUT|EAI_AGAIN|ENETUNREACH|network is unreachable|temporary failure|timed out|timeout|bad gateway|service unavailable|gateway timeout' "$log_file"
}

for attempt in $(seq 1 "$max_attempts"); do
  stdout_file="$(mktemp)"
  stderr_file="$(mktemp)"
  trap 'rm -f "$stdout_file" "$stderr_file"' EXIT

  if gh variable set "$name" --body "$value" >"$stdout_file" 2>"$stderr_file"; then
    cat "$stdout_file"
    rm -f "$stdout_file" "$stderr_file"
    trap - EXIT
    exit 0
  else
    status=$?
  fi

  cat "$stderr_file" >&2

  if [ "$attempt" -ge "$max_attempts" ]; then
    rm -f "$stdout_file" "$stderr_file"
    trap - EXIT
    echo "GitHub variable update failed after $max_attempts attempts: $name" >&2
    exit "$status"
  fi

  if ! is_transient_gh_failure "$stderr_file"; then
    rm -f "$stdout_file" "$stderr_file"
    trap - EXIT
    echo "GitHub variable update failed with a non-transient error; not retrying: $name" >&2
    exit "$status"
  fi

  rm -f "$stdout_file" "$stderr_file"
  trap - EXIT
  delay=$((attempt * attempt * 5))
  echo "Transient GitHub API failure while updating $name; retrying in ${delay}s." >&2
  sleep "$delay"
done
