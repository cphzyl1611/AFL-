"""Offline contracts for the serial Alfresco A/B/C bounded protocol."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = REPO_ROOT / "scripts" / "run_alfresco_bounded_protocol.py"


def load_protocol():
    spec = importlib.util.spec_from_file_location("alfresco_bounded_protocol_test", PROTOCOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("PROTOCOL_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def successful_report(
    run_root: Path,
    target: str,
    scope: str,
    *,
    node_identity: str | None = None,
) -> dict[str, object]:
    return {
        "ok": True,
        "artifact_final_result": "pass",
        "runner": {"exit_code": 0, "exit_status": "success", "recorded": True},
        "execution_ledger": {"required": True, "present": True, "reconciled": True},
        "mab_journal": {"required": True, "present": True, "reconciled": True},
        "readback": {"applicable": True, "attempted": True, "present": True, "reconciled": True, "artifact_valid": True, "verdict": "pass"},
        "target_binding": {
            "target_file_name": target,
            "node_identity": node_identity or f"sha256:node:{target}",
            "parent_identity": "sha256:parent:shared",
        },
        "task": {"mutation_scope": [scope]},
        "run_root": str(run_root),
    }


class SerialProtocolTest(unittest.TestCase):
    def test_entries_have_exact_order_and_bindings(self) -> None:
        module = load_protocol()
        self.assertEqual(module.PROTOCOL_ENTRIES, (
            ("A", "nv-afl-levelc-metadata.txt", "field_value"),
            ("B", "nv-afl-levelc-metadata-arm1.txt", "boundary"),
            ("C", "nv-afl-levelc-metadata-arm2.txt", "structure"),
        ))

    def test_protocol_passes_one_manifest_to_every_arm(self) -> None:
        module = load_protocol()
        commands: list[list[str]] = []

        with tempfile.TemporaryDirectory(prefix="alfresco-protocol-manifest-") as tmp:
            output_root = Path(tmp) / "protocol-output"
            manifest = Path(tmp) / "seeds.txt"
            source_dir = Path(tmp) / "seeds"
            source_dir.mkdir()
            manifest.write_text("a.http\\nb.http\\nc.http\\n", encoding="utf-8")

            def fake_command(command: list[str]) -> int:
                commands.append(command)
                run_root = Path(command[command.index("--run-root") + 1])
                target = command[command.index("--target-file-name") + 1]
                scope = command[command.index("--mutation-scope") + 1]
                report_path = run_root / "evidence" / "artifact_report.json"
                report_path.parent.mkdir(parents=True)
                (run_root / "task.json").write_text(
                    json.dumps({"mutation_scope": [scope]}), encoding="utf-8"
                )
                report_path.write_text(
                    json.dumps(successful_report(run_root, target, scope)), encoding="utf-8"
                )
                return 0

            result = module.run_protocol(
                repo_root=REPO_ROOT,
                output_root=output_root,
                runner=REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py",
                seed_manifest=manifest,
                seed_source_dir=source_dir,
                command_runner=fake_command,
            )

            self.assertEqual(result["status"], "pass")
            self.assertEqual(len(commands), 3)
            for command in commands:
                self.assertEqual(command[command.index("--seed-manifest") + 1], str(manifest.resolve()))
                self.assertEqual(command[command.index("--seed-source-dir") + 1], str(source_dir.resolve()))

    def test_protocol_runs_entries_serially_with_distinct_external_roots(self) -> None:
        module = load_protocol()
        commands: list[list[str]] = []

        with tempfile.TemporaryDirectory(prefix="alfresco-protocol-test-") as tmp:
            output_root = Path(tmp) / "protocol-output"

            def fake_command(command: list[str]) -> int:
                commands.append(command)
                run_root = Path(command[command.index("--run-root") + 1])
                target = command[command.index("--target-file-name") + 1]
                scope = command[command.index("--mutation-scope") + 1]
                report_path = run_root / "evidence" / "artifact_report.json"
                report_path.parent.mkdir(parents=True)
                (run_root / "task.json").write_text(
                    json.dumps({"mutation_scope": [scope]}), encoding="utf-8"
                )
                report_path.write_text(
                    json.dumps(successful_report(run_root, target, scope)), encoding="utf-8"
                )
                return 0

            result = module.run_protocol(
                repo_root=REPO_ROOT,
                output_root=output_root,
                runner=REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py",
                command_runner=fake_command,
            )

            self.assertEqual(result["status"], "pass")
            self.assertEqual(len(commands), 3)
            self.assertEqual(
                [command[command.index("--target-file-name") + 1] for command in commands],
                [entry[1] for entry in module.PROTOCOL_ENTRIES],
            )
            self.assertEqual(
                [command[command.index("--mutation-scope") + 1] for command in commands],
                [entry[2] for entry in module.PROTOCOL_ENTRIES],
            )
            roots = [Path(command[command.index("--run-root") + 1]) for command in commands]
            self.assertEqual(len(set(roots)), 3)
            for root in roots:
                self.assertFalse(root.is_relative_to(REPO_ROOT.resolve()))
                self.assertTrue(root.is_dir())
            self.assertTrue((output_root / "protocol_report.json").is_file())

    def test_protocol_stops_after_first_failed_entry(self) -> None:
        module = load_protocol()
        commands: list[list[str]] = []

        with tempfile.TemporaryDirectory(prefix="alfresco-protocol-stop-") as tmp:
            output_root = Path(tmp) / "protocol-output"

            def fake_command(command: list[str]) -> int:
                commands.append(command)
                run_root = Path(command[command.index("--run-root") + 1])
                report_path = run_root / "evidence" / "artifact_report.json"
                report_path.parent.mkdir(parents=True)
                report_path.write_text(json.dumps({"ok": False}), encoding="utf-8")
                return 9

            result = module.run_protocol(
                repo_root=REPO_ROOT,
                output_root=output_root,
                runner=REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py",
                command_runner=fake_command,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failed_entry"], "A")
            self.assertEqual(len(commands), 1)
            self.assertFalse((output_root / "runs" / "B").exists())
            self.assertFalse((output_root / "runs" / "C").exists())

    def test_lock_contention_rejects_protocol_without_child_launch(self) -> None:
        module = load_protocol()
        with tempfile.TemporaryDirectory(prefix="alfresco-protocol-lock-") as tmp:
            output_root = Path(tmp) / "protocol-output"
            output_root.mkdir()
            lock_path = output_root / "protocol.lock"
            with module.acquire_protocol_lock(lock_path):
                with self.assertRaisesRegex(RuntimeError, "^PROTOCOL_LOCK_HELD$"):
                    with module.acquire_protocol_lock(lock_path):
                        pass

    def test_protocol_rejects_reused_target_identity(self) -> None:
        module = load_protocol()
        commands: list[list[str]] = []

        with tempfile.TemporaryDirectory(prefix="alfresco-protocol-identity-") as tmp:
            output_root = Path(tmp) / "protocol-output"

            def fake_command(command: list[str]) -> int:
                commands.append(command)
                run_root = Path(command[command.index("--run-root") + 1])
                target = command[command.index("--target-file-name") + 1]
                scope = command[command.index("--mutation-scope") + 1]
                report_path = run_root / "evidence" / "artifact_report.json"
                report_path.parent.mkdir(parents=True)
                (run_root / "task.json").write_text(
                    json.dumps({"mutation_scope": [scope]}), encoding="utf-8"
                )
                report_path.write_text(
                    json.dumps(successful_report(
                        run_root, target, scope, node_identity="sha256:node:same"
                    )), encoding="utf-8"
                )
                return 0

            result = module.run_protocol(
                repo_root=REPO_ROOT,
                output_root=output_root,
                runner=REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py",
                command_runner=fake_command,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failure"], "TARGET_IDENTITY_NOT_DISTINCT")
            self.assertEqual(result["failed_entry"], "B")
            self.assertEqual(len(commands), 2)

    def test_protocol_rejects_child_success_without_complete_evidence(self) -> None:
        module = load_protocol()
        commands: list[list[str]] = []

        with tempfile.TemporaryDirectory(prefix="alfresco-protocol-evidence-") as tmp:
            output_root = Path(tmp) / "protocol-output"

            def fake_command(command: list[str]) -> int:
                commands.append(command)
                run_root = Path(command[command.index("--run-root") + 1])
                report_path = run_root / "evidence" / "artifact_report.json"
                report_path.parent.mkdir(parents=True)
                report_path.write_text(
                    json.dumps({"ok": True, "artifact_final_result": "pass"}), encoding="utf-8"
                )
                return 0

            result = module.run_protocol(
                repo_root=REPO_ROOT,
                output_root=output_root,
                runner=REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py",
                command_runner=fake_command,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failed_entry"], "A")
            self.assertEqual(len(commands), 1)


if __name__ == "__main__":
    unittest.main()
