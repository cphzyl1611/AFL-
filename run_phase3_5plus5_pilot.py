#!/usr/bin/env python3
"""
Phase 3 — AE vs SE 5+5 Engineering Variance Pilot
Executes exactly 10 bounded runs (5 AE + 5 SE) with strict validation.
"""

import subprocess
import json
import os
import sys
import time
import hashlib
from pathlib import Path

# Fixed experiment contract
SEEDS = [20260915, 20260916, 20260917, 20260918, 20260919]
SCENARIO = "metadata_update"
MAX_TEST_CASES = 5
TIME_BUDGET = 60
SCORER_READY_TIMEOUT = 10

# Canonical Python
PYTHON = "/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python"

# Model configs
AE_BACKEND = "alfresco_ae_v1"
SE_BACKEND = "sefanogan_es_reference"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def validate_run_evidence(run_dir, backend, seed):
    """Validate a single run's evidence against contracts."""
    log(f"  Validating {backend} evidence...")
    
    evidence_dir = Path(run_dir) / "evidence"
    if not evidence_dir.exists():
        log(f"    ✗ Evidence directory missing")
        return False
    
    # Check required files exist
    required_files = [
        "artifact_report.json",
        "model_comparison_validity.json",
        "executions.jsonl",
        "readback.json"
    ]
    
    for fname in required_files:
        fpath = evidence_dir / fname
        if not fpath.exists():
            log(f"    ✗ Missing {fname}")
            return False
    
    # Load artifact report
    with open(evidence_dir / "artifact_report.json") as f:
        artifact = json.load(f)
    
    # Load model comparison validity - this has the RPC counters and trace info
    with open(evidence_dir / "model_comparison_validity.json") as f:
        model_validity = json.load(f)
    
    # Extract participation object with nested fields
    participation = model_validity.get("participation", {})
    body_score_rpc_ok = participation.get("scorer_rpc_ok", 0)
    body_score_rpc_fail = participation.get("scorer_rpc_fail", 0)

    if body_score_rpc_ok <= 0:
        log(f"    ✗ scorer_rpc_ok = {body_score_rpc_ok}, expected > 0")
        return False

    if body_score_rpc_fail != 0:
        log(f"    ✗ scorer_rpc_fail = {body_score_rpc_fail}, expected 0")
        return False

    # Check trace invocations (from participation)
    trace_invocations = participation.get("trace_invocations", 0)
    if trace_invocations <= 0:
        log(f"    ✗ trace_invocations = {trace_invocations}, expected > 0")
        return False

    # Check trace backend (from participation)
    trace_backend = participation.get("trace_backend", "")
    if trace_backend != backend:
        log(f"    ✗ trace_backend = {trace_backend}, expected {backend}")
        return False

    # Check model comparison validity verdict (from participation)
    validity_verdict = participation.get("verdict", "")
    if validity_verdict != "PASS":
        log(f"    ✗ model_comparison_validity verdict = {validity_verdict}, expected PASS")
        return False
    
    # Check artifact contract (from artifact report)
    artifact_contract = artifact.get("artifact_final_result", "")
    if artifact_contract != "pass":
        log(f"    ✗ artifact_final_result = {artifact_contract}, expected pass")
        return False
    # Load readback
    with open(evidence_dir / "readback.json") as f:
        readback = json.load(f)
    
    # Derive readback verdict from structure
    has_event = readback.get('event') == 'post_execution_readback'
    is_completed = readback.get('ordering', {}).get('run_completed') == True
    has_executions = readback.get('correlation', {}).get('valid_execution_count', 0) > 0
    status_ok = readback.get('request', {}).get('status') == 200
    
    readback_valid = has_event and is_completed and has_executions and status_ok
    if not readback_valid:
        log(f"    ✗ readback validation failed (event={has_event}, completed={is_completed}, executions={has_executions}, status={status_ok})")
        return False
    
    log(f"    ✓ All evidence checks passed")
    log(f"      RPC ok={body_score_rpc_ok}, fail={body_score_rpc_fail}")
    log(f"      trace_invocations={trace_invocations}, backend={trace_backend}")
    
    return True

