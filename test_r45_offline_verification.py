#!/usr/bin/env python3
"""
R45 offline verification - prove the auth error repair works.
Uses exact R45 seed and config, with local stub only (no Alfresco).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# R45 exact seed content (full HTTP format)
R45_SEED = b"""PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/{id}/content HTTP/1.1
Host: 127.0.0.1
Content-Type: text/plain; charset=utf-8
Content-Length: 110

\xe5\x85\xb3\xe4\xba\x8e\xe7\xb3\xbb\xe7\xbb\x9f\xe8\x81\x94\xe8\xb0\x83\xe6\xb5\x8b\xe8\xaf\x95\xe7\x9a\x84\xe9\x80\x9a\xe7\x9f\xa5
\xe8\xaf\xb7\xe5\x90\x84\xe9\x83\xa8\xe9\x97\xa8\xe6\x8c\x89\xe7\x85\xa7\xe8\xae\xa1\xe5\x88\x92\xe5\xae\x8c\xe6\x88\x90\xe6\x8e\xa5\xe5\x8f\xa3\xe8\x81\x94\xe8\xb0\x83\xe3\x80\x81\xe6\x97\xa5\xe5\xbf\x97\xe5\xbd\x92\xe6\xa1\xa3\xe5\x92\x8c\xe9\x97\xae\xe9\xa2\x98\xe9\x97\xad\xe7\x8e\xaf\xe3\x80\x82
"""

def test_r45_offline_with_missing_auth():
    """Reproduce R45: missing ALFRESCO_USER/ALFRESCO_PASS causes harness exit."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create exact R45 target.json (with auth config)
        target_cfg = {
            "auth": {
                "type": "basic",
                "username_env": "ALFRESCO_USER",
                "password_env": "ALFRESCO_PASS"
            },
            "body_only_mode": 1,
            "default_endpoint": "content_update",
            "scenario": "content_update",
            "endpoints": [{
                "name": "content_update",
                "method": "PUT",
                "path": "/alfresco/api/-default-/public/alfresco/versions/1/nodes/test/content"
            }]
        }

        target_json = tmpdir / "target.json"
        target_json.write_text(json.dumps(target_cfg))

        status_json = tmpdir / "status.json"

        # Run harness WITHOUT setting ALFRESCO_USER/ALFRESCO_PASS
        env = os.environ.copy()
        env["NV_TARGET_CONFIG"] = str(target_json)
        env["NV_STATUS_PATH"] = str(status_json)
        env.pop("ALFRESCO_USER", None)  # Ensure not set
        env.pop("ALFRESCO_PASS", None)  # Ensure not set

        proc = subprocess.run(
            [sys.executable, "nv_http_harness.py"],
            input=R45_SEED,
            env=env,
            cwd="/home/dministrator/AFLplusplus-phase2-ae-snapshot-recovery",
            capture_output=True,
            timeout=10
        )

        # ACCEPTANCE CRITERIA:
        # POST_REPAIR: Exit code should be 2 (auth error), not crash
        assert proc.returncode == 2, f"Expected exit code 2, got {proc.returncode}"

        # POST_REPAIR: Status file MUST be written (not the R45 bug)
        assert status_json.exists(), "POST_REPAIR: Status file must be written even on auth error"

        status = json.loads(status_json.read_text())

        # POST_REPAIR: http_code should be -99 (auth error sentinel)
        assert status["http_code"] == -99, f"Expected http_code=-99, got {status['http_code']}"

        # POST_REPAIR: exec_seq should be 0 (invalid execution identity per C contract)
        # C code line 2557: "exec_seq == 0 means the harness did not report one"
        assert status["exec_seq"] == 0, f"Expected exec_seq=0 for auth error, got {status['exec_seq']}"

        # POST_REPAIR: is_exception should be 1
        assert status["is_exception"] == 1, "is_exception must be 1 for auth errors"

        print("✓ POST_REPAIR_AUTH_ERROR_WRITES_STATUS = YES")
        print("✓ POST_REPAIR_EXEC_SEQ_ZERO_INVALID_IDENTITY = YES")
        print("✓ POST_REPAIR_STATUS_OBSERVED = YES")
        print(f"✓ exec_seq={status['exec_seq']} (invalid), http_code={status['http_code']}, is_exception={status['is_exception']}")

        return True

if __name__ == "__main__":
    try:
        test_r45_offline_with_missing_auth()
        print("\n✓ R45 OFFLINE VERIFICATION: PASS")
        print("✓ Root cause confirmed: missing auth credentials")
        print("✓ Repair verified: status now written on auth errors")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ R45 OFFLINE VERIFICATION: FAIL")
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
