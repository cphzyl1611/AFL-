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
        "env_c_explicit_zero_is_honoured",
        "env_min_explore_override_applies",
        "ucb_phase_is_reached",
        "ucb_follows_updated_mean",
        "reward_updates_mean_incrementally",
    ],
    "unit_nv_sched": [
        "security_state_credit_raises_weight",
        "weight_scales_with_security_state_count",
        "over_selection_suppresses_weight",
        "weight_has_a_floor",
    ],
}

SOURCES = {
    "unit_nv_mab": "src/afl-fuzz-nv-mab.c",
    "unit_nv_sched": "src/afl-fuzz-nv-sched.c",
}


def build_and_run(name: str) -> str:
    test_src = REPO_ROOT / "test" / "unittests" / f"{name}.c"
    impl_src = REPO_ROOT / SOURCES[name]
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / name
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
    return run_proc.stdout


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


if __name__ == "__main__":
    unittest.main()