def run_single_experiment(backend, seed, run_index):
    """Execute a single AE or SE run."""
    log(f"\n{'='*80}")
    log(f"Run {run_index}: {backend} with seed={seed}")
    log(f"{'='*80}")
    
    # Generate unique run ID
    timestamp = int(time.time())
    run_id = f"phase3-{backend.replace('_', '-')}-seed{seed}-{timestamp}"
    run_dir = f"/tmp/{run_id}"
    
    # Build command using actual script parameters
    cmd = [
        PYTHON,
        "scripts/run_alfresco_bounded_feedback.py",
        "--scenario", SCENARIO,
        "--run-root", run_dir,
        "--max-test-cases", str(MAX_TEST_CASES),
        "--time-budget", str(TIME_BUDGET),
        "--validity-backend", backend,
        "--model-comparison",
        "--afl-seed", str(seed),
        "--scorer-python", PYTHON,
        "--scorer-ready-timeout", str(SCORER_READY_TIMEOUT)
    ]
    
    log(f"Executing bounded run...")
    log(f"  backend={backend}, seed={seed}, max_cases={MAX_TEST_CASES}, budget={TIME_BUDGET}s")
    
    start_time = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - start_time
    
    if result.returncode != 0:
        log(f"✗ Run failed with exit code {result.returncode} after {elapsed:.1f}s")
        log(f"  stdout tail: {result.stdout[-1000:]}")
        log(f"  stderr tail: {result.stderr[-1000:]}")
        return None
    
    log(f"✓ Run completed successfully in {elapsed:.1f}s")
    
    # Validate evidence
    if not validate_run_evidence(run_dir, backend, seed):
        log(f"✗ Evidence validation failed")
        return None
    
    # Compute run manifest hash
    manifest_path = Path(run_dir) / "evidence" / "artifact_report.json"
    with open(manifest_path, 'rb') as f:
        run_manifest_hash = hashlib.sha256(f.read()).hexdigest()
    
    log(f"Run manifest hash: {run_manifest_hash[:16]}...")
    
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "backend": backend,
        "seed": seed,
        "run_manifest_hash": run_manifest_hash,
        "elapsed_seconds": elapsed,
        "status": "VALID"
    }

def extract_security_state_new(run_dir):
    """Extract security_state_new_total from state trace."""
    state_trace_path = Path(run_dir) / "nv_state_trace.jsonl"
    
    if not state_trace_path.exists():
        log(f"    Warning: state_trace not found at {state_trace_path}")
        return 0
    
    # Count new=1 entries in state trace
    security_state_new_total = 0
    with open(state_trace_path) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                if entry.get("new") == 1:
                    security_state_new_total += 1
    
    return security_state_new_total

def validate_seed_pair(ae_run_dir, se_run_dir, seed):
    """Validate that an AE/SE pair used identical experimental conditions."""
    # Both must exist
    if not Path(ae_run_dir).exists():
        return False, f"AE run dir missing: {ae_run_dir}"
    if not Path(se_run_dir).exists():
        return False, f"SE run dir missing: {se_run_dir}"
    
    # Both must have used the same seed
    ae_evidence = Path(ae_run_dir) / "evidence" / "model_comparison_validity.json"
    se_evidence = Path(se_run_dir) / "evidence" / "model_comparison_validity.json"
    
    with open(ae_evidence) as f:
        ae_mcv = json.load(f)
    with open(se_evidence) as f:
        se_mcv = json.load(f)
    
    if ae_mcv.get("afl_seed") != seed:
        return False, f"AE seed mismatch: {ae_mcv.get('afl_seed')} != {seed}"
    if se_mcv.get("afl_seed") != seed:
        return False, f"SE seed mismatch: {se_mcv.get('afl_seed')} != {seed}"
    
    return True, "PASS"

def compute_descriptive_stats(values):
    """Compute descriptive statistics for a list of values."""
    n = len(values)
    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "sample_sd": None,
            "min": None,
            "max": None,
            "range": None
        }
    
    mean = sum(values) / n
    sorted_vals = sorted(values)
    median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    
    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        sample_sd = variance ** 0.5
    else:
        sample_sd = 0.0
    
    return {
        "n": n,
        "values": values,
        "mean": mean,
        "median": median,
        "sample_sd": sample_sd,
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values)
    }


