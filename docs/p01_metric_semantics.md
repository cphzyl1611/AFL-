# P0.1 metric and configuration semantics

Reference for the NV feedback telemetry as of the P0.1 release-hardening round.
It resolves the semantic ambiguities raised as findings M-4, M-5, M-6 and M-10
in the independent post-fix review of `2283976`, and documents the counters
added by P0.1.

Nothing here changes a metric definition. Where a number was already correct
but easy to misread, this document states what it actually counts.

---

## 1. Configuration precedence (M-5, M-6)

```
valid NV_MAB_C / NV_MAB_MIN_EXPLORE      (highest)
    > valid task.json mab_c / mab_min_explore
        > compiled NV_MAB_DEFAULT_C / NV_MAB_DEFAULT_MIN_EXPLORE   (lowest)
```

**Validity is checked before precedence is applied.** A variable that merely
exists never suppresses a lower layer. Each of the following is discarded
exactly as if the variable had not been set, and the next layer down applies:

| Input | Treated as |
|---|---|
| unset | absent |
| empty string | absent |
| whitespace only | absent |
| unparseable (`abc`) | absent |
| trailing garbage (`0.5x`) | absent |
| `mab_c <= 0` | absent — see below |
| `mab_c` overflow (`1e400` → `inf`) | absent |
| `min_explore < 1` | absent |
| `min_explore > NV_MAB_MAX_MIN_EXPLORE` (10^6) | absent |
| `min_explore` overflow (`ERANGE`) | absent |

Before P0.1 the task.json layer was gated on `!getenv("NV_MAB_C")`, so
`NV_MAB_C=` or `NV_MAB_C=garbage` silently discarded a perfectly good
task.json value and fell all the way back to the compiled default.

### `mab_c = 0` is invalid input, not an opt-out (M-6)

`c = 0` collapses UCB into pure greedy selection. This project's main mode is
UCB adaptive mutation, so a zero coefficient is a misconfiguration and falls
back to the default like any other invalid value. The header contract
(`NV_MAB_DEFAULT_C`, "must be > 0") and the code now agree; previously the
header said one thing and the task.json path accepted `0`.

There is no supported pure-greedy mode. If one is ever required it should
arrive as an explicit mode selector, not by disabling the coefficient.

The effective values are always reported as `nv_mab_c` and
`nv_mab_min_explore` in `fuzzer_stats`, so the resolved outcome is auditable
without re-deriving the precedence by hand.

---

## 2. Picks are decisions; pulls are reward updates (M-4)

These count different events and are **not** expected to be equal.

| Field | Incremented in | Counts |
|---|---|---|
| `nv_mab_cold_start_picks` | `nv_mab_pick()` | warm-up **decisions** |
| `nv_mab_ucb_picks` | `nv_mab_pick()` | UCB **decisions** |
| `nv_mab_total_pulls` | `nv_mab_update()` | **reward updates** applied |
| `nv_mab_armN_pulls` | `nv_mab_update()` | reward updates for arm N |

So:

```
cold_start_picks + ucb_picks  =  number of nv_mab_pick() calls
nv_mab_total_pulls            =  number of nv_mab_update() calls
Σ armN_pulls                  =  nv_mab_total_pulls          (always)
```

A decision can legitimately produce no reward update. The bandit picks an arm
and exports it, but the custom mutator may return zero bytes, or may decline
to use the arm — the `NV_JSON_ARM_USED` handshake then clears
`pending_update`, and `common_fuzz_stuff()` books nothing. Every early-return
path in `common_fuzz_stuff()` also clears it.

Therefore `cold_start_picks + ucb_picks >= nv_mab_total_pulls`, with the gap
being decisions whose mutation never reached a scored execution. The P0
evidence for the alfresco profile shows exactly this: `24 + 179 = 203` against
`total_pulls = 202`. That is correct behaviour, not a counting error.

**Do not "fix" this by making the counters equal.** They answer different
questions: how often did the bandit choose, versus how often did it learn.

---

## 3. `ss_cov_cnt` has two credit sources (M-10)

| Field | Scope | Meaning |
|---|---|---|
| `queue_entry.ss_cov_cnt` | per seed | coverage credit for that seed |
| `ss_cov_sum` | aggregate | `Σ ss_cov_cnt` over the queue |
| `ss_cov_max` | aggregate | largest `ss_cov_cnt` in the queue |
| `security_state_seed_credit` | aggregate | times a seed was credited **for a new security state** |

`ss_cov_cnt` is incremented from **two independent sources**:

1. **AFL native edge novelty** — `save_if_interesting()` in
   `src/afl-fuzz-bitmap.c` adds `2` for `new_bits == 2`, else `1`. Pre-existing
   behaviour, unchanged.
2. **New security state** — `nv_observe_security_state()` in
   `src/afl-fuzz-run.c` adds `1`. Added by P0.

Consequently:

```
ss_cov_sum  ==  security_state_seed_credit     only when there is no edge credit
ss_cov_sum  >   security_state_seed_credit     on an instrumented target
```

Every archived P0/P0.1 deterministic run uses `-n` (non-instrumented), so
`new_bits` is always 0, no edge credit is ever added, and the two are equal.
**That equality is a property of `-n` mode, not an invariant.** On an
instrumented target they diverge, and `ss_cov_sum` is then a *mixed* quantity.

