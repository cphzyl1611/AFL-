#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${NV_TOKEN:?NV_TOKEN is required}"

echo "[1/4] submit AE template"
AE_OUT=$(python3 runner/fuzz_test_runner.py submit --task-json runner/templates/task_ae_default.json)
echo "$AE_OUT"
AE_TASK_ID=$(python3 - <<'PY' "$AE_OUT"
import json,sys
print(json.loads(sys.argv[1])["task_id"])
PY
)

sleep 3
echo "[2/4] wait AE task finish"
while true; do
  Q=$(python3 runner/fuzz_test_runner.py query --task-id "$AE_TASK_ID")
  echo "$Q"
  STATUS=$(python3 - <<'PY' "$Q"
import json,sys
print(json.loads(sys.argv[1])["status"])
PY
)
  if [ "$STATUS" = "exited" ] || [ "$STATUS" = "stopped" ]; then
    break
  fi
  sleep 5
done

echo "[3/4] AE report"
python3 runner/fuzz_test_runner.py report --task-id "$AE_TASK_ID"

echo "[4/4] smoke test finished"
