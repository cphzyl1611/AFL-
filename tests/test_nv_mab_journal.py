"""Offline TDD coverage for the MAB per-update JSONL audit trail."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"



def load_runner():
    spec = importlib.util.spec_from_file_location("mab_journal_runner_test", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _materialize_artifacts(layout):
    """Minimal offline artifact materialization matching the alfresco test helper."""
    import json as _json
    payloads = {
        "status": {"http_code": 200},
        "status_seq": "1",
        "probe": {"ncov_total": 1},
        "state_db": [],
        "state_trace": '{"event":"state"}\n',
        "body_valid_stats": {"body_rule_pass": 1},
    }
    for name, payload in payloads.items():
        path = Path(layout[name])
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(_json.dumps(payload), encoding="utf-8")
    Path(layout["target_config"]).parent.mkdir(parents=True, exist_ok=True)
    Path(layout["target_config"]).write_text("{}", encoding="utf-8")
    Path(layout["task"]).write_text("{}", encoding="utf-8")
    Path(layout["seed_dir"]).mkdir(parents=True, exist_ok=True)
    Path(layout["seed"]).write_bytes(b"seed")
    Path(layout["err_dir"]).mkdir(parents=True, exist_ok=True)
    afl_stats = Path(layout["afl_output"]) / "fuzzer_stats"
    afl_stats.parent.mkdir(parents=True, exist_ok=True)
    afl_stats.write_text(
        "execs_done : 1\n"
        "nv_total_valid_exec : 0\n"
        "nv_mab_total_pulls : 0\n"
        "nv_mab_arm0_pulls : 0\n"
        "nv_mab_arm1_pulls : 0\n"
        "nv_mab_arm2_pulls : 0\n"
        "nv_mab_arm0_sum : 0\n"
        "nv_mab_arm1_sum : 0\n"
        "nv_mab_arm2_sum : 0\n"
        "nv_mab_arm0_pos : 0\n"
        "nv_mab_arm1_pos : 0\n"
        "nv_mab_arm2_pos : 0\n"
        "security_state_reward_src_seq : 0\n"
        "nv_mab_journal_error_count : 0\n"
        "nv_mab_journal_audit_invalid : 0\n"
        "ss_selected_sum : 0\n"
        "seed_audit_enabled : 1\n"
        "seed_audit_error_count : 0\n"
        "seed_audit_invalid : 0\n"
        "seed_audit_record_count : 0\n"
        "seed_audit_expected_selection_count : 0\n",
        encoding="utf-8",
    )
    Path(layout["mab_journal"]).parent.mkdir(parents=True, exist_ok=True)
    Path(layout["mab_journal"]).touch(exist_ok=True)
    Path(layout["evidence"] / "executions.jsonl").touch(exist_ok=True)
    Path(layout["seed_selection_audit"]).touch(exist_ok=True)


def update_record(exec_seq: int, arm: int, reward: float) -> dict:
    return {
        "schema_version": 1,
        "event": "mab_update",
        "exec_seq": exec_seq,
        "selected_arm": arm,
        "actual_used_arm": arm,
        "arm_match": True,
        "reward": reward,
        "reward_components": {
            "harness_native_coverage": 0.0,
            "security_state": reward,
            "exception": 0.0,
            "recovery": 0.0,
            "http_4xx_penalty": 0.0,
        },
        "security_state_new": reward > 0,
        "pulls_before": exec_seq - 1,
        "pulls_after": exec_seq,
        "sum_before": 0.0,
        "sum_after": reward,
        "mean_after": reward,
        "positive_after": 1 if reward > 0 else 0,
        "update_source": 1,
    }


def execution_record(iteration: int, selected: int, actual: int,
                      outcome: str, *, seq: int | None = 4,
                      counted: bool = True, target: bool = True,
                      status: bool | None = None,
                      cleanup_reason: str | None = None) -> dict:
    if status is None:
        status = seq is not None and seq > 0
    return {
        "schema_version": 1, "event": "execution",
        "iteration_id": iteration, "input_id": "unavailable", "stage": "fuzz",
        "selected_arm": selected, "actual_used_arm": actual,
        "arm_match": selected == actual, "counted_execution": counted,
        "harness_invoked": True, "target_invoked": target,
        "body_validated": target, "status_observed": status,
        "exec_seq": seq, "http_status": 200 if status else 0,
        "mab_outcome": outcome,
        "pending_cleanup_reason": cleanup_reason if outcome == "pending_cleanup" else None,
    }


class NvMabJournalTest(unittest.TestCase):
    def test_incomplete_ledger_cannot_prove_execution(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            _materialize_artifacts(layout)
            task = Path(layout["task"])
            task.write_text(json.dumps({"mutation_scope": ["field_value", "boundary"]}), encoding="utf-8")
            Path(runner.execution_ledger_path(layout)).write_text(
                json.dumps({"schema_version": 1, "event": "execution"}) + "\n",
                encoding="utf-8",
            )
            report = runner.inspect_artifacts(layout, launch_returncode=0)
        self.assertFalse(report["execution_proved"])
        self.assertFalse(report["ok"])

    def test_counted_unobserved_execution_cannot_prove_execution(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            _materialize_artifacts(layout)
            Path(layout["task"]).write_text(
                json.dumps({"mutation_scope": ["field_value", "boundary"]}), encoding="utf-8"
            )
            Path(runner.execution_ledger_path(layout)).write_text(
                json.dumps(execution_record(
                    1, 1, 1, "invalid_exec_identity", seq=None,
                    status=False
                )) + "\n", encoding="utf-8"
            )
            report = runner.inspect_artifacts(layout, launch_returncode=0)
        self.assertFalse(report["execution_proved"])
    def test_execution_ledger_records_committed_update_and_domains(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "executions.jsonl"
            path.write_text(json.dumps(execution_record(1, 0, 0, "committed_update")) + "\n")
            parsed = runner.parse_execution_ledger(path)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["committed_update_count"], 1)
        self.assertEqual(parsed["counted_execution_count"], 1)
        self.assertEqual(parsed["target_invocation_count"], 1)
        self.assertEqual(parsed["status_observed_count"], 1)

    def test_zero_reward_update_is_still_a_committed_execution(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "executions.jsonl"
            path.write_text(json.dumps(execution_record(1, 1, 1, "committed_update")) + "\n")
            parsed = runner.parse_execution_ledger(path)
        self.assertEqual(parsed["committed_update_count"], 1)

    def test_zero_exec_seq_is_invalid_identity_and_not_commit(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "executions.jsonl"
            path.write_text(json.dumps(execution_record(
                1, 0, 0, "invalid_exec_identity", seq=None, status=False)) + "\n")
            parsed = runner.parse_execution_ledger(path)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["status_observed_count"], 0)
        self.assertEqual(parsed["committed_update_count"], 0)

    def test_mismatch_and_pending_cleanup_are_separate_domains(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "executions.jsonl"
            path.write_text("".join(json.dumps(record) + "\n" for record in (
                execution_record(1, 0, 1, "arm_mismatch"),
                execution_record(2, 2, 2, "pending_cleanup", seq=None,
                                 target=False, status=False,
                                 cleanup_reason="budget_boundary"),
            )))
            parsed = runner.parse_execution_ledger(path)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["mismatch_count"], 1)
        self.assertEqual(parsed["pending_cleanup_count"], 1)
        self.assertEqual(parsed["committed_update_count"], 0)

    def test_reconciliation_does_not_equate_counted_and_target_domains(self) -> None:
        runner = load_runner()
        parsed = {"valid": True, "diagnostics": [],
                  "counted_execution_count": 4,
                  "target_invocation_count": 1,
                  "status_observed_count": 1,
                  "committed_update_count": 1}
        result = runner.reconcile_execution_ledger(parsed)
        self.assertTrue(result["reconciled"])
        self.assertEqual(result["counted_execution_count"], 4)
        self.assertEqual(result["target_execution_count"], 1)
    def test_parser_accepts_empty_journal_as_valid_zero_update_artifact(self) -> None:
        runner = load_runner()
        self.assertTrue(hasattr(runner, "parse_mab_journal"))
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            journal.touch()
            parsed = runner.parse_mab_journal(journal)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["record_count"], 0)
        self.assertEqual(parsed["update_count"], 0)

    def test_parser_reconciles_updates_and_non_update_events(self) -> None:
        runner = load_runner()
        self.assertTrue(hasattr(runner, "reconcile_mab_journal"))
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                update_record(5, 1, 0.0),
                {
                    "schema_version": 1,
                    "event": "mab_pending_cleared",
                    "reason": "budget_boundary",
                    "selected_arm": 2,
                    "actual_used_arm": 2,
                },
                {
                    "schema_version": 1,
                    "event": "mab_update_mismatch",
                    "selected_arm": 1,
                    "actual_used_arm": 2,
                },
            ]
            journal.write_text(
                "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
            stats = {
                "nv_mab_total_pulls": "2",
                "nv_mab_arm0_pulls": "1",
                "nv_mab_arm1_pulls": "1",
                "nv_mab_arm2_pulls": "0",
                "nv_mab_arm0_sum": "10.0",
                "nv_mab_arm1_sum": "0.0",
                "nv_mab_arm2_sum": "0.0",
                "nv_mab_arm0_pos": "1",
                "nv_mab_arm1_pos": "0",
                "nv_mab_arm2_pos": "0",
                "security_state_reward_src_seq": "5",
                "nv_mab_journal_error_count": "0",
                "nv_mab_journal_audit_invalid": "0",
            }
            reconciled = runner.reconcile_mab_journal(parsed, stats)
        self.assertTrue(parsed["valid"], parsed)
        self.assertEqual(parsed["update_count"], 2)
        self.assertEqual(parsed["pending_cleared_count"], 1)
        self.assertEqual(parsed["mismatch_count"], 1)
        self.assertEqual(parsed["last_update_exec_seq"], 5)
        self.assertTrue(reconciled["reconciled"], reconciled)

    def test_parser_rejects_malformed_partial_and_duplicate_updates(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            first = update_record(4, 0, 10.0)
            journal.write_text(
                json.dumps(first) + "\n" + json.dumps(first) + "\n{\"event\":",
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
        self.assertFalse(parsed["valid"])
        self.assertEqual(parsed["update_count"], 1)
        self.assertTrue(parsed["diagnostics"])

    def test_runner_sets_run_scoped_journal_and_reports_summary_only(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            env = runner.runtime_environment(
                layout, layout["target_config"], layout["task"], ("u", "p")
            )
            self.assertEqual(env["NV_MAB_JOURNAL_PATH"], str(layout["mab_journal"]))
            self.assertTrue(layout["mab_journal"].is_relative_to(layout["run_root"]))
            self.assertFalse(layout["mab_journal"].is_relative_to(REPO_ROOT))

    def test_parser_rejects_unknown_pending_clear_reason(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            journal.write_text(
                json.dumps({
                    "schema_version": 1,
                    "event": "mab_pending_cleared",
                    "reason": "invented_reason",
                    "selected_arm": 0,
                    "actual_used_arm": 0,
                }) + "\n",
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
        self.assertFalse(parsed["valid"])
        self.assertEqual(parsed["record_count"], 0)
        self.assertTrue(any("unknown_reason" in item for item in parsed["diagnostics"]))

    def test_artifact_report_marks_malformed_journal_invalid(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            for name in ("run_root", "seed_dir", "afl_output", "evidence", "err_dir"):
                Path(layout[name]).mkdir(parents=True, exist_ok=True)
            layout["target_config"].write_text("{}", encoding="utf-8")
            layout["task"].write_text("{}", encoding="utf-8")
            layout["seed"].write_bytes(b"seed")
            for name in ("status", "probe", "state_db", "body_valid_stats"):
                Path(layout[name]).write_text("{}", encoding="utf-8")
            layout["status_seq"].write_text("1", encoding="utf-8")
            layout["state_trace"].write_text("{}\n", encoding="utf-8")
            layout["mab_journal"].write_text("{broken", encoding="utf-8")
            (layout["afl_output"] / "fuzzer_stats").write_text(
                "nv_mab_total_pulls : 0\nsecurity_state_reward_src_seq : 0\n"
                "nv_mab_journal_error_count : 0\nnv_mab_journal_audit_invalid : 0\n"
                "nv_mab_arm0_pulls : 0\nnv_mab_arm1_pulls : 0\nnv_mab_arm2_pulls : 0\n"
                "nv_mab_arm0_sum : 0\nnv_mab_arm1_sum : 0\nnv_mab_arm2_sum : 0\n"
                "nv_mab_arm0_pos : 0\nnv_mab_arm1_pos : 0\nnv_mab_arm2_pos : 0\n",
                encoding="utf-8",
            )
            report = runner.inspect_artifacts(layout, launch_returncode=0)
        self.assertFalse(report["ok"])
        self.assertFalse(report["mab_journal"]["reconciled"])
        self.assertIn("mab_journal_reconciliation", report["missing_required"])

    def test_journal_setup_failure_has_explicit_fail_closed_error(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            layout["evidence"].mkdir(parents=True, exist_ok=True)
            layout["mab_journal"].mkdir()
            with self.assertRaisesRegex(RuntimeError, "^MAB_JOURNAL_SETUP_FAILED$"):
                runner.initialize_mab_journal(layout)


def pending_cleared_event(arm: int, reason: str) -> dict:
    """A non-update terminal event for an arm that never completed execution."""
    return {
        "schema_version": 1,
        "event": "mab_pending_cleared",
        "reason": reason,
        "selected_arm": arm,
        "actual_used_arm": arm,
    }


def mismatch_event(selected: int, actual: int) -> dict:
    return {
        "schema_version": 1,
        "event": "mab_update_mismatch",
        "selected_arm": selected,
        "actual_used_arm": actual,
    }


class NvMabJournalStopBoundaryTest(unittest.TestCase):
    """Semantic-only offline tests for stop-boundary / exec_seq=0 / cleanup."""

    def test_pending_arm_with_zero_exec_seq_is_not_mab_update(self) -> None:
        """exec_seq=0 must never appear as a committed mab_update."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            journal.write_text(
                json.dumps(update_record(0, 1, 0.0)) + "\n",
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
        self.assertFalse(parsed["valid"])
        self.assertEqual(parsed["update_count"], 0)
        # The parser counts invalid lines as records but rejects them as updates.
        self.assertTrue(any("duplicate_or_invalid_update" in d
                            for d in parsed["diagnostics"]))

    def test_mab_update_requires_valid_execution_identity(self) -> None:
        """Every committed mab_update must carry exec_seq > 0."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                update_record(5, 1, 0.0),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["update_count"], 2)
        for arm in range(3):
            if arm in (0, 1):
                self.assertGreaterEqual(parsed["per_arm_pulls"][arm], 1)

    def test_zero_exec_seq_is_classified_as_pending_cleanup(self) -> None:
        """exec_seq=0 with pending flag is a pending cleanup, not update."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                pending_cleared_event(1, "invalid_exec_identity"),
                pending_cleared_event(2, "budget_boundary"),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
            stats = {
                "nv_mab_total_pulls": "1",
                "nv_mab_arm0_pulls": "1",
                "nv_mab_arm1_pulls": "0",
                "nv_mab_arm2_pulls": "0",
                "nv_mab_arm0_sum": "10.0",
                "nv_mab_arm1_sum": "0.0",
                "nv_mab_arm2_sum": "0.0",
                "nv_mab_arm0_pos": "1",
                "nv_mab_arm1_pos": "0",
                "nv_mab_arm2_pos": "0",
                "security_state_reward_src_seq": "4",
                "nv_mab_journal_error_count": "0",
                "nv_mab_journal_audit_invalid": "0",
            }
            reconciled = runner.reconcile_mab_journal(parsed, stats)
        self.assertTrue(parsed["valid"], parsed)
        self.assertEqual(parsed["update_count"], 1)
        self.assertEqual(parsed["pending_cleared_count"], 2)
        self.assertEqual(parsed["last_update_exec_seq"], 4)
        self.assertTrue(reconciled["reconciled"], reconciled)

    def test_each_budget_cleared_pending_arm_gets_its_own_event(self) -> None:
        """Every pending arm that is cleared must produce an independent
        mab_pending_cleared record with its arm identity preserved."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                pending_cleared_event(1, "budget_boundary"),
                pending_cleared_event(2, "budget_boundary"),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["pending_cleared_count"], 2)
        self.assertEqual(parsed["update_count"], 0)
        self.assertEqual(parsed["record_count"], 2)

    def test_budget_boundary_cleanup_preserves_arm_identity(self) -> None:
        """Each pending_cleared record must carry its arm identity."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                pending_cleared_event(1, "budget_boundary"),
                pending_cleared_event(2, "stop_soon"),
            ]
            raw = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
            journal.write_text(raw, encoding="utf-8")
            parsed = runner.parse_mab_journal(journal)
        self.assertTrue(parsed["valid"])
        self.assertIn('"selected_arm": 1', raw)
        self.assertIn('"selected_arm": 2', raw)

    def test_journal_update_count_matches_committed_mab_updates(self) -> None:
        """nv_mab_total_pulls MUST equal the count of committed mab_update
        records in the journal.  This is a source-defined equality.  """
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                update_record(5, 0, 0.0),
                pending_cleared_event(1, "budget_boundary"),
                pending_cleared_event(2, "budget_boundary"),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
            stats = {
                "nv_mab_total_pulls": "2",
                "nv_mab_arm0_pulls": "2",
                "nv_mab_arm1_pulls": "0",
                "nv_mab_arm2_pulls": "0",
                "nv_mab_arm0_sum": "10.0",
                "nv_mab_arm1_sum": "0.0",
                "nv_mab_arm2_sum": "0.0",
                "nv_mab_arm0_pos": "1",
                "nv_mab_arm1_pos": "0",
                "nv_mab_arm2_pos": "0",
                "security_state_reward_src_seq": "5",
                "nv_mab_journal_error_count": "0",
                "nv_mab_journal_audit_invalid": "0",
            }
            reconciled = runner.reconcile_mab_journal(parsed, stats)
        self.assertEqual(int(stats["nv_mab_total_pulls"]), parsed["update_count"])
        self.assertEqual(parsed["update_count"], 2)
        self.assertTrue(reconciled["reconciled"], reconciled)

    def test_pending_cleanup_does_not_count_as_mab_update(self) -> None:
        """pending_cleared MUST NOT increase nv_mab_total_pulls or per-arm pulls."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                pending_cleared_event(1, "budget_boundary"),
                pending_cleared_event(2, "stop_soon"),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
            stats = {
                "nv_mab_total_pulls": "1",
                "nv_mab_arm0_pulls": "1",
                "nv_mab_arm1_pulls": "0",
                "nv_mab_arm2_pulls": "0",
                "nv_mab_arm0_sum": "10.0",
                "nv_mab_arm1_sum": "0.0",
                "nv_mab_arm2_sum": "0.0",
                "nv_mab_arm0_pos": "1",
                "nv_mab_arm1_pos": "0",
                "nv_mab_arm2_pos": "0",
                "security_state_reward_src_seq": "4",
                "nv_mab_journal_error_count": "0",
                "nv_mab_journal_audit_invalid": "0",
            }
            reconciled = runner.reconcile_mab_journal(parsed, stats)
        self.assertEqual(parsed["update_count"], 1)
        self.assertEqual(parsed["pending_cleared_count"], 2)
        self.assertTrue(reconciled["reconciled"], reconciled)

    def test_zero_reward_committed_update_is_counted(self) -> None:
        """reward=0 in a committed update is a REAL committed update."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                update_record(5, 1, 0.0),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
            stats = {
                "nv_mab_total_pulls": "2",
                "nv_mab_arm0_pulls": "1",
                "nv_mab_arm1_pulls": "1",
                "nv_mab_arm2_pulls": "0",
                "nv_mab_arm0_sum": "10.0",
                "nv_mab_arm1_sum": "0.0",
                "nv_mab_arm2_sum": "0.0",
                "nv_mab_arm0_pos": "1",
                "nv_mab_arm1_pos": "0",
                "nv_mab_arm2_pos": "0",
                "security_state_reward_src_seq": "5",
                "nv_mab_journal_error_count": "0",
                "nv_mab_journal_audit_invalid": "0",
            }
            reconciled = runner.reconcile_mab_journal(parsed, stats)
        self.assertEqual(parsed["update_count"], 2)
        self.assertGreaterEqual(parsed["per_arm_pulls"][1], 1)
        self.assertTrue(reconciled["reconciled"], reconciled)

    def test_mab_aggregate_semantics_are_source_consistent(self) -> None:
        """The equation nv_mab_total_pulls == count(mab_update records) holds."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                update_record(5, 1, 0.0),
                update_record(6, 2, 5.0),
                pending_cleared_event(1, "budget_boundary"),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
            stats = {
                "nv_mab_total_pulls": "3",
                "nv_mab_arm0_pulls": "1",
                "nv_mab_arm1_pulls": "1",
                "nv_mab_arm2_pulls": "1",
                "nv_mab_arm0_sum": "10.0",
                "nv_mab_arm1_sum": "0.0",
                "nv_mab_arm2_sum": "5.0",
                "nv_mab_arm0_pos": "1",
                "nv_mab_arm1_pos": "0",
                "nv_mab_arm2_pos": "1",
                "security_state_reward_src_seq": "6",
                "nv_mab_journal_error_count": "0",
                "nv_mab_journal_audit_invalid": "0",
            }
            reconciled = runner.reconcile_mab_journal(parsed, stats)
        self.assertEqual(parsed["update_count"], int(stats["nv_mab_total_pulls"]))
        self.assertTrue(reconciled["reconciled"], reconciled)

    def test_every_committed_mab_update_has_real_exec_seq(self) -> None:
        """Every committed mab_update must have exec_seq > 0."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                update_record(5, 1, 0.0),
                update_record(6, 2, -5.0),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
        self.assertTrue(parsed["valid"], parsed)
        self.assertEqual(parsed["update_count"], 3)
        self.assertGreater(parsed["last_update_exec_seq"], 0)

    def test_pending_cleanup_never_claims_target_execution(self) -> None:
        """mab_pending_cleared must never contain a valid exec_seq field."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                pending_cleared_event(1, "budget_boundary"),
                pending_cleared_event(2, "stop_soon"),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["update_count"], 0)
        self.assertEqual(parsed["last_update_exec_seq"], 0)

    def test_status_state_trace_journal_identity_is_reconcilable(self) -> None:
        """Committed updates have exec_seq that the status/state trace carries."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                update_record(5, 1, 0.0),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
            stats = {
                "nv_mab_total_pulls": "2",
                "nv_mab_arm0_pulls": "1",
                "nv_mab_arm1_pulls": "1",
                "nv_mab_arm2_pulls": "0",
                "nv_mab_arm0_sum": "10.0",
                "nv_mab_arm1_sum": "0.0",
                "nv_mab_arm2_sum": "0.0",
                "nv_mab_arm0_pos": "1",
                "nv_mab_arm1_pos": "0",
                "nv_mab_arm2_pos": "0",
                "security_state_reward_src_seq": "5",
                "nv_mab_journal_error_count": "0",
                "nv_mab_journal_audit_invalid": "0",
            }
            reconciled = runner.reconcile_mab_journal(parsed, stats)
        self.assertEqual(parsed["last_update_exec_seq"], int(stats["security_state_reward_src_seq"]))
        self.assertTrue(reconciled["reconciled"])

    def test_artifact_reconciliation_accepts_valid_pending_cleanup(self) -> None:
        """Offline artifact reconciliation passes with valid pending cleanup events."""
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            _materialize_artifacts(layout)
            Path(layout["mab_journal"]).write_text(
                json.dumps(update_record(4, 0, 10.0), sort_keys=True) + "\n"
                + json.dumps(pending_cleared_event(1, "budget_boundary"), sort_keys=True) + "\n"
                + json.dumps(pending_cleared_event(2, "budget_boundary"), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            Path(runner.execution_ledger_path(layout)).write_text(
                "".join(
                    json.dumps(record, sort_keys=True) + "\n"
                    for record in (
                        execution_record(4, 0, 0, "committed_update"),
                        execution_record(1, 1, 1, "pending_cleanup", seq=None, counted=False, target=False, status=False, cleanup_reason="budget_boundary"),
                        execution_record(2, 2, 2, "pending_cleanup", seq=None, counted=False, target=False, status=False, cleanup_reason="budget_boundary"),
                    )
                ),
                encoding="utf-8",
            )
            (Path(layout["afl_output"]) / "fuzzer_stats").write_text(
                "execs_done : 5\n"
                "nv_total_valid_exec : 4\n"
                "nv_mab_total_pulls : 1\n"
                "nv_mab_arm0_pulls : 1\n"
                "nv_mab_arm1_pulls : 0\n"
                "nv_mab_arm2_pulls : 0\n"
                "nv_mab_arm0_sum : 10.0\n"
                "nv_mab_arm1_sum : 0.0\n"
                "nv_mab_arm2_sum : 0.0\n"
                "nv_mab_arm0_pos : 1\n"
                "nv_mab_arm1_pos : 0\n"
                "nv_mab_arm2_pos : 0\n"
                "security_state_reward_src_seq : 4\n"
                "nv_mab_journal_error_count : 0\n"
                "nv_mab_journal_audit_invalid : 0\n"
                "ss_selected_sum : 0\n"
                "seed_audit_enabled : 1\n"
                "seed_audit_error_count : 0\n"
                "seed_audit_invalid : 0\n"
                "seed_audit_record_count : 0\n"
                "seed_audit_expected_selection_count : 0\n",
                encoding="utf-8",
            )
            report = runner.inspect_artifacts(layout, launch_returncode=0)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["mab_journal"]["reconciled"], report)
        self.assertTrue(report["execution_proved"], report)

    def test_artifact_reconciliation_rejects_zero_exec_update(self) -> None:
        """Any exec_seq=0 mab_update MUST cause artifact reconciliation to fail."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            _materialize_artifacts(layout)
            Path(layout["mab_journal"]).write_text(
                json.dumps(update_record(0, 1, 0.0), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report = runner.inspect_artifacts(layout, launch_returncode=0)
        self.assertFalse(report["ok"])
        self.assertFalse(report["mab_journal"]["reconciled"])
        self.assertIn("mab_journal_reconciliation", report["missing_required"])

    def test_artifact_reconciliation_rejects_unexplained_pending_arm(self) -> None:
        """If a pending arm has no terminal event, reconciliation must fail."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            _materialize_artifacts(layout)
            Path(layout["mab_journal"]).write_text(
                json.dumps(update_record(4, 0, 10.0), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (Path(layout["afl_output"]) / "fuzzer_stats").write_text(
                "execs_done : 5\n"
                "nv_total_valid_exec : 4\n"
                "nv_mab_total_pulls : 1\n"
                "nv_mab_arm0_pulls : 1\n"
                "nv_mab_arm1_pulls : 0\n"
                "nv_mab_arm2_pulls : 0\n"
                "nv_mab_arm0_sum : 10.0\n"
                "nv_mab_arm1_sum : 0.0\n"
                "nv_mab_arm2_sum : 0.0\n"
                "nv_mab_arm0_pos : 1\n"
                "nv_mab_arm1_pos : 0\n"
                "nv_mab_arm2_pos : 0\n"
                "security_state_reward_src_seq : 4\n"
                "nv_mab_pending : 1\n"
                "nv_mab_journal_error_count : 0\n"
                "nv_mab_journal_audit_invalid : 0\n"
                "ss_selected_sum : 0\n"
                "seed_audit_enabled : 1\n"
                "seed_audit_error_count : 0\n"
                "seed_audit_invalid : 0\n"
                "seed_audit_record_count : 0\n"
                "seed_audit_expected_selection_count : 0\n",
                encoding="utf-8",
            )
            report = runner.inspect_artifacts(layout, launch_returncode=0)
        self.assertFalse(report["ok"])
        self.assertFalse(report["mab_journal"]["reconciled"])
        self.assertIn("mab_journal_reconciliation", report["missing_required"])

    def test_multi_arm_artifact_report_explains_stop_boundary(self) -> None:
        """Offline multi-arm scenario: one valid update + two pending clears."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            layout = runner.build_run_layout(Path(tmp), REPO_ROOT)
            _materialize_artifacts(layout)
            Path(layout["mab_journal"]).write_text(
                json.dumps(update_record(4, 0, 10.0), sort_keys=True) + "\n"
                + json.dumps(pending_cleared_event(1, "budget_boundary"), sort_keys=True) + "\n"
                + json.dumps(pending_cleared_event(2, "budget_boundary"), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            Path(runner.execution_ledger_path(layout)).write_text(
                "".join(
                    json.dumps(record, sort_keys=True) + "\n"
                    for record in (
                        execution_record(4, 0, 0, "committed_update"),
                        execution_record(1, 1, 1, "pending_cleanup", seq=None, counted=False, target=False, status=False, cleanup_reason="budget_boundary"),
                        execution_record(2, 2, 2, "pending_cleanup", seq=None, counted=False, target=False, status=False, cleanup_reason="budget_boundary"),
                    )
                ),
                encoding="utf-8",
            )
            (Path(layout["afl_output"]) / "fuzzer_stats").write_text(
                "execs_done : 5\n"
                "nv_total_valid_exec : 4\n"
                "nv_mab_total_pulls : 1\n"
                "nv_mab_arm0_pulls : 1\n"
                "nv_mab_arm1_pulls : 0\n"
                "nv_mab_arm2_pulls : 0\n"
                "nv_mab_arm0_sum : 10.0\n"
                "nv_mab_arm1_sum : 0.0\n"
                "nv_mab_arm2_sum : 0.0\n"
                "nv_mab_arm0_pos : 1\n"
                "nv_mab_arm1_pos : 0\n"
                "nv_mab_arm2_pos : 0\n"
                "security_state_reward_src_seq : 4\n"
                "nv_mab_journal_error_count : 0\n"
                "nv_mab_journal_audit_invalid : 0\n"
                "ss_selected_sum : 0\n"
                "seed_audit_enabled : 1\n"
                "seed_audit_error_count : 0\n"
                "seed_audit_invalid : 0\n"
                "seed_audit_record_count : 0\n"
                "seed_audit_expected_selection_count : 0\n",
                encoding="utf-8",
            )
            report = runner.inspect_artifacts(layout, launch_returncode=0)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["mab_journal"]["reconciled"])
        self.assertTrue(report["execution_proved"])


class NvMabJournalOfflineRealScenarioTest(unittest.TestCase):
    """Batch 6: Offline recreation of the historical multi-arm run failure."""

    def test_offline_multi_arm_stop_boundary_scenario(self) -> None:
        """Simulate the 3-arm / max_test_cases=4 / budget_boundary scenario."""
        runner = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "mab_updates.jsonl"
            records = [
                update_record(4, 0, 10.0),
                pending_cleared_event(1, "budget_boundary"),
                pending_cleared_event(2, "budget_boundary"),
            ]
            journal.write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
                encoding="utf-8",
            )
            parsed = runner.parse_mab_journal(journal)
            stats = {
                "nv_mab_total_pulls": "1",
                "nv_mab_arm0_pulls": "1",
                "nv_mab_arm1_pulls": "0",
                "nv_mab_arm2_pulls": "0",
                "nv_mab_arm0_sum": "10.0",
                "nv_mab_arm1_sum": "0.0",
                "nv_mab_arm2_sum": "0.0",
                "nv_mab_arm0_pos": "1",
                "nv_mab_arm1_pos": "0",
                "nv_mab_arm2_pos": "0",
                "security_state_reward_src_seq": "4",
                "nv_mab_journal_error_count": "0",
                "nv_mab_journal_audit_invalid": "0",
            }
            reconciled = runner.reconcile_mab_journal(parsed, stats)
        self.assertTrue(parsed["valid"], parsed)
        self.assertEqual(parsed["update_count"], 1)
        self.assertEqual(parsed["pending_cleared_count"], 2)
        self.assertEqual(parsed["mismatch_count"], 0)
        self.assertTrue(reconciled["reconciled"], reconciled)


if __name__ == "__main__":
    unittest.main()
