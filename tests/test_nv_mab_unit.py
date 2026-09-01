"""Compile and run the deterministic C unit tests for the NV feedback core.

These cover the two P0 audit findings directly against the production
functions in src/afl-fuzz-nv-mab.c and src/afl-fuzz-nv-sched.c:

  * the UCB exploration coefficient must never be a silent zero;
  * cold start must sample every enabled arm fairly instead of draining arm0;
  * a seed credited with new security states must out-weigh one that is not.
"""

import shutil
import subprocess
import tempfile
import unittest
import json
import math
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INCLUDE = REPO_ROOT / "include"

SUITES = {
    "unit_nv_mab": [
        "cold_start_is_fair",
        "scope_mask_respected",
        "defaults_give_positive_c",
        "uninitialised_mab_is_never_silently_greedy",
        "env_c_override_applies",
        "env_c_negative_falls_back",
        "env_c_garbage_falls_back",
        "env_c_zero_falls_back",
        "env_c_validity_is_reported",
        "env_overflow_falls_back",
        "env_min_explore_validity_is_reported",
        "env_min_explore_override_applies",
        "ucb_phase_is_reached",
        "ucb_follows_updated_mean",
        "reward_updates_mean_incrementally",
    ],
    "unit_nv_mab_journal": [
        "journal_positive_update",
        "journal_zero_reward_update",
        "journal_schema_contains_required_update_fields",
        "journal_update_aggregate_ordering",
        "journal_open_failure_returns_failure",
        "journal_open_failure_marks_audit_invalid_without_rollback",
        "journal_write_failure_is_fail_closed",
        "journal_flush_failure_is_fail_closed",
        "journal_non_update_events_do_not_increment_pulls",
        "journal_non_update_failure_is_fail_closed",
        "journal_zero_exec_seq_pending_is_cleared",
        "journal_arm_mismatch_is_rejected",
        "journal_missing_actual_arm_is_rejected",
    ],
    "unit_nv_sched": [
        "security_state_credit_raises_weight",
        "weight_scales_with_security_state_count",
        "over_selection_suppresses_weight",
        "weight_has_a_floor",
    ],
    "unit_nv_sched_picker": [
        "three_metadata_seeds_are_full_http_distinct_and_credential_free",
        "seed_directory_is_loaded_through_read_testcases_and_add_to_queue",
        "production_picker_selects_each_initial_seed",
        "selection_audit_has_exact_allowed_fields",
        "selection_audit_has_no_sensitive_fields",
        "selection_audit_distinguishes_seeds_without_request_data",
        "production_picker_uses_security_state_credit",
        "selection_audit_does_not_change_picker_decision",
        "selection_audit_is_disabled_when_path_unset",
        "selection_audit_does_not_modify_rng_or_weights",
        "seed_audit_open_failure_is_observable",
        "seed_audit_write_failure_is_observable",
        "seed_audit_close_failure_is_observable",
    ],
}

SOURCES = {
    "unit_nv_mab": "src/afl-fuzz-nv-mab.c",
    "unit_nv_mab_journal": "src/afl-fuzz-nv-mab.c",
    "unit_nv_sched": "src/afl-fuzz-nv-sched.c",
    "unit_nv_sched_picker": [
        "src/afl-fuzz-queue.c",
        "src/afl-fuzz-nv-sched.c",
        "src/afl-fuzz-init.c",
    ],
}


def build_and_run(name: str) -> str:
    test_src = REPO_ROOT / "test" / "unittests" / f"{name}.c"
    sources = SOURCES[name]
    if isinstance(sources, str):
        sources = [sources]
    impl_sources = [REPO_ROOT / source for source in sources]
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / name
        compile_proc = subprocess.run(
            [
                "gcc", "-std=c11", "-Wall", "-ffunction-sections",
                "-fdata-sections", "-I", str(INCLUDE), "-o", str(binary),
                str(test_src), *(str(source) for source in impl_sources),
                "-Wl,--gc-sections", "-lm",
            ],
            capture_output=True,
            text=True,
        )
        if compile_proc.returncode != 0:
            raise AssertionError(
                f"failed to compile {name}:\n{compile_proc.stderr}"
            )
        run_proc = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=60
        )
    if run_proc.returncode != 0:
        raise AssertionError(
            f"{name} reported failures (exit {run_proc.returncode}):\n"
            f"{run_proc.stdout}"
        )
    return run_proc.stdout + run_proc.stderr


class NvFeedbackUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("gcc") is None:
            raise unittest.SkipTest("gcc is not available")
        cls.output = {name: build_and_run(name) for name in SUITES}

    def test_every_case_passes(self) -> None:
        for name, cases in SUITES.items():
            out = self.output[name]
            for case in cases:
                self.assertIn(
                    f"PASS {case}", out, f"{name}: {case} did not pass\n{out}"
                )
            self.assertIn("FAILURES 0", out, f"{name} reported failures\n{out}")

    def test_cold_start_visits_every_arm(self) -> None:
        """The audited bug produced 012000000...; a fair start cycles."""
        line = next(
            l for l in self.output["unit_nv_mab"].splitlines()
            if l.startswith("SEQ cold_start_is_fair ")
        )
        sequence = line.split(" ", 2)[2]
        for arm in "012":
            self.assertGreaterEqual(
                sequence[:12].count(arm), 3,
                f"arm {arm} under-sampled in the first 12 decisions: {sequence}",
            )

    def test_ucb_branch_is_actually_entered(self) -> None:
        line = next(
            l for l in self.output["unit_nv_mab"].splitlines()
            if l.startswith("PICKS ucb_phase_is_reached ")
        )
        ucb = int(line.split("ucb=")[1])
        self.assertGreater(ucb, 0, f"UCB branch never ran: {line}")

    def test_reward_update_changes_the_next_decision(self) -> None:
        line = next(
            l for l in self.output["unit_nv_mab"].splitlines()
            if l.startswith("UCBSHIFT ")
        )
        self.assertIn("before=0", line)
        self.assertIn("after=2", line)

    def test_production_picker_visits_multiple_seeds(self) -> None:
        line = next(
            l for l in self.output["unit_nv_sched_picker"].splitlines()
            if l.startswith("SELECTED ")
        )
        selected = line.split()[1:]
        self.assertEqual(set(selected), {"0", "1", "2"}, line)

    def test_seed_selection_audit_has_exact_allowed_fields(self) -> None:
        """Parse the JSON line emitted by the production C audit writer."""
        lines = [
            line.removeprefix("AUDIT_JSON ")
            for line in self.output["unit_nv_sched_picker"].splitlines()
            if line.startswith("AUDIT_JSON ")
        ]
        self.assertGreaterEqual(len(lines), 3)
        for line in lines:
            record = json.loads(line)
            self.assertEqual(
                set(record),
                {"queue_id", "depth", "ss_cov_cnt", "ss_selected_cnt", "ss_prob"},
            )
            self.assertIsInstance(record["queue_id"], int)
            self.assertIsInstance(record["depth"], int)
            self.assertIsInstance(record["ss_cov_cnt"], int)
            self.assertIsInstance(record["ss_selected_cnt"], int)
            self.assertIsInstance(record["ss_prob"], (int, float))
            self.assertTrue(math.isfinite(record["ss_prob"]))

    def test_seed_selection_audit_has_no_sensitive_fields(self) -> None:
        lines = [
            line.removeprefix("AUDIT_JSON ").lower()
            for line in self.output["unit_nv_sched_picker"].splitlines()
            if line.startswith("AUDIT_JSON ")
        ]
        for raw in lines:
            for forbidden in (
                "event", "authorization", "token", "password", "username",
                "seed", "request", "body", "path", "alfresco", "metadata",
            ):
                self.assertNotIn(forbidden, raw)

    def test_seed_audit_failure_fallback_is_observable(self) -> None:
        self.assertGreaterEqual(
            self.output["unit_nv_sched_picker"].count(
                "NV_SEED_SELECTION_AUDIT_ERROR"
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
