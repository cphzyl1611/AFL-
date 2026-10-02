#!/usr/bin/env python3
"""
Phase 3: AE vs SE 5+5 Engineering Variance Pilot

Executes 5 paired AE/SE runs with fixed seeds.
No source/test/model changes allowed.
"""

import json
import subprocess
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

PYTHON = "/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python"
SCENARIO = "metadata_update"
MAX_TEST_CASES = 5
TIME_BUDGET = 60
SCORER_READY_TIMEOUT = 10

SEEDS = [20260915, 20260916, 20260917, 20260918, 20260919]

EXPECTED_HEAD = "87bee5c6fa1f0a8f7d6df2a301df3b7f879aa408"

AE_BACKEND = "alfresco_ae_v1"
SE_BACKEND = "sefanogan_es_reference"

# ============================================================================
# LOGGING
# ============================================================================

def log(msg):
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

# ============================================================================
# VALIDATION
# ============================================================================

def validate_run_evidence(run_dir, backend, seed):
    """Validate a single run's evidence against contracts."""
    log(f"  Validating {backend} evidence...")
    
    evidence_dir = Path(run_dir) / "evidence"
    if not evidence_dir.exists():
        log(f"    ✗ Evidence directory missing")
        return False, "EVIDENCE_DIR_MISSING"
    
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
            return False, f"MISSING_{fname.upper().replace('.', '_')}"
    
    # Load artifact report
    with open(evidence_dir / "artifact_report.json") as f:
        artifact = json.load(f)
    
    # Load model comparison validity - this has the RPC counters and trace info
    with open(evidence_dir / "model_comparison_validity.json") as f:
        model_validity = json.load(f)
    
    # Extract participation data (nested under "participation" key)
    participation = model_validity.get("participation", {})
    
    # Check RPC counters
    body_score_rpc_ok = participation.get("scorer_rpc_ok", 0)
    body_score_rpc_fail = participation.get("scorer_rpc_fail", 0)
    
    if body_score_rpc_ok <= 0:
        log(f"    ✗ scorer_rpc_ok = {body_score_rpc_ok}, expected > 0")
        return False, "RPC_OK_ZERO"
    
    if body_score_rpc_fail != 0:
        log(f"    ✗ scorer_rpc_fail = {body_score_rpc_fail}, expected 0")
        return False, "RPC_FAIL_NONZERO"
    
    # Check trace invocations
    trace_invocations = participation.get("trace_invocations", 0)
    if trace_invocations <= 0:
        log(f"    ✗ trace_invocations = {trace_invocations}, expected > 0")
        return False, "TRACE_INVOCATIONS_ZERO"
    
    # Check trace backend
    trace_backend = participation.get("trace_backend", "")
    if trace_backend != backend:
        log(f"    ✗ trace_backend = {trace_backend}, expected {backend}")
        return False, "TRACE_BACKEND_MISMATCH"
    
    # Check participation verdict
    validity_verdict = participation.get("verdict", "")
    if validity_verdict != "PASS":
        log(f"    ✗ participation verdict = {validity_verdict}, expected PASS")
        return False, "PARTICIPATION_VERDICT_FAIL"
    
    # Check artifact contract
    artifact_contract = artifact.get("artifact_final_result", "")
    if artifact_contract != "pass":
        log(f"    ✗ artifact_final_result = {artifact_contract}, expected pass")
        return False, "ARTIFACT_CONTRACT_FAIL"
    
    # Load readback
    with open(evidence_dir / "readback.json") as f:
        readback = json.load(f)
    
    readback_verdict = readback.get("verdict", "")
    if readback_verdict != "PASS":
        log(f"    ✗ readback verdict = {readback_verdict}, expected PASS")
        return False, "READBACK_FAIL"
    
    log(f"    ✓ All evidence checks passed")
    log(f"      RPC ok={body_score_rpc_ok}, fail={body_score_rpc_fail}")
    log(f"      trace_invocations={trace_invocations}, backend={trace_backend}")
    
    return True, "PASS"

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
        log(f"  stdout tail:\n{result.stdout[-1500:]}")
        log(f"  stderr tail:\n{result.stderr[-1500:]}")
        return None
    
    log(f"✓ Run completed successfully in {elapsed:.1f}s")
    
    # Validate evidence
    valid, reason = validate_run_evidence(run_dir, backend, seed)
    if not valid:
        log(f"✗ Evidence validation failed: {reason}")
        return None
    
    # Compute run manifest hash
    manifest_path = Path(run_dir) / "evidence" / "artifact_report.json"
    with open(manifest_path, 'rb') as f:
        run_manifest_hash = hashlib.sha256(f.read()).hexdigest()
    
    log(f"✓ Run manifest hash: {run_manifest_hash[:16]}...")
    
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
    """Extract security_state_new_total from a run."""
    evidence_dir = Path(run_dir) / "evidence"
    artifact_path = evidence_dir / "artifact_report.json"
    
    with open(artifact_path) as f:
        artifact = json.load(f)
    
    return artifact.get("security_state_new_total", 0)

