#!/usr/bin/env bash
set -u
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FULL=0
if [[ "${1:-}" == "--full" ]]; then
  FULL=1
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--full]" >&2
  exit 2
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$ROOT/reproduce-results/task4-$STAMP"
mkdir -p "$OUT"

RESULT=0

record_rc() {
  local name="$1"
  local rc="$2"
  if [[ "$rc" -ne 0 ]]; then
    echo "$name=FAIL rc=$rc" | tee -a "$OUT/RESULT.txt"
    RESULT=1
  else
    echo "$name=PASS" | tee -a "$OUT/RESULT.txt"
  fi
}

{
  echo "timestamp=$(date -Iseconds)"
  echo "repo=$ROOT"
  echo "branch=$(git branch --show-current 2>/dev/null || true)"
  echo "head=$(git rev-parse HEAD 2>/dev/null || true)"
  echo "describe=$(git describe --tags --always --dirty 2>/dev/null || true)"
  echo
  echo "[status]"
  git status --short 2>/dev/null || true
} > "$OUT/git.txt"

{
  uname -a || true
  echo
  python3 --version || true
  python3 -m pytest --version || true
  make --version | head -1 || true
  cc --version | head -1 || true
  echo
  echo "[proxy variables: names only]"
  env | sed -n 's/^\([^=]*[Pp][Rr][Oo][Xx][Yy]\)=.*/\1=<set>/p' | sort || true
} > "$OUT/environment.txt" 2>&1

echo "== Build =="
(
  set -o pipefail
  make -j"${JOBS:-$(nproc 2>/dev/null || echo 4)}"
) 2>&1 | tee "$OUT/build.log"
rc=${PIPESTATUS[0]}
record_rc BUILD "$rc"

echo "== Focused Task 4 acceptance =="
(
  set -o pipefail
  python3 -m pytest \
    tests/test_formal_security_score.py \
    tests/test_api_formal_schema_compliance.py \
    tests/test_delivery_platform_interfaces.py \
    tests/test_fuzz_api.py \
    tests/test_url_query.py \
    -k "not test_filter_by_task_name" \
    -q
) 2>&1 | tee "$OUT/focused-tests.log"
rc=${PIPESTATUS[0]}
record_rc FOCUSED_TESTS "$rc"

echo "== URL-query integration =="
(
  set -o pipefail
  python3 -m pytest tests/test_query_integration.py -q
) 2>&1 | tee "$OUT/query-integration.log"
rc=${PIPESTATUS[0]}
record_rc QUERY_INTEGRATION "$rc"

echo "== Local API smoke =="
PORT="${TASK4_API_PORT:-18081}"

env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy \
    python3 integration/api_server.py --host 127.0.0.1 --port "$PORT" \
    >"$OUT/api-server.log" 2>&1 &
API_PID=$!

cleanup() {
  if kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

api_rc=1
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
         -u ALL_PROXY -u all_proxy \
         python3 - "$PORT" >"$OUT/api-smoke.log" 2>&1 <<'PY'
import json
import sys
import urllib.request
import urllib.error

port = int(sys.argv[1])
base = f"http://127.0.0.1:{port}"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

try:
    for path in ("/health", "/capabilities"):
        with opener.open(base + path, timeout=2) as r:
            body = json.loads(r.read().decode("utf-8"))
            if r.status != 200:
                raise SystemExit(1)
            print(path, r.status, json.dumps(body, ensure_ascii=False))
except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
    raise SystemExit(1)
PY
  then
    api_rc=0
    break
  fi

  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "local API server exited before readiness" >"$OUT/api-smoke.log"
    break
  fi

  sleep 0.5
done

cat "$OUT/api-smoke.log" 2>/dev/null || true
record_rc API_SMOKE "$api_rc"
cleanup
trap - EXIT

if [[ "$FULL" -eq 1 ]]; then
  echo "== Full historical regression (diagnostic) =="
  python3 -m pytest tests/ \
    -k "not test_filter_by_task_name" \
    --tb=no -q \
    2>&1 | tee "$OUT/full-regression.log"
  full_rc=${PIPESTATUS[0]}
  echo "FULL_REGRESSION_RC=$full_rc" | tee -a "$OUT/RESULT.txt"
  echo "NOTE: full mode is diagnostic; historical/environment-dependent test debt may remain." \
    | tee -a "$OUT/RESULT.txt"
fi

(
  cd "$OUT" || exit 1
  find . -maxdepth 1 -type f ! -name SHA256SUMS.txt -print0 \
    | sort -z \
    | xargs -0 sha256sum
) > "$OUT/SHA256SUMS.txt"

echo
if [[ "$RESULT" -eq 0 ]]; then
  echo "TASK4_REPRODUCTION=PASS"
else
  echo "TASK4_REPRODUCTION=FAIL"
fi
echo "RESULT_DIR=$OUT"

exit "$RESULT"
