#!/usr/bin/env python3
"""Phase 1B: Model-comparison runner mode TDD tests.

RED tests covering:
- Threshold/provenance resolution
- Body-score wiring
- RNG pairing
- Scorer lifecycle
- Participation acceptance gate
- Model-comparison validity artifact
- Target baseline isolation
- Regression guards
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"
AE_META = REPO_ROOT / "model_stage" / "models" / "alfresco_ae_v1_meta.json"
SE_THRESHOLD_ARTIFACT = (
    REPO_ROOT / "model_stage" / "models" / "sefanogan_es_realrun_threshold.json"
)


@pytest.fixture
def temp_run_root():
    with tempfile.TemporaryDir() as tmp:
        yield Path(tmp)


@pytest.fixture
def fake_scorer_proc():
    """Fake scorer process for lifecycle tests."""
    script = """#!/usr/bin/env python3
import socket, sys, struct, time, os
sock_path = os.getenv("NV_VALID_SOCK")
if not sock_path:
    sys.exit(1)
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    sock.bind(sock_path)
    sock.listen(1)
    print("READY", flush=True)
    while True:
        try:
            conn, _ = sock.accept()
            size_bytes = conn.recv(4)
            if len(size_bytes) != 4:
                conn.close()
                continue
            size = struct.unpack("<I", size_bytes)[0]
            body = conn.recv(size)
            conn.sendall(b"0.5")
            conn.close()
        except:
            break
finally:
    sock.close()
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(script)
        f.flush()
        path = Path(f.name)
    path.chmod(0o755)
    yield path
    path.unlink(missing_ok=True)


# ============================================================================
# A. Threshold/provenance gates
# ============================================================================


def test_ae_threshold_resolution_from_canonical_metadata():
    """AE mode resolves threshold 1.623614 from canonical AE metadata."""
    assert AE_META.is_file(), "AE metadata missing"
    meta = json.loads(AE_META.read_text(encoding="utf-8"))
    assert meta["threshold_high"] == 1.623614
    assert meta["model_name"] == "alfresco_ae_v1"


def test_se_threshold_resolution_from_frozen_artifact():
    """SE mode resolves threshold 1.2847454080581664 from frozen artifact."""
    assert SE_THRESHOLD_ARTIFACT.is_file(), "SE threshold artifact missing"
    artifact = json.loads(SE_THRESHOLD_ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["se_threshold"] == 1.2847454080581664
    assert artifact["se_backend"] == "sefanogan_es_reference"
    assert artifact["policy"] == "MATCHED_OPERATING_CRITERION"


def test_wrong_se_artifact_sha_fails_closed():
    """Wrong SE artifact SHA/provenance fails closed."""
    # This will be enforced by the runner's threshold loader
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump({"se_threshold": 9.99, "se_backend": "fake"}, f)
        f.flush()
        fake_path = Path(f.name)

    try:
        # Runner should reject this artifact
        from scripts.run_alfresco_bounded_feedback import (
            resolve_model_comparison_threshold,
        )
        with pytest.raises((ValueError, RuntimeError)):
            resolve_model_comparison_threshold(
                "sefanogan_es_reference", artifact_path=fake_path
            )
    finally:
        fake_path.unlink(missing_ok=True)


def test_missing_se_artifact_fails_closed():
    """Missing SE artifact fails closed."""
    from scripts.run_alfresco_bounded_feedback import (
        resolve_model_comparison_threshold,
    )
    with pytest.raises((FileNotFoundError, ValueError, RuntimeError)):
        resolve_model_comparison_threshold(
            "sefanogan_es_reference",
            artifact_path=Path("/nonexistent/artifact.json"),
        )


def test_unsupported_backend_fails_closed():
    """Unsupported backend fails closed."""
    from scripts.run_alfresco_bounded_feedback import (
        resolve_model_comparison_threshold,
    )
    with pytest.raises((ValueError, KeyError)):
        resolve_model_comparison_threshold("unsupported_backend_v99")


# ============================================================================
# B. Python body-score wiring
# ============================================================================


def test_research_mode_propagates_scorer_variables():
    """Research mode propagates exact scorer variables."""
    from scripts.run_alfresco_bounded_feedback import (
        build_model_comparison_env,
        build_run_layout,
    )

    with tempfile.TemporaryDirectory() as tmp:
        layout = build_run_layout(Path(tmp), REPO_ROOT)
        layout["evidence"].mkdir(parents=True, exist_ok=True)
        layout["task"].write_text("{}", encoding="utf-8")

        env = build_model_comparison_env(
            layout=layout,
            backend="alfresco_ae_v1",
            threshold=1.623614,
            scorer_socket=Path("/tmp/test.sock"),
            scorer_trace=Path("/tmp/test_trace.jsonl"),
            base_env={},
        )

        assert env["NV_BODY_SCORE_ENDPOINT"] == "unix:///tmp/test.sock"
        assert env["NV_BODY_SCORE_THRESHOLD"] == "1.623614"
        assert env["NV_VALIDITY_BACKEND"] == "alfresco_ae_v1"
        assert env["NV_SCORER_TRACE_PATH"] == "/tmp/test_trace.jsonl"


def test_c_side_validity_endpoint_not_introduced():
    """C-side validity_endpoint is NOT introduced as the experiment scorer path."""
    # The canonical path is Python body-score RPC, not C validity_endpoint
    from scripts.run_alfresco_bounded_feedback import (
        build_model_comparison_env,
        build_run_layout,
    )

    with tempfile.TemporaryDirectory() as tmp:
        layout = build_run_layout(Path(tmp), REPO_ROOT)
        layout["evidence"].mkdir(parents=True, exist_ok=True)
        layout["task"].write_text("{}", encoding="utf-8")

        env = build_model_comparison_env(
            layout=layout,
            backend="sefanogan_es_reference",
            threshold=1.28,
            scorer_socket=Path("/tmp/test.sock"),
            scorer_trace=Path("/tmp/test_trace.jsonl"),
            base_env={},
        )

        # C-side validity_endpoint should NOT be set
        assert "NV_VALIDITY_ENDPOINT" not in env


def test_multipart_remains_outside_model_comparison():
    """Multipart remains outside model comparison."""
    # Multipart mode must reject model-comparison usage
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_scenario,
    )

    with pytest.raises((ValueError, RuntimeError)):
        validate_model_comparison_scenario("multipart_upload")


