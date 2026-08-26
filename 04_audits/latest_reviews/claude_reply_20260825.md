
  state exactly what is unknown.

  Do not silently guess.

erns, listed 1 directory, ran 5 shell commands

Now max_test_cases — Q5's core question.

  Searched for 5 patterns, read 1 file, listed 1 directory, ran 5 shell commands

PWD    = /home/dministrator/AFLplusplus-alfresco-real-feedback
BRANCH = feature/alfresco-bounded-real-feedback
HEAD   = dbffb19312faaa6164ca6c4b7abe43ff985e2d83
STATUS = ?? AFLplusplus_other_AI_handoff_20260825.md
PRE-RUN LOCAL GATE

PRE-RUN LOCAL GATE = NEEDS_MINIMAL_FIX

Repository identity

PWD    = /home/dministrator/AFLplusplu
BRANCH = feature/alfresco-bounded-real-feedback                                                            HEAD   = dbffb19312faaa6164ca6c4b7abe4
plus_other_AI_handoff_20260825.md
         ?? scripts/run_alfresco_bounded_feedback.py
         ?? tests/test_alfresco_bounded_feedback.py

Runner SHA256 = e9a61a0160c9601460219ed7e146728614fae8ead378aaccaca15e2dd119d546  (168 lines / 4284 bytes)  MATCH
Test   SHA256 = 9a7103982f73950afe6f43e1750c932c6e13bd20872f235b92dfbf40087e7516  (748 lines / 24548       bytes) MATCH

All four expected identity facts match. No discrepancy.
Source-derived findings
                                                                                                           1. Run-root

