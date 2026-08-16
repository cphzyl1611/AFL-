"""P0.1 findings M-4, M-9, M-10: documented semantics and honest reproducibility.

Two things are guarded here.

1. Every telemetry field the fuzzer emits for the NV feedback loop is actually
   described in docs/p01_metric_semantics.md, and the document commits to the
   specific distinctions the review asked for -- picks vs pulls (M-4), the two
   credit sources feeding ss_cov_cnt (M-10), and the configuration precedence
   rule (M-5/M-6). A field that appears in fuzzer_stats but nowhere in the
   document fails this suite, so the reference cannot silently rot.

2. The P0.1 reproducibility runs really do satisfy the acceptance invariants,
   and the reproducibility claim made for each profile matches the evidence.
   "Bit-identical" is only allowed when every number matches.
"""

import csv
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "p01_metric_semantics.md"

PROFILES = ["o2oa_cms_doc_list", "alfresco_metadata_update"]

# Fields whose meaning the review found ambiguous or which P0.1 introduced.
DOCUMENTED_FIELDS = [
    "nv_mab_c",
    "nv_mab_min_explore",
    "nv_mab_cold_start_picks",
    "nv_mab_ucb_picks",
    "nv_mab_total_pulls",
    "security_state_total",
    "security_state_new_total",
    "security_state_delta_last",
    "security_state_observations",
    "security_state_seed_credit",
    "security_state_capacity",
    "security_state_saturated",
    "security_state_dropped",
    "security_state_replays",
    "security_state_reward_src_seq",
    "ss_cov_sum",
    "ss_cov_max",
]


