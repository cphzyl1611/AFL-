#!/usr/bin/env python3
"""Test if scorer blocks on PIPE when parent doesn't read stdout/stderr."""

import os
import subprocess
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SCORER_PYTHON = "/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python3"
SCORER_SCRIPT = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"
BACKEND = "sefanogan_es_reference"

def test_with_pipe():
    """Exact production launch: stdout/stderr to PIPE, never read."""
    print("=" * 80)
    print("TEST 1: Production launch (PIPE, never read)")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "scorer.sock"

        # Exact production environment
        env = dict(os.environ)
        env["NV_VALID_SOCK"] = str(socket_path)
        env["NV_VALIDITY_BACKEND"] = BACKEND

        canonical_base = Path.home() / "alfresco-audit-artifacts" / "sefanogan-es-round3-20260901-" / "training_runs" / "seed-20260519"
        env["SEFANOGAN_REFERENCE_CHECKPOINT"] = str(canonical_base / "sefanogan_es_reference.pt")
        env["SEFANOGAN_REFERENCE_META_PATH"] = str(canonical_base / "sefanogan_es_reference.json")

        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPO_ROOT) if not existing else str(REPO_ROOT) + os.pathsep + existing

        print(f"Launching scorer with PIPE (production path)...")
        proc = subprocess.Popen(
            [SCORER_PYTHON, str(SCORER_SCRIPT)],
            env=env,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,  # Same as production
            stderr=subprocess.PIPE,  # Same as production
            text=True,
        )

        print(f"PID: {proc.pid}")

        # Wait for socket (same timeout as production)
        start = time.time()
        timeout = 10.0
        socket_ready = False

        while time.time() - start < timeout:
            if socket_path.exists():
                socket_ready = True
                elapsed = time.time() - start
                print(f"Socket ready after {elapsed:.2f}s")
                break

            exit_code = proc.poll()
            if exit_code is not None:
                print(f"Process died with exit code {exit_code}")
                break

            time.sleep(0.1)

        elapsed = time.time() - start
        exit_code = proc.poll()

        print()
        print(f"After {elapsed:.2f}s:")
        print(f"  Socket exists: {socket_path.exists()}")
        print(f"  Process alive: {exit_code is None}")
        print(f"  Exit code: {exit_code}")

        if exit_code is None:
            print()
            print("Process still running - checking if blocked on PIPE...")
            print("(If blocked, it won't respond to terminate quickly)")

            proc.terminate()
            try:
                exit_code = proc.wait(timeout=2.0)
                print(f"Terminated gracefully with code {exit_code}")
            except subprocess.TimeoutExpired:
                print("Terminate timed out - process blocked!")
                proc.kill()
                exit_code = proc.wait()
                print(f"Killed with code {exit_code}")

        print()
        return socket_ready, exit_code


def test_with_files():
    """Control: stdout/stderr to files (Step 4 replay path)."""
    print("=" * 80)
    print("TEST 2: File output (Step 4 replay path)")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = Path(tmpdir) / "scorer.sock"
        stdout_path = Path(tmpdir) / "stdout.txt"
        stderr_path = Path(tmpdir) / "stderr.txt"

        env = dict(os.environ)
        env["NV_VALID_SOCK"] = str(socket_path)
        env["NV_VALIDITY_BACKEND"] = BACKEND

        canonical_base = Path.home() / "alfresco-audit-artifacts" / "sefanogan-es-round3-20260901-" / "training_runs" / "seed-20260519"
        env["SEFANOGAN_REFERENCE_CHECKPOINT"] = str(canonical_base / "sefanogan_es_reference.pt")
        env["SEFANOGAN_REFERENCE_META_PATH"] = str(canonical_base / "sefanogan_es_reference.json")

        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPO_ROOT) if not existing else str(REPO_ROOT) + os.pathsep + existing

        print(f"Launching scorer with file output...")
        with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
            proc = subprocess.Popen(
                [SCORER_PYTHON, str(SCORER_SCRIPT)],
                env=env,
                cwd=str(REPO_ROOT),
                stdout=out,
                stderr=err,
                text=True,
            )

        print(f"PID: {proc.pid}")

        start = time.time()
        timeout = 10.0
        socket_ready = False

        while time.time() - start < timeout:
            if socket_path.exists():
                socket_ready = True
                elapsed = time.time() - start
                print(f"Socket ready after {elapsed:.2f}s")
                break

            exit_code = proc.poll()
            if exit_code is not None:
                print(f"Process died with exit code {exit_code}")
                break

            time.sleep(0.1)

        elapsed = time.time() - start
        exit_code = proc.poll()

        print()
        print(f"After {elapsed:.2f}s:")
        print(f"  Socket exists: {socket_path.exists()}")
        print(f"  Process alive: {exit_code is None}")

        if exit_code is None:
            proc.terminate()
            proc.wait(timeout=2.0)

        print()
        return socket_ready, exit_code


def main():
    print()
    print("HYPOTHESIS: Scorer blocks on PIPE buffer when parent doesn't read.")
    print()

    pipe_ready, pipe_exit = test_with_pipe()
    print()
    file_ready, file_exit = test_with_files()

    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"PIPE (production):  socket_ready={pipe_ready}, exit_code={pipe_exit}")
    print(f"Files (replay):     socket_ready={file_ready}, exit_code={file_exit}")
    print()

    if not pipe_ready and file_ready:
        print("CONCLUSION: PIPE blocking confirmed!")
        print("Production scorer hangs when stdout/stderr directed to PIPE")
        print("because parent never reads from PIPE, buffer fills, child blocks.")
        return 0
    else:
        print("CONCLUSION: PIPE blocking NOT confirmed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
