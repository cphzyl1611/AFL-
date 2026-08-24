"""Offline integration tests for production NV feedback attribution."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nv_json_mutator

from tests.test_nv_feedback_execution_identity import (
    AUDITED_RUNNER,
    FAKE_TARGET,
    RULES,
    VALID_FULL_HTTP,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_SRC = REPO_ROOT / "test" / "phase3b" / "feedback_attribution_probe.c"
INCLUDE = REPO_ROOT / "include"
COVSET_SRC = REPO_ROOT / "src" / "afl-fuzz-nv-covset.c"
MAB_SRC = REPO_ROOT / "src" / "afl-fuzz-nv-mab.c"
CJSON_SRC = REPO_ROOT / "src" / "third_party" / "cjson" / "cJSON.c"
FUZZ_ONE_SRC = REPO_ROOT / "src" / "afl-fuzz-one.c"
PYTHON_SRC = REPO_ROOT / "src" / "afl-fuzz-python.c"
QUEUE_SRC = REPO_ROOT / "src" / "afl-fuzz-queue.c"


def parse_probe_value(value: str) -> int | float:
    try:
        return int(value)
    except ValueError:
        return float(value)


def parse_probe_line(line: str) -> tuple[str, dict[str, int | float]]:
    tokens = line.split()
    return tokens[0], {
        key: parse_probe_value(value)
        for key, value in (token.split("=", 1) for token in tokens[1:])
    }


def parse_stats_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


PROBE_LABELS = {
    "FIRST",
    "SECOND",
    "SATURATED",
    "REWARD",
    "REJECT",
    "CONTINUOUS",
    "REPORTING",
}


class NvFeedbackAttributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nv_feedback_attribution_")
        self.tmp = Path(self._tmp.name)
        self.status = self.tmp / "status.json"
        self.probe = self.tmp / "feedback_attribution_probe"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def build_probe(self) -> None:
        python_config = Path(sys.executable).with_name("python3-config")
        python_flags = shlex.split(
            subprocess.check_output(
                [str(python_config), "--embed", "--cflags", "--ldflags"],
                text=True,
                timeout=20,
            )
        )
        python_libdir = sysconfig.get_config_var("LIBDIR")
        self.assertTrue(python_libdir)
        queue_object = self.tmp / "afl-fuzz-queue.o"
        queue_compiled = subprocess.run(
            [
                "gcc",
                "-std=c11",
                "-ffunction-sections",
                "-fdata-sections",
                "-I",
                str(INCLUDE),
                "-Dmark_as_det_done=phase3c_queue_mark_as_det_done",
                "-Dcalculate_score=phase3c_queue_calculate_score",
                "-Dqueue_testcase_get=phase3c_queue_testcase_get",
                "-c",
                str(QUEUE_SRC),
                "-o",
                str(queue_object),
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=30,
        )
        self.assertEqual(queue_compiled.returncode, 0, queue_compiled.stderr)
        compiled = subprocess.run(
            [
                "gcc",
                "-std=c11",
                "-ffunction-sections",
                "-fdata-sections",
                "-DUSE_PYTHON",
                "-I",
                str(INCLUDE),
                "-o",
                str(self.probe),
                str(PROBE_SRC),
                str(FUZZ_ONE_SRC),
                str(PYTHON_SRC),
                str(COVSET_SRC),
                str(MAB_SRC),
                str(CJSON_SRC),
                str(queue_object),
                "-Wl,--gc-sections",
                f"-Wl,-rpath,{python_libdir}",
                *python_flags,
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=30,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)

    def capture_status(self, name: str) -> tuple[Path, int]:
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "NV_STATUS_PATH": str(self.status),
            "NV_BODY_RULES": str(RULES),
        }
        completed = subprocess.run(
            [sys.executable, "-c", AUDITED_RUNNER, str(FAKE_TARGET)],
            input=VALID_FULL_HTTP,
            capture_output=True,
            cwd=REPO_ROOT,
            env=env,
            timeout=20,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr.decode(errors="replace"),
        )
        self.assertNotIn(b"NETWORK_AUDIT_EVENT=", completed.stderr)

        document = self.tmp / name
        shutil.copyfile(self.status, document)
        payload = json.loads(document.read_text(encoding="utf-8"))
        return document, int(payload["exec_seq"])

    def run_probe(
        self, *args: object
    ) -> list[tuple[str, dict[str, int | float]]]:
        probe_env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(REPO_ROOT),
        }
        completed = subprocess.run(
            [str(self.probe), *(str(arg) for arg in args)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=probe_env,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("NETWORK_AUDIT_EVENT=", completed.stderr)
        return [
            parse_probe_line(line)
            for line in completed.stdout.splitlines()
            if line.strip() and line.split(maxsplit=1)[0] in PROBE_LABELS
        ]

    def test_new_state_is_credited_once_and_existing_state_is_not(self) -> None:
        first_status, first_seq = self.capture_status("first.json")
        second_status, second_seq = self.capture_status("second.json")
        self.assertEqual(second_seq, first_seq + 1)
        self.build_probe()

        rows = self.run_probe("credit", first_status, second_status)

        self.assertEqual(
            rows,
            [
                (
                    "FIRST",
                    {
                        "has": 1,
                        "new": 1,
                        "exec_seq": first_seq,
                        "used": 1,
                        "ss_cov": 1,
                        "seed_credit": 1,
                    },
                ),
                (
                    "SECOND",
                    {
                        "has": 1,
                        "new": 0,
                        "exec_seq": second_seq,
                        "used": 1,
                        "ss_cov": 1,
                        "seed_credit": 1,
                    },
                ),
            ],
        )

    def test_saturated_state_set_produces_no_false_seed_credit(self) -> None:
        status, exec_seq = self.capture_status("saturated.json")
        self.build_probe()

        rows = self.run_probe("saturation", status)

        self.assertEqual(
            rows,
            [
                (
                    "SATURATED",
                    {
                        "has": 1,
                        "new": 0,
                        "exec_seq": exec_seq,
                        "used": 1,
                        "ss_cov": 0,
                        "seed_credit": 0,
                        "saturated": 1,
                        "dropped": 1,
                    },
                )
            ],
        )

    def test_reward_source_sequence_matches_fresh_observation(self) -> None:
        status, exec_seq = self.capture_status("reward.json")
        self.build_probe()

        rows = self.run_probe("reward", status, 1, 1)

        self.assertEqual(
            rows,
            [
                (
                    "REWARD",
                    {
                        "rc": 0,
                        "selected": 1,
                        "observed_seq": exec_seq,
                        "reward_src_seq": exec_seq,
                        "total_pulls": 1,
                        "arm0": 0,
                        "arm1": 1,
                        "arm2": 0,
                        "pending": 0,
                        "update_source": 0,
                        "target_calls": 1,
                    },
                )
            ],
        )

    def test_c_validation_rejection_clears_pending_without_execution(self) -> None:
        status, sentinel_seq = self.capture_status("reject-sentinel.json")
        self.assertGreater(sentinel_seq, 0)
        status_before = status.read_bytes()
        allocator_seq_path = self.status.with_name(self.status.name + ".seq")
        allocator_seq_before = allocator_seq_path.read_bytes()
        self.build_probe()

        rows = self.run_probe(
            "reject",
            status,
            "INVALID\r\nHost: offline\r\n\r\n{}",
        )

        self.assertEqual(status.read_bytes(), status_before)
        self.assertEqual(allocator_seq_path.read_bytes(), allocator_seq_before)

        self.assertEqual(
            rows,
            [
                (
                    "REJECT",
                    {
                        "rc": 0,
                        "enable_validity": 1,
                        "invalid_before": 0,
                        "invalid_after": 1,
                        "invalid_delta": 1,
                        "invalid_parse_before": 0,
                        "invalid_parse_after": 1,
                        "invalid_parse_delta": 1,
                        "invalid_rule_before": 0,
                        "invalid_rule_after": 0,
                        "invalid_rule_delta": 0,
                        "write_before": 0,
                        "write_after": 1,
                        "write_delta": 1,
                        "target_before": 0,
                        "target_after": 0,
                        "target_delta": 0,
                        "status_producer_before": 0,
                        "status_producer_after": 0,
                        "status_producer_delta": 0,
                        "pending_before": 1,
                        "pending_arm_before": 1,
                        "update_source_before": 1,
                        "pending_after": 0,
                        "update_source_after": 0,
                        "status_count_before": 0,
                        "status_count_after": 0,
                        "status_count_delta": 0,
                        "observations_before": 0,
                        "observations_after": 0,
                        "observations_delta": 0,
                        "last_exec_seq_before": 0,
                        "last_exec_seq_after": 0,
                        "last_exec_seq_delta": 0,
                        "reward_src_seq_before": 77,
                        "reward_src_seq_after": 77,
                        "total_pulls_before": 0,
                        "total_pulls_after": 0,
                        "arm0_before": 0,
                        "arm0_after": 0,
                        "arm1_before": 0,
                        "arm1_after": 0,
                        "arm2_before": 0,
                        "arm2_after": 0,
                        "sum_rewards_unchanged": 1,
                        "mean_rewards_unchanged": 1,
                        "network_before": 0,
                        "network_after": 0,
                        "network_delta": 0,
                    },
                )
            ],
        )

    def test_confirmed_actual_arm_receives_the_only_mab_update(self) -> None:
        selected_arm = 2
        with mock.patch.dict(
            os.environ,
            {"NV_CUR_ARM": str(selected_arm)},
            clear=False,
        ):
            os.environ.pop("NV_JSON_ARM_USED", None)
            mutated = nv_json_mutator.afl_custom_fuzz(
                None,
                VALID_FULL_HTTP,
                b"",
                65536,
            )
            self.assertTrue(mutated)
            self.assertEqual(os.environ.get("NV_JSON_ARM_USED"), "2")

        status, exec_seq = self.capture_status("confirmed-arm.json")
        self.build_probe()
        rows = self.run_probe("reward", status, 1, selected_arm)

        self.assertEqual(
            rows,
            [
                (
                    "REWARD",
                    {
                        "rc": 0,
                        "selected": selected_arm,
                        "observed_seq": exec_seq,
                        "reward_src_seq": exec_seq,
                        "total_pulls": 1,
                        "arm0": 0,
                        "arm1": 0,
                        "arm2": 1,
                        "pending": 0,
                        "update_source": 0,
                        "target_calls": 1,
                    },
                )
            ],
        )

    def test_selected_but_unconfirmed_arm_receives_no_mab_update(self) -> None:
        selected_arm = 2
        status, exec_seq = self.capture_status("unconfirmed-arm.json")
        self.build_probe()

        rows = self.run_probe("reward", status, 0, selected_arm)

        self.assertEqual(
            rows,
            [
                (
                    "REWARD",
                    {
                        "rc": 0,
                        "selected": selected_arm,
                        "observed_seq": exec_seq,
                        "reward_src_seq": 0,
                        "total_pulls": 0,
                        "arm0": 0,
                        "arm1": 0,
                        "arm2": 0,
                        "pending": 0,
                        "update_source": 0,
                        "target_calls": 1,
                    },
                )
            ],
        )

    def test_continuous_confirmed_actual_arm_is_the_only_credited_arm(self) -> None:
        self.build_probe()

        rows = self.run_probe(
            "continuous",
            "positive",
            self.status,
            FAKE_TARGET,
            RULES,
            sys.executable,
            self.tmp / "target-input",
        )

        self.assertEqual(
            rows,
            [
                (
                    "CONTINUOUS",
                    {
                        "scenario": 0,
                        "fuzz_rc": 0,
                        "selected": 0,
                        "nv_cur": 0,
                        "nv_used": 0,
                        "mutator_calls": 1,
                        "pending_at_common": 1,
                        "pending_arm_at_common": 0,
                        "target_calls": 1,
                        "observed_seq": 1,
                        "reward_src_seq": 1,
                        "total_pulls": 1,
                        "arm0": 1,
                        "arm1": 0,
                        "arm2": 0,
                        "pending_after": 0,
                        "update_source_after": 0,
                        "mutator_reported": 0,
                    },
                )
            ],
        )

    def test_continuous_selected_arm_without_confirmation_is_not_credited(self) -> None:
        self.build_probe()

        rows = self.run_probe(
            "continuous",
            "unconfirmed",
            self.status,
            FAKE_TARGET,
            RULES,
            sys.executable,
            self.tmp / "target-input",
        )

        self.assertEqual(
            rows,
            [
                (
                    "CONTINUOUS",
                    {
                        "scenario": 1,
                        "fuzz_rc": 0,
                        "selected": 0,
                        "nv_cur": 0,
                        "nv_used": -1,
                        "mutator_calls": 1,
                        "pending_at_common": 0,
                        "pending_arm_at_common": 0,
                        "target_calls": 1,
                        "observed_seq": 1,
                        "reward_src_seq": 0,
                        "total_pulls": 0,
                        "arm0": 0,
                        "arm1": 0,
                        "arm2": 0,
                        "pending_after": 0,
                        "update_source_after": 0,
                        "mutator_reported": 0,
                    },
                )
            ],
        )

    def test_continuous_mismatched_confirmation_does_not_credit_selected_arm(self) -> None:
        self.build_probe()

        rows = self.run_probe(
            "continuous",
            "mismatch",
            self.status,
            FAKE_TARGET,
            RULES,
            sys.executable,
            self.tmp / "target-input",
        )

        self.assertEqual(
            rows,
            [
                (
                    "CONTINUOUS",
                    {
                        "scenario": 2,
                        "fuzz_rc": 0,
                        "selected": 0,
                        "nv_cur": 0,
                        "nv_used": 1,
                        "mutator_calls": 1,
                        "pending_at_common": 0,
                        "pending_arm_at_common": 0,
                        "target_calls": 1,
                        "observed_seq": 1,
                        "reward_src_seq": 0,
                        "total_pulls": 0,
                        "arm0": 0,
                        "arm1": 0,
                        "arm2": 0,
                        "pending_after": 0,
                        "update_source_after": 0,
                        "mutator_reported": 0,
                    },
                )
            ],
        )

    def test_production_reports_conserve_the_live_feedback_state(self) -> None:
        report_out = self.tmp / "phase3c-report"
        report_out.mkdir()
        self.build_probe()

        rows = self.run_probe(
            "reporting",
            self.status,
            FAKE_TARGET,
            RULES,
            sys.executable,
            self.tmp / "target-input",
            report_out,
        )
        runtime = next(values for label, values in rows if label == "REPORTING")

        stats_path = report_out / "fuzzer_stats"
        eval_path = report_out / "eval_report.json"
        self.assertTrue(stats_path.is_file())
        self.assertTrue(eval_path.is_file())
        stats = parse_stats_file(stats_path)
        evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
        security = evaluation["security_state_cov"]
        mab = evaluation["mab"]

        self.assertEqual(runtime["fuzz_rc"], 0)
        self.assertEqual(runtime["fixed_queue"], 1)
        self.assertEqual(runtime["same_queue"], 1)
        self.assertEqual(runtime["queue_count"], 1)
        self.assertEqual(runtime["selected_index"], 0)
        self.assertEqual(runtime["target_calls"], 1)
        self.assertEqual(runtime["network_calls"], 0)

        arm_count = int(runtime["arm_count"])
        runtime_pull_sum = sum(
            int(runtime[f"arm{arm}_pulls"]) for arm in range(arm_count)
        )
        stats_pull_sum = sum(
            int(stats[f"nv_mab_arm{arm}_pulls"]) for arm in range(arm_count)
        )
        eval_pull_sum = sum(arm["pulls"] for arm in mab["arms"])
        self.assertEqual(runtime_pull_sum, runtime["total_pulls"])
        self.assertEqual(stats_pull_sum, int(stats["nv_mab_total_pulls"]))
        self.assertEqual(eval_pull_sum, mab["total_pulls"])
        self.assertEqual(int(stats["nv_mab_total_pulls"]), runtime["total_pulls"])
        self.assertEqual(mab["total_pulls"], runtime["total_pulls"])

        security_fields = {
            "state_total": "security_state_total",
            "state_new": "security_state_new_total",
            "observations": "security_state_observations",
            "seed_credit": "security_state_seed_credit",
            "replays": "security_state_replays",
            "reward_src_seq": "security_state_reward_src_seq",
        }
        for runtime_key, report_key in security_fields.items():
            with self.subTest(report_key=report_key):
                self.assertEqual(int(stats[report_key]), runtime[runtime_key])
                self.assertEqual(security[report_key], runtime[runtime_key])

        self.assertEqual(runtime["reward_src_seq"], runtime["last_exec_seq"])
        self.assertEqual(
            int(stats["nv_mab_cold_start_picks"]), runtime["cold_start_picks"]
        )
        self.assertEqual(mab["cold_start_picks"], runtime["cold_start_picks"])
        self.assertEqual(int(stats["nv_mab_ucb_picks"]), runtime["ucb_picks"])
        self.assertEqual(mab["ucb_picks"], runtime["ucb_picks"])

        self.assertEqual(len(mab["arms"]), arm_count)
        for arm in range(arm_count):
            with self.subTest(arm=arm):
                runtime_pulls = int(runtime[f"arm{arm}_pulls"])
                runtime_mean = float(runtime[f"arm{arm}_mean"])
                runtime_sum = float(runtime[f"arm{arm}_sum"])
                runtime_pos = int(runtime[f"arm{arm}_pos"])
                eval_arm = mab["arms"][arm]

                self.assertEqual(int(stats[f"nv_mab_arm{arm}_pulls"]), runtime_pulls)
                self.assertEqual(eval_arm["pulls"], runtime_pulls)
                self.assertAlmostEqual(
                    float(stats[f"nv_mab_arm{arm}_mean"]),
                    runtime_mean,
                    delta=max(5e-10, abs(runtime_mean) * 5e-10),
                )
                self.assertAlmostEqual(
                    eval_arm["mean_reward"], runtime_mean, delta=5e-6
                )
                self.assertAlmostEqual(
                    float(stats[f"nv_mab_arm{arm}_sum"]),
                    runtime_sum,
                    delta=max(5e-10, abs(runtime_sum) * 5e-10),
                )
                self.assertAlmostEqual(
                    eval_arm["sum_reward"], runtime_sum, delta=5e-6
                )
                self.assertEqual(int(stats[f"nv_mab_arm{arm}_pos"]), runtime_pos)
                self.assertEqual(eval_arm["pos_cnt"], runtime_pos)

        self.assertEqual(runtime["queue_cov_before"], 0)
        self.assertEqual(runtime["selected_before"], 0)
        self.assertEqual(runtime["queue_cov_sum"], runtime["seed_credit"])
        self.assertEqual(int(stats["ss_cov_sum"]), runtime["seed_credit"])
        self.assertGreater(runtime["weight_after_credit"], runtime["weight_before"])
        self.assertGreater(
            runtime["weight_after_credit"], runtime["weight_after_selection"]
        )
        self.assertGreater(runtime["selected_after"], runtime["selected_before"])

        self.assertEqual(runtime["replay_delta"], 1)
        self.assertEqual(runtime["replay_state_total_delta"], 0)
        self.assertEqual(runtime["replay_new_delta"], 0)
        self.assertEqual(runtime["replay_observations_delta"], 0)
        self.assertEqual(runtime["replay_seed_delta"], 0)
        self.assertEqual(runtime["replay_pulls_delta"], 0)
        self.assertEqual(runtime["replay_reward_src_unchanged"], 1)

        self.assertEqual(int(stats["nv_err_exec"]), runtime["err_exec"])
        self.assertEqual(evaluation["err"]["err_exec"], runtime["err_exec"])
        self.assertEqual(int(stats["nv_rec_total"]), runtime["rec_total"])
        self.assertEqual(evaluation["rec"]["rec_total"], runtime["rec_total"])
        self.assertEqual(int(stats["nv_rec_success"]), runtime["rec_success"])
        self.assertEqual(evaluation["rec"]["rec_success"], runtime["rec_success"])


if __name__ == "__main__":
    unittest.main()