scripts/run_alfresco_bounded_feedback.py
                                                                                                           - build_run_layout(run_root, repo_roote planning function. It resolves both
g. No mkdir. It does not require run_root to pre-exist — Path.resolve() on a non-existent path is fine on Python 3.13.

- run_root is never selected by the program. It is a caller-supplied parameter, and main() (lines 153–164) never calls build_run_layout. There is no --run-root argument, no default, and no environment lookup.
- Delegation: lines 12–28 load scripts/run_alfresco_levelc_metadata.py by file path via importlib without    running its main(). resolve_existingender_runtime_target_config (73–80)delegate into it. Neither is called from main() either.
- A fresh run-scoped directory is NOT guaranteed by this runner. The only directory creation in the whole    chain is a side effect of run_alfresget_config →kdir(parents=True, exist_ok=True) (line 190), which is unreachable from main().

For contrast, the audited Level-C launcher does guarantee it: run_scoped_dir() (scripts/run_alfresco_levelc_metadata.py:146–147) returns /tmp/nv-alfresco-levelc-<pid></pid>, created at line 494–495 and removed in the finally at 541–543 unless --keep-run-dir.
2. Status artifact
                                                                                                           - Writer: nv_http_harness.py, write_st writes STATUS_PATH + ".tmp" then EXTERNAL_BLOCKERS =

## Minimal next step

                                                                                                             Do NOT execute it yet.

  D. POST-RUN EVIDENCE EXTRACTION

  For this first response, provide the commands/procedure only.
                                                                                                             Do not execute B/C.

  ============================================================
  10. IMPORTANT BEHAVIORAL RULE                                                                              ======================================

  Most questions should be resolvable from the source that is already
  present.

  If you encounter ambiguity:
  inspect source first.
                                                                                                             If source cannot resolve it:

  state exactly what is unknown.

  Do not silently guess.
                                                                                                             Do not modify anything during this fir

I'll start by verifying repository identity, then read the handoff document.
  Ran 1 shell command
Identity verified — all four facts match. Now the handoff document.

  Read 1 file
                                                                                                             Handoff read. Now the bounded runner —Q4/Q5.

Now the critical piece — exec_seq allocation and the sidecar in the harness.

  Searched for 2 patterns, listed 1 directory, ran 5 shell commands
                                                                                                             Now max_test_cases — Q5's core questio
                                                                                                             Searched for 5 patterns, read 1 file, ll commands

This is a key finding. Let me verify the production harness truly lacks the bridge that the offline fixture has.
                                                                                                             Ran 2 shell commands
re made. Everything below is derived from the current source.

PRE-RUN LOCAL GATE

PRE-RUN LOCAL GATE = NEEDS_MINIMAL_FIX
plus_other_AI_handoff_20260825.md
         ?? scripts/run_alfresco_bounded_feedback.py
         ?? tests/test_alfresco_bounded_feedback.py

Runner SHA256 = e9a61a0160c9601460219ed7e146728614fae8ead378aaccaca15e2dd119d546  (168 lines / 4284 bytes)  MATCH
Test   SHA256 = 9a7103982f73950afe6f43e1750c932c6e13bd20872f235b92dfbf40087e7516  (748 lines / 24548 bytes) MATCH

dentity facts match. No discrepancy.

Source-derived findings

1. Run-root

scripts/run_alfresco_bounded_feedback.py

- build_run_layout(run_root, repo_roote planning function. It resolves bothpaths, rejects run_root equal to or inside repo_root (line 91–92, RUN_ROOT_INSIDE_GIT_WORKTREE), and
  returns a dict of six paths: run_roo), seed (seed.http), status(nv_http_status.json), afl_output (afl-out), evidence (evidence).
- It creates nothing. No mkdir. It does not require run_root to pre-exist — Path.resolve() on a non-existent path is fine on Python 3.13.
- run_root is never selected by the prd parameter, and main() (lines 153–164)

2. Status artifact

- Writer: nv_http_harness.py, write_status() lines 265–317. Atomic: writes STATUS_PATH + ".tmp" then os.replace (313–317). This is the only production writer.
- Path: nv_http_harness.py:8 — STATUS_ATH", "/tmp/nv_http_status.json"),resolved once at module import.
- How the path is passed: by environment. scripts/run_alfresco_levelc_metadata.py:209 (harness_env) sets NV_STATUS_PATH = status_path_for(run_dir). For an AFL run it must be exported into afl-fuzz's
  environment, which both the C side ad read.
  run: only if NV_STATUS_PATH is unique per run. The bounded layout does this by construction (run_root/nv_http_status.json, line 98). Nothing enforces it.
- Historical /tmp status files are irrelevant to a new run: each is bound to its own NV_STATUS_PATH, and the C-side high-water lives in process memory (afl->nv_last_exec_seq), starting at 0.

3. exec_seq namespace and high-water p
   tp_harness.py, next_exec_seq() lines 204–262. Read-increment-persist under fcntl.flock(LOCK_EX) held on the sidecar itself (225–247), then fsync.

- Sidecar exists. Path: seq_sidecar_path() line 194–201 → STATUS_PATH + ".seq". For the bounded layout that is <run_root>/nv_http_status.json.seq.
- Namespace choice: the status-file path does determine the namespace — one sidecar per NV_STATUS_PATH
  (docstring, 197–199).
- Across process restart: the counter survives, because it is file-backed. This is the whole point (docstring 207–212): AFL runs the harness as a fresh process per execution, so the module-level SEQ
  (line 184, incremented at 285) is almented as legacy (comments 287–289).
- Validity rejection does NOT consume py:568–574: on not vr["ok"] thefunction bumps a body-valid stat and return 0 — before any write_status() call. Confirmed by the contract comment at lines 292–295. Note the consequence: on rejection no status document is written at all, so the previous run's document stays on disk.
- Observer/read-back does NOT consume server is AlfrescoClient.get_node /
  PRE_RUN_EXEC_SEQ_HIGH_WATER = H:

1. Fix S = the exact NV_STATUS_PATH the run will export.
2. Let K = S + ".seq".
3. If K does not exist            -> H = 0
   else read K, strip whitespace.
4. If empty or not an integer     -> H = 0
   If the integer is negative     -> H = 0
   else                           -> H = that integer

Freshness enforcement: nv_status_is_fresh() in src/afl-fuzz-nv-covset.c:89–113. When exec_seq > 0, exec_seq <= *last_exec_seq ⇒ NV_STATUS_REPLAY (line 99); accepted ids advance the high-water (101). A replay increments nv_sec_state_replays and returns before any state, credit, reward or MAB effect (afl-fuzz-run.c:194–199).

One real hazard this makes explicit: afl->nv_last_exec_seq starts at 0 in a calloc'd afl_state_t. If NV_STATUS_PATH were reused from a previous run, a leftover status document with exec_seq > 0 would be
consumed as fresh on the first read — h run_root is what prevents this, so it

Refuted as functional — the prior suspicion is confirmed.

scripts/run_alfresco_bounded_feedback.py:153–164:

parser.add_argument("--preflight-only", action="store_true")   # 155
parser.parse_args()                                            # 156  <-- result discarded
try:
    runtime_credentials()                                      # 159
except RuntimeError as exc:
    print(str(exc), file=sys.stderr); 1-162
except RuntimeError as exc:
    print(str(exc), file=sys.stderr); return 2                 # 161-162
return 0                                                       # 164

           │          │ None/empty/whitespace                                       │
├─────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────┤
│ Alfresco target/node        │ No       │ resolve_existing_dedicated_node (30–71) never called        │
│ resolution                  │          │                                                             │
├─────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────┤
│ Independent service GET     │ No                                        │
├─────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────┤
│ Target identity capture     │ No       │ render_runtime_target_config (73–80) never called           │
├─────────────────────────────┼──────────┼─────────────────────────────────────────────────────────────┤
│ Run-root preparation        │ No    ) never called                      │
───────────┼──────────┼─────────────────────────────────────────────────────────────┤
│ Any network access          │ No       │ —                                                           │
└─────────────────────────────┴──────────┴─────────────────────────────────────────────────────────────┘