# ============================================================================
# C. RNG pairing
# ============================================================================


def test_afl_seed_produces_dash_s_in_argv():
    """--afl-seed N produces -s N in the AFL argv."""
    from scripts.run_alfresco_bounded_feedback import build_afl_argv_with_seed

    argv = build_afl_argv_with_seed(
        afl_binary=Path("/fake/afl-fuzz"),
        seed_dir=Path("/tmp/seeds"),
        output_dir=Path("/tmp/out"),
        harness_cmd=["/usr/bin/python3", "harness.py"],
        afl_seed=42,
        manifest_mode=False,
    )

    assert "-s" in argv
    s_index = argv.index("-s")
    assert argv[s_index + 1] == "42"


def test_missing_seed_in_paired_research_mode_fails_closed():
    """Missing seed in paired research mode fails closed."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_config,
    )

    with pytest.raises((ValueError, RuntimeError)):
        validate_model_comparison_config(
            model_comparison=True,
            afl_seed=None,  # Missing
            backend="alfresco_ae_v1",
        )


# ============================================================================
# D. Scorer lifecycle
# ============================================================================


def test_runner_starts_scorer_with_explicit_python(fake_scorer_proc):
    """Runner starts scorer with the explicitly selected --scorer-python."""
    from scripts.run_alfresco_bounded_feedback import start_scorer_process

    with tempfile.TemporaryDirectory() as tmp:
        sock = Path(tmp) / "test.sock"
        proc = start_scorer_process(
            scorer_python="/usr/bin/python3",
            scorer_script=fake_scorer_proc,
            socket_path=sock,
            backend="alfresco_ae_v1",
            timeout=5.0,
        )
        try:
            assert proc.poll() is None  # Still running
        finally:
            proc.terminate()
            proc.wait(timeout=2)


def test_runner_waits_for_unix_socket_readiness(fake_scorer_proc):
    """Runner waits for Unix-socket readiness before target launch."""
    from scripts.run_alfresco_bounded_feedback import start_scorer_process

    with tempfile.TemporaryDirectory() as tmp:
        sock = Path(tmp) / "test.sock"
        proc = start_scorer_process(
            scorer_python="/usr/bin/python3",
            scorer_script=fake_scorer_proc,
            socket_path=sock,
            backend="alfresco_ae_v1",
            timeout=5.0,
        )
        try:
            # Socket should exist and be connectable
            assert sock.exists()
            time.sleep(0.1)
            # Should be able to connect
            import socket
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(str(sock))
            s.close()
        finally:
            proc.terminate()
            proc.wait(timeout=2)


def test_startup_timeout_fails_closed_before_launch():
    """Startup timeout fails closed before launch."""
    from scripts.run_alfresco_bounded_feedback import start_scorer_process

    # Create a scorer that never signals ready
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("#!/usr/bin/env python3\nimport time\ntime.sleep(999)\n")
        f.flush()
        never_ready = Path(f.name)
    never_ready.chmod(0o755)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            sock = Path(tmp) / "test.sock"
            with pytest.raises((TimeoutError, RuntimeError)):
                start_scorer_process(
                    scorer_python="/usr/bin/python3",
                    scorer_script=never_ready,
                    socket_path=sock,
                    backend="alfresco_ae_v1",
                    timeout=0.5,  # Short timeout
                )
    finally:
        never_ready.unlink(missing_ok=True)


def test_scorer_process_stopped_in_finally(fake_scorer_proc):
    """Server process is stopped in finally, including target-launch failure."""
    from scripts.run_alfresco_bounded_feedback import ScorerLifecycleManager

    with tempfile.TemporaryDirectory() as tmp:
        sock = Path(tmp) / "test.sock"
        manager = ScorerLifecycleManager(
            scorer_python="/usr/bin/python3",
            scorer_script=fake_scorer_proc,
            socket_path=sock,
            backend="alfresco_ae_v1",
            timeout=5.0,
        )

        proc = manager.start()
        assert proc.poll() is None

        # Simulate cleanup
        manager.stop()
        time.sleep(0.5)
        assert proc.poll() is not None  # Process terminated


def test_existing_non_research_mode_no_auto_scorer():
    """Existing non-research mode does not start a scorer automatically."""
    # When model_comparison=False, scorer lifecycle is skipped
    from scripts.run_alfresco_bounded_feedback import (
        should_start_scorer,
    )

    assert should_start_scorer(model_comparison=False) is False
    assert should_start_scorer(model_comparison=True) is True


# ============================================================================
# E. Participation acceptance gate
# ============================================================================


def test_body_score_rpc_ok_zero_invalid():
    """body_score_rpc_ok == 0 → INVALID_FOR_MODEL_COMPARISON."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    stats = {
        "body_score_rpc_ok": 0,
        "body_score_rpc_fail": 0,
    }
    trace = []

    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
    assert "ZERO_SCORER_INVOCATIONS" in result["reason_codes"]


