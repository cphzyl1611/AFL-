1. Run-root




scripts/run\_alfresco\_bounded\_feedback.py

- build\_run\_layout(run\_root, repo\_root) — lines 82–101. It is a pure planning function. It resolves both paths, rejects run\_root equal to or inside repo\_root (line 91–92, RUN\_ROOT\_INSIDE\_GIT\_WORKTREE), and returns a dict of six paths: run\_root, target\_config (target.json), seed (seed.http), status (nv\_http\_status.json), afl\_output (afl-out), evidence (evidence).



- It creates nothing. No mkdir. It does not require run\_root to pre-exist — Path.resolve() on a non-existent path is fine on Python 3.13.



- run\_root is never selected by the program. It is a caller-supplied parameter, and main() (lines 153–164) never calls build\_run\_layout. There is no --run-root argument, no default, and no environment lookup.



- Delegation: lines 12–28 load scripts/run\_alfresco\_levelc\_metadata.py by file path via importlib without running its main(). resolve\_existing\_dedicated\_node (30–71) and render\_runtime\_target\_config (73–80) delegate into it. Neither is called from main() either.



- A fresh run-scoped directory is NOT guaranteed by this runner. The only directory creation in the whole chain is a side effect of run\_alfresco\_levelc\_metadata.render\_target\_config → out\_path.parent.mkdir(parents=True, exist\_ok=True) (line 190), which is unreachable from main().




