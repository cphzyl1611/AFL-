#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo " Task 4 one-click verification"
echo "============================================================"
echo "Repo : $ROOT"
echo "Head : $(git rev-parse --short HEAD 2>/dev/null || echo UNKNOWN)"
echo

for cmd in python3 make; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $cmd" >&2
    exit 2
  fi
done

if ! python3 -c 'import pytest' >/dev/null 2>&1; then
  echo "ERROR: pytest is not installed."
  echo "Run: python3 -m pip install -U pytest"
  exit 2
fi

if [[ ! -x "$ROOT/afl-fuzz" ]]; then
  echo "[1/4] afl-fuzz not found; building..."
  make -j"${JOBS:-$(nproc 2>/dev/null || echo 4)}"
else
  echo "[1/4] afl-fuzz already built."
fi

echo
echo "[2/4] Running focused Task 4 acceptance tests..."
python3 -m pytest \
  tests/test_formal_security_score.py \
  tests/test_api_formal_schema_compliance.py \
  tests/test_delivery_platform_interfaces.py \
  tests/test_fuzz_api.py \
  tests/test_url_query.py \
  -k "not test_filter_by_task_name" \
  -q

echo
echo "[3/4] Running URL-query integration tests..."
python3 -m pytest tests/test_query_integration.py -q

echo
echo "[4/4] Running local integration API smoke..."
PORT="${TASK4_API_PORT:-18081}"
LOG="$(mktemp)"

env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy \
    python3 integration/api_server.py --host 127.0.0.1 --port "$PORT" \
    >"$LOG" 2>&1 &
PID=$!

cleanup() {
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
  rm -f "$LOG"
}
trap cleanup EXIT

ok=0
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
         -u ALL_PROXY -u all_proxy \
         python3 - "$PORT" <<'PY'
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
            obj = json.loads(r.read().decode("utf-8"))
            if r.status != 200:
                raise SystemExit(1)
            print(f"{path}: HTTP {r.status}")
except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
    raise SystemExit(1)
PY
  then
    ok=1
    break
  fi

  if ! kill -0 "$PID" 2>/dev/null; then
    echo "ERROR: local API server exited before becoming ready." >&2
    cat "$LOG" >&2 || true
    exit 1
  fi

  echo "  waiting for local API... ($attempt/10)"
  sleep 0.5
done

if [[ "$ok" -ne 1 ]]; then
  echo "ERROR: local API smoke failed." >&2
  cat "$LOG" >&2 || true
  exit 1
fi

cleanup
trap - EXIT

echo
echo "============================================================"
echo " TASK4_ONECLICK=PASS"
echo " This verification did NOT access a real O2OA/Alfresco service."
echo " For reproducibility logs, run: ./scripts/reproduce_task4.sh"
echo "============================================================"