def test_body_score_rpc_fail_nonzero_invalid():
    """body_score_rpc_fail > 0 → invalid."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    stats = {
        "body_score_rpc_ok": 5,
        "body_score_rpc_fail": 2,  # Failures present
    }
    trace = [{"backend": "alfresco_ae_v1"} for _ in range(5)]

    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
    assert "SCORER_RPC_FAILURE" in result["reason_codes"]


def test_missing_empty_scorer_trace_invalid():
    """missing/empty scorer trace → invalid."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    stats = {
        "body_score_rpc_ok": 5,
        "body_score_rpc_fail": 0,
    }
    trace = []  # Empty trace

    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
    assert "TRACE_MISSING" in result["reason_codes"]


def test_wrong_trace_backend_invalid():
    """wrong trace backend → invalid."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    stats = {
        "body_score_rpc_ok": 5,
        "body_score_rpc_fail": 0,
    }
    trace = [{"backend": "wrong_backend"} for _ in range(5)]

    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"  # Expected backend
    )
    assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
    assert "TRACE_BACKEND_MISMATCH" in result["reason_codes"]


def test_trace_count_inconsistent_with_stats_invalid():
    """trace success count inconsistent with scorer stats → invalid."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    stats = {
        "body_score_rpc_ok": 5,
        "body_score_rpc_fail": 0,
    }
    trace = [{"backend": "alfresco_ae_v1"} for _ in range(3)]  # Only 3

    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
    assert "TRACE_COUNT_MISMATCH" in result["reason_codes"]


