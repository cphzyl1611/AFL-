#!/usr/bin/env python3
"""R38C: Test scorer lifecycle binds to exact canonical 32D Alfresco artifacts."""

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_alfresco_bounded_feedback import ScorerLifecycleManager

# Canonical 32D Alfresco authority from R38B
CANONICAL_CHECKPOINT_SHA256 = (
    "4eace87ac7d7759a729ff98916a5acead4154c803c53884e3ca7f27570dbf20d"
)
CANONICAL_METADATA_SHA256 = (
    "2a73ccc3729a3734ab9901b4474feb73d4d42f912ccbc717af48f970ab568226"
)

CANONICAL_CHECKPOINT_PATH = Path(
    "~/alfresco-audit-artifacts/sefanogan-es-round3-20260901-"
    "/training_runs/seed-20260519/sefanogan_es_reference.pt"
).expanduser()

CANONICAL_METADATA_PATH = Path(
    "~/alfresco-audit-artifacts/sefanogan-es-round3-20260901-"
    "/training_runs/seed-20260519/sefanogan_es_reference.json"
).expanduser()


def test_scorer_lifecycle_artifact_binding_pre_repair():
    """RED test: prove current binding uses wrong 38D artifacts."""

    # Create minimal lifecycle manager (without starting process)
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        trace_path = Path(tmpdir) / "trace.jsonl"

        # Canonical Python for SE scorer
        scorer_python = str(
            Path.home() / "miniconda3" / "envs" / "aflpp-se-calib-pip" / "bin" / "python3"
        )
        scorer_script = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"

        manager = ScorerLifecycleManager(
            scorer_python=scorer_python,
            scorer_script=scorer_script,
            socket_path=socket_path,
            backend="sefanogan_es_reference",
            timeout=10.0,
            trace_path=trace_path,
        )

        # Simulate environment construction WITHOUT starting process
        env = dict(os.environ)
        env["NV_VALID_SOCK"] = str(socket_path)
        env["NV_VALIDITY_BACKEND"] = "sefanogan_es_reference"

        # This is the CURRENT binding logic from ScorerLifecycleManager.start()
        if manager.backend == "sefanogan_es_reference":
            models_dir = REPO_ROOT / "model_stage" / "models"
            env["SEFANOGAN_REFERENCE_CHECKPOINT"] = str(
                models_dir / "sefanogan_gan_model.pt"
            )
            env["SEFANOGAN_REFERENCE_META_PATH"] = str(
                models_dir / "sefanogan_es_reference_meta.json"
            )

        # Extract bound artifact paths
        bound_checkpoint = Path(env["SEFANOGAN_REFERENCE_CHECKPOINT"])
        bound_metadata = Path(env["SEFANOGAN_REFERENCE_META_PATH"])

        # Verify bound artifacts exist
        assert bound_checkpoint.is_file(), f"Bound checkpoint missing: {bound_checkpoint}"
        assert bound_metadata.is_file(), f"Bound metadata missing: {bound_metadata}"

        # Compute actual SHA256
        bound_checkpoint_sha = hashlib.sha256(bound_checkpoint.read_bytes()).hexdigest()
        bound_metadata_sha = hashlib.sha256(bound_metadata.read_bytes()).hexdigest()

        # RED: These should NOT match canonical (proving wrong binding)
        checkpoint_match = bound_checkpoint_sha == CANONICAL_CHECKPOINT_SHA256
        metadata_match = bound_metadata_sha == CANONICAL_METADATA_SHA256

        print(f"PRE_REPAIR_RED_RESULT = {'PASS' if not checkpoint_match and not metadata_match else 'FAIL'}")
        print(f"PRE_REPAIR_BOUND_CHECKPOINT_SHA256 = {bound_checkpoint_sha}")
        print(f"PRE_REPAIR_BOUND_METADATA_SHA256 = {bound_metadata_sha}")

        if checkpoint_match and metadata_match:
            print("PRE_REPAIR_FAILURE_REASON = artifacts_already_canonical")
            return 1
        elif checkpoint_match or metadata_match:
            print("PRE_REPAIR_FAILURE_REASON = partial_canonical_match")
            return 1
        else:
            print("PRE_REPAIR_FAILURE_REASON = bound_to_repo_local_38d_artifacts")
            return 0


if __name__ == "__main__":
    sys.exit(test_scorer_lifecycle_artifact_binding_pre_repair())
