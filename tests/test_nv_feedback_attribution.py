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
from tests.test_nv_mab_journal import load_runner


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
    "MULTI_ARM",
    "REPORTING",
    "PENDING",
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
        self, *args: object, allowed_returncodes: tuple[int, ...] = (0,)
    ) -> list[tuple[str, dict[str, int | float]]]:
        probe_env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(REPO_ROOT),
        }
        probe_env.setdefault("NV_MAB_JOURNAL_PATH", str(self.tmp / "probe-mab.jsonl"))
        probe_env.setdefault("NV_EXECUTION_LEDGER_PATH", str(self.tmp / "executions.jsonl"))
        completed = subprocess.run(
            [str(self.probe), *(str(arg) for arg in args)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=probe_env,
            timeout=20,
        )
        self.assertIn(completed.returncode, allowed_returncodes, completed.stderr)
        self.assertNotIn("NETWORK_AUDIT_EVENT=", completed.stderr)
        return [
            parse_probe_line(line)
            for line in completed.stdout.splitlines()
            if line.strip() and line.split(maxsplit=1)[0] in PROBE_LABELS
        ]

    def test_harness_without_status_is_not_counted_as_target_invocation(self) -> None:
        self.build_probe()
        ledger = self.tmp / "no-status-ledger.jsonl"
        completed = subprocess.run(
            [
                str(self.probe),
                "no-status-target",
                str(self.tmp / "missing-status.json"),
                str(ledger),
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
        self.assertTrue(record["harness_invoked"])
        self.assertFalse(record["target_invoked"])
        self.assertFalse(record["status_observed"])
        self.assertEqual(record["mab_outcome"], "target_execution_no_mab")

    def test_status_consumer_waits_for_delayed_new_execution_identity(self) -> None:
        first_status, first_seq = self.capture_status("wait-first.json")
        second_status, second_seq = self.capture_status("wait-second.json")
        self.assertEqual(second_seq, first_seq + 1)
        self.build_probe()

        completed = subprocess.run(
            [str(self.probe), "wait-for-fresh", str(first_status), str(second_status)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("WAIT has=1", completed.stdout)
        self.assertIn(f"exec_seq={second_seq}", completed.stdout)

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

    def test_each_pending_cleanup_branch_writes_a_non_update_journal_event(self) -> None:
        self.build_probe()
        status, _ = self.capture_status("pending-status.json")
        for reason in ("budget_boundary", "stop_soon", "timeout", "invalid_input", "skip"):
            with self.subTest(reason=reason):
                journal = self.tmp / f"{reason}.jsonl"
                rows = self.run_probe(
                    "pending", reason, status, journal,
                    allowed_returncodes=(0, 1),
                )
                self.assertEqual(len(rows), 1, rows)
                label, values = rows[0]
                self.assertEqual(label, "PENDING")
                self.assertEqual(values["rc"], 1 if reason != "invalid_input" else 0)
                self.assertEqual(values["pulls"], 0)
                self.assertEqual(values["arm_pulls"], 0)
                self.assertEqual(values["records"], 1)
                record = json.loads(journal.read_text(encoding="utf-8"))
                self.assertEqual(record["event"], "mab_pending_cleared")
                self.assertEqual(record["reason"], reason)
                self.assertNotEqual(record["event"], "mab_update")

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
                         "arm0_sum": 10,
                         "arm1_sum": 0,
                         "arm2_sum": 0,
                         "arm0_pos": 1,
                         "arm1_pos": 0,
                         "arm2_pos": 0,
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

        self.assertEqual(len(rows), 1)
        label, values = rows[0]
        self.assertEqual(label, "CONTINUOUS")
        self.assertEqual(values["scenario"], 1)
        self.assertEqual(values["fuzz_rc"], 0)
        self.assertEqual(values["selected"], 0)
        self.assertEqual(values["nv_cur"], 0)
        self.assertEqual(values["nv_used"], -1)
        self.assertEqual(values["mutator_calls"], 1)
        self.assertEqual(values["pending_at_common"], 1)
        self.assertEqual(values["pending_arm_at_common"], 3)
        self.assertEqual(values["target_calls"], 1)
        self.assertEqual(values["observed_seq"], 1)
        self.assertEqual(values["reward_src_seq"], 0)
        self.assertEqual(values["pending_after"], 0)
        self.assertEqual(values["update_source_after"], 0)
        self.assertEqual([values[f"arm{arm}"] for arm in range(3)], [0, 0, 0])
        self.assertEqual(
            [values[f"arm{arm}_sum"] for arm in range(3)], [0, 0, 0]
        )
        self.assertEqual(
            [values[f"arm{arm}_pos"] for arm in range(3)], [0, 0, 0]
        )
        records = [
            json.loads(line)
            for line in (self.tmp / "executions.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["mab_outcome"], "arm_mismatch")
        self.assertEqual(records[0]["selected_arm"], 0)
        self.assertEqual(records[0]["actual_used_arm"], 3)
        journal = [
            json.loads(line)
            for line in (self.tmp / "probe-mab.jsonl").read_text().splitlines()
        ]
        self.assertEqual(
            [record["event"] for record in journal],
            ["mab_update_mismatch", "mab_pending_cleared"],
        )
        self.assertNotIn("mab_update", [record["event"] for record in journal])

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

        self.assertEqual(len(rows), 1)
        label, values = rows[0]
        self.assertEqual(label, "CONTINUOUS")
        self.assertEqual(values["scenario"], 2)
        self.assertEqual(values["fuzz_rc"], 0)
        self.assertEqual(values["selected"], 0)
        self.assertEqual(values["nv_cur"], 0)
        self.assertEqual(values["nv_used"], 1)
        self.assertEqual(values["mutator_calls"], 1)
        self.assertEqual(values["pending_at_common"], 1)
        self.assertEqual(values["pending_arm_at_common"], 1)
        self.assertEqual(values["target_calls"], 1)
        self.assertEqual(values["observed_seq"], 1)
        self.assertEqual(values["reward_src_seq"], 0)
        self.assertEqual(values["pending_after"], 0)
        self.assertEqual(values["update_source_after"], 0)
        self.assertEqual([values[f"arm{arm}"] for arm in range(3)], [0, 0, 0])
        self.assertEqual(
            [values[f"arm{arm}_sum"] for arm in range(3)], [0, 0, 0]
        )
        self.assertEqual(
            [values[f"arm{arm}_pos"] for arm in range(3)], [0, 0, 0]
        )
        records = [
            json.loads(line)
            for line in (self.tmp / "executions.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["mab_outcome"], "arm_mismatch")
        self.assertEqual(records[0]["selected_arm"], 0)
        self.assertEqual(records[0]["actual_used_arm"], 1)
        journal = [
            json.loads(line)
            for line in (self.tmp / "probe-mab.jsonl").read_text().splitlines()
        ]
        self.assertEqual(
            [record["event"] for record in journal],
            ["mab_update_mismatch", "mab_pending_cleared"],
        )
        self.assertNotIn("mab_update", [record["event"] for record in journal])

    def test_production_path_journal_reconciles_commit_cleanup_and_mismatch(self) -> None:
        self.build_probe()
        journal = self.tmp / "production-path.jsonl"
        with mock.patch.dict(os.environ, {"NV_MAB_JOURNAL_PATH": str(journal)}, clear=False):
            rows = self.run_probe(
                "continuous",
                "positive",
                self.status,
                FAKE_TARGET,
                RULES,
                sys.executable,
                self.tmp / "target-input",
            )
        self.assertEqual(rows[0][0], "CONTINUOUS")
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        self.assertEqual([record["event"] for record in records], ["mab_update"])
        self.assertGreater(records[0]["exec_seq"], 0)
        self.assertEqual(records[0]["selected_arm"], records[0]["actual_used_arm"])
        self.assertEqual(records[0]["pulls_after"], 1)
        self.assertEqual(rows[0][1]["total_pulls"], 1)
        parsed = load_runner().parse_mab_journal(journal)
        stats = {
            "nv_mab_total_pulls": "1",
            "nv_mab_arm0_pulls": "1",
            "nv_mab_arm1_pulls": "0",
            "nv_mab_arm2_pulls": "0",
            "nv_mab_arm0_sum": str(records[0]["sum_after"]),
            "nv_mab_arm1_sum": "0",
            "nv_mab_arm2_sum": "0",
            "nv_mab_arm0_pos": "1",
            "nv_mab_arm1_pos": "0",
            "nv_mab_arm2_pos": "0",
            "security_state_reward_src_seq": str(records[0]["exec_seq"]),
        }
        self.assertTrue(load_runner().reconcile_mab_journal(parsed, stats)["reconciled"])

    def test_production_path_zero_exec_seq_clears_pending_without_commit(self) -> None:
        self.build_probe()
        status = self.tmp / "zero-exec.json"
        status.write_text(
            json.dumps({
                "exec_seq": 0,
                "method": "PUT",
                "path": "/offline/node",
                "response_class": "2xx",
                "ncov_delta": 0,
            }) + "\n",
            encoding="utf-8",
        )
        journal = self.tmp / "zero-exec.jsonl"
        with mock.patch.dict(os.environ, {"NV_MAB_JOURNAL_PATH": str(journal)}, clear=False):
            rows = self.run_probe("reward", status, 1, 1, journal)
        self.assertEqual(rows[0][1]["total_pulls"], 0)
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        self.assertEqual(records[0]["event"], "mab_pending_cleared")
        self.assertEqual(records[0]["reason"], "invalid_exec_identity")

    def test_production_path_zero_reward_commits_and_mismatch_does_not_aggregate(self) -> None:
        self.build_probe()
        status, exec_seq = self.capture_status("zero-reward.json")
        journal = self.tmp / "zero-reward.jsonl"
        with mock.patch.dict(os.environ, {"NV_MAB_JOURNAL_PATH": str(journal)}, clear=False):
            rows = self.run_probe("reward", status, 1, 1, journal, "zero")
        self.assertEqual(rows[0][1]["total_pulls"], 1)
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        self.assertEqual(records[0]["event"], "mab_update")
        self.assertEqual(records[0]["exec_seq"], exec_seq)
        self.assertEqual(records[0]["reward"], 0)

        mismatch_journal = self.tmp / "mismatch.jsonl"
        with mock.patch.dict(os.environ, {"NV_MAB_JOURNAL_PATH": str(mismatch_journal)}, clear=False):
            mismatch_rows = self.run_probe(
                "continuous", "mismatch", self.status, FAKE_TARGET, RULES,
                sys.executable, self.tmp / "target-input",
            )
        self.assertEqual(mismatch_rows[0][1]["total_pulls"], 0)
        mismatch = [json.loads(line) for line in mismatch_journal.read_text().splitlines()]
        self.assertEqual(mismatch[0]["event"], "mab_update_mismatch")

    def test_multiple_actual_mutator_arms_update_and_reconcile_in_journal(self) -> None:
        """Three production picker decisions traverse the Python handshake path."""
        self.build_probe()
        journal = self.tmp / "multi-arm-updates.jsonl"
        multi_arm_rules = self.tmp / "multi-arm-rules.json"
        multi_arm_rules.write_text(
            json.dumps({
                "common": {"max_bytes": 16384, "max_depth": 8,
                           "max_keys": 128, "max_string": 2048},
                "endpoints": {
                    "offline_feedback": {
                        "type": "object", "allow_unknown": True
                    }
                },
            }),
            encoding="utf-8",
        )
        rows = self.run_probe(
            "multi-arm",
            self.status,
            FAKE_TARGET,
            multi_arm_rules,
            sys.executable,
            self.tmp / "target-input",
            journal,
        )
        self.assertEqual(len(rows), 1, rows)
        label, values = rows[0]
        self.assertEqual(label, "MULTI_ARM")
        self.assertEqual(
            (values["rc0"], values["rc1"], values["rc2"], values["calls"]),
            (0, 0, 0, 3),
        )
        self.assertEqual(values["total_pulls"], 3)
        self.assertEqual(
            [values[f"arm{arm}"] for arm in range(3)], [1, 1, 1]
        )
        self.assertEqual(values["records"], values["total_pulls"])

        records = [
            json.loads(line)
            for line in journal.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(records), 3)
        self.assertEqual(
            [record["selected_arm"] for record in records], [0, 1, 2]
        )
        self.assertEqual(
            [record["actual_used_arm"] for record in records], [0, 1, 2]
        )
        self.assertTrue(all(record["arm_match"] for record in records))
        self.assertTrue(
            all(record["exec_seq"] > 0 for record in records), records
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