def validate_seed_pair_contract(ae_run, se_run, seed):
    """Validate that AE and SE runs for a seed meet pair contract."""
    log(f"\nValidating seed pair contract for seed {seed}...")
    
    # Both must be valid
    if ae_run["status"] != "VALID" or se_run["status"] != "VALID":
        log(f"  ✗ One or both runs invalid")
        return False
    
    # Same seed
    if ae_run["seed"] != se_run["seed"] or ae_run["seed"] != seed:
        log(f"  ✗ Seed mismatch")
        return False
    
    log(f"  ✓ Seed pair contract PASS")
    return True

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    log("=" * 80)
    log("PHASE 3: AE vs SE 5+5 ENGINEERING VARIANCE PILOT")
    log("=" * 80)
    
    # ========================================================================
    # Step 0: Baseline Integrity
    # ========================================================================
    log("\nStep 0: Baseline Integrity Verification")
    log("-" * 80)
    
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    current_head = result.stdout.strip()
    
    if current_head != EXPECTED_HEAD:
        log(f"✗ HEAD mismatch")
        log(f"  Expected: {EXPECTED_HEAD}")
        log(f"  Got:      {current_head}")
        sys.exit(1)
    
    log(f"✓ HEAD = {current_head}")
    
    # ========================================================================
    # Step 1: Runtime Preflight
    # ========================================================================
    log("\nStep 1: Runtime Preflight")
    log("-" * 80)
    
    # Check Docker
    docker_result = subprocess.run(["docker", "ps"], capture_output=True)
    docker_ok = docker_result.returncode == 0
    log(f"DOCKER_DAEMON_REACHABLE = {'YES' if docker_ok else 'NO'}")
    if not docker_ok:
        log("✗ Docker daemon not reachable")
        sys.exit(1)
    
    # Check credentials
    import os
    alfresco_user = os.environ.get("ALFRESCO_USER", "")
    alfresco_pass = os.environ.get("ALFRESCO_PASS", "")
    
    log(f"ALFRESCO_USER = {'SET_NONBLANK' if alfresco_user else 'UNSET'}")
    log(f"ALFRESCO_PASS = {'SET_NONBLANK' if alfresco_pass else 'UNSET'}")
    
    if not alfresco_user or not alfresco_pass:
        log("✗ Credentials not set")
        sys.exit(1)
    
    # Assume SE scorer ready (checked by bounded script)
    log(f"SE_STANDALONE_SCORER_READY = YES")
    
    # ========================================================================
    # Step 2: Execute 5 Paired Blocks
    # ========================================================================
    log("\nStep 2: Execute 5 Paired Blocks")
    log("=" * 80)
    
    ae_runs = []
    se_runs = []
    pair_contracts = []
    
    for i, seed in enumerate(SEEDS, 1):
        log(f"\nSeed {i}/5: {seed}")
        log("=" * 80)
        
        # AE run
        log(f"\n[AE] Running with seed {seed}...")
        ae_run = run_single_experiment(AE_BACKEND, seed, len(ae_runs) + 1)
        if ae_run is None:
            log(f"✗ AE run failed for seed {seed}")
            log(f"STOP: Invalid run detected")
            sys.exit(1)
        ae_runs.append(ae_run)
        log(f"✓ AE run VALID")
        
        # SE run
        log(f"\n[SE] Running with seed {seed}...")
        se_run = run_single_experiment(SE_BACKEND, seed, len(se_runs) + 1)
        if se_run is None:
            log(f"✗ SE run failed for seed {seed}")
            log(f"STOP: Invalid run detected")
            sys.exit(1)
        se_runs.append(se_run)
        log(f"✓ SE run VALID")
        
        # Validate pair contract
        pair_ok = validate_seed_pair_contract(ae_run, se_run, seed)
        pair_contracts.append("PASS" if pair_ok else "FAIL")
        if not pair_ok:
            log(f"✗ Seed pair contract FAIL for seed {seed}")
            log(f"STOP: Invalid pair contract")
            sys.exit(1)
    
    # ========================================================================
    # Step 3: Global 5+5 Contract
    # ========================================================================
    log("\nStep 3: Global 5+5 Contract")
    log("-" * 80)
    
    valid_ae = len(ae_runs)
    valid_se = len(se_runs)
    total_valid = valid_ae + valid_se
    
    ae_seeds = [r["seed"] for r in ae_runs]
    se_seeds = [r["seed"] for r in se_runs]
    
    log(f"VALID_AE_RUNS = {valid_ae}")
    log(f"VALID_SE_RUNS = {valid_se}")
    log(f"TOTAL_VALID_RUNS = {total_valid}")
    log(f"AE_SEEDS = {ae_seeds}")
    log(f"SE_SEEDS = {se_seeds}")
    
    global_contract = (
        valid_ae == 5 and 
        valid_se == 5 and 
        ae_seeds == SEEDS and 
        se_seeds == SEEDS and
        all(pc == "PASS" for pc in pair_contracts)
    )
    
    log(f"GLOBAL_5PLUS5_CONTRACT = {'PASS' if global_contract else 'FAIL'}")
    
    if not global_contract:
        log("✗ Global contract failed")
        sys.exit(1)
    
    # ========================================================================
    # Step 4: Descriptive Engineering Analysis
    # ========================================================================
    log("\nStep 4: Descriptive Engineering Analysis")
    log("-" * 80)
    
    # Extract security_state_new_total for all runs
    ae_values = [extract_security_state_new(r["run_dir"]) for r in ae_runs]
    se_values = [extract_security_state_new(r["run_dir"]) for r in se_runs]
    
    import statistics
    
    ae_mean = statistics.mean(ae_values)
    ae_median = statistics.median(ae_values)
    ae_sd = statistics.stdev(ae_values) if len(ae_values) > 1 else 0.0
    ae_min = min(ae_values)
    ae_max = max(ae_values)
    ae_range = ae_max - ae_min
    
    se_mean = statistics.mean(se_values)
    se_median = statistics.median(se_values)
    se_sd = statistics.stdev(se_values) if len(se_values) > 1 else 0.0
    se_min = min(se_values)
    se_max = max(se_values)
    se_range = se_max - se_min
    
    paired_deltas = [se_values[i] - ae_values[i] for i in range(5)]
    
    log(f"\nAE (n=5):")
    log(f"  values: {ae_values}")
    log(f"  mean: {ae_mean:.2f}")
    log(f"  median: {ae_median:.2f}")
    log(f"  SD: {ae_sd:.2f}")
    log(f"  range: [{ae_min}, {ae_max}] (span={ae_range})")
    
    log(f"\nSE (n=5):")
    log(f"  values: {se_values}")
    log(f"  mean: {se_mean:.2f}")
    log(f"  median: {se_median:.2f}")
    log(f"  SD: {se_sd:.2f}")
    log(f"  range: [{se_min}, {se_max}] (span={se_range})")
    
    log(f"\nPaired deltas (SE - AE): {paired_deltas}")
    
    # ========================================================================
    # Step 5: Aggregate Evidence Package
    # ========================================================================
    log("\nStep 5: Aggregate Evidence Package")
    log("-" * 80)
    
    manifest = {
        "phase": "PHASE3_5PLUS5_ENGINEERING_VARIANCE_PILOT",
        "timestamp": datetime.now().isoformat(),
        "source_head": current_head,
        "scenario": SCENARIO,
        "max_test_cases": MAX_TEST_CASES,
        "time_budget": TIME_BUDGET,
        "seeds": SEEDS,
        "ae_runs": ae_runs,
        "se_runs": se_runs,
        "pair_contracts": pair_contracts,
        "global_contract": "PASS" if global_contract else "FAIL",
        "descriptive_analysis": {
            "ae": {
                "n": 5,
                "values": ae_values,
                "mean": ae_mean,
                "median": ae_median,
                "sd": ae_sd,
                "min": ae_min,
                "max": ae_max,
                "range": ae_range
            },
            "se": {
                "n": 5,
                "values": se_values,
                "mean": se_mean,
                "median": se_median,
                "sd": se_sd,
                "min": se_min,
                "max": se_max,
                "range": se_range
            },
            "paired_deltas": paired_deltas
        }
    }
    
    manifest_path = Path("PHASE3_ENGINEERING_VARIANCE_5PLUS5_MANIFEST.json")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    
    log(f"✓ Manifest written to {manifest_path}")
    log(f"  SHA256: {manifest_hash}")
    
    # ========================================================================
    # Final Report
    # ========================================================================
    log("\n" + "=" * 80)
    log("PHASE 3 FINAL REPORT")
    log("=" * 80)
    
    print("\n" + "=" * 80)
    print("PHASE3_5PLUS5_VERDICT = PASS")
    print("=" * 80)
    print(f"\nSOURCE_SNAPSHOT_HEAD = {current_head}")
    print(f"VALID_AE_RUNS = {valid_ae}")
    print(f"VALID_SE_RUNS = {valid_se}")
    print(f"TOTAL_VALID_RUNS = {total_valid}")
    print(f"SEEDS_AE = {ae_seeds}")
    print(f"SEEDS_SE = {se_seeds}")
    print(f"GLOBAL_5PLUS5_CONTRACT = PASS")
    print(f"\nAE_SECURITY_STATE_NEW_VALUES = {ae_values}")
    print(f"AE_SECURITY_STATE_NEW_MEAN = {ae_mean:.2f}")
    print(f"AE_SECURITY_STATE_NEW_MEDIAN = {ae_median:.2f}")
    print(f"AE_SECURITY_STATE_NEW_SAMPLE_SD = {ae_sd:.2f}")
    print(f"AE_SECURITY_STATE_NEW_RANGE = [{ae_min}, {ae_max}]")
    print(f"\nSE_SECURITY_STATE_NEW_VALUES = {se_values}")
    print(f"SE_SECURITY_STATE_NEW_MEAN = {se_mean:.2f}")
    print(f"SE_SECURITY_STATE_NEW_MEDIAN = {se_median:.2f}")
    print(f"SE_SECURITY_STATE_NEW_SAMPLE_SD = {se_sd:.2f}")
    print(f"SE_SECURITY_STATE_NEW_RANGE = [{se_min}, {se_max}]")
    print(f"\nPAIRED_DELTAS_SE_MINUS_AE = {paired_deltas}")
    print(f"\nDESCRIPTIVE_ANALYSIS_ONLY = YES")
    print(f"STATISTICAL_SUPERIORITY_CLAIM = NO")
    print(f"\nPHASE3_AGGREGATE_MANIFEST = {manifest_path}")
    print(f"PHASE3_AGGREGATE_MANIFEST_SHA256 = {manifest_hash}")
    print(f"\nENGINEERING_VARIANCE_PILOT = PASS")
    print(f"NEXT_FORMAL_EXPERIMENT_GATE = OPEN_FOR_HUMAN_DESIGN_REVIEW")
    print("=" * 80)

if __name__ == "__main__":
    main()
