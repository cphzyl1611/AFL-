# Failure, Exclusion, and Stopping Rules

## Fail-Fast Validity Gates

Every run (AE or SE) must pass all applicable validity gates before the next run begins. This fail-fast policy was validated in Phase-3 and prevents invalid runs from polluting the experiment.

### Universal Validity Gates (AE and SE)

**Evidence Contract Gates:**

```
body_score_rpc_ok > 0
body_score_rpc_fail = 0
trace_invocations > 0
exact_backend_recorded = TRUE
trace_stats_reconciliation = PASS
artifact_contract = PASS
model_comparison_validity = PASS
readback = PASS
```

**Interpretation:**

- **body_score_rpc_ok > 0:** At least one successful RPC call to the scoring backend occurred
- **body_score_rpc_fail = 0:** No RPC failures occurred during the run
- **trace_invocations > 0:** The scorer trace mechanism was invoked at least once
- **exact_backend_recorded:** The run manifest records which backend (AE or SE) was used
- **trace_stats_reconciliation:** Trace file contents reconcile with reported counters
- **artifact_contract:** All required run artifacts (fuzzer_stats, manifest JSON, trace files) are present and parseable
- **model_comparison_validity:** The run is suitable for paired comparison (target baseline confirmed, seed recorded, etc.)
- **readback:** All emitted files can be read back and verified

### SE-Specific Validity Gates

**SE Provenance Gates:**

```
se_checkpoint_sha256 = 4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d
se_metadata_sha256 = 2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226
se_metadata_input_dim = 32
se_threshold = 1.2847454080581664
se_backend = sefanogan_es_reference
```

**Interpretation:**

SE runs must prove exact canonical model provenance. Any deviation from the frozen SE artifact invalidates the SE run.

### AE-Specific Validity Gates

**AE Configuration Gates:**

```
ae_backend = alfresco_ae_v1
ae_threshold = 1.623614
```

**Interpretation:**

AE runs must use the exact frozen AE configuration.

## Paired Block Validity

A paired block is valid for analysis only if **both** the AE run and SE run within the pair pass all applicable validity gates.

**If either run fails:**

- The entire paired block is excluded from the primary analysis
- The failure is recorded with detailed reason
- The seed is **not** replaced
- The next seed in the preregistered list is used

## Failure Classification

### Infrastructure Failure

**Definition:**

The experimental infrastructure failed, preventing the run from completing or producing valid artifacts.

**Examples:**

- Network outage during HTTP requests to the target
- Disk full, preventing fuzzer_stats from being written
- Process killed by OOM or system reboot
- Scorer RPC endpoint unreachable
- Git worktree corruption

**Recording:**

```json
{
  "failure_type": "infrastructure",
  "reason": "<specific error message>",
  "recoverable": false
}
```

**Action:**

- Exclude the paired block
- Do NOT replace the seed
- Continue with next seed

### Target Failure

**Definition:**

The target application failed in a way that invalidates the run.

**Examples:**

- Target crashed before any executions completed
- Target returned HTTP 500 for all requests (not a coverage finding, but a broken target)
- Target baseline could not be reset between runs

**Recording:**

```json
{
  "failure_type": "target",
  "reason": "<specific error message>",
  "recoverable": false
}
```

**Action:**

- Exclude the paired block
- Do NOT replace the seed
- If multiple consecutive target failures occur, **stop the entire campaign** and investigate

### Scorer Failure

**Definition:**

The scoring backend (AE or SE) failed to provide valid scores.

**Examples:**

- body_score_rpc_fail > 0
- Trace file not written
- SE checkpoint file not found or hash mismatch
- Scorer process crashed

**Recording:**

```json
{
  "failure_type": "scorer",
  "backend": "AE" or "SE",
  "reason": "<specific error message>",
  "recoverable": false
}
```

**Action:**

- Exclude the paired block
- Do NOT replace the seed
- If multiple consecutive scorer failures occur for one backend, **stop the entire campaign** and investigate

### Evidence Contract Failure

**Definition:**

The run completed, but the evidence artifacts do not satisfy the reproducibility contract.

**Examples:**

- trace_stats_reconciliation = FAIL (trace file disagrees with manifest counters)
- artifact_contract = FAIL (required file missing or unparseable)
- readback = FAIL (cannot re-read emitted JSON)

**Recording:**

```json
{
  "failure_type": "evidence_contract",
  "reason": "<specific contract violation>",
  "recoverable": false
}
```

**Action:**

- Exclude the paired block
- Do NOT replace the seed
- If evidence contract failures are systematic, **stop the entire campaign** and fix the harness

### Valid Zero Result (NOT a Failure)

**Definition:**

The run completed successfully, passed all validity gates, and observed `security_state_new_total = 0`.

**This is a scientific observation, not a failure.**

**Recording:**

```json
{
  "run_status": "valid",
  "security_state_new_total": 0
}
```

**Action:**

- Include the paired block in the primary analysis
- A valid zero is data, not an exclusion

## Stopping Rules

### Rule S1: Consecutive Infrastructure Failures

**Condition:**

If **3 consecutive paired blocks** fail due to infrastructure failures:

**Action:**

- **STOP the entire campaign immediately**
- Freeze all evidence to date
- Investigate and fix infrastructure
- Require human approval before resuming
- Do NOT automatically continue to the next seed

**Rationale:**

Consecutive infrastructure failures indicate systemic problems, not random transient errors.

