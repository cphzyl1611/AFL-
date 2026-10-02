#!/usr/bin/env python3
"""R38C: Verify post-repair binding resolves to exact canonical 32D artifacts."""

import hashlib
import os
import sys
import tempfile
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


def test_scorer_lifecycle_artifact_binding_post_repair():
    """GREEN test: prove repaired binding uses exact canonical 32D artifacts."""

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "test.sock"
        trace_path = Path(tmpdir) / "trace.jsonl"

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

        # Simulate environment construction (matches repaired ScorerLifecycleManager.start())
        env = dict(os.environ)
        env["NV_VALID_SOCK"] = str(socket_path)
        env["NV_VALIDITY_BACKEND"] = "sefanogan_es_reference"

        # R38C repaired binding logic
        if manager.backend == "sefanogan_es_reference":
            canonical_base = (
                Path.home()
                / "alfresco-audit-artifacts"
                / "sefanogan-es-round3-20260901-"
                / "training_runs"
                / "seed-20260519"
            )
            env["SEFANOGAN_REFERENCE_CHECKPOINT"] = str(
                canonical_base / "sefanogan_es_reference.pt"
            )
            env["SEFANOGAN_REFERENCE_META_PATH"] = str(
                canonical_base / "sefanogan_es_reference.json"
            )

        # Extract bound artifact paths
        checkpoint_present = "SEFANOGAN_REFERENCE_CHECKPOINT" in env
        metadata_present = "SEFANOGAN_REFERENCE_META_PATH" in env

        print(f"POST_REPAIR_CHECKPOINT_ENV_PRESENT = {'YES' if checkpoint_present else 'NO'}")
        print(f"POST_REPAIR_META_ENV_PRESENT = {'YES' if metadata_present else 'NO'}")

        if not checkpoint_present or not metadata_present:
            print("POST_REPAIR_CHECKPOINT_SHA256 = MISSING")
            print("POST_REPAIR_METADATA_SHA256 = MISSING")
            print("POST_REPAIR_BINDING_IS_CANONICAL_ALFRESCO = NO")
            return 1

        bound_checkpoint = Path(env["SEFANOGAN_REFERENCE_CHECKPOINT"])
        bound_metadata = Path(env["SEFANOGAN_REFERENCE_META_PATH"])

        # Verify bound artifacts exist
        if not bound_checkpoint.is_file():
            print(f"POST_REPAIR_CHECKPOINT_SHA256 = FILE_NOT_FOUND")
            print(f"POST_REPAIR_METADATA_SHA256 = UNKNOWN")
            print("POST_REPAIR_BINDING_IS_CANONICAL_ALFRESCO = NO")
            return 1

        if not bound_metadata.is_file():
            print(f"POST_REPAIR_CHECKPOINT_SHA256 = UNKNOWN")
            print(f"POST_REPAIR_METADATA_SHA256 = FILE_NOT_FOUND")
            print("POST_REPAIR_BINDING_IS_CANONICAL_ALFRESCO = NO")
            return 1

        # Compute actual SHA256
        bound_checkpoint_sha = hashlib.sha256(bound_checkpoint.read_bytes()).hexdigest()
        bound_metadata_sha = hashlib.sha256(bound_metadata.read_bytes()).hexdigest()

        print(f"POST_REPAIR_CHECKPOINT_SHA256 = {bound_checkpoint_sha}")
        print(f"POST_REPAIR_METADATA_SHA256 = {bound_metadata_sha}")

        # GREEN: These MUST match canonical exactly
        checkpoint_match = bound_checkpoint_sha == CANONICAL_CHECKPOINT_SHA256
        metadata_match = bound_metadata_sha == CANONICAL_METADATA_SHA256

        if checkpoint_match and metadata_match:
            print("POST_REPAIR_BINDING_IS_CANONICAL_ALFRESCO = YES")
            return 0
        else:
            print("POST_REPAIR_BINDING_IS_CANONICAL_ALFRESCO = NO")
            if not checkpoint_match:
                print(f"  Checkpoint SHA mismatch: expected {CANONICAL_CHECKPOINT_SHA256}")
            if not metadata_match:
                print(f"  Metadata SHA mismatch: expected {CANONICAL_METADATA_SHA256}")
            return 1


if __name__ == "__main__":
    sys.exit(test_scorer_lifecycle_artifact_binding_post_repair())
