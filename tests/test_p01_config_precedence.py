"""P0.1 findings M-5/M-6/M-7: one unambiguous configuration precedence.

The rule, asserted here end to end against the real afl-fuzz binary:

    valid environment override > valid task.json value > compiled default

"Valid" is checked before precedence is applied.  A variable that merely
exists must not suppress a lower layer -- the P0 code gated task.json on
`!getenv("NV_MAB_C")`, so `NV_MAB_C=` or `NV_MAB_C=garbage` silently discarded
a good task.json value and fell all the way back to the compiled default.

Also pinned here:
  M-6  c <= 0 is invalid input, not a pure-greedy opt-out.
  M-7  overflowing overrides (1e400, 99999999999999999999) are rejected
       instead of yielding inf / LONG_MAX.

Evidence is written to out/p01_config_precedence/matrix.csv.
"""

import csv
import os
import shutil
import subprocess
import tempfile
import sysconfig
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = None
AFL_FUZZ = REPO_ROOT / "afl-fuzz"
TARGET = REPO_ROOT / "targets" / "nv_p0_deterministic_target.py"
SEEDS = REPO_ROOT / "in" / "p0_o2oa_cms_doc_list"

DEFAULT_C = 0.05
DEFAULT_MIN_EXPLORE = 8
CASE_TIMEOUT = 60

# label, task.json fragment, env overrides, expected c, expected min_explore
MATRIX = [
    ("env_absent__task_absent", {}, {}, DEFAULT_C, DEFAULT_MIN_EXPLORE),
    ("env_absent__task_valid",
     {"mab_c": 0.9, "mab_min_explore": 5}, {}, 0.9, 5),
    ("env_valid__task_valid",
     {"mab_c": 0.9, "mab_min_explore": 5},
     {"NV_MAB_C": "0.3", "NV_MAB_MIN_EXPLORE": "2"}, 0.3, 2),
    ("env_empty__task_valid",
     {"mab_c": 0.9, "mab_min_explore": 5},
     {"NV_MAB_C": "", "NV_MAB_MIN_EXPLORE": ""}, 0.9, 5),
    ("env_whitespace__task_valid",
     {"mab_c": 0.9, "mab_min_explore": 5},
     {"NV_MAB_C": "   ", "NV_MAB_MIN_EXPLORE": "  "}, 0.9, 5),
    ("env_garbage__task_valid",
     {"mab_c": 0.9, "mab_min_explore": 5},
     {"NV_MAB_C": "abc", "NV_MAB_MIN_EXPLORE": "xyz"}, 0.9, 5),
    ("env_negative__task_valid",
     {"mab_c": 0.9, "mab_min_explore": 5},
     {"NV_MAB_C": "-1", "NV_MAB_MIN_EXPLORE": "-4"}, 0.9, 5),
    ("env_zero__task_valid",
     {"mab_c": 0.9, "mab_min_explore": 5},
     {"NV_MAB_C": "0", "NV_MAB_MIN_EXPLORE": "0"}, 0.9, 5),
    ("env_overflow__task_valid",
     {"mab_c": 0.9, "mab_min_explore": 5},
     {"NV_MAB_C": "1e400", "NV_MAB_MIN_EXPLORE": "99999999999999999999"},
     0.9, 5),
    ("env_zero__task_absent", {}, {"NV_MAB_C": "0"},
     DEFAULT_C, DEFAULT_MIN_EXPLORE),
    ("env_overflow__task_absent", {},
     {"NV_MAB_C": "1e400", "NV_MAB_MIN_EXPLORE": "99999999999999999999"},
     DEFAULT_C, DEFAULT_MIN_EXPLORE),
    ("env_absent__task_zero", {"mab_c": 0}, {},
     DEFAULT_C, DEFAULT_MIN_EXPLORE),
    ("env_absent__task_negative", {"mab_c": -1, "mab_min_explore": 0}, {},
     DEFAULT_C, DEFAULT_MIN_EXPLORE),
]


def loader_env(extra: dict) -> dict:
    env = {**os.environ, **extra}
    libdir = sysconfig.get_config_var("LIBDIR")
    if libdir:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{libdir}:{existing}" if existing else libdir
    for key in ("NV_MAB_C", "NV_MAB_MIN_EXPLORE"):
        if key not in extra:
            env.pop(key, None)
    return env


def evidence_root(name: str) -> Path:
    """Where this test writes its artifacts.

    Committed evidence under out/ is a deliverable, so a plain test run must
    not overwrite or delete it.  The suite writes to a scratch directory by
    default; regenerating the tracked evidence is a deliberate act:

        NV_P01_WRITE_EVIDENCE=1 python3 -m unittest tests.<module>
    """
    if os.environ.get("NV_P01_WRITE_EVIDENCE") == "1":
        return REPO_ROOT / "out" / name
    return Path(tempfile.mkdtemp(prefix=f"{name}_"))