### Rule S2: Consecutive Target Failures

**Condition:**

If **2 consecutive paired blocks** fail due to target failures:

**Action:**

- **STOP the entire campaign immediately**
- Freeze all evidence to date
- Investigate target stability
- Require human approval before resuming

**Rationale:**

Target failures invalidate the entire experimental premise. The protocol assumes a stable, reachable target.

### Rule S3: Consecutive Scorer Failures (Single Backend)

**Condition:**

If **3 consecutive paired blocks** fail due to scorer failures in the **same backend** (all AE or all SE):

**Action:**

- **STOP the entire campaign immediately**
- Freeze all evidence to date
- Investigate scorer backend
- Require human approval before resuming

**Rationale:**

Systematic scorer failures for one backend indicate a broken backend, not random errors.

### Rule S4: Evidence Contract Failures

**Condition:**

If **any 2 paired blocks** (not necessarily consecutive) fail due to evidence contract violations:

**Action:**

- **STOP the entire campaign immediately**
- Freeze all evidence to date
- Fix the evidence contract implementation
- Require human approval before resuming

**Rationale:**

Evidence contract failures compromise reproducibility. The protocol cannot proceed without trustworthy artifacts.

### Rule S5: Planned Completion

**Condition:**

All N preregistered seed blocks have been attempted (valid or failed).

**Action:**

- Campaign completes
- Report all results: valid blocks, excluded blocks, exclusion reasons
- Denominator remains N

### Rule S6: Early Stopping for Futility (Optional, Must Be Preregistered)

**If preregistered before execution:**

A blinded futility analysis may be performed at a preregistered interim point (e.g., after 50% of planned N).

**Blinding Requirement:**

The futility analysis must not reveal which backend is ahead. Analyze only:

- Observed variance of paired differences
- Probability of detecting a preregistered MPID given observed variance
- Feasibility of achieving target CI width

**Decision:**

If the study is clearly underpowered (e.g., observed variance is 10× higher than assumed), the protocol may allow early stopping with full transparent reporting.

**Not Permitted:**

- Stopping because "SE is winning" or "AE is losing"
- Stopping because Δ̄ is close to zero and "equivalence looks likely"
- Any unblinded early stopping based on model labels

## No Replacement Policy

**Critical Rule:**

Failed paired blocks are **never replaced** with new seeds.

**Rationale:**

- Replacement would allow post-hoc seed selection bias
- The denominator must remain the preregistered N
- Failures are part of the evidence and must be reported

**Reporting:**

The final report must include:

- N total preregistered blocks
- k successful blocks
- (N - k) failed blocks with detailed failure reasons
- Primary analysis based on k valid blocks
- Sensitivity analysis addressing potential selection bias if k << N

## Interruption and Restart Policy

### Interruption Between Completed Runs (Allowed)

**Condition:**

The campaign is interrupted after a run completes and all validity gates are checked, but before the next run starts.

**Examples:**

- Overnight pause between paired blocks
- Human review of intermediate results (as long as no stopping decision is based on unblinded model labels)

**Action:**

- Resume campaign with next seed in the frozen list
- Record interruption timestamp in evidence manifest
- No validity compromise

### Interruption Overlapping an Active Run (Invalidates Run)

**Condition:**

The campaign is interrupted while a run is actively executing (fuzzer is still running, time budget not yet expired).

**Examples:**

- Process killed mid-run
- System reboot during active fuzzing
- Manual Ctrl+C during a run

**Action:**

- The interrupted run is **invalid**
- The paired block containing that run is excluded
- Do NOT resume the interrupted run
- Start the next seed fresh

**Rationale:**

Interrupted runs may have incomplete coverage, partial timer budgets, or corrupted state. The protocol requires single-invocation, uninterrupted runs.

### Evidence Recording for Interruptions

Every run manifest must record:

- Start timestamp (ISO 8601)
- End timestamp (ISO 8601)
- Interruption flag (TRUE if the run was interrupted)
- Completion status (completed, interrupted, failed)

## Human Adjudication Gate

**Trigger Conditions:**

Any of the stopping rules S1-S4 trigger the human adjudication gate.

**Procedure:**

1. Campaign stops immediately
2. All evidence to date is frozen with SHA256 commitment
3. A failure analysis report is generated
4. Human reviewer examines:
   - Failure reasons
   - Systemic vs. transient errors
   - Whether protocol assumptions are still valid
5. Human decides:
   - Fix and resume (with documented changes)
   - Abandon campaign
   - Modify protocol (requires new preregistration)

**No Automatic Resumption:**

The protocol does not allow automatic resumption after hitting a stopping rule. Human judgment is required.

## Exclusion Reporting

The final evidence package must include:

```json
{
  "total_preregistered_blocks": N,
  "valid_blocks": k,
  "excluded_blocks": N - k,
  "exclusions": [
    {
      "seed": <integer>,
      "pair_index": <integer>,
      "failure_type": "<infrastructure|target|scorer|evidence_contract>",
      "failed_run": "<AE|SE|both>",
      "reason": "<detailed reason>",
      "timestamp": "<ISO 8601>"
    },
    ...
  ]
}
```

## Notes

- Fail-fast gates prevent invalid runs from continuing
- Valid zero results are included in analysis, not excluded
- Failures are never silently replaced
- Stopping rules protect against systemic failures
- All exclusions are transparently reported
- The denominator remains the preregistered N