For contrast, the audited Level-C launcher does guarantee it: run\_scoped\_dir() (scripts/run\_alfresco\_levelc\_metadata.lfresco-levelc-, created at line494–495 and removed in the finally at 541–543 unless --keep-run-dir.

- Writer: nv\_http\_harness.py, write\_status() lines 265–317. Atomic: writes STATUS\_PATH + ".tmp" then os.replace (313–317). This is the only production writer.



- Path: nv\_http\_harness.py:8 — STATUS\_PATH = os.getenv("NV\_STATUS\_PATH", "/tmp/nv\_http\_status.json"), resolved once at module import.



- How the path is passed: by environment. scripts/run\_alfresco\_levelc\_metadata.py:209 (harness\_env) sets NV\_STATUS\_PATH = status\_path\_for(run\_dir). For an AFL run it must be exported into afl-fuzz's environment.




  Ran 2 shell commands




Now Q10 — reporting conservation.

Searched for 4 patterns, ran 7 shell commands

One last verification before I conclude — that body\_validate really rejects a full HTTP envelope.

Searched for 1 pattern

No modifications were made. Everything current source.

PRE-RUN LOCAL GATE = NEEDS\_MINIMAL\_FIX

Repository identity

PWD    = /home//AFLplusplus-alfresco-real-feedback

BRANCH = feature/alfresco-bounded-real

HEAD   = dbffb19312faaa6164ca6c4b7abe43ff985e2d83

STATUS = ?? AFLplusplus\_other\_AI\_handoff\_20260825.md

?? scripts/run\_alfresco\_bounded\_feedback.py

?? tests/test\_alfresco\_bounde

All four expected identity facts match. No discrepancy.

Source-derived findings

1. Run-root




- build\_run\_layout(run\_root, repo\_root) — lines 82–101. It is a pure planning function. It resolves both paths, rejects run\_root equal to or inside repo\_root (line 91–92, RUN\_ROOT\_INSIDE\_GIT\_WORKTREE), and returns a dict of six paths: run\_root, target\_config (target.json), seed (seed.http), status (nv\_http\_status.json), afl\_output (afl-out), evidence (evidence).



- It creates nothing. No mkdir. It does not require run\_root to pre-exist — Path.resolve() on a non-existent path is fine on Python 3.13.



- run\_root is never selected by the program. It is a caller-supplied parameter, and main() (lines 153–164) never calls build\_run\_layout. There is no --run-root argument, no default, and no environment lookup.



- Delegation: lines 12–28 load scripts/run\_alfresco\_levelc\_metadata.py by file path via importlib without running its main(). resolve\_existing\_dedicated\_node (30–71) and render\_runtime\_target\_config (73–80) delegate into it. Neither is called from main() either.



- A fresh run-scoped directory is NOT guaranteed. The only directory creation in the whole chain is unreachable from main().




2. nv\_http\_status.json path and lifecycle




- Writer: nv\_http\_harness.py, write\_status() lines 265–317. Atomic: writes STATUS\_PATH + ".tmp" then os.replace (313–317). This is the only production writer.



- Path: nv\_http\_harness.py:8 — STATUS\_PATH = os.getenv("NV\_STATUS\_PATH", "/tmp/nv\_http\_status.json"), resolved once at module import.



- How the path is passed: by environment. scripts/run\_alfresco\_levelc\_metadata.py:209 (harness\_env) sets NV\_STATUS\_PATH = status\_path\_for(run\_dir). For an AFL run it must be exported into afl-fuzz's environment, which both the C side and the inherited harness child read.



- Consumers: two, both in src/afl-fuzz-run.c:



  - nv\_observe\_security\_state() (lines 2208).



- Historical /tmp status files are irrelevant to a new run: each is bound to its own NV\_STATUS\_PATH, and the C-side high-water lives in process memory (afl->nv\_last\_exec\_seq), starting at 0.




3. exec\_seq namespace and high-water




- Allocation: nv\_http\_harness.py: seq\_sidecar\_path() line 194–201 → STATUS\_PATH + ".seq". For the bounded layout that is \<run\_root>/nv\_http\_status.json.seq.



- Namespace choice: the status-file path does determine the namespace — one sidecar per NV\_STATUS\_PATH (docstring, 197–199).



- Across process restart: the counter is file-backed. AFL runs the harness as a fresh process per execution, so the module-level SEQ is always 1 and is explicitly documented as legacy.



- Validity rejection does NOT consume an exec\_seq. On rejection no status document is written at all, so the previous run's document stays on disk.



- Observer/read-back does NOT consume an exec\_seq. The read-back observer is AlfrescoClient.get\_node / version\_count and never calls nv\_http\_harness.



- High-water logic:

  -> H = 0 if file missing/empty/invalid/negative, else integer value.



- Replay check: exec\_seq <= afl->nv\_last\_exec\_seq ⇒ NV\_STATUS\_REPLAY; accepted ids advance the high-water.




4. Bounded runner preflight verification




scripts/run\_alfresco\_bounded\_feedback.py:

Python

```
parser.add_argument("--preflight-only", action="store_true")   # 155
parser.parse_args()                                           # 156 <-- result discarded
try:
    runtime_credentials()                                     # 159
except RuntimeError as exc:
    print(str(exc), file=sys.stderr)                          # 161-162

```

| **Check**                       | **Validated?** | **Details**                                                         |
| ------------------------------- | -------------- | ------------------------------------------------------------------- |
| Credential presence             | Yes            | runtime\_credentials() lines 138–150; rejects None/empty/whitespace |
| Alfresco target/node resolution | No             | resolve\_existing\_dedicated\_node (30–71) never called             |
| Independent service GET         | No             | Not performed in stub                                               |
| Run-root preparation            | No             | build\_run\_layout (82–101) never called                            |
| Any network access              | No             | No network calls made                                               |

5. Termination and case budget accounting




- max\_test\_cases comes from task JSON, not from argv. Loaded by `nv_load_task_json(afl, getenv("NV_TASK_PATH"))` at `src/afl-fuzz.c:3572–3573`.



- Counter: `afl->nv_total_valid_exec`, incremented in `fuzz_run_target()`, `src/afl-fuzz-run.c:416–432`.




C

```
if (likely(afl->queue_cur &&
           strcmp(afl->stage_name, "dry_run") &&
           strcmp(afl->stage_name, "calibration"))) {
  afl->nv_total_valid_exec++;
  if (afl->nv_task.max_test_cases &&
      afl->nv_total_valid_exec >= afl->nv_task.max_test_cases) {
    afl->stop_soon = 2;
    return res;
  }
}

```

| **Event**                                         | **Consumes Case?** | **Why**                                                                   |
| ------------------------------------------------- | ------------------ | ------------------------------------------------------------------------- |
| C-side validity reject                            | No                 | `common_fuzz_stuff` returns at 2172–2176, before `fuzz_run_target`        |
| Adapter / Python body-validation reject           | Yes                | Rejection happens inside target execution; `fuzz_run_target` has returned |
| Service execution (4xx/5xx/timeout/conn\_refused) | Yes                | Target ran; counter is outcome-independent                                |
| Dry run / calibration                             | No                 | Excluded by `strcmp` guard                                                |

6. Representation bridge — blocker analysis




| **Component**       | **Interface / Scope**                                | **Format / Behavior**                           |
| ------------------- | ---------------------------------------------------- | ----------------------------------------------- |
| Producer            | `nv_json_mutator.py:118–150`, `afl_custom_fuzz`      | FULL HTTP — always, via `_emit_http` (97–101)   |
| Validation boundary | `src/afl-fuzz-run.c:795`, `nv_validity_check`        | Checks HTTP header structure & path             |
| Adapter             | `nv_http_body_adapter.py:10–36`, `extract_http_body` | FULL HTTP → byte-exact body                     |
| Production harness  | `nv_http_harness.py:526`                             | Expects body-only JSON when `body_only_mode: 1` |

7. Feedback / reward / MAB attribution




Runtime correlation fields:

- `exec_seq` -> `obs.exec_seq` (emitted by `nv_http_harness.py:296`, parsed `afl-fuzz-run.c:174–178`)



- `NV_JSON_ARM_USED` -> Mutator sets env `nv_json_mutator.py:129`; fuzzer reads `src/afl-fuzz-one.c:1957, 1974–1988`



- `security_state_total` -> `afl->nv_cov_used` (`afl-fuzz-stats.c:443`, `:716`)



- `security_state_seed_credit` -> incremented `afl-fuzz-run.c:314`; emitted `:447 / :723`



- `nv_mab_total_pulls` -> `afl->nv_mab.total_pulls` (`src/afl-fuzz-nv-mab.c:182`)




8. Source queue entry credit




C

```
if (is_new) {
  afl->nv_sec_state_new_total++;
  if (afl->queue_cur) {
    afl->queue_cur->ss_cov_cnt++;
    afl->nv_sec_state_seed_credit++;
  }
}

```

Credit is exclusive to `afl->queue_cur`.

10. Reporting conservation




- `runtime security_state_total == fuzzer_stats security_state_total == eval_report.json`



- `sum(per-arm pulls) == nv_mab_total_pulls`



- Conditional identity:

  `ss_cov_sum == security_state_seed_credit + ss_new_bits_any + queued_with_cov`




Blockers Summary:

- **CB-1**: Representation bridge not wired into `nv_http_harness.py`.



- **CB-2**: Bounded runner `main()` is a stub.




### Step-by-Step Execution Plan

A. LOCAL READ-ONLY PREPARATION

Bash

```
cd /home/<USER>/AFLplusplus-alfresco-real-feedback

# A1. Re-confirm identity
git rev-parse HEAD; git branch --show-current; git status --short
sha256sum scripts/run_alfresco_bounded_feedback.py tests/test_alfresco_bounded_feedback.py

# A2. Confirm fuzzer binary exists
ls -la ./afl-fuzz
ls -la src/afl-fuzz-run.c src/afl-fuzz-nv-mab.c src/afl-fuzz-nv-sched.c src/afl-fuzz-nv-covset.c

# A3. Check representation extraction logic
sed -n '553,559p' nv_http_harness.py
sed -n '24,32p' tests/fixtures/nv_feedback_fake_target.py

# A4. Prepare run root outside worktree
export NV_RUN_ROOT="/tmp/nv-alfresco-bounded-$(date +%Y%m%d-%H%M%S)-$$"
echo "NV_RUN_ROOT=$NV_RUN_ROOT"

# A5. Establish high-water mark
test -e "$NV_RUN_ROOT/nv_http_status.json.seq" \
  && cat "$NV_RUN_ROOT/nv_http_status.json.seq" \
  || echo "PRE_RUN_EXEC_SEQ_HIGH_WATER=0"

```

B. PREFLIGHT VERIFICATION

Bash

```
# B1. Verify credential presence
for v in ALFRESCO_USER ALFRESCO_PASS; do
  [ -n "${!v:-}" ] && echo "$v=SET_NONBLANK" || echo "$v=UNSET_OR_BLANK"
done

# B2. Stub check (exit 0)
python3 scripts/run_alfresco_bounded_feedback.py --preflight-only; echo "exit=$?"

# B3. Full Level-C preflight
python3 scripts/run_alfresco_levelc_metadata.py --rounds 1 --keep-run-dir \
  --evidence-dir "$NV_RUN_ROOT/evidence-preflight"

```

C. BOUNDED RUN EXECUTION (After resolving CB-1)

Bash

```
mkdir -p "$NV_RUN_ROOT"

# C1. Render run-scoped target config
python3 - <<'PY'
import importlib.util, os
from pathlib import Path
PY

# C2. Full HTTP seed setup
mkdir -p "$NV_RUN_ROOT/in"
printf 'PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/%s\nContent-Type:application/json\n\n{"properties":{"cm:title":"NV_BOUNDED","cm:description":"NV_BOUNDED"}}\n' \
  "$NODE_A_ID" > "$NV_RUN_ROOT/in/seed.http"

# C3. Task configuration
cat > "$NV_RUN_ROOT/task.json" <<EOF
{
  "target_type": "http_api",
  "target_endpoint": "metadata_update",
  "seed_source": "seed_file",
  "seed_location": "$NV_RUN_ROOT/in",
  "mutation_scope": ["field_value"],
  "max_test_cases": 5,
  "time_budget": 120,
  "enable_validity": 1
}
EOF

# C4. Set environment
export NV_TASK_PATH="$NV_RUN_ROOT/task.json"
export NV_TARGET_CONFIG="$NV_RUN_ROOT/target.json"
export NV_STATUS_PATH="$NV_RUN_ROOT/nv_http_status.json"
export NV_PROBE_PATH="$NV_RUN_ROOT/nv_probe.json"
export NV_STATE_DB="$NV_RUN_ROOT/nv_state_db.json"
export NV_CTX_PATH="$NV_RUN_ROOT/nv_ctx.json"
export NV_ERR_DIR="$NV_RUN_ROOT/err_cases"
export NV_BODY_VALID_STATS="$NV_RUN_ROOT/nv_body_valid_stats.json"
export AFL_PYTHON_MODULE=nv_json_mutator
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
export AFL_NO_UI=1 AFL_SKIP_CPUFREQ=1 AFL_NO_CRASHES=1
export no_proxy=127.0.0.1,localhost NO_PROXY=127.0.0.1,localhost

# C5. Run AFL
timeout 180s ./afl-fuzz -n -m none -s \
  -i "$NV_RUN_ROOT/in" -o "$NV_RUN_ROOT/afl-out" \
  -- python3 "$PWD/nv_http_harness.py"
echo "afl_exit=$?"

```

D. POST-RUN EVIDENCE EXTRACTION

Bash

```
S="$NV_RUN_ROOT/afl-out/default/fuzzer_stats"
E="$NV_RUN_ROOT/afl-out/default/eval_report.json"

grep -E 'nv_total_valid_exec|nv_valid_cnt|nv_invalid_|nv_max_test_cases|nv_mab_total_pulls|nv_mab_arm._pulls' "$S"
grep -E 'security_state_' "$S"
grep -E 'ss_cov_sum|ss_cov_max|ss_new_bits_any|ss_new_bits_kept' "$S"

python3 - <<'PY'
import json
with open("'"$S"'") as f: st = dict(line.strip().split(":", 1) for line in f if ":" in line)
with open("'"$E"'") as f: ev = json.load(f)
c=ev["cov"]; m=ev["mab"]
print("state_total  stats==eval :", int(st["security_state_total"].strip())==c["security_state_total"])
print("mab pulls    sum==total  :", sum(a["pulls"] for a in m["arms"])==m["total_pulls"])
bits=int(st["ss_new_bits_any"].strip())
print("ss_new_bits_any          :", bits, "(must be 0 for the simple form)")
print("ss_cov_sum==seed_credit  :",
      int(st["ss_cov_sum"].strip())==c["security_state_seed_credit"] if bits==0 else "N/A - use +bitmap form")
PY

python3 scripts/run_alfresco_levelc_metadata.py --rounds 1 --keep-run-dir \
  --evidence-dir "$NV_RUN_ROOT/evidence-postrun"

```