The tests agree: --preflight-only appears in tests/test_alfresco_bounded_feedback.py:637 and :687 only as
an argv token inside credential-failur== 2 and MISSING_RUNTIME_CREDENTIALS.No test asserts preflight behaviour.

The real preflight already exists and C launcher: preflight() at
scripts/run_alfresco_levelc_metadata.phealth (docker_health, 406–427),unauthenticated root probe must return 401, authenticated must return 200.

5. max_test_cases accounting

(afl->stage_name, "dry_run") &&
             strcmp(afl->stage_name, "calibration"))))) {
  afl->nv_total_valid_exec++;
  if (afl->nv_task.max_test_cases &&
      afl->nv_total_valid_exec >= afl->nv_task.max_test_cases) {
    afl->stop_soon = 2;
    return res;
  }
}

ent                 │ Consumes  │                       Why                       │
│                                      │  a case?  │                                                 │
├──────────────────────────────────────┼───────────┼─────────────────────────────────────────────────┤
│                                      │           │ common_fuzz_stuff returns at                    │
│ C-side validity reject               │ No        │ afl-fuzz-run.c:2172–2176, before                │
│                                     t (2181)                          │
├──────────────────────────────────────┼───────────┼─────────────────────────────────────────────────┤
│ Adapter / Python body-validation     │           │ rejection happens inside the already-executed   │
│ reject                              n_target has returned, so the     │
────────────────────┼───────────┼─────────────────────────────────────────────────┤
│ Observer GET / read-back             │ No        │ in-process urllib, never goes through the       │
│                                      │           │ forkserver                                      │
├──────────────────────────────────────┼───────────┼─────────────────────────────────────────────────┤
│ Failed production execution          │ Yes       │ the target ran; the counter is                  │
│ (4xx/5xx/timeout/conn_refused)      ndent                             │
├──────────────────────────────────────┼───────────┼─────────────────────────────────────────────────┤
│ Dry run / calibration                │ No        │ excluded by the strcmp guard                    │
└───────────────────────────────────────────────────────────────────────┘

