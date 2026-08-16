# v0.7.1 — Execution identity for the real HTTP harness

Baseline: `v0.7.0-nv-feedback-release` (`a51ad6bb685c3f90a73494a2f211e5cf9c934a1c`).

The v0.7.0 independent audit closed with `REAL_HARNESS_REPLAY_UPGRADE = PARTIAL`:
the C side had execution-level replay identity, but `nv_http_harness.py` — the
harness every real HTTP chain uses — reported no `exec_seq`, so it fell back to
the legacy content stamp. This round closes that gap and nothing else.

---

## 1. What `exec_seq` means

`exec_seq` is the identity of **one real target execution inside one status
namespace** (one `NV_STATUS_PATH`).

- Two different executions always get different `exec_seq`, even when the
  request, the response, the body hash and the millisecond are all identical.
- Re-reading one execution's status document always yields the same `exec_seq`;
  that is what makes a second read a replay.
- Every outcome of an execution attempt carries one: `2xx`, `3xx`, `4xx`,
  `5xx`, `timeout`, `conn_refused`, and request exceptions.
- One logical AFL target execution consumes exactly one identity. Redirects,
  TCP retries and the post-exception `health_check()` probes happen *inside*
  one execution and do not allocate more, because allocation happens once, in
  `write_status()`, which runs once per execution.
- A testcase rejected by the validity layer never had a target execution, so it
  gets no identity at all — that path returns before `write_status()`.

The legacy `ts_ms ^ (body_hash16 << 32)` stamp is still written and still used
as a fallback by any harness that reports no `exec_seq`.

## 2. Why a file, not a variable

AFL++ runs the harness as:

```
afl-fuzz -n -i <in> -o <out> -- python3 nv_http_harness.py
```

There is no `__AFL_LOOP`, no persistent mode: `main()` reads stdin once and the
process exits. **The lifecycle is one fresh OS process per execution.**

That is measurable, not assumed. Before this change the harness already had a
module-level `SEQ` counter, and it reported `seq: 1` on every single execution —
a process-lifetime counter cannot identify an execution when the process only
ever handles one. The counter therefore has to outlive the process.

```
SEQUENCE_STORAGE   = <NV_STATUS_PATH>.seq   (one sidecar per status namespace)
ALLOCATION         = open → flock(LOCK_EX) → read → +1 → truncate → write → fsync → unlock
DEGRADED           = returns 0 if the sidecar cannot be maintained; the C side
                     reads 0 as "not reported" and uses the legacy fallback
```

The sidecar sits next to the status document, so instances with separate
`NV_STATUS_PATH` values — which is what `fuzz_gui.py` gives every instance —
never share a counter.

## 3. Process and restart behaviour

The counter is persistent, so it keeps rising across executions and across
harness processes. If the sidecar is deleted or lost, allocation restarts from
1.

That is safe by construction on the C side: `nv_status_is_fresh()` treats a
*lower* `exec_seq` as a restarted counter and resynchronises, rather than
locking the fuzzer out of every future observation. Only an *equal* id is a
replay. A restart therefore costs nothing beyond the one observation that
happens to collide, and cannot deadlock.

## 4. Concurrency assumption

Within one status namespace, AFL++ runs one target execution at a time, and the
repository ships no parallel `-M`/`-S` configuration. Allocation is still done
under an exclusive `flock` on the sidecar, so two harness processes that did
share a namespace could not be handed the same id.

The lock is held on the sidecar itself — no separate lock file is created, so
nothing extra appears next to the evidence.

## 5. Harness mapping

Every HTTP launcher in the repository — all ten scripts — runs the same target,
`nv_http_harness.py`. There is no per-platform harness. A "platform chain" is a
target config plus a request shape.

| Platform | Config | Launcher | Harness |
|---|---|---|---|
| O2OA | `targets/o2oa_query.json` | `scripts/run_o2oa_main_baseline_rule.sh`, `scripts/run_cms_*.sh` | `nv_http_harness.py` |
| Alfresco | caller-supplied `CFG` | `scripts/run_main_baseline_rule_generic.sh` | `nv_http_harness.py` |
| Flowable | `flowable_query.json` | *(no launcher references it)* | `nv_http_harness.py` if used |

The repository commits no Alfresco HTTP target config: the committed Alfresco
AFL work uses `targets/alfresco_*_mock.py` and `*_online_filter_wrapper.py`,
which write their own JSONL and **no NV status document at all**. An Alfresco
HTTP run is driven through the generic launcher, which is this same harness.

NV status writers, complete:

| Writer | `exec_seq` before | after |
|---|---|---|
| `nv_http_harness.py` | NO | **YES** |
| `targets/nv_p0_deterministic_target.py` | YES | YES |
| `test/p01/status_seq_target.c` | YES | YES |

`nv_state_probe.py` and `nv_neuron_probe.py` write `NV_PROBE_PATH`, a different
document that the replay consumer never reads; they are not status writers.

## 6. C-side compatibility

The C replay logic is **unchanged** in this round. `nv_status_is_fresh()`,
`nv_observe_security_state()` and the reward path are byte-identical to
v0.7.0.

Compatibility is verified by running the production consumer over documents the
real harness actually wrote (`test/v071/status_consumer_probe.c`, which links
`src/afl-fuzz-nv-covset.c`):

```
ACCEPT exec_seq=1 identity=exec_seq     execution #1
ACCEPT exec_seq=2 identity=exec_seq     execution #2, byte-identical request
REPLAY exec_seq=2 identity=exec_seq     re-read of #2
```

Under the legacy stamp the middle line would have been `REPLAY` and a real
observation would have been silently discarded.

## 7. Schema compatibility

The change is additive. Nothing was removed or renamed:

- `ts_ms` and `body_hash16` are still written, and still form the fallback
  identity for harnesses without `exec_seq`.
- The legacy `seq` field is still written. It is always `1` — that is what it
  always was — and is kept only so historical evidence and older consumers keep
  parsing. `exec_seq` is the real identity.

Historical evidence written before this change remains readable and is
unmodified.

## 8. Sequence state is runtime scratch

The sidecar is runtime state, not evidence. With the default
`NV_STATUS_PATH=/tmp/nv_http_status.json` it lives entirely outside the
repository; if a run places the status document under `out/`, the sidecar is
covered by the existing `out*/` ignore rule. Running the tests and the evidence
collector leaves `git status` unchanged.

## 9. What this release does NOT claim

```
This release does NOT claim:
- real O2OA full fuzzing
- real Alfresco full fuzzing
- real-service cross-platform migration VERIFIED
- Flowable full AFL++ chain
```

Also unchanged and unclaimed:

- No NC_MAB change, no security-state model change.
- No AE v1, fAnoGAN or SE-fAnoGAN-ES change. AE v1 remains primary, fAnoGAN
  remains a candidate, `FULL_SE_FANOGAN_ES = NO`.
- No long-running fuzzing campaign, no real service was contacted. Every
  execution in this round's evidence went to a local deterministic HTTP server
  on `127.0.0.1`.
- Flowable gains no AFL++ chain here. `flowable_query.json` would inherit the
  upgrade if it were ever driven through the shared harness; no launcher does.
