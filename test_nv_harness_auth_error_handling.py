#!/usr/bin/env python3
"""
Regression test: Harness auth error handling

Verifies that when required auth environment variables are missing,
the harness writes status with http_code=-99 instead of crashing.

This prevents AFL++ from recording executions as invalid_exec_identity
and ensures proper execution ledger tracking.
"""
import os
import sys
import json
import tempfile
import subprocess
import pytest


MINIMAL_SEED = b"""PUT /test HTTP/1.1
Host: 127.0.0.1
Content-Type: text/plain

test body
"""


def run_harness_with_config(config_dict, seed_content=MINIMAL_SEED, env_vars=None):
    """Helper: Run harness with given config and return status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write config
        config_path = os.path.join(tmpdir, "target.json")
        with open(config_path, "w") as f:
            json.dump(config_dict, f)

        # Write seed
        seed_path = os.path.join(tmpdir, "seed.http")
        with open(seed_path, "wb") as f:
            f.write(seed_content)

        # Status path
        status_path = os.path.join(tmpdir, "status.json")

        # Setup environment
        env = os.environ.copy()
        env["NV_TARGET_CONFIG"] = config_path
        env["NV_STATUS_PATH"] = status_path

        # Remove auth env vars
        for var in ["ALFRESCO_USER", "ALFRESCO_PASS", "NV_TOKEN"]:
            env.pop(var, None)

        # Apply custom env vars if provided
        if env_vars:
            env.update(env_vars)

        # Run harness
        harness_path = os.path.join(os.path.dirname(__file__), "nv_http_harness.py")
        with open(seed_path, "rb") as stdin_file:
            result = subprocess.run(
                [sys.executable, harness_path],
                stdin=stdin_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=5
            )

        # Read status if written
        status_data = None
        if os.path.exists(status_path):
            with open(status_path, "r") as f:
                status_data = json.load(f)

        return {
            "exit_code": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace"),
            "stderr": result.stderr.decode("utf-8", errors="replace"),
            "status_written": status_data is not None,
            "status_data": status_data
        }


def test_basic_auth_missing_username():
    """Missing ALFRESCO_USER should write status with http_code=-99."""
    config = {
        "auth": {
            "type": "basic",
            "username_env": "ALFRESCO_USER",
            "password_env": "ALFRESCO_PASS"
        },
        "base": "http://127.0.0.1:8899",
        "body_only_mode": 1,
        "default_endpoint": "test",
        "endpoints": [{"name": "test", "method": "PUT", "path": "/test"}],
        "scenario": "content_update"
    }

    result = run_harness_with_config(config)

    assert result["status_written"], "Status file should be written"
    assert result["status_data"]["http_code"] == -99, "http_code should be -99 for auth error"
    assert result["status_data"]["exec_seq"] == 0, "exec_seq should be 0"
    assert result["status_data"]["is_exception"] == 1, "is_exception should be 1"
    assert result["exit_code"] == 2, "Exit code should be 2"


def test_basic_auth_missing_password():
    """Missing ALFRESCO_PASS should write status with http_code=-99."""
    config = {
        "auth": {
            "type": "basic",
            "username_env": "ALFRESCO_USER",
            "password_env": "ALFRESCO_PASS"
        },
        "base": "http://127.0.0.1:8899",
        "body_only_mode": 1,
        "default_endpoint": "test",
        "endpoints": [{"name": "test", "method": "PUT", "path": "/test"}],
        "scenario": "content_update"
    }

    # Provide username but not password
    result = run_harness_with_config(config, env_vars={"ALFRESCO_USER": "testuser"})

    assert result["status_written"], "Status file should be written"
    assert result["status_data"]["http_code"] == -99, "http_code should be -99 for auth error"
    assert result["exit_code"] == 2, "Exit code should be 2"


def test_bearer_auth_missing_token():
    """Missing NV_TOKEN should write status with http_code=-99."""
    config = {
        "auth": {
            "type": "bearer",
            "token_env": "NV_TOKEN"
        },
        "base": "http://127.0.0.1:8899",
        "body_only_mode": 1,
        "default_endpoint": "test",
        "endpoints": [{"name": "test", "method": "PUT", "path": "/test"}],
        "scenario": "content_update"
    }

    result = run_harness_with_config(config)

    assert result["status_written"], "Status file should be written"
    assert result["status_data"]["http_code"] == -99, "http_code should be -99 for auth error"
    assert result["exit_code"] == 2, "Exit code should be 2"


def test_raw_token_auth_missing_token():
    """Missing token for raw_token auth should write status with http_code=-99."""
    config = {
        "auth": {
            "type": "raw_token",
            "header": "X-Auth-Token",
            "token_env": "MY_TOKEN"
        },
        "base": "http://127.0.0.1:8899",
        "body_only_mode": 1,
        "default_endpoint": "test",
        "endpoints": [{"name": "test", "method": "PUT", "path": "/test"}],
        "scenario": "content_update"
    }

    result = run_harness_with_config(config)

    assert result["status_written"], "Status file should be written"
    assert result["status_data"]["http_code"] == -99, "http_code should be -99 for auth error"
    assert result["exit_code"] == 2, "Exit code should be 2"


def test_no_auth_config_succeeds():
    """When no auth is configured, harness should attempt HTTP (will fail connection but write status)."""
    config = {
        "base": "http://127.0.0.1:8899",
        "body_only_mode": 1,
        "default_endpoint": "test",
        "endpoints": [{"name": "test", "method": "PUT", "path": "/test"}],
        "scenario": "content_update"
    }

    result = run_harness_with_config(config)

    assert result["status_written"], "Status file should be written"
    # Connection refused should give http_code=-2, not -99
    assert result["status_data"]["http_code"] == -2, "http_code should be -2 for connection refused"
    assert result["exit_code"] == 2, "Exit code should be 2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
