"""Offline execution-identity and replay-isolation integration tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FAKE_TARGET = REPO_ROOT / "tests" / "fixtures" / "nv_feedback_fake_target.py"
RULES = REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"
PROBE_SRC = REPO_ROOT / "test" / "v071" / "status_consumer_probe.c"
COVSET_SRC = REPO_ROOT / "src" / "afl-fuzz-nv-covset.c"
CJSON_SRC = REPO_ROOT / "src" / "third_party" / "cjson" / "cJSON.c"
INCLUDE = REPO_ROOT / "include"

AUDITED_RUNNER = """
import os
import runpy
import sys

fixture = sys.argv[1]

def deny_network(event, _args):
    if event.startswith("socket."):
        os.write(2, ("NETWORK_AUDIT_EVENT=" + event + "\\n").encode())
        raise RuntimeError("network activity is forbidden in this fixture")

sys.addaudithook(deny_network)
sys.argv = [fixture]
runpy.run_path(fixture, run_name="__main__")
"""

VALID_FULL_HTTP = (
    b"PUT /offline/node HTTP/1.1\r\n"
    b"Content-Type: application/json\r\n"
    b"\r\n"
    b'{"name":"offline-node","properties":{"cm:title":"local"}}'
)


class NvFeedbackExecutionIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nv_feedback_identity_")
        self.tmp = Path(self._tmp.name)
        self.status = self.tmp / "status.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_target(self, testcase: bytes) -> subprocess.CompletedProcess[bytes]:
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "NV_STATUS_PATH": str(self.status),
            "NV_BODY_RULES": str(RULES),
        }
        return subprocess.run(
            [sys.executable, "-c", AUDITED_RUNNER, str(FAKE_TARGET)],
            input=testcase,
            capture_output=True,
            cwd=REPO_ROOT,
            env=env,
            timeout=20,
        )

    def read_status(self) -> dict:
        return json.loads(self.status.read_text(encoding="utf-8"))

    @property
    def seq_path(self) -> Path:
        return self.status.parent / "status.json.seq"

    def consume(self, *documents: Path) -> list[str]:
        probe = self.tmp / "status_consumer_probe"
        compile_proc = subprocess.run(
            [
                "gcc",
                "-std=c11",
                "-Wall",
                "-I",
                str(INCLUDE),
                "-o",
                str(probe),
                str(PROBE_SRC),
                str(COVSET_SRC),
                str(CJSON_SRC),
                "-lm",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=20,
        )
        self.assertEqual(compile_proc.returncode, 0, compile_proc.stderr)
        consumed = subprocess.run(
            [str(probe), *(str(path) for path in documents)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=20,
        )
        self.assertEqual(consumed.returncode, 0, consumed.stderr)
        return [line.split()[0] for line in consumed.stdout.splitlines()]

    def test_each_legitimate_execution_mints_exactly_one_new_exec_seq(self) -> None:
        first = self.run_target(VALID_FULL_HTTP)
        self.assertEqual(first.returncode, 0, first.stderr.decode(errors="replace"))
        first_seq = self.read_status()["exec_seq"]

        second = self.run_target(VALID_FULL_HTTP)
        self.assertEqual(second.returncode, 0, second.stderr.decode(errors="replace"))
        second_seq = self.read_status()["exec_seq"]

        self.assertGreater(first_seq, 0)
        self.assertEqual(second_seq, first_seq + 1)
        self.assertEqual(int(self.seq_path.read_text()), second_seq)

    def test_body_rejection_after_extraction_mints_no_status_or_exec_seq(self) -> None:
        rejected = self.run_target(
            b"PUT /offline/node HTTP/1.1\nContent-Type: application/json\n\n"
            b"not-json"
        )

        self.assertEqual(
            rejected.returncode,
            3,
            rejected.stderr.decode(errors="replace"),
        )
        self.assertFalse(self.status.exists())
        self.assertFalse(self.seq_path.exists())

    def test_representation_rejection_leaves_no_fresh_observation(self) -> None:
        baseline = self.run_target(VALID_FULL_HTTP)
        self.assertEqual(
            baseline.returncode,
            0,
            baseline.stderr.decode(errors="replace"),
        )
        status_before = self.status.read_bytes()
        seq_before = self.seq_path.read_bytes()

        rejected = self.run_target(
            b"PUT /offline/node HTTP/1.1\r\n"
            b"Content-Type: application/json\r\n"
            b'{"name":"missing-envelope-boundary"}'
        )

        self.assertEqual(
            rejected.returncode,
            2,
            rejected.stderr.decode(errors="replace"),
        )
        self.assertEqual(self.status.read_bytes(), status_before)
        self.assertEqual(self.seq_path.read_bytes(), seq_before)
        self.assertEqual(self.consume(self.status, self.status), ["ACCEPT", "REPLAY"])

    def test_body_rejection_leaves_only_replay_feedback(self) -> None:
        baseline = self.run_target(VALID_FULL_HTTP)
        self.assertEqual(
            baseline.returncode,
            0,
            baseline.stderr.decode(errors="replace"),
        )
        status_before = self.status.read_bytes()
        seq_before = self.seq_path.read_bytes()

        rejected = self.run_target(
            b"PUT /offline/node HTTP/1.1\nContent-Type: application/json\n\n"
            b"not-json"
        )

        self.assertEqual(
            rejected.returncode,
            3,
            rejected.stderr.decode(errors="replace"),
        )
        self.assertEqual(self.status.read_bytes(), status_before)
        self.assertEqual(self.seq_path.read_bytes(), seq_before)
        self.assertEqual(self.consume(self.status, self.status), ["ACCEPT", "REPLAY"])

    def test_fixture_completes_with_socket_activity_forbidden(self) -> None:
        completed = self.run_target(VALID_FULL_HTTP)

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr.decode(errors="replace"),
        )
        self.assertNotIn(b"NETWORK_AUDIT_EVENT=", completed.stderr)

    def test_same_and_stale_exec_seq_are_replay_only(self) -> None:
        first = self.run_target(VALID_FULL_HTTP)
        self.assertEqual(first.returncode, 0, first.stderr.decode(errors="replace"))
        first_status = self.tmp / "first-status.json"
        shutil.copyfile(self.status, first_status)

        second = self.run_target(VALID_FULL_HTTP)
        self.assertEqual(second.returncode, 0, second.stderr.decode(errors="replace"))
        second_status = self.tmp / "second-status.json"
        shutil.copyfile(self.status, second_status)

        self.assertEqual(
            self.consume(first_status, second_status, second_status, first_status),
            ["ACCEPT", "ACCEPT", "REPLAY", "REPLAY"],
        )


if __name__ == "__main__":
    unittest.main()
