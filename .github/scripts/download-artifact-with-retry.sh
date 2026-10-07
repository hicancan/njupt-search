#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <run-id> <repo> <artifact-name> <output-dir>" >&2
  exit 2
fi

run_id="$1"
repo="$2"
artifact_name="$3"
output_dir="$4"

last_status=1
for attempt in 1 2 3 4 5; do
  rm -rf "$output_dir"
  if gh run download "$run_id" --repo "$repo" --name "$artifact_name" --dir "$output_dir"; then
    exit 0
  else
    last_status=$?
  fi
  if [ "$attempt" -lt 5 ]; then
    sleep_seconds=$((attempt * 10))
    echo "artifact download failed on attempt $attempt; retrying in ${sleep_seconds}s..." >&2
    sleep "$sleep_seconds"
  fi
done

echo "artifact download failed after 5 attempts: run=$run_id artifact=$artifact_name repo=$repo" >&2
exit "$last_status"
