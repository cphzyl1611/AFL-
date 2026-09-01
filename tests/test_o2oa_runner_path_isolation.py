"""Offline TDD contracts for O2OA runner/adapter root isolation."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import base64
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "runner" / "fuzz_test_runner.py"
ADAPTER_PATH = REPO_ROOT / "integration" / "fuzz_adapter.py"
PLAN_SCRIPT = REPO_ROOT / "scripts" / "run_runner_real_fuzz_plan.sh"
RUNNER_SCRIPT = REPO_ROOT / "scripts" / "run_runner_real_fuzz.sh"
DOWNSTREAM_SCRIPT = (
    REPO_ROOT / "scripts" / "run_cms_body_valid_compare_real_rulescore_only.sh"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    if path == RUNNER_PATH:
        with tempfile.TemporaryDirectory() as isolated_home:
            with mock.patch("pathlib.Path.home", return_value=Path(isolated_home)):
                spec.loader.exec_module(module)
    else:
        spec.loader.exec_module(module)
    return module


class O2OARunnerPathIsolationTest(unittest.TestCase):
    def test_runner_does_not_default_to_official_main_repo(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_default")
        self.assertFalse(hasattr(runner, "ROOT"))
        with self.assertRaises((TypeError, ValueError)):
            runner.submit(str(REPO_ROOT / "runner/templates/task_ae_default.json"))

    def test_adapter_passes_bounded_repo_root(self) -> None:
        adapter = load_module(ADAPTER_PATH, "o2oa_isolation_adapter_repo")
        calls = []

        def fake_runner(args, *, repo_root=None, run_root=None):
            calls.append((args, repo_root, run_root))
            return {"task_id": "bounded-task", "run_dir": str(run_root)}

        profile = {
            "profile": "test",
            "template": "runner/templates/task_ae_default.json",
            "seed_dir": "in/o2oa_body_model_compare",
            "manifest": "runner/templates/manifest.txt",
        }
        request = {"platform": "test", "run_root": "/tmp/o2oa-isolation-run"}
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "bounded-repo"
            (repo_root / "runner/templates").mkdir(parents=True)
            (repo_root / "in/o2oa_body_model_compare").mkdir(parents=True)
            (repo_root / ".git").mkdir()
            (repo_root / "runner/templates/task_ae_default.json").write_text(
                json.dumps({"seed_dir": "in/o2oa_body_model_compare", "launch_cmd": ["true"]}),
                encoding="utf-8",
            )
            (repo_root / "runner/templates/manifest.txt").touch()
            with mock.patch.object(adapter, "ROOT", repo_root), mock.patch.object(
                adapter, "load_profile", return_value=profile
            ), mock.patch.object(adapter, "run_runner", side_effect=fake_runner):
                adapter.action_submit(request)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], repo_root.resolve())
        self.assertEqual(calls[0][2], Path("/tmp/o2oa-isolation-run").resolve())

    def test_non_dry_run_requires_external_run_root(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_required_root")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            (repo_root / "runner/templates").mkdir(parents=True)
            task = repo_root / "runner/templates/task.json"
            task.write_text(json.dumps({"launch_cmd": ["true"]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                runner.submit(str(task), repo_root=repo_root)

    def test_task_run_output_paths_stay_outside_git_worktree(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_layout")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            run_root = Path(tmp).parent / f"{repo_root.name}-external"
            repo_root.mkdir()
            (repo_root / ".git").mkdir()
            layout = runner.build_run_layout(repo_root=repo_root, run_root=run_root)
            for key in ("task_dir", "run_dir", "afl_out_dir", "stdout", "stderr"):
                self.assertTrue(layout[key].is_relative_to(run_root), key)
                self.assertFalse(layout[key].is_relative_to(repo_root), key)

    def test_path_traversal_fails_closed(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_traversal")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            run_root = Path(tmp) / "external"
            repo_root.mkdir()
            run_root.mkdir()
            with self.assertRaises(ValueError):
                runner.resolve_repo_path("../outside", repo_root)
            with self.assertRaises(ValueError):
                runner.resolve_run_path("../outside", run_root)

    def test_launch_command_traversal_fails_closed(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_launch_traversal")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            with self.assertRaises(ValueError):
                runner.build_launch_cmd(
                    {"launch_cmd": ["bash", "../outside.sh"], "seed_dir": "in"},
                    "task",
                    Path(tmp) / "run",
                    Path(tmp) / "run/out",
                    repo_root=repo_root,
                    run_root=Path(tmp) / "run",
                )

    def test_symlink_escape_fails_closed(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_symlink")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            outside = Path(tmp) / "outside"
            repo_root.mkdir()
            outside.mkdir()
            (repo_root / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                runner.resolve_repo_path("link/file", repo_root)

    def test_run_root_symlink_escape_fails_closed(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_run_symlink")
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            outside = Path(tmp) / "outside"
            run_root.mkdir()
            outside.mkdir()
            (run_root / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                runner.resolve_run_path("link/output", run_root)

    def test_dry_run_does_not_launch_or_write_main_repo(self) -> None:
        adapter = load_module(ADAPTER_PATH, "o2oa_isolation_adapter_dry_run")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "bounded"
            repo_root.mkdir()
            (repo_root / ".git").mkdir()
            sentinel = repo_root / "runner" / "tasks"
            request = {"platform": "test", "run_root": str(Path(tmp) / "run")}
            profile = {
                "profile": "test",
                "template": "runner/templates/task.json",
                "seed_dir": "in/o2oa_body_model_compare",
                "manifest": "runner/templates/manifest.txt",
            }
            (repo_root / "runner/templates").mkdir(parents=True)
            (repo_root / "in/o2oa_body_model_compare").mkdir(parents=True)
            (repo_root / "runner/templates/task.json").write_text(
                json.dumps({"launch_cmd": ["true"]}), encoding="utf-8"
            )
            (repo_root / "runner/templates/manifest.txt").touch()
            with mock.patch.object(adapter, "ROOT", repo_root), mock.patch.object(
                adapter, "load_profile", return_value=profile
            ), mock.patch.object(adapter, "run_runner") as launch:
                result = adapter.action_submit(request, dry_run=True)
            self.assertEqual(result["process_result"], 1)
            launch.assert_not_called()
            self.assertFalse(sentinel.exists())

    def test_legacy_stats_output_is_remapped_to_run_root(self) -> None:
        adapter = load_module(ADAPTER_PATH, "o2oa_isolation_adapter_legacy_stats")
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            self.assertEqual(
                adapter.resolve_run_output("/tmp/nv_body_valid_stats.json", run_root),
                (run_root / "body_valid_stats.json").resolve(),
            )

    def test_default_o2oa_dry_run_keeps_outputs_external(self) -> None:
        adapter = load_module(ADAPTER_PATH, "o2oa_isolation_adapter_default_profile")
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            request = {
                "platform": "o2oa_default",
                "repo_root": str(REPO_ROOT),
                "run_root": str(run_root),
            }
            result = adapter.action_submit(request, dry_run=True)
            self.assertEqual(result["process_result"], 1)
            mapped = result["mapped_runner_task"]
            self.assertTrue(
                Path(mapped["result_stats_json"]).is_relative_to(run_root.resolve())
            )
            main_repo = Path("/home/dministrator/AFLplusplus").resolve()
            if REPO_ROOT.resolve() != main_repo:
                self.assertNotIn(str(main_repo) + "/", json.dumps(result))

    def test_explicit_bounded_binary_path_is_used(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_binary")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            run_root = Path(tmp) / "external"
            repo_root.mkdir()
            run_root.mkdir()
            binary = repo_root / "afl-fuzz"
            binary.touch()
            binary.chmod(0o755)
            command = runner.build_launch_cmd(
                {"afl_bin": "afl-fuzz", "target_cmd": ["true"], "seed_dir": "in"},
                "task",
                run_root / "run",
                run_root / "run/out",
                repo_root=repo_root,
                run_root=run_root,
            )
            self.assertEqual(command[0], str(binary.resolve()))

    def test_relative_input_paths_resolve_against_repo_root(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_input")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            self.assertEqual(
                runner.resolve_repo_path("in/seed", repo_root),
                (repo_root / "in/seed").resolve(),
            )

    def test_relative_output_paths_resolve_against_run_root(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_output")
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            self.assertEqual(
                runner.resolve_run_path("out/summary.csv", run_root),
                (run_root / "out/summary.csv").resolve(),
            )

    def test_runner_produces_full_downstream_path_contract(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_env")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo_root = base / "repo"
            run_dir = base / "external/runs/task"
            seed_dir = repo_root / "in/seeds"
            manifest = repo_root / "model_stage/manifests/dataset_manifest_156.txt"
            (repo_root / "targets").mkdir(parents=True)
            seed_dir.mkdir(parents=True)
            manifest.parent.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            (repo_root / "targets/o2oa_query.json").write_text("{}\n", encoding="utf-8")
            (seed_dir / "seed.json").write_text("{}\n", encoding="utf-8")
            manifest.write_text("seed.json,normal\n", encoding="utf-8")
            task = {
                "seed_dir": "in/seeds",
                "manifest": "model_stage/manifests/dataset_manifest_156.txt",
                "duration_plan": [20, 60],
            }

            env = runner.build_launch_env(
                task,
                "task",
                run_dir,
                run_dir / "afl_out",
                repo_root,
            )

            self.assertEqual(env["ROOT"], str(repo_root.resolve()))
            self.assertEqual(env["CFG"], str(repo_root / "targets/o2oa_query.json"))
            self.assertEqual(env["IN_DIR"], str(run_dir / "manifest_seeds"))
            self.assertEqual(env["SEED_MANIFEST"], str(manifest))
            self.assertEqual(env["OUT_ROOT"], str(run_dir / "out"))
            self.assertEqual(
                env["BODY_VALID_STATS"], str(run_dir / "nv_body_valid_stats.json")
            )
            self.assertEqual(env["STATUS_PATH"], str(run_dir / "nv_http_status.json"))
            self.assertEqual(env["RUNNER_RUN_DIR"], str(run_dir))
            self.assertEqual(env["DUR"], "20")
            self.assertEqual(env["RUNNER_DURATION_PLAN"], "20 60")

    def test_runner_passes_run_scoped_task_path_to_afl(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_task_path")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo_root = base / "repo"
            run_dir = base / "external/runs/task"
            seed_dir = repo_root / "in/seeds"
            manifest = repo_root / "model_stage/manifests/dataset_manifest_156.txt"
            (repo_root / "targets").mkdir(parents=True)
            seed_dir.mkdir(parents=True)
            manifest.parent.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            (repo_root / "targets/o2oa_query.json").write_text("{}\n", encoding="utf-8")
            (seed_dir / "seed.json").write_text("{}\n", encoding="utf-8")
            manifest.write_text("seed.json,normal\n", encoding="utf-8")
            task = {
                "seed_dir": "in/seeds",
                "manifest": "model_stage/manifests/dataset_manifest_156.txt",
                "duration_plan": [20],
            }
            task_path = run_dir / "task.json"
            task_path.write_text(json.dumps(task), encoding="utf-8")

            env = runner.build_launch_env(
                task,
                "task",
                run_dir,
                run_dir / "afl_out",
                repo_root,
                task_path=task_path,
            )

            self.assertEqual(env["NV_TASK_PATH"], str(task_path.resolve()))

    def test_runtime_task_contract_contains_afl_feedback_fields(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_isolation_runtime_task_contract")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo_root = base / "repo"
            run_dir = base / "external/runs/task"
            seed_dir = repo_root / "in/seeds"
            manifest = repo_root / "model_stage/manifests/dataset_manifest_156.txt"
            (repo_root / "targets").mkdir(parents=True)
            seed_dir.mkdir(parents=True)
            manifest.parent.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            (repo_root / "targets/o2oa_query.json").write_text("{}\n", encoding="utf-8")
            (seed_dir / "seed.json").write_text("{}\n", encoding="utf-8")
            manifest.write_text("seed.json,normal\n", encoding="utf-8")
            task = {
                "target_type": "http_api",
                "target_endpoint": "cms_doc_list",
                "seed_dir": "in/seeds",
                "manifest": "model_stage/manifests/dataset_manifest_156.txt",
                "duration_plan": [30],
            }
            task_path = run_dir / "task.json"
            task_path.write_text(json.dumps(task), encoding="utf-8")

            runner.build_launch_env(
                task,
                "task",
                run_dir,
                run_dir / "afl_out",
                repo_root,
                task_path=task_path,
            )
            runtime_task = json.loads(task_path.read_text(encoding="utf-8"))

            self.assertEqual(runtime_task["target_type"], "http_api")
            self.assertEqual(runtime_task["target_endpoint"], "cms_doc_list")
            self.assertEqual(runtime_task["seed_source"], "manifest")
            self.assertEqual(runtime_task["seed_location"], str((run_dir / "manifest_seeds").resolve()))
            self.assertEqual(runtime_task["mutation_scope"], ["field_value", "boundary", "structure"])
            self.assertGreater(runtime_task["max_test_cases"], 0)
            self.assertEqual(runtime_task["time_budget"], 30)
            self.assertEqual(runtime_task["enable_validity"], 1)


class O2OADownstreamShellPathIsolationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.root = self.base / "bounded-source"
        self.home = self.base / "home"
        self.root.mkdir()
        self.home.mkdir()
        (self.home / "AFLplusplus").mkdir()
        (self.home / "AFLplusplus" / "sentinel").write_text(
            "unchanged", encoding="utf-8"
        )

        scripts = self.root / "scripts"
        scripts.mkdir()
        for source in (PLAN_SCRIPT, RUNNER_SCRIPT, DOWNSTREAM_SCRIPT):
            shutil.copy2(source, scripts / source.name)

        (self.root / "targets").mkdir()
        (self.root / "targets/o2oa_query.json").write_text("{}\n", encoding="utf-8")
        (self.root / "validity").mkdir()
        (self.root / "validity/o2oa_query_rules.json").write_text(
            "{}\n", encoding="utf-8"
        )
        (self.root / "nv_http_harness.py").write_text(
            "raise SystemExit('offline fake afl-fuzz must not launch the harness')\n",
            encoding="utf-8",
        )

        seed_source = self.root / "in/seeds"
        seed_source.mkdir(parents=True)
        (seed_source / "manifest.json").write_text('{"manifest": true}\n', encoding="utf-8")
        (seed_source / "extra.json").write_text('{"extra": true}\n', encoding="utf-8")
        manifest = self.root / "model_stage/manifests/dataset_manifest_156.txt"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("manifest.json,normal\n", encoding="utf-8")
        self.manifest = manifest

        fake_afl = self.root / "afl-fuzz"
        fake_afl.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
original_args="$*"
in_dir=""
out_dir=""
while (($#)); do
  case "$1" in
    -i) in_dir="$2"; shift 2 ;;
    -o) out_dir="$2"; shift 2 ;;
    --) break ;;
    *) shift ;;
  esac
done
for seed in "$in_dir"/*; do
  [[ -f "$seed" && ! -L "$seed" ]] || exit 91
done
mkdir -p "$out_dir"
printf '%s\n' \\
  "ROOT=$ROOT" \\
  "CFG=$CFG" \\
  "IN_DIR=$IN_DIR" \\
  "SEED_MANIFEST=$SEED_MANIFEST" \\
  "OUT_ROOT=$OUT_ROOT" \\
  "BODY_VALID_STATS=$BODY_VALID_STATS" \\
  "STATUS_PATH=$STATUS_PATH" \\
  "RUNNER_RUN_DIR=$RUNNER_RUN_DIR" \\
  "NV_TASK_PATH=${NV_TASK_PATH:-}" \\
  "NV_KEEP_INITIAL_SEEDS=${NV_KEEP_INITIAL_SEEDS:-}" \\
  "AFL_ARGS=$original_args" \\
  "DUR=$DUR" \\
  "AFL_INPUT=$in_dir" \\
  "AFL_OUTPUT=$out_dir" \\
  "INPUT_FILES=$(for seed in "$in_dir"/*; do basename "$seed"; done | paste -sd, -)" \\
  > "$CAPTURE_PATH"
printf '%s\n' \\
  'nv_total_valid_exec : 1' \\
  'nv_err_exec : 0' \\
  'nv_err_rate : 0' \\
  'saved_hangs : 0' \\
  'saved_crashes : 0' \\
  > "$out_dir/fuzzer_stats"
if [[ "${FAKE_AFL_SKIP_STATS:-0}" == 1 ]]; then
  rm -f "$out_dir/fuzzer_stats"
fi
printf '%s\n' '{"http_code": 200, "latency_ms": 1, "ncov_total": 1}' > "$STATUS_PATH"
printf '%s\n' '{"body_rule_pass": 1, "body_rule_reject": 0, "body_score_pass": 1, "body_score_reject": 0, "body_score_rpc_ok": 1, "body_score_rpc_fail": 0}' > "$BODY_VALID_STATS"
if [[ "${FAKE_AFL_TIMEOUT_AFTER_ARTIFACTS:-0}" == 1 ]]; then
  exit 124
fi
""",
            encoding="utf-8",
        )
        fake_afl.chmod(0o755)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_chain(self, name: str = "run-A", **overrides):
        run_dir = self.base / name
        manifest_view = run_dir / "manifest_seeds"
        manifest_view.mkdir(parents=True)
        shutil.copy2(self.root / "in/seeds/manifest.json", manifest_view / "0001__manifest.json")
        capture = run_dir / "capture.env"
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(self.home),
            "ROOT": str(self.root),
            "CFG": str(self.root / "targets/o2oa_query.json"),
            "IN_DIR": str(manifest_view),
            "SEED_MANIFEST": str(self.manifest),
            "OUT_ROOT": str(run_dir / "out"),
            "BODY_VALID_STATS": str(run_dir / "nv_body_valid_stats.json"),
            "STATUS_PATH": str(run_dir / "nv_http_status.json"),
            "RUNNER_RUN_DIR": str(run_dir),
            "NV_TASK_PATH": str(run_dir / "task.json"),
            "NV_KEEP_INITIAL_SEEDS": "1",
            "RUNNER_DURATION_PLAN": "7",
            "NV_TOKEN": "offline-placeholder",
            "NV_BODY_SCORE_ENDPOINT": "unix:///offline/not-contacted.sock",
            "NV_BODY_SCORE_THRESHOLD": "1.0",
            "CAPTURE_PATH": str(capture),
        }
        env.update({key: str(value) for key, value in overrides.items()})
        result = subprocess.run(
            [str(self.root / "scripts/run_runner_real_fuzz_plan.sh")],
            cwd=self.base,
            env=env,
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
        values = {}
        if capture.is_file():
            values = dict(
                line.split("=", 1)
                for line in capture.read_text(encoding="utf-8").splitlines()
            )
        return result, values, run_dir

    def assert_chain_succeeds(self, name: str = "run-A"):
        result, values, run_dir = self.run_chain(name)
        self.assertEqual(result.returncode, 0, result.stderr)
        return values, run_dir

    def test_plan_passes_task_path_to_downstream(self) -> None:
        values, run_dir = self.assert_chain_succeeds()
        self.assertEqual(values["NV_TASK_PATH"], str(run_dir / "task.json"))

    def test_manifest_run_keeps_initial_seeds_available(self) -> None:
        values, _ = self.assert_chain_succeeds()
        self.assertEqual(values["NV_KEEP_INITIAL_SEEDS"], "1")

    def test_plan_collects_artifacts_after_controlled_timeout(self) -> None:
        result, values, run_dir = self.run_chain(
            "run-timeout-after-artifacts", FAKE_AFL_TIMEOUT_AFTER_ARTIFACTS=1
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values["AFL_OUTPUT"], str(run_dir / "out/rule_score"))
        self.assertTrue((run_dir / "summary_dur7.csv").is_file())

    def test_manifest_run_uses_sequential_queue_selection(self) -> None:
        values, _ = self.assert_chain_succeeds()
        self.assertIn("-Z", values["AFL_ARGS"].split())

    def test_plan_passes_root_to_downstream(self) -> None:
        values, _ = self.assert_chain_succeeds()
        self.assertEqual(values["ROOT"], str(self.root))

    def test_plan_passes_cfg_to_downstream(self) -> None:
        values, _ = self.assert_chain_succeeds()
        self.assertEqual(values["CFG"], str(self.root / "targets/o2oa_query.json"))

    def test_plan_passes_in_dir_to_downstream(self) -> None:
        values, run_dir = self.assert_chain_succeeds()
        self.assertEqual(values["IN_DIR"], str(run_dir / "manifest_seeds"))

    def test_plan_passes_out_root_to_downstream(self) -> None:
        values, run_dir = self.assert_chain_succeeds()
        self.assertEqual(values["OUT_ROOT"], str(run_dir / "out"))
        self.assertEqual(values["AFL_OUTPUT"], str(run_dir / "out/rule_score"))

    def test_plan_passes_body_valid_stats_to_downstream(self) -> None:
        values, run_dir = self.assert_chain_succeeds()
        self.assertEqual(
            values["BODY_VALID_STATS"], str(run_dir / "nv_body_valid_stats.json")
        )

    def test_plan_passes_status_path_to_downstream(self) -> None:
        values, run_dir = self.assert_chain_succeeds()
        self.assertEqual(values["STATUS_PATH"], str(run_dir / "nv_http_status.json"))

    def test_plan_passes_run_dir_and_duration_to_downstream(self) -> None:
        values, run_dir = self.assert_chain_succeeds()
        self.assertEqual(values["RUNNER_RUN_DIR"], str(run_dir))
        self.assertEqual(values["DUR"], "7")

    def test_plan_passes_seed_manifest_to_downstream(self) -> None:
        values, _ = self.assert_chain_succeeds()
        self.assertEqual(values["SEED_MANIFEST"], str(self.manifest))

    def test_downstream_does_not_default_to_home_aflplusplus(self) -> None:
        values, _ = self.assert_chain_succeeds()
        self.assertEqual(values["ROOT"], str(self.root))
        self.assertEqual(
            (self.home / "AFLplusplus" / "sentinel").read_text(encoding="utf-8"),
            "unchanged",
        )
        self.assertEqual(list((self.home / "AFLplusplus").iterdir()), [self.home / "AFLplusplus/sentinel"])

    def test_downstream_does_not_use_shared_tmp_stats(self) -> None:
        values, _ = self.assert_chain_succeeds()
        self.assertNotEqual(values["BODY_VALID_STATS"], "/tmp/nv_body_valid_stats.json")

    def test_downstream_does_not_use_shared_tmp_status(self) -> None:
        values, _ = self.assert_chain_succeeds()
        self.assertNotEqual(values["STATUS_PATH"], "/tmp/nv_http_status.json")

    def test_two_run_roots_are_isolated(self) -> None:
        values_a, run_a = self.assert_chain_succeeds("run-A")
        values_b, run_b = self.assert_chain_succeeds("run-B")
        for key in ("OUT_ROOT", "BODY_VALID_STATS", "STATUS_PATH", "RUNNER_RUN_DIR"):
            self.assertNotEqual(values_a[key], values_b[key], key)
        self.assertTrue(Path(values_a["OUT_ROOT"]).is_relative_to(run_a))
        self.assertTrue(Path(values_b["OUT_ROOT"]).is_relative_to(run_b))

    def test_manifest_view_is_used_as_input(self) -> None:
        values, run_dir = self.assert_chain_succeeds()
        self.assertEqual(values["IN_DIR"], str(run_dir / "manifest_seeds"))
        self.assertEqual(values["AFL_INPUT"], values["IN_DIR"])
        self.assertEqual(values["INPUT_FILES"], "0001__manifest.json")
        self.assertNotIn("extra.json", values["INPUT_FILES"])
        manifest_view = run_dir / "manifest_seeds"
        self.assertTrue((manifest_view / "0001__manifest.json").is_file())
        self.assertFalse((manifest_view / "0001__manifest.json").is_symlink())

    def test_missing_run_root_fails_closed(self) -> None:
        result, values, _ = self.run_chain(RUNNER_RUN_DIR="")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(values, {})

    def test_downstream_nonzero_runner_status_propagates(self) -> None:
        fake_afl = self.root / "afl-fuzz"
        with fake_afl.open("a", encoding="utf-8") as handle:
            handle.write("\nexit 7\n")
        result, values, run_dir = self.run_chain()
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(values["AFL_INPUT"], str(run_dir / "manifest_seeds"))
        self.assertEqual(values["INPUT_FILES"], "0001__manifest.json")

    def test_missing_fuzzer_stats_is_nonzero_failure(self) -> None:
        result, values, run_dir = self.run_chain(FAKE_AFL_SKIP_STATS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_fuzzer_stats", result.stderr)
        self.assertFalse((run_dir / "out" / "rule_score" / "fuzzer_stats").exists())
        self.assertEqual(values["AFL_INPUT"], str(run_dir / "manifest_seeds"))

    def test_fake_afl_zero_without_stats_does_not_become_success(self) -> None:
        result, _, run_dir = self.run_chain(FAKE_AFL_SKIP_STATS="1")
        self.assertNotEqual(result.returncode, 0)
        summary_lines = (run_dir / "out" / "summary.csv").read_text().splitlines()
        self.assertEqual(len(summary_lines), 1)

    def test_path_traversal_fails_closed(self) -> None:
        run_dir = self.base / "run-A"
        escape = self.base / "escape"
        result, values, _ = self.run_chain(
            OUT_ROOT=run_dir / "../escape",
            BODY_VALID_STATS=escape / "stats.json",
            STATUS_PATH=escape / "status.json",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(values, {})
        self.assertFalse(escape.exists())

    def test_symlink_output_escape_fails_closed(self) -> None:
        run_dir = self.base / "run-A"
        run_dir.mkdir()
        outside = self.base / "outside"
        outside.mkdir()
        (run_dir / "out").symlink_to(outside, target_is_directory=True)
        result, values, _ = self.run_chain()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(values, {})
        self.assertEqual(list(outside.iterdir()), [])

    def test_dry_run_does_not_write_main_repo(self) -> None:
        before = {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        values, run_dir = self.assert_chain_succeeds()
        after = {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertTrue(Path(values["OUT_ROOT"]).is_relative_to(run_dir))


if __name__ == "__main__":
    unittest.main()


class O2OARunnerTerminalStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.repo = self.base / "repo"
        self.run_root = self.base / "run-root"
        self.repo.mkdir()
        self.run_root.mkdir()
        (self.repo / ".git").mkdir()
        (self.repo / "in").mkdir()
        self.child = self.repo / "fake_child.py"
        self.child.write_text(
            "import os, sys, time\n"
            "from pathlib import Path\n"
            "delay = float(sys.argv[2])\n"
            "time.sleep(delay)\n"
            "stats = os.environ.get('FAKE_STATS_PATH')\n"
            "if stats:\n"
            "    Path(stats).parent.mkdir(parents=True, exist_ok=True)\n"
            "    Path(stats).write_text('execs_done : 1\\n', encoding='utf-8')\n"
            "raise SystemExit(int(sys.argv[1]))\n",
            encoding="utf-8",
        )
        self.runner = load_module(RUNNER_PATH, "o2oa_terminal_runner")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def submit_fake(self, returncode: int, delay: float = 0.0, **task_overrides):
        task = {
            "seed_dir": "in",
            "launch_cmd": [
                str(Path(__import__("sys").executable).resolve()),
                str(self.child),
                str(returncode),
                str(delay),
            ],
        }
        task.update(task_overrides)
        emit_fuzzer_stats = task_overrides.pop("emit_fuzzer_stats", True)
        task.pop("emit_fuzzer_stats", None)
        if emit_fuzzer_stats:
            task["env"] = {"FAKE_STATS_PATH": "{AFL_OUT_DIR}/fuzzer_stats"}
        task_path = self.repo / f"task-{returncode}-{delay}.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            self.runner.submit(
                str(task_path), repo_root=self.repo, run_root=self.run_root
            )
        result = json.loads(output.getvalue())
        status_path = self.run_root / "tasks" / result["task_id"] / "status.json"
        return result["task_id"], status_path

    def wait_terminal(self, status_path: Path, timeout: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout
        terminal = {"exited", "failed", "timed_out", "stopped"}
        while time.monotonic() < deadline:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("status") in terminal:
                supervisor_pid = status.get("pid")
                grace_deadline = time.monotonic() + 0.5
                while (
                    isinstance(supervisor_pid, int)
                    and self.runner.is_pid_alive(supervisor_pid)
                    and time.monotonic() < grace_deadline
                ):
                    time.sleep(0.01)
                return status
            time.sleep(0.02)
        self.fail(f"status did not become terminal: {status}")

    def call_json(self, function, *args, **kwargs) -> dict:
        output = io.StringIO()
        with redirect_stdout(output):
            function(*args, **kwargs)
        return json.loads(output.getvalue())

    def test_child_zero_exit_updates_status_terminal(self) -> None:
        task_id, status_path = self.submit_fake(0)
        status = self.wait_terminal(status_path)
        self.assertEqual(status["status"], "exited")
        self.assertEqual(status["runner_exit_code"], 0)
        self.assertEqual(status["launch_returncode"], 0)
        self.assertEqual(status["child_launch_returncode"], 0)
        self.assertIsNotNone(status["finished_at"])

    def test_child_nonzero_exit_updates_status_terminal(self) -> None:
        task_id, status_path = self.submit_fake(1)
        status = self.wait_terminal(status_path)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["runner_exit_code"], 1)
        self.assertEqual(status["launch_returncode"], 1)
        self.assertIn("runner_exit_code_1", status["failure_reason"])

    def test_missing_stats_updates_terminal_status_failed(self) -> None:
        task = {
            "seed_dir": "in",
            "launch_cmd": [
                str(__import__("sys").executable),
                "-c",
                "pass",
            ],
        }
        task_path = self.repo / "missing-stats.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            self.runner.submit(str(task_path), repo_root=self.repo, run_root=self.run_root)
        result = json.loads(output.getvalue())
        status_path = self.run_root / "tasks" / result["task_id"] / "status.json"
        status = self.wait_terminal(status_path)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["runner_exit_code"], 0)
        self.assertEqual(status["launch_returncode"], 0)
        self.assertEqual(status["child_launch_returncode"], 0)
        self.assertEqual(status["failure_reason"], "missing_fuzzer_stats")
        queried = self.call_json(
            self.runner.query,
            result["task_id"],
            repo_root=self.repo,
            run_root=self.run_root,
        )
        self.assertEqual(queried["status"], "failed")
        self.assertEqual(queried["failure_reason"], "missing_fuzzer_stats")
        report = self.call_json(
            self.runner.report,
            result["task_id"],
            repo_root=self.repo,
            run_root=self.run_root,
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failure_reason"], "missing_fuzzer_stats")

    def test_child_timeout_updates_status_terminal(self) -> None:
        _, status_path = self.submit_fake(0, 1.0, timeout_sec=0.05)
        status = self.wait_terminal(status_path)
        self.assertEqual(status["status"], "timed_out")
        self.assertEqual(status["launch_returncode"], 124)
        self.assertEqual(status["child_launch_returncode"], 0)
        self.assertEqual(status["failure_reason"], "runner_timeout")

    def test_child_timeout_returncode_124_preserves_timeout_status(self) -> None:
        _, status_path = self.submit_fake(124)
        status = self.wait_terminal(status_path)
        self.assertEqual(status["status"], "timed_out")
        self.assertEqual(status["runner_exit_code"], 124)
        self.assertEqual(status["launch_returncode"], 124)
        self.assertEqual(status["failure_reason"], "runner_timeout")

    def test_child_startup_failure_updates_status_failed(self) -> None:
        task = {
            "seed_dir": "in",
            "launch_cmd": [str(self.repo / "missing-child")],
        }
        task_path = self.repo / "startup-failure.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            self.runner.submit(
                str(task_path), repo_root=self.repo, run_root=self.run_root
            )
        result = json.loads(output.getvalue())
        failed_path = self.run_root / "tasks" / result["task_id"] / "status.json"
        status = self.wait_terminal(failed_path)
        self.assertEqual(status["status"], "failed")
        self.assertIsNone(status["child_launch_returncode"])
        self.assertIsNone(status["launch_returncode"])
        self.assertEqual(status["runner_exit_code"], None)
        self.assertEqual(status["failure_reason"], "child_popen_failed")

    def test_no_usable_test_cases_failure_is_classified(self) -> None:
        task = {
            "seed_dir": "in",
            "launch_cmd": [
                str(__import__("sys").executable),
                "-c",
                "import sys; sys.stderr.write('No usable test cases in manifest_seeds\\n'); sys.exit(1)",
            ],
        }
        task_path = self.repo / "no-usable.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            self.runner.submit(str(task_path), repo_root=self.repo, run_root=self.run_root)
        result = json.loads(output.getvalue())
        status_path = self.run_root / "tasks" / result["task_id"] / "status.json"
        status = self.wait_terminal(status_path)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["failure_reason"], "no_usable_test_cases")

    def test_stop_updates_status_to_stopped(self) -> None:
        task_id, status_path = self.submit_fake(0, 2.0)
        result = self.call_json(
            self.runner.stop,
            task_id,
            repo_root=self.repo,
            run_root=self.run_root,
        )
        self.assertEqual(result["status"], "stopped")
        status = self.wait_terminal(status_path)
        self.assertEqual(status["status"], "stopped")
        self.assertIsNone(status["child_launch_returncode"])
        self.assertIsNotNone(status["finished_at"])

    def test_query_and_report_expose_terminal_result(self) -> None:
        task_id, status_path = self.submit_fake(2)
        self.wait_terminal(status_path)
        queried = self.call_json(
            self.runner.query,
            task_id,
            repo_root=self.repo,
            run_root=self.run_root,
        )
        self.assertEqual(queried["status"], "failed")
        self.assertEqual(queried["runner_exit_code"], 2)
        report = self.call_json(
            self.runner.report,
            task_id,
            repo_root=self.repo,
            run_root=self.run_root,
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["runner_exit_code"], 2)
        self.assertEqual(report["launch_returncode"], 2)

    def test_status_does_not_expose_sensitive_command_argument(self) -> None:
        task = {
            "seed_dir": "in",
            "launch_cmd": [str(__import__("sys").executable), "-c", "pass", "offline-token"],
            "env": {"NV_TOKEN": "offline-token"},
        }
        task_path = self.repo / "privacy.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            self.runner.submit(str(task_path), repo_root=self.repo, run_root=self.run_root)
        result = json.loads(output.getvalue())
        status_path = self.run_root / "tasks" / result["task_id"] / "status.json"
        status = self.wait_terminal(status_path)
        serialized = json.dumps(status)
        self.assertNotIn("offline-token", serialized)
        self.assertNotIn("Authorization", serialized)
        spec = self.run_root / "runs" / status["task_id"] / "supervisor_spec.json"
        self.assertNotIn("offline-token", spec.read_text(encoding="utf-8"))

    def test_failure_reason_does_not_expose_stderr(self) -> None:
        task = {
            "seed_dir": "in",
            "launch_cmd": [
                str(__import__("sys").executable),
                "-c",
                "import sys; sys.stderr.write('Authorization: Bearer test-token-for-stderr-redaction\\n'); sys.exit(7)",
            ],
        }
        task_path = self.repo / "stderr-privacy.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            self.runner.submit(str(task_path), repo_root=self.repo, run_root=self.run_root)
        result = json.loads(output.getvalue())
        status_path = self.run_root / "tasks" / result["task_id"] / "status.json"
        status = self.wait_terminal(status_path)
        serialized = json.dumps(status)
        self.assertEqual(status["failure_reason"], "runner_failed")
        self.assertNotIn("offline-token", serialized)
        self.assertNotIn("Authorization", serialized)

    def test_report_exposes_terminal_result_without_output_artifacts(self) -> None:
        task_id, status_path = self.submit_fake(1, emit_fuzzer_stats=False)
        self.wait_terminal(status_path)
        report = self.call_json(
            self.runner.report,
            task_id,
            repo_root=self.repo,
            run_root=self.run_root,
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["runner_exit_code"], 1)
        self.assertEqual(report["recorded"], True)
        self.assertEqual(report["fuzzer_stats"], {})

    def test_status_update_is_atomic_on_replace_failure(self) -> None:
        path = self.run_root / "atomic-status.json"
        path.write_text('{"status":"old"}\n', encoding="utf-8")
        with mock.patch.object(self.runner.os, "replace", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                self.runner.save_json(path, {"status": "new"})
        self.assertEqual(path.read_text(encoding="utf-8"), '{"status":"old"}\n')

    def _run_supervisor_with_status_write_failure(self) -> tuple[int, Path, Path, str]:
        task_dir = self.run_root / "tasks" / "status-write-failure"
        run_dir = self.run_root / "runs" / "status-write-failure"
        task_dir.mkdir(parents=True)
        run_dir.mkdir(parents=True)
        status_path = task_dir / "status.json"
        fallback_path = self.run_root / "supervisor-fallback.json"
        stdout_path = self.run_root / "supervisor.stdout"
        stderr_path = self.run_root / "supervisor.stderr"
        start_marker = self.run_root / "start"
        start_marker.touch()
        status_path.write_text(
            json.dumps(
                {
                    "task_id": "offline-status-failure",
                    "status": "running",
                    "pid": os.getpid(),
                    "run_dir": str(run_dir),
                    "afl_out_dir": str(run_dir / "afl_out"),
                    "report_json": str(task_dir / "report.json"),
                    "status_fallback_path": str(fallback_path),
                }
            ),
            encoding="utf-8",
        )
        spec_path = self.run_root / "supervisor-spec.json"
        spec_path.write_text(
            json.dumps(
                {
                    "cwd": str(self.repo),
                    "stdout": str(stdout_path),
                    "stderr": str(stderr_path),
                    "start_marker": str(start_marker),
                    "stop_marker": str(self.run_root / "stop"),
                    "fallback_path": str(fallback_path),
                    "timeout_sec": 1,
                }
            ),
            encoding="utf-8",
        )
        command = [str(__import__("sys").executable), "-c", "pass"]
        encoded = base64.b64encode(
            json.dumps(command).encode("utf-8")
        ).decode("ascii")
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"RUNNER_COMMAND_B64": encoded}), mock.patch.object(
            self.runner, "save_json", side_effect=OSError("injected status write failure")
        ), redirect_stderr(stderr):
            rc = self.runner._supervisor_status(status_path, spec_path=spec_path)
        return rc, status_path, fallback_path, stderr.getvalue()

    def test_status_write_failure_has_independent_fallback(self) -> None:
        rc, status_path, fallback_path, _ = self._run_supervisor_with_status_write_failure()
        self.assertNotEqual(rc, 0)
        self.assertFalse(status_path.read_text(encoding="utf-8").find('"status": "failed"') >= 0)
        self.assertTrue(fallback_path.is_file())
        fallback = json.loads(fallback_path.read_text(encoding="utf-8"))
        self.assertEqual(fallback["status"], "failed")
        self.assertEqual(fallback["failure_reason"], "status_write_failed")
        self.assertEqual(fallback["status_artifact"], "fallback")
        self.assertEqual(fallback["status_write_error"], "runner_failed")
        self.assertNotEqual(fallback_path, status_path)

    def test_status_write_failure_is_not_silent(self) -> None:
        rc, _, _, stderr = self._run_supervisor_with_status_write_failure()
        self.assertNotEqual(rc, 0)
        self.assertIn("status_write_failed", stderr)

    def test_supervisor_output_is_not_unconditionally_discarded(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("os.devnull", source)
        self.assertNotIn("file_actions=[", source)

    def test_status_write_failure_does_not_report_success(self) -> None:
        rc, _, fallback_path, _ = self._run_supervisor_with_status_write_failure()
        self.assertNotEqual(rc, 0)
        fallback = json.loads(fallback_path.read_text(encoding="utf-8"))
        self.assertNotEqual(fallback.get("status"), "exited")
        self.assertNotEqual(fallback.get("runner_exit_code"), 0)

    def test_status_write_failure_is_visible_to_query_and_report(self) -> None:
        _, status_path, fallback_path, _ = self._run_supervisor_with_status_write_failure()
        queried = self.call_json(
            self.runner.query,
            "status-write-failure",
            repo_root=self.repo,
            run_root=self.run_root,
        )
        self.assertEqual(queried["status"], "failed")
        self.assertEqual(queried["failure_reason"], "status_write_failed")
        report = self.call_json(
            self.runner.report,
            "status-write-failure",
            repo_root=self.repo,
            run_root=self.run_root,
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failure_reason"], "status_write_failed")
        self.assertEqual(report["recorded"], False)
        self.assertEqual(Path(queried["status_fallback_path"]), fallback_path)
        self.assertEqual(Path(report["status_fallback_path"]), fallback_path)
        self.assertEqual(status_path.read_text(encoding="utf-8").count('"status": "running"'), 1)


class ResultPathFinalizeTest(unittest.TestCase):
    """The terminal status must reference the run-scoped summary file that
    actually exists, not a stale plan-level template path."""

    def setUp(self) -> None:
        self.runner = load_module(RUNNER_PATH, "o2oa_isolation_runner_finalize")

    def test_result_summary_csv_is_corrected_to_run_scoped_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifact"
            artifact_root.mkdir()
            (artifact_root / "summary.csv").write_text(
                "mode,last_http_code\nrule_score,200\n", encoding="utf-8"
            )
            status = {"result_summary_csv": "/stale/plan/level/summary.csv"}
            self.runner._finalize_result_paths(status, artifact_root)
            self.assertEqual(
                status["result_summary_csv"],
                str(artifact_root / "summary.csv"),
            )

    def test_result_summary_csv_unchanged_when_run_scoped_summary_absent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifact"
            artifact_root.mkdir()
            status = {"result_summary_csv": "/declared/plan/level/summary.csv"}
            self.runner._finalize_result_paths(status, artifact_root)
            self.assertEqual(
                status["result_summary_csv"],
                "/declared/plan/level/summary.csv",
            )