When a report needs the security-state signal alone, read
`security_state_seed_credit`. `ss_cov_sum` answers "what does the seed
scheduler see", which is deliberately both signals.

This does not affect the separation asserted in
`out/p0_edge_cov_smoke/BOUNDARY.md`: `security_state_total` and `edges_found`
remain wholly independent metrics. Only the *scheduler weight input* mixes
them.

---

## 4. Security-state counters

| Field | Meaning |
|---|---|
| `security_state_total` | distinct states in the covset (`nv_cov_used`) |
| `security_state_new_total` | cumulative first-time discoveries |
| `security_state_delta_last` | new states in the most recent observation |
| `security_state_observations` | executions whose status document was consumed |
| `security_state_seed_credit` | times a queue entry was credited for a new state |
| `security_state_capacity` | covset capacity (P0.1) |
| `security_state_saturated` | 1 once the covset ran out of capacity (P0.1) |
| `security_state_dropped` | states discarded because it was full (P0.1) |
| `security_state_replays` | status documents rejected as already consumed (P0.1) |
| `security_state_reward_src_seq` | execution id that fed the most recent reward (P0.1) |

### State identity

`fnv1a64("METHOD PATH|RESPONSE_CLASS")`, with every component folded onto a
finite set first (P0.1 M-1C), because all three arrive from a status document
that fuzzed bytes can reach:

- **METHOD** — one of `GET POST PUT PATCH DELETE HEAD OPTIONS`, else `INVALID`.
- **RESPONSE_CLASS** — one of `2xx 3xx 4xx 5xx conn_refused timeout`, else `other`.
- **PATH** — passed through when structurally sound; otherwise `malformed_path`
  (not absolute, longer than `NV_STATE_PATH_MAX` = 200, or containing
  non-printable bytes). When the task config declares an endpoint allowlist, a
  path outside it becomes `unknown_path`. With no config loaded,
  `nv_is_allowed_pair()` allows everything and the path passes through.

### Saturation

The covset is a fixed-capacity open-addressed table that is never resized.
Insertion probes at most `capacity` slots and then reports saturation: it does
not evict, does not count the state as new, and therefore cannot manufacture a
reward or a seed credit. Fuzzing continues with `security_state_saturated = 1`
and `security_state_dropped` rising, which is the signal that the state space
has outgrown the table.

### Replay identity

A status document must be consumed exactly once **per target execution**.
Identity is the execution, carried as `exec_seq` in the status document, not
the document's content. Two distinct executions may legitimately produce
byte-identical documents — same body, same response, same millisecond — and
both must count. When a harness does not report `exec_seq`, the legacy
`ts_ms ^ (body_hash16 << 32)` stamp is used as a fallback; it cannot
distinguish such executions, which is why `exec_seq` exists.

A *lower or equal* `exec_seq` than the last accepted one is replay-only. The
consumer retains its monotonic high-water mark, so stale documents cannot move
identity backwards and become fresh observations later. If the sequence
sidecar is lost while the consumer remains alive, fresh observations resume
only after the new counter exceeds the retained high-water mark.

---

## 5. Observation counts are not execution counts

`security_state_observations` is always lower than `execs_done`, by design:

- dry-run, calibration and trim executions never reach `common_fuzz_stuff()`
  and are never offered for consumption;
- executions abandoned on an early-return path (`stop_soon`, the timeout
  limit, `skip_requested`) are not scored;
- genuine replays are rejected.

`summary.csv` reports `state_log_records`, `state_log_minus_observations` and
`state_accounting_note` so the gap can be reconciled against the target's own
execution log.

---

## 6. Reproducibility vocabulary (M-9)

Two distinct claims; use the accurate one.

**Bit-identical** — every reported number is identical across runs at a pinned
AFL seed.

**Behaviourally reproducible** — the acceptance invariants hold identically,
while wall-clock-sensitive counters vary:

```
ucb_picks > 0
every enabled arm sampled
at least one mean_reward moved off its initial value
security states discovered
security_state_seed_credit > 0
ss_cov_sum > 0
the seed scheduler consumes the feedback
```

Measured at P0.1 over two runs per profile at AFL seed `20260816`
(`out/p01_*_repro_run{1,2}/`):

| Profile | Classification | Notes |
|---|---|---|
| `o2oa_cms_doc_list` | **behavioural** | arm pull split and observation counts vary between runs |
| `alfresco_metadata_update` | **behavioural** | same; total pulls varied 199–202 across runs |

**Neither profile is bit-identical, and neither should ever be described as
such.** Pinning the AFL seed fixes the mutation sequence, not the run: the
campaign stops on a `max_test_cases` / `time_budget` boundary, so how many
executions complete — and therefore the arm pull split, the observation count
and `nv_err_exec` — depends on machine speed.

This was measured twice. Two runs inside one worktree happened to produce a
bit-identical MAB metric set for `o2oa_cms_doc_list`, which looked like
stronger reproducibility than it is; repeating the same two runs in a clean
clone on the same machine produced `arm0_pulls` of 165 versus 92. Apparent
bit-identity across a pair of runs is not evidence of bit-identity — the
acceptance invariants in the list above are what actually hold.

---

## 7. Scope boundary

Every P0/P0.1 experiment referenced here runs against a local, network-free
deterministic target. None of it is a platform experiment, and none of it
touches a real O2OA, Alfresco or Flowable service. Conclusions about real
services depend solely on real-service evidence.
