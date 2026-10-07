#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test_root="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/njupt-github-retry.XXXXXX")"
trap 'rm -rf "$test_root"' EXIT
mkdir "$test_root/bin"

cat > "$test_root/bin/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
attempt=0
if [ -f "$GH_TEST_STATE" ]; then
  read -r attempt < "$GH_TEST_STATE"
fi
attempt=$((attempt + 1))
printf '%s\n' "$attempt" > "$GH_TEST_STATE"
if [ "$attempt" -le "$GH_TEST_FAILURES" ]; then
  echo "$GH_TEST_ERROR" >&2
  exit "$GH_TEST_EXIT"
fi
echo verified-result
STUB
cat > "$test_root/bin/sleep" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$test_root/bin/gh" "$test_root/bin/sleep"

export PATH="$test_root/bin:$PATH"
export TMPDIR="$test_root"
export GH_TEST_STATE="$test_root/attempts"

run_case() {
  local label="$1"
  local script="$2"
  local expected_status="$3"
  local expected_attempts="$4"
  export GH_TEST_FAILURES="$5"
  export GH_TEST_EXIT="$6"
  export GH_TEST_ERROR="$7"
  shift 7

  rm -f "$GH_TEST_STATE"
  local status=0
  bash "$script_dir/$script" "$@" > "$test_root/stdout" 2> "$test_root/stderr" || status=$?
  local attempts
  attempts="$(cat "$GH_TEST_STATE")"
  if [ "$status" -ne "$expected_status" ] || [ "$attempts" -ne "$expected_attempts" ]; then
    echo "FAIL $label: expected status=$expected_status attempts=$expected_attempts; got status=$status attempts=$attempts" >&2
    cat "$test_root/stderr" >&2
    exit 1
  fi
  if [ "$expected_status" -eq 0 ] && ! grep -qx verified-result "$test_root/stdout"; then
    echo "FAIL $label: successful command output was lost" >&2
    exit 1
  fi
  echo "PASS $label"
}

for http_status in 401 403 404; do
  run_case "API HTTP $http_status fails immediately" gh-api-with-retry.sh 17 1 5 17 "HTTP $http_status" repos/example/repository
done
run_case 'API exhausted retries preserve the failure exit code' gh-api-with-retry.sh 23 5 5 23 'HTTP 503' repos/example/repository
run_case 'API succeeds after transient failures' gh-api-with-retry.sh 0 3 2 23 'HTTP 503' repos/example/repository
run_case 'Artifact exhausted retries preserve the failure exit code' download-artifact-with-retry.sh 29 5 5 29 'HTTP 503' 123 example/repository product "$test_root/download"
run_case 'Artifact succeeds after transient failures' download-artifact-with-retry.sh 0 3 2 29 'HTTP 503' 123 example/repository product "$test_root/download"
