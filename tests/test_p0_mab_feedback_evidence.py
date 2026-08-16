"""P0 acceptance assertions over the deterministic integration evidence.

Guards the eight properties the P0 round had to establish, against the
evidence the fuzzer itself wrote:

  UCB actually ran, every arm was pulled, reward was earned, the reward moved
  an arm's mean off its initial value, security states were discovered, the
  discovery credited a seed, and the same chain produced evidence for two
  platform profiles.

Every number is read from fuzzer_stats / eval_report.json / summary.csv, and
the three are cross-checked against each other.
"""

import csv
import json
import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

PROFILES = ["o2oa_cms_doc_list", "alfresco_metadata_update"]

MIN_SECURITY_STATES = 3


def evidence_dir(profile: str) -> Path:
    return REPO_ROOT / "out" / f"p0_mab_feedback_{profile}"


def parse_key_value(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip()
    return out


def load(profile: str):
    base = evidence_dir(profile)
    if not base.is_dir():
        raise unittest.SkipTest(f"P0 evidence not present: {base}")
    stats = parse_key_value(base / "fuzzer_stats")
    report = json.loads((base / "eval_report.json").read_text(encoding="utf-8"))
    with (base / "summary.csv").open(encoding="utf-8-sig", newline="") as fh:
        summary = next(csv.DictReader(fh))
    return stats, report, summary


class P0MabFeedbackEvidenceTest(unittest.TestCase):
    def test_ucb_branch_ran_for_every_profile(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                stats, report, _ = load(profile)
                self.assertGreater(
                    int(stats["nv_mab_ucb_picks"]), 0,
                    "UCB never executed; selection stayed in warm-up",
                )
                self.assertEqual(
                    int(stats["nv_mab_ucb_picks"]), report["mab"]["ucb_picks"]
                )

    def test_exploration_coefficient_is_not_silently_zero(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                stats, report, _ = load(profile)
                self.assertGreater(float(stats["nv_mab_c"]), 0.0)
                self.assertGreater(int(stats["nv_mab_min_explore"]), 0)
                self.assertAlmostEqual(
                    float(stats["nv_mab_c"]), report["mab"]["c"], places=6
                )

    def test_every_arm_was_pulled(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                stats, _, _ = load(profile)
                for arm in range(3):
                    self.assertGreater(
                        int(stats[f"nv_mab_arm{arm}_pulls"]), 0,
                        f"arm{arm} never pulled",
                    )

    def test_reward_was_earned_and_moved_a_mean(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                stats, _, _ = load(profile)
                sums = [float(stats[f"nv_mab_arm{a}_sum"]) for a in range(3)]
                means = [float(stats[f"nv_mab_arm{a}_mean"]) for a in range(3)]
                self.assertTrue(
                    any(s > 0 for s in sums), f"no positive reward earned: {sums}"
                )
                self.assertTrue(
                    any(m != 0.0 for m in means),
                    f"every arm mean still at its initial value: {means}",
                )

    def test_security_states_were_discovered(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                stats, report, _ = load(profile)
                total = int(stats["security_state_total"])
                self.assertGreaterEqual(total, MIN_SECURITY_STATES)
                self.assertGreater(int(stats["security_state_observations"]), 0)
                self.assertEqual(
                    total, report["security_state_cov"]["security_state_total"]
                )

    def test_seed_scheduler_received_security_state_credit(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                stats, _, summary = load(profile)
                self.assertGreater(
                    int(stats["security_state_seed_credit"]), 0,
                    "no queue entry was ever credited with a new state",
                )
                self.assertGreater(
                    int(stats["ss_cov_sum"]), 0,
                    "ss_cov_cnt never left zero; the scheduler sees no signal",
                )
                self.assertEqual(
                    int(stats["security_state_seed_credit"]),
                    int(summary["security_state_seed_credit"]),
                )

    def test_state_log_reconciles_with_fuzzer_counters(self) -> None:
        """The target's own log must explain the fuzzer's counters."""
        for profile in PROFILES:
            with self.subTest(profile=profile):
                stats, _, summary = load(profile)
                self.assertGreaterEqual(
                    int(summary["state_log_records"]),
                    int(stats["security_state_observations"]),
                    "fewer target executions than observed states",
                )
                self.assertGreaterEqual(
                    int(summary["state_log_distinct_states"]),
                    int(stats["security_state_total"]),
                    "covset holds states the target never logged",
                )

    def test_security_state_cov_is_reported_apart_from_edge_coverage(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                _, report, _ = load(profile)
                self.assertIn("security_state_cov", report)
                self.assertIn("cov", report)
                self.assertIn(
                    "not AFL native edge coverage",
                    report["security_state_cov"]["note"],
                )


if __name__ == "__main__":
    unittest.main()