- Graceful termination at N: stop_soongraceful stop" (src/afl-fuzz.c:3709,4135). Normal shutdown runs, so fuzzer_stats and eval_report.json are written.
- One ordering consequence worth recording. On the Nth case, fuzz_run_target returns early at line 432. Back in common_fuzz_stuff, nv_observe_security_state still runs (line 2208) — so the Nth execution's state accounting and ss_cov_cnt credit are applied — but the very next block is if (afl->stop_soon) { pending_update = 0; return 1; } (2212–2216), so the Nth case's MAB reward is discarded. Expect
  nv_mab_total_pulls ≤ N−1 in a run te
  ───────────────────────────────┼───────────────────────────────────────────────────┤
  │ Validation  │ src/afl-fuzz-run.c:795–860,       │ FULL HTTP — sscanf(line, "%15s %255s"), path[0]   │
  │ boundary    │ nv_validity_check, called at 2167 │ == '/', nv_is_allowed_pair(), body must start     │
  │             │                                   │ with {/[                                          │
  ├─────────────┼───────────────────────────────────┼───────────────────────────────────────────────────┤
  │ Adapter     │ nv_http_body_adapter.pe-exact body                       │
  │             │ extract_http_body                 │                                                   │
  ├─────────────┼──────────────────────────────────────────────────────────┤
  │ Production  │                                   │ body-only JSON —                                  │
  │ harness     │ nv_http_harness.py:526–585        │ targets/alfresco_metadata_update.json:11 sets     │
  │             │                                   │ "body_only_mode": 1                               │
  └─────────────┴───────────────────────────────────┴───────────────────────────────────────────────────┘

l bounded run: every AFL-produced testcase is discarded inside the harness. No status document → no exec_seq → no observation → no security state → no ss_cov_cnt credit → no reward → no MAB update. The gate would burn its case budget and produce zero feedback evidence, while every HTTP-level assertion (no 5xx, no crash) would vacuously "pass".

Corroborating evidence that this link he real service:

- Seeds for the AFL metadata path are split by representation: in/alfresco_metadata_update_dataset/*.json and in/alfresco_afl_metadata_update_smoke/*.json are body-only; in/p0_alfresco_metadata_update/*.txt are FULL HTTP (PUT /alfresco/.../nodes/meta + blank line + JSON) and carry the literal placeholder node id
  meta.ace: the production harness must extract the body when the testcase carries an HTTP envelope, exactly as tests/fixtures/nv_feedback_fake_target.py:27 does.

7. Feedback / reward / MAB attribution

The chain, with the fields that actual

fuzz_run_target → status doc written by harness → nv_observe_security_state(afl, sp, &obs) (afl-fuzz-run.c:2208) → freshness → covset insert → credit → nv_reward_from_obs → nv_mab_update.

─────────────────────
Requested: NV_JSON_ARM_USED
Real field: exists — env handshake
Location: mutator sets it nv_json_mutator.py:129; fuzzer clears then re-reads src/afl-fuzz-one.c:1957,
1974–1988
──────────────────────────────────────
Requested: security_state_reward_src_seq
Real field: afl->nv_sec_state_reward_s
uzz-run.c:2262; emitted afl-fuzz-stats.c:439/452 and :732
────────────────────────────────────────
Requested: INSERTED / EXISTING / SATURATED
Real field: NV_COVSET_INSERTED / _EXISTING / _SATURATED from nv_covset_insert_into
Location: src/afl-fuzz-nv-covset.c:116+; wrapper afl-fuzz-run.c:109–118
──────────────────────────────────────
Requested: security_state_total
Real field: afl->nv_cov_used
Location: afl-fuzz-stats.c:443 (JSON),
────────────────────────────────────────
Requested: security_state_seed_credit
Real field: afl->nv_sec_state_seed_credit
Location: incremented afl-fuzz-run.c:3
l. afl-fuzz-run.c:271–303 — if NV_STATE_TRACE_PATH is set (resolved once, ck_strdup-copied), one JSON line is appended per consumed observation:

{"exec_seq":<n></n>,"state":"<METHOD PATH|CLASS>","state_id":"<hex></hex>","new":0|1}

This is the single most useful artifac is opt-in — set it.

R6 arm-confirmation holds. src/afl-fuzz-one.c:1974–1988: the reward arm is armed only when
NV_JSON_ARM_USED matches the picked arnding_update = 0. So the updated arm ismmediately before nv_mab_update (2262–2263), so reward source sequence == the fresh production exec_seq by construction.

Snapshot ordering is correct. obs is captured before save_if_interesting (2255), because that calls calibrate_case, which re-executes and overwrites the single status document — see the comment at
2183–2188. Reward is applied only from

8. Source queue entry credit

src/afl-fuzz-run.c:305–320:

if (is_new) {
  afl->nv_sec_state_new_total++;
  if (afl->queue_cur) {
    afl->queue_cur->ss_cov_cnt++;
 ss_prob: declared include/afl-fuzz.h:250ff; initialised in add_to_queue (src/afl-fuzz-queue.c:734–736: ss_cov_cnt=0, ss_selected_cnt=0, ss_prob=1.0); ss_selected_cnt is incremented on selection in select_next_queue_entry (afl-fuzz-queue.c:71, 88, 97); ss_prob is recomputed there (line 62).

One caveat that matters for Q10, not fd writer: src/afl-fuzz-bitmap.c:800–802

if (new_bits && afl->queue_cur) {
  afl->queue_cur->ss_cov_cnt += (new_bits == 2) ? 2 : 1;
}

This is AFL's native edge-coverage creue_cur, so exclusivity is preserved —or every live entry and accumulates total, on every call. Step 2 (77–92) is the roulette.

The property you asked for holds exactly: with the same queue entry and the same ss_selected_cnt, a higher ss_cov_cnt strictly increases the numerator, so ss_prob strictly increases, and the entry's share of
total strictly increases. No random drt, because ss_prob is persisted on theentry and exported: ss_prob_max at src/afl-fuzz-stats.c:838, alongside ss_cov_sum, ss_selected_sum, ss_cov_max2, ss_selected_max (835–838) and ss_cov_max at :810. ss_cov_cnt for the current entry is also written directly at afl-fuzz-stats.c:694–695.

fuzzer_stats and eval_report.json are written by the same function from the same snapshot — nv_write_eval_report_json is called at src/afl-fuzz-stats.c:881, inside the same write_stats_file that emits the fields at 689–838. Both therefore read identical in-memory values. summary.csv is derived, not independent: scripts/summarize_p0_mab_feedback.py reads fuzzer_stats + eval_report.json +
security_states.jsonl and copies fields header comment states "Nothing herecomputes metrics of its own."

Checkable after the bounded run:

✅ runtime security_state_total == fuzzer_stats security_state_total == eval_report.json security_state_total
All three are afl->nv_cov_used — afl-fuzz-stats.c:443 (JSON) and :716 (fuzzer_stats), forwarded by summarize_p0_mab_feedback.py:155. This is a true identity by construction, so it validates the reporting
path, not the arithmetic.

✅ sum(per-arm pulls) == nv_mab_total_pulls
nv_mab_update (src/afl-fuzz-nv-mab.c:1s and arms[arm].pulls together under asingle guarded path (arm bounds-checked at line 180), and is the only writer of either. Per-arm pulls are
emitted at afl-fuzz-stats.c:468–471 anne conservation check.

❌ sum(live queue ss_cov_cnt) == security_state_seed_credit — not valid as written.

ss_cov_cnt has two independent credit
rm equals ss_new_bits_any + (# events with new_bits == 2). ss_new_bits_any and ss_new_bits_kept are exported at afl-fuzz-stats.c:811–812, so the term is observable.

The clean way to make the desired equality hold is a run condition, not a code change: run with -n (non-instrumented), as every existing script does (run_p0_mab_feedback_experiment.sh:85, run_alfresco_afl_metadata_online_filter_smoke.sh:59). With no instrumentation the bitmap stays virgin,
new_bits stays 0, and the second term  conditional identity and verify itsprecondition:

if ss_new_bits_any == 0:      ss_cov_sum == security_state_seed_credit
otherwise:                    ss_cov_sdit

Blockers

CODE_BLOCKERS =

CB-1 — Representation bridge not wired into the production harness. (hard blocker; blocks the gate
regardless of who drives the run)
nv_http_harness.py:553–559 passes raw stdin to body_validate in body_only_mode, while nv_json_mutator.py:147 always emits FULL HTTP and src/afl-fuzz-run.c:795 validates FULL HTTP.
nv_http_body_adapter.extract_http_bodyt is called only fromtests/fixtures/nv_feedback_fake_target.py:27. Result: 100% body-validation rejection, zero status documents, zero exec_seq, zero feedback — while the run still consumes its case budget (see §5) and reports vacuous HTTP-level success.

Minimal fix (not a redesign): in nv_http_harness.py's body_only_mode branch, extract the HTTP body before
validating when the testcase carries aines the audited fixture already uses.Reuses an existing tested module; the Level-C body-only path must keep working, so the extraction has to be conditional on an envelope being present rather than mandatory.

CB-2 — Bounded runner main() is a stub. (blocks the automated path only)
scripts/run_alfresco_bounded_feedback.py:153–164 parses --preflight-only and discards it (§4), checks credential presence, returns. It never calls build_run_layout, resolve_existing_dedicated_node, or
render_runtime_target_config; it neverunches afl-fuzz, and exposes no

EXTERNAL_BLOCKERS =

- E-1 ALFRESCO_USER / ALFRESCO_PASS unset or blank. All three entry points fail closed: run_alfresco_bounded_feedback.py:138–150, run_alfresco_levelc_metadata.py:94–112, and the harness's _require_runtime_credential. No values requested, none printed.
- E-2 Approved node identity not yet rion requires a live authenticated GET,so it cannot be done offline.
- E-3 ./afl-fuzz build state not verified (the repo-root binary was not executed or stat-checked, per the
  read-only constraint).

Not blockers: git state, file identities, the offline feedback architecture, the C-side accounting, the scheduler, or the reporting path — all verified sound above.

Minimal next step

Do not execute B or C yet. CB-1 must be resolved first, or step C produces no feedback evidence.

A. LOCAL READ-ONLY PREPARATION

cd /home/dministrator/AFLplusplus-alfr

# A1. Re-confirm identity (must match §"Repository identity")

git rev-parse HEAD; git branch --show-current; git status --short
sha256sum scripts/run_alfresco_boundedsco_bounded_feedback.py
NV_RUN_ROOT"

# A5. Establish H from the run's OWN namespace (§3). Fresh root => H must be 0.

test -e "$NV_RUN_ROOT/nv_http_status.json.seq" 
  && cat "$NV_RUN_ROOT/nv_http_status.json.seq" 
  || echo "PRE_RUN_EXEC_SEQ_HIGH_WATER=0"

# Ignore every other */nv_http_status.t namespaces.

Then apply the CB-1 fix and run the fote, explicitly-approved editing task —it is out of scope for this read-only review, and I have not made the change.

B. HUMAN-EXECUTED REAL ALFRESCO PREFLIGHT

Load credentials with your existing ap not paste them into a shell that logs
eps it minimal; --keep-run-dir preserves evidence.
python3 scripts/run_alfresco_levelc_metadata.py 
  --rounds 1 
  --keep-run-dir 
  --evidence-dir "$NV_RUN_ROOT/evidence-preflight"

Record from its JSON summary, pseudony.status, unauthenticated_root (must be

C. BOUNDED REAL RUN

Only after CB-1 is fixed and B passes. Shape follows scripts/run_p0_mab_feedback_experiment.sh — that script is the audited precedent for every flag below.

mkdir -p "$NV_RUN_ROOT"

# C1. Render the run-scoped target config with the resolved node id

python3 - <<'PY'
import importlib.util, os
from pathlib import Path
spec = importlib.util.spec_from_file_location("b", "scripts/run_alfresco_bounded_feedback.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
root = Path(os.environ["NV_RUN_ROOT"])
print(m.render_runtime_target_config(o/ "target.json"))
PY

# C2. One FULL HTTP seed, node id matc

mkdir -p "$NV_RUN_ROOT/in"
printf 'PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/%s\nContent-Type:
application/json\n\n{"properties":{"cmription":"NV_BOUNDED"}}\n' 
$NV_RUN_ROOT/in/seed.http"

# C3. Task config: FIELD_VALUE arm only (mutation_scope bit 0x1 -> nv-mab.c:22)

cat > "$NV_RUN_ROOT/task.json" <<EOF
{
  "target_type": "http_api",
  "target_endpoint": "metadata_update"
  "seed_source": "seed_file",
  "seed_location": "$NV_RUN_ROOT/in",
  "mutation_scope": ["field_value"],
  "max_test_cases": 5,
  "time_budget": 120,
ONFIG="$NV_RUN_ROOT/target.json"
export NV_ENDPOINT_NAME="metadata_update"
export NV_BODY_RULES="$PWD/validity/alfresco_metadata_update_rules.json"
export NV_STATUS_PATH="$NV_RUN_ROOT/nv_http_status.json"
export NV_STATE_TRACE_PATH="$NV_RUN_ROOT/state_trace.jsonl"   # per-case audit trail
export NV_PROBE_PATH="$NV_RUN_ROOT/nv_probe.json"
export NV_STATE_DB="$NV_RUN_ROOT/nv_st
export NV_CTX_PATH="$NV_RUN_ROOT/nv_ctx.json"
export NV_ERR_DIR="$NV_RUN_ROOT/err_cases"
export NV_BODY_VALID_STATS="$NV_RUN_RO
export AFL_PYTHON_MODULE=nv_json_mutator
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
export AFL_NO_UI=1 AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1
unset AFL_NO_STARTUP_CALIBRATION      # else task.json is never loaded (afl-fuzz.c:3571)
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export no_proxy=127.0.0.1,localhost NO

# C5. Run. -n keeps ss_cov_cnt single-sourced (§10). timeout is the safety fuse.

timeout 180s ./afl-fuzz -n -m none -s
  -i "$NV_RUN_ROOT/in" -o "$NV_RUN_ROOT/afl-out" 
  -- python3 "$PWD/nv_http_harness.py"
echo "afl_exit=$?"

D. POST-RUN EVIDENCE EXTRACTION

# D2. R4/R6/R9 — accounting

grep -E 'nv_total_valid_exec|nv_valid_cnt|nv_invalid_|nv_max_test_cases|nv_mab_total_pulls|nv_mab_arm._pulls' "$S"
grep -E 'security_state_' "$S"

# D3. R5/R7 — seed credit and scheduler visibility

grep -E 'ss_cov_sum|ss_cov_max|ss_cov_max|ss_new_bits_any|ss_new_bits_kept'"$S"

# D4. R9 — the three conservation checks

python3 - <<'PY'
os.environ["NV_RUN_ROOT"]+"/afl-out/default/eval_report.json"))
c=ev["security_state_cov"]; m=ev["mab"]
print("state_total  stats==eval :", int(st["security_state_total"])==c["security_state_total"])
print("mab pulls    sum==total  :", sum(a["pulls"] for a in m["arms"])==m["total_pulls"])
bits=int(st["ss_new_bits_any"])
print("ss_new_bits_any          :", bits, "(must be 0 for the simple form)")
print("ss_cov_sum==seed_credit  :",
      int(st["ss_cov_sum"])==c["securis==0 else "N/A - use +bitmap form")
PY

# D5. R8 — independent read-back (obseo case budget)

python3 scripts/run_alfresco_levelc_metadata.py --rounds 1 --keep-run-dir 
  --evidence-dir "$NV_RUN_ROOT/evidence-postrun"

# Confirm the .seq sidecar above is UNCHANGED by this observer.

Report INCONCLUSIVE rather than PASS for R5 if security_state_new_total == 0 — with a single seed on one arm against a healthy service, all-2xx is a plausible and acceptable outcome in which no new state isminted and no seed credit can legitimately appear.
