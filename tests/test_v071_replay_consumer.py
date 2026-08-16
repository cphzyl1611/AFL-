"""v0.7.1 -- the C replay consumer against real harness output.

Checking that the JSON contains an ``exec_seq`` key proves nothing about the
fuzzer.  What matters is the decision ``nv_status_is_fresh()`` makes when it is
handed documents the real ``nv_http_harness.py`` actually wrote.

The probe in ``test/v071/status_consumer_probe.c`` links the production
``src/afl-fuzz-nv-covset.c`` and replays the production extraction logic, so
the ACCEPT/REPLAY verdicts below come from the shipping implementation.

The sequence under test is the one the release protocol asks for:

    execution #1              -> ACCEPT
    identical execution #2    -> ACCEPT   (legacy stamp would have said REPLAY)
    re-read of document #2    -> REPLAY
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_v071_exec_seq import (
    LocalServer,
    run_harness,
    read_status,
    write_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_SRC = REPO_ROOT / "test" / "v071" / "status_consumer_probe.c"
COVSET_SRC = REPO_ROOT / "src" / "afl-fuzz-nv-covset.c"
CJSON_SRC = REPO_ROOT / "src" / "third_party" / "cjson" / "cJSON.c"
INCLUDE = REPO_ROOT / "include"

SEED = b'POST /api/doc/query HTTP/1.1\r\n\r\n{"k":"v"}'


class ReplayConsumerTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="v071_replay_consumer_"))
        cls.probe = cls.tmp / "status_consumer_probe"

        compile_proc = subprocess.run(
            [
                "gcc", "-std=c11", "-Wall", "-I", str(INCLUDE),
                "-o", str(cls.probe),
                str(PROBE_SRC), str(COVSET_SRC), str(CJSON_SRC), "-lm",
            ],
            capture_output=True, text=True,
        )
        if compile_proc.returncode != 0:
            raise AssertionError(
                f"failed to compile status_consumer_probe:\n{compile_proc.stderr}"
            )

        cls.server = LocalServer()
        cls.config = cls.tmp / "task.json"
        write_config(cls.config, cls.server.base)

        # Two executions of the same request, each preserved as its own file
        # so the consumer can be driven over them in order.
        cls.status = cls.tmp / "nv_http_status.json"
        cls.doc1 = cls.tmp / "exec1.json"
        cls.doc2 = cls.tmp / "exec2.json"

        run_harness(cls.status, cls.config, SEED)
        shutil.copy(cls.status, cls.doc1)

        run_harness(cls.status, cls.config, SEED)
        shutil.copy(cls.status, cls.doc2)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def consume(self, *docs):
        proc = subprocess.run(
            [str(self.probe)] + [str(d) for d in docs],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [line.split()[0] for line in proc.stdout.strip().splitlines()]

    def test_the_two_executions_really_were_indistinguishable_legacy(self):
        """Without exec_seq these two documents would collide.

        Guards the premise of the whole test: if the bodies or responses
        differed, accepting both would prove nothing.
        """
        a = read_status(self.doc1)
        b = read_status(self.doc2)
        self.assertEqual(a["body_hash16"], b["body_hash16"])
        self.assertEqual(a["class"], b["class"])
        self.assertEqual(a["http_code"], b["http_code"])
        self.assertNotEqual(a["exec_seq"], b["exec_seq"])

    def test_distinct_executions_are_both_accepted(self):
        self.assertEqual(self.consume(self.doc1, self.doc2),
                         ["ACCEPT", "ACCEPT"])

    def test_rereading_the_same_document_is_a_replay(self):
        self.assertEqual(self.consume(self.doc1, self.doc2, self.doc2),
                         ["ACCEPT", "ACCEPT", "REPLAY"])

    def test_identity_used_is_exec_seq_not_the_legacy_stamp(self):
        proc = subprocess.run(
            [str(self.probe), str(self.doc1), str(self.doc2)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for line in proc.stdout.strip().splitlines():
            self.assertIn("identity=exec_seq", line,
                          f"consumer fell back to the legacy stamp: {line}")

    def test_a_document_with_no_exec_seq_still_uses_the_legacy_fallback(self):
        """The upgrade must not break harnesses that never report exec_seq."""
        legacy = self.tmp / "legacy.json"
        doc = read_status(self.doc1)
        doc.pop("exec_seq")
        with open(legacy, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

        proc = subprocess.run(
            [str(self.probe), str(legacy), str(legacy)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.strip().splitlines()
        self.assertEqual([ln.split()[0] for ln in lines], ["ACCEPT", "REPLAY"])
        for line in lines:
            self.assertIn("identity=legacy_stamp", line)


if __name__ == "__main__":
    unittest.main()