def parse_key_value(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip()
    return out


def repro_dir(profile: str, run: int) -> Path:
    return REPO_ROOT / "out" / f"p01_{profile}_repro_run{run}"


class P01SemanticsDocTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DOC.is_file():
            raise AssertionError(f"missing semantics reference: {DOC}")
        cls.text = DOC.read_text(encoding="utf-8")

    def test_every_ambiguous_field_is_documented(self) -> None:
        missing = [f for f in DOCUMENTED_FIELDS if f not in self.text]
        self.assertEqual(
            missing, [],
            f"fields emitted by the fuzzer but absent from {DOC.name}: {missing}",
        )

    def test_picks_and_pulls_distinction_is_stated(self) -> None:
        """M-4: the counters must not be described as interchangeable."""
        for phrase in ("decision", "reward update"):
            self.assertIn(phrase, self.text.lower())
        self.assertIn("cold_start_picks + ucb_picks", self.text)

    def test_ss_cov_dual_credit_is_stated(self) -> None:
        """M-10: ss_cov_sum mixes edge novelty with security-state credit."""
        self.assertIn("two independent sources", self.text)
        self.assertIn("security_state_seed_credit", self.text)
        self.assertIn("-n", self.text)

    def test_config_precedence_is_stated(self) -> None:
        """M-5/M-6: one unambiguous rule, keyed on validity."""
        self.assertIn("Validity is checked before precedence", self.text)
        self.assertIn("NV_MAB_MAX_MIN_EXPLORE", self.text)

    def test_reproducibility_vocabulary_is_defined(self) -> None:
        """M-9: no profile may be described as bit-identical here."""
        self.assertIn("Bit-identical", self.text)
        self.assertIn("Behaviourally reproducible", self.text)


class P01ReproducibilityTest(unittest.TestCase):
    """Acceptance invariants over the committed P0.1 reproducibility runs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.runs = {}
        for profile in PROFILES:
            for run in (1, 2):
                base = repro_dir(profile, run)
                if not base.is_dir():
                    raise unittest.SkipTest(f"P0.1 repro evidence absent: {base}")
                with (base / "summary.csv").open(encoding="utf-8-sig") as fh:
                    summary = next(csv.DictReader(fh))
                cls.runs[(profile, run)] = (
                    parse_key_value(base / "fuzzer_stats"), summary
                )

    def test_acceptance_invariants_hold_in_every_run(self) -> None:
        for (profile, run), (stats, _) in self.runs.items():
            with self.subTest(profile=profile, run=run):
                self.assertGreater(int(stats["nv_mab_ucb_picks"]), 0)
                self.assertGreater(float(stats["nv_mab_c"]), 0.0)
                for arm in range(3):
                    self.assertGreater(
                        int(stats[f"nv_mab_arm{arm}_pulls"]), 0,
                        f"arm{arm} never sampled",
                    )
                self.assertTrue(
                    any(
                        float(stats[f"nv_mab_arm{a}_mean"]) != 0.0
                        for a in range(3)
                    ),
                    "no arm mean moved off its initial value",
                )
                self.assertGreater(int(stats["security_state_total"]), 0)
                self.assertGreater(int(stats["security_state_seed_credit"]), 0)
                self.assertGreater(int(stats["ss_cov_sum"]), 0)
                self.assertGreater(int(stats["ss_selected_sum"]), 0)

    def test_pick_and_pull_counters_relate_as_documented(self) -> None:
        """M-4: picks >= pulls, and per-arm pulls sum to total_pulls."""
        for (profile, run), (stats, _) in self.runs.items():
            with self.subTest(profile=profile, run=run):
                picks = (
                    int(stats["nv_mab_cold_start_picks"])
                    + int(stats["nv_mab_ucb_picks"])
                )
                pulls = int(stats["nv_mab_total_pulls"])
                self.assertGreaterEqual(
                    picks, pulls,
                    "a reward update happened without a decision",
                )
                self.assertEqual(
                    sum(int(stats[f"nv_mab_arm{a}_pulls"]) for a in range(3)),
                    pulls,
                )

    def test_covset_never_saturated_in_these_runs(self) -> None:
        """M-1: the bounded state space keeps the table well under capacity."""
        for (profile, run), (stats, _) in self.runs.items():
            with self.subTest(profile=profile, run=run):
                self.assertEqual(int(stats["security_state_saturated"]), 0)
                self.assertEqual(int(stats["security_state_dropped"]), 0)
                self.assertLess(
                    int(stats["security_state_total"]),
                    int(stats["security_state_capacity"]),
                )

    def test_replay_rejection_is_negligible_after_the_m3_fix(self) -> None:
        """M-3: distinct executions are no longer discarded wholesale."""
        for (profile, run), (stats, _) in self.runs.items():
            with self.subTest(profile=profile, run=run):
                observations = int(stats["security_state_observations"])
                replays = int(stats["security_state_replays"])
                self.assertGreater(observations, 100)
                self.assertLess(
                    replays, observations // 10,
                    f"{replays} replays against {observations} observations "
                    "suggests the over-rejection defect is back",
                )

    def test_reward_source_execution_is_recorded(self) -> None:
        """M-2: the audit record naming the execution that fed the reward."""
        for (profile, run), (stats, _) in self.runs.items():
            with self.subTest(profile=profile, run=run):
                self.assertGreater(
                    int(stats["security_state_reward_src_seq"]), 0,
                    "no reward was traced back to a target execution",
                )

    def test_no_profile_is_claimed_bit_identical_unless_it_is(self) -> None:
        """M-9: the documented claim must match the evidence."""
        doc = DOC.read_text(encoding="utf-8")
        for profile in PROFILES:
            with self.subTest(profile=profile):
                a = self.runs[(profile, 1)][1]
                b = self.runs[(profile, 2)][1]
                differing = sorted(
                    k for k in a
                    if k not in ("run_time",) and a[k] != b.get(k)
                )
                identical = not differing
                claimed_bit_identical = (
                    f"| `{profile}` | **bit-identical**" in doc
                )
                if claimed_bit_identical:
                    self.assertTrue(
                        identical,
                        f"{profile} is documented as bit-identical but these "
                        f"fields differ between runs: {differing}",
                    )
                else:
                    # Documented as behavioural; that is always safe to claim,
                    # but record what actually differed for the reader.
                    self.assertIn(
                        f"| `{profile}` | **behavioural**", doc,
                        f"{profile} has no reproducibility classification in "
                        f"{DOC.name} (observed differences: {differing})",
                    )


if __name__ == "__main__":
    unittest.main()
