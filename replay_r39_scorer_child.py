#!/usr/bin/env python3
"""R39 Exact Scorer Child Replay - Step 4 of Postmortem Protocol.

Reproduces the exact scorer subprocess that R39 attempted to start, with
stderr/stdout captured to files instead of PIPE'd to parent.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
R39_RUN_ROOT = Path("/tmp/r39_real_run_20261001_031203_107473")

# Exact R39 child configuration
SCORER_PYTHON = "/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python3"
SCORER_SCRIPT = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"
BACKEND = "sefanogan_es_reference"

def main():
    print("=" * 80)
    print("R39 EXACT SCORER CHILD REPLAY - STEP 4")
    print("=" * 80)
    print()

    # Create fresh temp socket
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "replay_scorer.sock"
        stdout_path = Path(tmpdir) / "scorer_stdout.txt"
        stderr_path = Path(tmpdir) / "scorer_stderr.txt"

        print(f"Replay socket: {socket_path}")
        print(f"Replay stdout: {stdout_path}")
        print(f"Replay stderr: {stderr_path}")
        print()

        # Construct exact R39 child environment
        env = dict(os.environ)
        env["NV_VALID_SOCK"] = str(socket_path)
        env["NV_VALIDITY_BACKEND"] = BACKEND

        # R38C canonical artifact binding (from production code lines 2746-2754)
        canonical_base = Path.home() / "alfresco-audit-artifacts" / "sefanogan-es-round3-20260901-" / "training_runs" / "seed-20260519"
        env["SEFANOGAN_REFERENCE_CHECKPOINT"] = str(canonical_base / "sefanogan_es_reference.pt")
        env["SEFANOGAN_REFERENCE_META_PATH"] = str(canonical_base / "sefanogan_es_reference.json")

        # PYTHONPATH injection (from production code lines 2756-2762)
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(REPO_ROOT)
            if not existing
            else str(REPO_ROOT) + os.pathsep + existing
        )

        print("Child environment (NV-specific):")
        print(f"  NV_VALID_SOCK: {env['NV_VALID_SOCK']}")
        print(f"  NV_VALIDITY_BACKEND: {env['NV_VALIDITY_BACKEND']}")
        print(f"  SEFANOGAN_REFERENCE_CHECKPOINT: {env['SEFANOGAN_REFERENCE_CHECKPOINT']}")
        print(f"  SEFANOGAN_REFERENCE_META_PATH: {env['SEFANOGAN_REFERENCE_META_PATH']}")
        print(f"  PYTHONPATH: {env['PYTHONPATH'][:200]}...")
        print()

        # Verify artifacts exist before launch
        checkpoint = Path(env["SEFANOGAN_REFERENCE_CHECKPOINT"])
        metadata = Path(env["SEFANOGAN_REFERENCE_META_PATH"])

        print("Artifact pre-flight:")
        print(f"  Checkpoint exists: {checkpoint.is_file()} ({checkpoint})")
        print(f"  Metadata exists: {metadata.is_file()} ({metadata})")
        print()

        if not checkpoint.is_file() or not metadata.is_file():
            print("ERROR: Canonical artifacts not found")
            print("EXACT_CHILD_REPLAY_STATUS = ARTIFACT_MISSING")
            return 1

        print("Launching exact scorer child process...")
        print(f"Executable: {SCORER_PYTHON}")
        print(f"Script: {SCORER_SCRIPT}")
        print(f"CWD: {REPO_ROOT}")
        print()

        with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
            proc = subprocess.Popen(
                [SCORER_PYTHON, str(SCORER_SCRIPT)],
                env=env,
                cwd=str(REPO_ROOT),
                stdout=out,
                stderr=err,
                text=True,
            )

            print(f"EXACT_CHILD_REPLAY_STARTED = YES")
            print(f"EXACT_CHILD_REPLAY_PID = {proc.pid}")
            print()

            # Wait for socket or process death (10 second timeout)
            start = time.time()
            timeout = 10.0
            socket_ready = False

            while time.time() - start < timeout:
                if socket_path.exists():
                    socket_ready = True
                    break

                if proc.poll() is not None:
                    break

                time.sleep(0.1)

            elapsed = time.time() - start
            exit_code = proc.poll()

            if socket_ready:
                print(f"EXACT_CHILD_REPLAY_SOCKET_READY = YES (after {elapsed:.2f}s)")
                proc.terminate()
                proc.wait(timeout=2.0)
            else:
                print(f"EXACT_CHILD_REPLAY_SOCKET_READY = NO (after {elapsed:.2f}s)")

                if exit_code is None:
                    proc.terminate()
                    exit_code = proc.wait(timeout=2.0)

            print(f"EXACT_CHILD_REPLAY_EXIT_CODE = {exit_code}")
            print()

        # Read captured output
        stdout_content = stdout_path.read_text()
        stderr_content = stderr_path.read_text()

        print("Captured stdout:")
        print("-" * 80)
        print(stdout_content if stdout_content else "(empty)")
        print("-" * 80)
        print()

        print("Captured stderr:")
        print("-" * 80)
        print(stderr_content if stderr_content else "(empty)")
        print("-" * 80)
        print()

        if stderr_content:
            first_line = stderr_content.split('\n')[0]
            print(f"EXACT_CHILD_REPLAY_FIRST_STDERR_LINE = {first_line}")
        else:
            print("EXACT_CHILD_REPLAY_FIRST_STDERR_LINE = (none)")

        print()
        print("=" * 80)
        print("STEP 4 COMPLETE - EXACT CHILD ERROR CAPTURED")
        print("=" * 80)

        return 0 if socket_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
