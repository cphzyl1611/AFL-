#!/usr/bin/env python3
"""Simplified Phase 1B CLI wiring tests."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"


def test_cli_flags_present():
    """All four model-comparison flags appear in --help."""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "--model-comparison" in result.stdout
    assert "--afl-seed" in result.stdout
    assert "--scorer-python" in result.stdout
    assert "--scorer-ready-timeout" in result.stdout


def test_model_comparison_without_seed_fails():
    """--model-comparison without --afl-seed is rejected at parse validation."""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--model-comparison", "--preflight-only"],
        capture_output=True,
        text=True,
        timeout=5,
        env={"ALFRESCO_USER": "test", "ALFRESCO_PASS": "test"},
    )
    # Should fail with config error (2) due to missing --afl-seed
    assert result.returncode == 2
    assert "MODEL_COMPARISON_REQUIRES_AFL_SEED" in result.stderr


def test_model_comparison_with_multipart_fails():
    """--model-comparison with multipart scenario is rejected."""
    result = subprocess.run(
        [
            sys.executable, str(RUNNER),
            "--model-comparison",
            "--afl-seed", "12345",
            "--scenario", "multipart_upload",
            "--preflight-only",
        ],
        capture_output=True,
        text=True,
        timeout=5,
        env={"ALFRESCO_USER": "test", "ALFRESCO_PASS": "test"},
    )
    # Should fail with config error (2) due to multipart incompatibility
    assert result.returncode == 2
    assert "MULTIPART_NOT_SUPPORTED_IN_MODEL_COMPARISON" in result.stderr


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