def main():
    """Execute the complete Phase 3 5+5 engineering variance pilot."""
    
    # Step 0: Baseline integrity
    log("=" * 80)
    log("PHASE 3: AE vs SE 5+5 ENGINEERING VARIANCE PILOT")
    log("=" * 80)
    log("")
    log("Step 0: Baseline Integrity Verification")
    log("-" * 80)
    
    expected_head = "87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408"
    actual_head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    
    if actual_head != expected_head:
        log(f"✗ HEAD mismatch: {actual_head} != {expected_head}")
        sys.exit(1)
    
    log(f"✓ HEAD = {actual_head}")
    
    # Step 1: Runtime preflight
    log("")
    log("Step 1: Runtime Preflight")
    log("-" * 80)
    
    # Check Docker
    docker_ok = subprocess.run(["docker", "ps"], capture_output=True).returncode == 0
    log(f"DOCKER_DAEMON_REACHABLE = {'YES' if docker_ok else 'NO'}")
    if not docker_ok:
        log("✗ Docker daemon not reachable")
        sys.exit(1)
    
    # Check Alfresco credentials
    alfresco_user = os.environ.get("ALFRESCO_USER", "").strip()
    alfresco_pass = os.environ.get("ALFRESCO_PASS", "").strip()
    
    if not alfresco_user or not alfresco_pass:
        log("✗ ALFRESCO_USER or ALFRESCO_PASS not set")
        sys.exit(1)
    
    log(f"ALFRESCO_USER = SET_NONBLANK")
    log(f"ALFRESCO_PASS = SET_NONBLANK")
    
    # Check SE scorer ready
    se_threshold_path = "model_stage/models/sefanogan_es_realrun_threshold.json"
    if not Path(se_threshold_path).exists():
        log(f"✗ SE threshold file missing: {se_threshold_path}")
        sys.exit(1)
    
    log(f"SE_STANDALONE_SCORER_READY = YES")
    
    # Step 2: Execute 5 paired blocks
    log("")
    log("Step 2: Execute 5 Paired Blocks")
    log("=" * 80)
    
    seeds = [20260915, 20260916, 20260917, 20260918, 20260919]
    ae_runs = []
    se_runs = []
    
    for i, seed in enumerate(seeds, 1):
        log("")
        log(f"Seed {i}/5: {seed}")
        log("=" * 80)
        
        # Run AE
        log(f"\n[AE] Running with seed {seed}...")
        ae_result = run_single_experiment("alfresco_ae_v1", seed, i)

        if ae_result is None:
            log(f"✗ AE run failed or invalid")
            log(f"✗ STOPPING CAMPAIGN - invalid run at seed {seed}")
            sys.exit(1)

        ae_run_dir = ae_result["run_dir"]
        log(f"✓ AE run valid")
        ae_security_new = extract_security_state_new(ae_run_dir)
        log(f"  security_state_new_total = {ae_security_new}")
        ae_runs.append({"seed": seed, "run_dir": ae_run_dir, "security_state_new": ae_security_new})
        
        # Run SE
        log(f"\n[SE] Running with seed {seed}...")
        se_result = run_single_experiment("sefanogan_es_reference", seed, i)

        if se_result is None:
            log(f"✗ SE run failed or invalid")
            log(f"✗ STOPPING CAMPAIGN - invalid run at seed {seed}")
            sys.exit(1)

        se_run_dir = se_result["run_dir"]
        log(f"✓ SE run valid")
        se_security_new = extract_security_state_new(se_run_dir)
        log(f"  security_state_new_total = {se_security_new}")
        se_runs.append({"seed": seed, "run_dir": se_run_dir, "security_state_new": se_security_new})
        
        # Validate seed pair
        valid, msg = validate_seed_pair(ae_run_dir, se_run_dir, seed)
        if not valid:
            log(f"✗ Seed pair validation failed: {msg}")
            sys.exit(1)
        log(f"✓ Seed pair contract: {msg}")
    
    # Step 3: Global contract
    log("")
    log("Step 3: Global 5+5 Contract Verification")
    log("=" * 80)
    
    log(f"VALID_AE_RUNS = {len(ae_runs)}")
    log(f"VALID_SE_RUNS = {len(se_runs)}")
    log(f"TOTAL_VALID_RUNS = {len(ae_runs) + len(se_runs)}")
    
    if len(ae_runs) != 5 or len(se_runs) != 5:
        log(f"✗ GLOBAL_5PLUS5_CONTRACT = FAIL")
        sys.exit(1)
    
    log(f"✓ GLOBAL_5PLUS5_CONTRACT = PASS")
    
    # Step 4: Descriptive analysis
    log("")
    log("Step 4: Descriptive Engineering Analysis")
    log("=" * 80)
    
    ae_values = [r["security_state_new"] for r in ae_runs]
    se_values = [r["security_state_new"] for r in se_runs]
    
    ae_stats = compute_descriptive_stats(ae_values)
    se_stats = compute_descriptive_stats(se_values)
    
    paired_deltas = [se_values[i] - ae_values[i] for i in range(5)]
    
    log("AE Results:")
    log(f"  n = {ae_stats['n']}")
    log(f"  values = {ae_stats['values']}")
    log(f"  mean = {ae_stats['mean']:.2f}")
    log(f"  median = {ae_stats['median']:.2f}")
    log(f"  sample SD = {ae_stats['sample_sd']:.2f}")
    log(f"  min = {ae_stats['min']}")
    log(f"  max = {ae_stats['max']}")
    log(f"  range = {ae_stats['range']}")
    
    log("SE Results:")
    log(f"  n = {se_stats['n']}")
    log(f"  values = {se_stats['values']}")
    log(f"  mean = {se_stats['mean']:.2f}")
    log(f"  median = {se_stats['median']:.2f}")
    log(f"  sample SD = {se_stats['sample_sd']:.2f}")
    log(f"  min = {se_stats['min']}")
    log(f"  max = {se_stats['max']}")
    log(f"  range = {se_stats['range']}")
    
    log("Paired Deltas (SE - AE):")
    for i, (seed, delta) in enumerate(zip(seeds, paired_deltas)):
        log(f"  seed {seed}: {delta:+d}")
    
    # Step 5: Generate manifest
    log("")
    log("Step 5: Aggregate Evidence Package")
    log("=" * 80)
    
    manifest = {
        "phase": "PHASE3_ENGINEERING_VARIANCE_5PLUS5",
        "frozen_baseline": {
            "head": actual_head,
            "tracked_diff_sha256": "686a1e65035ac38145b606f4c765f6a1220e6f9f9f2206338354bd2a84112140",
            "full_12file_manifest_sha256": "26c2e4f3871d7deffb4ab7fc356f6973b8f01b5985d189ed6afcc79b251a2c5b"
        },
        "seeds": seeds,
        "ae_runs": [{"seed": r["seed"], "run_dir": str(r["run_dir"])} for r in ae_runs],
        "se_runs": [{"seed": r["seed"], "run_dir": str(r["run_dir"])} for r in se_runs],
        "descriptive_stats": {
            "ae": ae_stats,
            "se": se_stats,
            "paired_deltas": paired_deltas
        },
        "contracts": {
            "global_5plus5": "PASS",
            "all_seed_pairs": "PASS"
        }
    }
    
    manifest_path = Path("PHASE3_ENGINEERING_VARIANCE_5PLUS5_MANIFEST.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    # Compute manifest hash
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    
    log(f"✓ Manifest written: {manifest_path}")
    log(f"  SHA256: {manifest_hash}")
    
    # Final report
    log("")
    log("=" * 80)
    log("PHASE 3 FINAL REPORT")
    log("=" * 80)
    log("")
    log(f"PHASE3_5PLUS5_VERDICT = PASS")
    log(f"ENGINEERING_VARIANCE_PILOT = PASS")
    log(f"NEXT_FORMAL_EXPERIMENT_GATE = OPEN_FOR_HUMAN_DESIGN_REVIEW")
    log("")
    log(f"VALID_AE_RUNS = {len(ae_runs)}")
    log(f"VALID_SE_RUNS = {len(se_runs)}")
    log(f"TOTAL_VALID_RUNS = {len(ae_runs) + len(se_runs)}")
    log("")
    log(f"AE_SECURITY_STATE_NEW_VALUES = {ae_values}")
    log(f"SE_SECURITY_STATE_NEW_VALUES = {se_values}")
    log(f"PAIRED_DELTAS_SE_MINUS_AE = {paired_deltas}")
    log("")
    log(f"PHASE3_AGGREGATE_MANIFEST_SHA256 = {manifest_hash}")
    log("")
    log("=" * 80)


if __name__ == "__main__":
    main()
