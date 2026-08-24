"""Compile and run the deterministic C unit tests for the security-state covset.

Covers P0.1 finding M-1: the coverage set is a fixed-capacity open-addressed
table, and its probe loop had no termination condition for a full table -- a
brand new state arriving after saturation spun forever and hung afl-fuzz.

The suite is run under a wall clock timeout on purpose.  An infinite probe
loop is not an assertion failure, it is a hang, so the timeout *is* the
regression assertion: if the bound is ever removed, this test fails instead of
blocking the suite.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INCLUDE = REPO_ROOT / "include"

# Generous next to a bounded run (which finishes in microseconds) and still far
# below anything an unbounded probe loop would ever reach.
RUN_TIMEOUT_SEC = 20

CASES = [
    "fill_reports_every_slot_inserted",
    "full_table_finds_existing_state",
    "full_table_reports_saturation",
    "saturated_insert_does_not_bump_used",
    "saturated_insert_evicts_nothing",
    "lookup_still_works_after_saturation",
    "space_reclaimed_accepts_new_state",
    # M-1C: the state key itself must have bounded cardinality
    "method_is_canonicalised",
    "unknown_methods_collapse_to_one_token",
    "known_classes_survive",
    "unknown_classes_collapse_to_other",
    "wellformed_path_is_passed_through",
    "malformed_paths_are_labelled",
    "overlong_path_is_labelled",
    "nonprintable_path_is_labelled",
    "malformed_paths_share_one_label",
    # M-3: replay identity is the execution, not the content
    "same_execution_consumed_twice_is_a_replay",
    "identical_content_from_a_new_execution_is_accepted",
    "legacy_stamp_fallback_still_works",
    "stale_sequence_is_replay_and_preserves_high_water_mark",
    "newer_sequence_after_stale_is_accepted",
    "accepted_sequence_replay_is_rejected",
]


class NvCovsetUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("gcc") is None:
            raise unittest.SkipTest("gcc is not available")

        test_src = REPO_ROOT / "test" / "unittests" / "unit_nv_covset.c"
        impl_src = REPO_ROOT / "src" / "afl-fuzz-nv-covset.c"

        cls._tmp = tempfile.TemporaryDirectory()
        binary = Path(cls._tmp.name) / "unit_nv_covset"
        compile_proc = subprocess.run(
            [
                "gcc", "-std=c11", "-Wall", "-I", str(INCLUDE),
                "-o", str(binary), str(test_src), str(impl_src), "-lm",
            ],
            capture_output=True,
            text=True,
        )
        if compile_proc.returncode != 0:
            raise AssertionError(
                f"failed to compile unit_nv_covset:\n{compile_proc.stderr}"
            )

        try:
            proc = subprocess.run(
                [str(binary)], capture_output=True, text=True,
                timeout=RUN_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as exc:
            partial = (exc.stdout or b"")
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            raise AssertionError(
                "nv_covset_insert_into did not return within "
                f"{RUN_TIMEOUT_SEC}s -- the probe loop is unbounded on a full "
                f"table.\nPartial output:\n{partial}"
            ) from exc

        cls.output = proc.stdout
        cls.returncode = proc.returncode

    @classmethod
    def tearDownClass(cls) -> None:
        tmp = getattr(cls, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_every_case_passes(self) -> None:
        for case in CASES:
            self.assertIn(
                f"PASS {case}", self.output, f"{case} did not pass\n{self.output}"
            )
        self.assertIn("FAILURES 0", self.output, self.output)
        self.assertEqual(self.returncode, 0, self.output)

    def test_saturating_insert_actually_returned(self) -> None:
        """The hang guard: the call must be entered and then come back."""
        self.assertIn("PROBE saturating_insert_start", self.output)
        self.assertIn(
            "PROBE saturating_insert_returned rc=-1", self.output,
            f"saturating insert did not return SATURATED\n{self.output}",
        )


if __name__ == "__main__":
    unittest.main()