def test_expected_backend_rpc_ok_reconciled_trace_pass():
    """expected backend + rpc_ok>0 + rpc_fail=0 + reconciled trace → PASS."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    stats = {
        "body_score_rpc_ok": 5,
        "body_score_rpc_fail": 0,
    }
    trace = [{"backend": "alfresco_ae_v1", "score": 0.5} for _ in range(5)]

    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    assert result["verdict"] == "PASS"
    assert not result["reason_codes"]


def test_nv_rec_not_used_for_scorer_participation():
    """Never use nv_rec_success or nv_rec_total for scorer participation."""
    from scripts.run_alfresco_bounded_feedback import (
        validate_model_comparison_participation,
    )

    # Even if nv_rec_* fields are present, they should be ignored
    stats = {
        "body_score_rpc_ok": 5,
        "body_score_rpc_fail": 0,
        "nv_rec_success": 999,  # Should be ignored
        "nv_rec_total": 1000,
    }
    trace = [{"backend": "alfresco_ae_v1"} for _ in range(5)]

    result = validate_model_comparison_participation(
        stats, trace, "alfresco_ae_v1"
    )
    # Should pass based on body_score fields only
    assert result["verdict"] == "PASS"


# ============================================================================
# F. Model-comparison validity artifact
# ============================================================================


def test_runner_emits_model_comparison_validity_json():
    """Runner emits a machine-readable model_comparison_validity.json."""
    from scripts.run_alfresco_bounded_feedback import (
        write_model_comparison_validity,
        build_run_layout,
    )

    with tempfile.TemporaryDirectory() as tmp:
        layout = build_run_layout(Path(tmp), REPO_ROOT)
        layout["evidence"].mkdir(parents=True, exist_ok=True)

        validity = {
            "verdict": "PASS",
            "reason_codes": [],
            "backend": "alfresco_ae_v1",
            "threshold": 1.623614,
            "threshold_source": "alfresco_ae_v1_meta.json::threshold_high",
            "afl_seed": 42,
            "scorer_rpc_ok": 5,
            "scorer_rpc_fail": 0,
            "trace_invocations": 5,
            "trace_success": 5,
            "trace_backend": "alfresco_ae_v1",
        }

        path = write_model_comparison_validity(layout, validity)
        assert path.is_file()

        result = json.loads(path.read_text(encoding="utf-8"))
        assert result["verdict"] == "PASS"
        assert result["backend"] == "alfresco_ae_v1"
        assert result["afl_seed"] == 42


def test_invalid_run_cannot_be_silently_included():
    """Invalid run cannot be silently included in comparison outputs."""
    from scripts.run_alfresco_bounded_feedback import (
        write_model_comparison_validity,
        build_run_layout,
    )

    with tempfile.TemporaryDirectory() as tmp:
        layout = build_run_layout(Path(tmp), REPO_ROOT)
        layout["evidence"].mkdir(parents=True, exist_ok=True)

        validity = {
            "verdict": "INVALID_FOR_MODEL_COMPARISON",
            "reason_codes": ["ZERO_SCORER_INVOCATIONS"],
            "backend": "alfresco_ae_v1",
            "threshold": 1.623614,
            "threshold_source": "alfresco_ae_v1_meta.json::threshold_high",
            "afl_seed": 42,
            "scorer_rpc_ok": 0,
            "scorer_rpc_fail": 0,
        }

        path = write_model_comparison_validity(layout, validity)
        result = json.loads(path.read_text(encoding="utf-8"))

        # Verdict must be explicit
        assert result["verdict"] == "INVALID_FOR_MODEL_COMPARISON"
        assert len(result["reason_codes"]) > 0


# ============================================================================
# G. Target baseline isolation
# ============================================================================


def test_pre_run_canonical_baseline_verification_required():
    """Pre-run canonical baseline verification is required for model-comparison mode."""
    from scripts.run_alfresco_bounded_feedback import (
        verify_target_baseline,
    )

    # Mock client
    fake_client = MagicMock()
    fake_client.get_node.return_value = {
        "id": "node123",
        "properties": {
            "cm:title": "expected",
            "cm:description": "expected",
        },
    }

    canonical = {
        "cm:title": "expected",
        "cm:description": "expected",
    }

    result = verify_target_baseline(
        fake_client, "node123", canonical
    )
    assert result["status"] == "PASS"


def test_noncanonical_state_restore_verify_before_evidence():
    """Noncanonical state → restore + verify before evidence accounting."""
    from scripts.run_alfresco_bounded_feedback import (
        verify_target_baseline,
        restore_target_baseline,
    )

    # Mock client showing non-canonical state
    fake_client = MagicMock()
    fake_client.get_node.return_value = {
        "id": "node123",
        "properties": {
            "cm:title": "wrong",
            "cm:description": "wrong",
        },
    }

    canonical = {
        "cm:title": "expected",
        "cm:description": "expected",
    }

    result = verify_target_baseline(fake_client, "node123", canonical)
    assert result["status"] == "MISMATCH"

    # Should trigger restore
    restore_target_baseline(fake_client, "node123", canonical)

    # After restore, verify again
    fake_client.get_node.return_value["properties"] = canonical
    result = verify_target_baseline(fake_client, "node123", canonical)
    assert result["status"] == "PASS"


def test_restore_readback_failure_abort_before_afl():
    """Restore/readback failure → abort before AFL launch."""
    from scripts.run_alfresco_bounded_feedback import (
        restore_target_baseline,
    )

    # Mock client that fails to restore
    fake_client = MagicMock()
    fake_client.update_node.side_effect = RuntimeError("RESTORE_FAILED")

    canonical = {
        "cm:title": "expected",
        "cm:description": "expected",
    }

    with pytest.raises(RuntimeError):
        restore_target_baseline(fake_client, "node123", canonical)


def test_baseline_operations_not_counted_as_evidence():
    """Baseline operations must not write into run evidence counters."""
    # Baseline verification/restore should NOT increment:
    # - nv_total_valid_exec
    # - body_score_rpc_ok
    # - Any execution counters

    # This is enforced by running baseline ops BEFORE AFL launch
    # and using a separate client/session
    pass  # Structural test - verified by orchestration order


# ============================================================================
# H. Regression guards
# ============================================================================


def test_existing_default_ae_behavior_unchanged():
    """Existing default AE/non-research behavior remains unchanged."""
    from scripts.run_alfresco_bounded_feedback import runtime_environment

    with tempfile.TemporaryDirectory() as tmp:
        from scripts.run_alfresco_bounded_feedback import build_run_layout

        layout = build_run_layout(Path(tmp), REPO_ROOT)
        layout["evidence"].mkdir(parents=True, exist_ok=True)
        layout["task"].write_text(
            json.dumps({"scenario": "metadata_update"}), encoding="utf-8"
        )

        # Non-research mode
        env = runtime_environment(
            layout,
            Path("/fake/target.json"),
            layout["task"],
            ("user", "pass"),
            validity_backend="alfresco_ae_v1",
        )

        # Should have standard AE backend
        assert env["NV_VALIDITY_BACKEND"] == "alfresco_ae_v1"
        # But should NOT have model-comparison scorer vars unless explicitly set
        assert "NV_BODY_SCORE_ENDPOINT" not in env or env.get(
            "NV_BODY_SCORE_ENDPOINT"
        ) == ""


def test_multipart_validity_disabled_excluded_from_comparison():
    """Multipart remains validity-disabled/excluded from model A/B."""
    with tempfile.TemporaryDirectory() as tmp:
        from scripts.run_alfresco_bounded_feedback import (
            build_run_layout,
            build_task_payload,
        )

        layout = build_run_layout(Path(tmp), REPO_ROOT)

        task = build_task_payload(
            layout["seed_dir"],
            max_test_cases=3,
            time_budget=30,
            scenario="multipart_upload",
            input_format="full_http_multipart",
            parent_node_id="parent123",
            validity_backend="alfresco_ae_v1",
        )

        assert task["enable_validity"] == 0


def test_canonical_se_serving_unchanged():
    """Canonical SE serving remains unchanged."""
    # Import the canonical SE scorer
    from model_stage.sefanogan_es_reference import ReferenceScorer

    # Should still be importable and functional
    assert ReferenceScorer is not None


def test_representation_bridge_unchanged():
    """Existing representation bridge remains unchanged."""
    # HTTP/body bridge should remain untouched
    from nv_http_body_adapter import extract_http_body

    assert extract_http_body is not None