def parse_key_value(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip()
    return out


class P01ConfigPrecedenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not AFL_FUZZ.is_file():
            raise unittest.SkipTest("afl-fuzz is not built")
        if not SEEDS.is_dir():
            raise unittest.SkipTest(f"seed directory missing: {SEEDS}")

        global EVIDENCE
        EVIDENCE = evidence_root("p01_config_precedence")
        if EVIDENCE.exists():
            shutil.rmtree(EVIDENCE)
        EVIDENCE.mkdir(parents=True)

        cls.results = {}
        for label, task_extra, env_extra, _, _ in MATRIX:
            out = EVIDENCE / label
            out.mkdir()

            task = {
                "target_type": "http_api",
                "target_endpoint": "p01_precedence",
                "seed_source": "seed_file",
                "seed_location": str(SEEDS),
                "mutation_scope": ["field_value", "boundary", "structure"],
                "max_test_cases": 20,
                "time_budget": 5,
                "enable_validity": 0,
            }
            task.update(task_extra)
            task_path = out / "task.json"
            import json as _json
            task_path.write_text(_json.dumps(task), encoding="utf-8")

            env = loader_env({
                "AFL_NO_UI": "1",
                "AFL_SKIP_CPUFREQ": "1",
                "AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1",
                "AFL_PYTHON_MODULE": "nv_json_mutator",
                "PYTHONPATH": str(REPO_ROOT),
                "NV_TASK_PATH": str(task_path),
                "NV_STATUS_PATH": str(out / "status.json"),
                "NV_P0_PROFILE": "o2oa_cms_doc_list",
                **env_extra,
            })
            subprocess.run(
                [
                    str(AFL_FUZZ), "-n", "-m", "none", "-s", "1", "-V", "2",
                    "-i", str(SEEDS), "-o", str(out / "afl"),
                    "--", "python3", str(TARGET), "@@",
                ],
                capture_output=True, text=True, timeout=CASE_TIMEOUT,
                cwd=str(REPO_ROOT), env=env,
            )

            stats_path = out / "afl" / "default" / "fuzzer_stats"
            if not stats_path.is_file():
                stats_path = out / "afl" / "fuzzer_stats"
            if not stats_path.is_file():
                cls.results[label] = None
                continue
            stats = parse_key_value(stats_path)
            cls.results[label] = (
                float(stats["nv_mab_c"]), int(stats["nv_mab_min_explore"])
            )

        with (EVIDENCE / "matrix.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([
                "case", "task_json", "env", "expected_c", "actual_c",
                "expected_min_explore", "actual_min_explore", "verdict",
            ])
            for label, task_extra, env_extra, exp_c, exp_me in MATRIX:
                got = cls.results.get(label)
                ok = got is not None and abs(got[0] - exp_c) < 1e-9 and got[1] == exp_me
                w.writerow([
                    label, task_extra or "-", env_extra or "-", exp_c,
                    got[0] if got else "MISSING", exp_me,
                    got[1] if got else "MISSING", "PASS" if ok else "FAIL",
                ])

    def test_every_precedence_case_resolves_as_documented(self) -> None:
        failures = []
        for label, _, _, exp_c, exp_me in MATRIX:
            got = self.results.get(label)
            if got is None:
                failures.append(f"{label}: no fuzzer_stats produced")
                continue
            if abs(got[0] - exp_c) > 1e-9 or got[1] != exp_me:
                failures.append(
                    f"{label}: expected c={exp_c} min_explore={exp_me}, "
                    f"got c={got[0]} min_explore={got[1]}"
                )
        self.assertEqual(failures, [], "\n".join(failures))

    def test_invalid_env_never_suppresses_task_json(self) -> None:
        """M-5: the regression that made a good task value vanish."""
        for label in (
            "env_empty__task_valid",
            "env_whitespace__task_valid",
            "env_garbage__task_valid",
            "env_zero__task_valid",
            "env_overflow__task_valid",
        ):
            got = self.results.get(label)
            self.assertIsNotNone(got, f"{label} produced no stats")
            self.assertAlmostEqual(
                got[0], 0.9, places=9,
                msg=f"{label}: an invalid environment override discarded the "
                    f"task.json value (c={got[0]}, expected 0.9)",
            )

    def test_exploration_is_never_disabled(self) -> None:
        """M-6/M-7: c stays finite and strictly positive in every case."""
        for label, got in self.results.items():
            self.assertIsNotNone(got, f"{label} produced no stats")
            self.assertGreater(got[0], 0.0, f"{label}: c collapsed to {got[0]}")
            self.assertLess(got[0], 1e6, f"{label}: c overflowed to {got[0]}")
            self.assertGreaterEqual(got[1], 1, f"{label}: min_explore={got[1]}")
            self.assertLessEqual(
                got[1], 1000000, f"{label}: min_explore overflowed to {got[1]}"
            )


if __name__ == "__main__":
    unittest.main()
