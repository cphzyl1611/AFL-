#!/usr/bin/env python3
"""Phase 1B main() integration tests - proves real main() orchestration path.

These tests invoke the actual main() function with full mocking, proving:
- model-comparison flag routing
- scorer lifecycle integration
- fixed-seed AFL argv wiring
- participation validation
- validity artifact writer
- fail-closed behavior
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"


def load_runner_module():
    """Load runner as a module for patching."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("runner", RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


class TestMainIntegrationModelComparison:
    """Test main() actually invokes model-comparison orchestration."""

    @staticmethod
    def get_standard_mocks():
        """Standard mock objects with proper UUIDs for Alfresco validation."""
        mock_client = MagicMock()
        mock_client.get_node.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "parentId": "660e8400-e29b-41d4-a716-446655440000",
            "name": "nv-afl-levelc-metadata.txt",
        }
        mock_client.list_children.return_value = [
            {"id": "770e8400-e29b-41d4-a716-446655440000", "name": "nv-afl-bounded", "isFolder": True, "parentId": "shared"},
            {"id": "550e8400-e29b-41d4-a716-446655440000", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "770e8400-e29b-41d4-a716-446655440000"},
        ]

        mock_resolved = {
            "file_id": "550e8400-e29b-41d4-a716-446655440000",
            "folder_id": "770e8400-e29b-41d4-a716-446655440000",
            "target_name": "nv-afl-levelc-metadata.txt"
        }

        mock_identity = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "parentId": "770e8400-e29b-41d4-a716-446655440000",
            "name": "nv-afl-levelc-metadata.txt"
        }

        return mock_client, mock_resolved, mock_identity

    def test_main_model_comparison_calls_validate_config(self):
        """main() calls validate_model_comparison_config when --model-comparison is set."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "node123", "parentId": "parent456", "name": "nv-afl-levelc-metadata.txt",
                }

                validate_called = False
                original_validate = runner.validate_model_comparison_config
                def track_validate(*args, **kwargs):
                    nonlocal validate_called
                    validate_called = True
                    return original_validate(*args, **kwargs)

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "validate_model_comparison_config", side_effect=track_validate):
                                with patch.object(runner, "launch_bounded_afl", return_value=0):
                                    with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                        with patch.object(runner, "ScorerLifecycleManager"):
                                            with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test"}):
                                                with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "1"}):
                                                    with patch.object(runner, "parse_scorer_trace", return_value=[{"backend": "alfresco_ae_v1"}]):
                                                        runner.main()

                assert validate_called, "validate_model_comparison_config should be called"

    def test_main_model_comparison_calls_validate_scenario(self):
        """main() calls validate_model_comparison_scenario."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "node123", "parentId": "parent456", "name": "nv-afl-levelc-metadata.txt",
                }

                scenario_validated = False
                original_validate_scenario = runner.validate_model_comparison_scenario
                def track_scenario(*args, **kwargs):
                    nonlocal scenario_validated
                    scenario_validated = True
                    return original_validate_scenario(*args, **kwargs)

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "validate_model_comparison_scenario", side_effect=track_scenario):
                                with patch.object(runner, "launch_bounded_afl", return_value=0):
                                    with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                        with patch.object(runner, "ScorerLifecycleManager"):
                                            with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test"}):
                                                with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "1"}):
                                                    with patch.object(runner, "parse_scorer_trace", return_value=[{"backend": "alfresco_ae_v1"}]):
                                                        runner.main()

                assert scenario_validated, "validate_model_comparison_scenario should be called"

    def test_main_model_comparison_resolves_threshold(self):
        """main() calls resolve_model_comparison_threshold."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--validity-backend", "alfresco_ae_v1",
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "parentId": "660e8400-e29b-41d4-a716-446655440000",
                    "name": "nv-afl-levelc-metadata.txt",
                }
                mock_client.list_children.return_value = [
                    {"id": "770e8400-e29b-41d4-a716-446655440000", "name": "nv-afl-bounded", "isFolder": True, "parentId": "shared"},
                    {"id": "550e8400-e29b-41d4-a716-446655440000", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "770e8400-e29b-41d4-a716-446655440000"},
                ]

                threshold_resolved = False
                def mock_resolve(*args, **kwargs):
                    nonlocal threshold_resolved
                    threshold_resolved = True
                    return {"threshold": 0.95, "threshold_source": "test_source", "backend": "alfresco_ae_v1"}

                mock_scorer = MagicMock()

                mock_resolved = {
                    "file_id": "550e8400-e29b-41d4-a716-446655440000",
                    "folder_id": "770e8400-e29b-41d4-a716-446655440000",
                    "target_name": "nv-afl-levelc-metadata.txt"
                }

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value={
                                    "id": "550e8400-e29b-41d4-a716-446655440000",
                                    "parentId": "770e8400-e29b-41d4-a716-446655440000",
                                    "name": "nv-afl-levelc-metadata.txt"
                                }):
                                    with patch.object(runner, "resolve_model_comparison_threshold", side_effect=mock_resolve):
                                        with patch.object(runner, "ScorerLifecycleManager", return_value=mock_scorer):
                                            with patch.object(runner, "launch_bounded_afl", return_value=0):
                                                with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                                    with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "1"}):
                                                        with patch.object(runner, "parse_scorer_trace", return_value=[{"backend": "alfresco_ae_v1"}]):
                                                            runner.main()

                assert threshold_resolved, "resolve_model_comparison_threshold should be called"

    def test_main_model_comparison_starts_scorer_lifecycle(self):
        """main() starts ScorerLifecycleManager when model-comparison is on."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                scorer_started = False
                mock_scorer = MagicMock()
                def mock_scorer_init(*args, **kwargs):
                    nonlocal scorer_started
                    scorer_started = True
                    return mock_scorer

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "ScorerLifecycleManager", side_effect=mock_scorer_init):
                                        with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test"}):
                                            with patch.object(runner, "launch_bounded_afl", return_value=0):
                                                with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                                    with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "1"}):
                                                        with patch.object(runner, "parse_scorer_trace", return_value=[{"backend": "alfresco_ae_v1"}]):
                                                            runner.main()

                assert scorer_started, "ScorerLifecycleManager should be instantiated"
                mock_scorer.start.assert_called_once()

    def test_main_model_comparison_builds_model_comparison_env(self):
        """main() calls build_model_comparison_env with threshold and socket."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                env_built = False
                captured_threshold = None
                captured_socket = None
                original_build_env = runner.build_model_comparison_env
                def track_build_env(layout, backend, threshold, scorer_socket, scorer_trace, base_env):
                    nonlocal env_built, captured_threshold, captured_socket
                    env_built = True
                    captured_threshold = threshold
                    captured_socket = scorer_socket
                    return original_build_env(layout, backend, threshold, scorer_socket, scorer_trace, base_env)

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "build_model_comparison_env", side_effect=track_build_env):
                                        with patch.object(runner, "ScorerLifecycleManager"):
                                            with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test"}):
                                                with patch.object(runner, "launch_bounded_afl", return_value=0):
                                                    with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                                        with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "1"}):
                                                            with patch.object(runner, "parse_scorer_trace", return_value=[{"backend": "alfresco_ae_v1"}]):
                                                                runner.main()

                assert env_built, "build_model_comparison_env should be called"
                assert captured_threshold == 0.95
                assert captured_socket is not None

    def test_main_model_comparison_passes_fixed_seed_to_afl(self):
        """main() passes --afl-seed to launch_bounded_afl."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "99999",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                captured_seed = None
                def capture_launch(layout, config_path, child_env, *, max_test_cases, time_budget, afl_seed=None):
                    nonlocal captured_seed
                    captured_seed = afl_seed
                    return 0

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "launch_bounded_afl", side_effect=capture_launch):
                                        with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                            with patch.object(runner, "ScorerLifecycleManager"):
                                                with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test"}):
                                                    with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "1"}):
                                                        with patch.object(runner, "parse_scorer_trace", return_value=[{"backend": "alfresco_ae_v1"}]):
                                                            runner.main()

                assert captured_seed == 99999, f"AFL seed should be 99999, got {captured_seed}"

    def test_main_model_comparison_validates_participation(self):
        """main() calls validate_model_comparison_participation after run."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                participation_validated = False
                def mock_validate(*args, **kwargs):
                    nonlocal participation_validated
                    participation_validated = True
                    return {"verdict": "PASS", "reason_codes": []}

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "launch_bounded_afl", return_value=0):
                                        with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                            with patch.object(runner, "ScorerLifecycleManager"):
                                                with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test"}):
                                                    with patch.object(runner, "validate_model_comparison_participation", side_effect=mock_validate):
                                                        with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "1"}):
                                                            with patch.object(runner, "parse_scorer_trace", return_value=[{"backend": "alfresco_ae_v1"}]):
                                                                runner.main()

                assert participation_validated, "validate_model_comparison_participation should be called"

    def test_main_model_comparison_writes_validity_artifact(self):
        """main() calls write_model_comparison_validity."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                validity_written = False
                captured_validity = None
                def mock_write(layout, validity):
                    nonlocal validity_written, captured_validity
                    validity_written = True
                    captured_validity = validity
                    return Path("/tmp/validity.json")

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "launch_bounded_afl", return_value=0):
                                        with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                            with patch.object(runner, "ScorerLifecycleManager"):
                                                with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test_source"}):
                                                    with patch.object(runner, "write_model_comparison_validity", side_effect=mock_write):
                                                        with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "1"}):
                                                            with patch.object(runner, "parse_scorer_trace", return_value=[{"backend": "alfresco_ae_v1"}]):
                                                                runner.main()

                assert validity_written, "write_model_comparison_validity should be called"
                assert captured_validity is not None
                assert captured_validity["mode"] == "model_comparison"
                assert captured_validity["afl_seed"] == 20260915

    def test_main_model_comparison_cleanup_scorer_on_exception(self):
        """main() calls scorer.stop() even if AFL launch raises."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                mock_scorer = MagicMock()
                scorer_stopped = False
                def track_stop():
                    nonlocal scorer_stopped
                    scorer_stopped = True
                mock_scorer.stop = track_stop

                def mock_launch(*args, **kwargs):
                    raise RuntimeError("AFL_LAUNCH_FAILED")

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "ScorerLifecycleManager", return_value=mock_scorer):
                                        with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test"}):
                                            with patch.object(runner, "launch_bounded_afl", side_effect=mock_launch):
                                                try:
                                                    runner.main()
                                                except RuntimeError:
                                                    pass  # Expected

                assert scorer_stopped, "scorer.stop() should be called even on AFL launch failure"


class TestMainIntegrationBaseline:
    """Test baseline mode does NOT invoke model-comparison path."""

    def get_standard_mocks(self):
        """Standard mocks for baseline tests."""
        mock_client = MagicMock()
        mock_client.list_children.return_value = [
            {"id": "12345678-90ab-cdef-1234-567890abcdef", "name": "nv-afl-bounded", "isFolder": True, "parentId": "shared"},
            {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "12345678-90ab-cdef-1234-567890abcdef"},
        ]
        mock_resolved = {
            "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "folder_id": "12345678-90ab-cdef-1234-567890abcdef",
            "parent_id": "12345678-90ab-cdef-1234-567890abcdef",
            "target_name": "nv-afl-levelc-metadata.txt",
        }
        mock_identity = {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "parentId": "12345678-90ab-cdef-1234-567890abcdef",
            "name": "nv-afl-levelc-metadata.txt",
        }
        return mock_client, mock_resolved, mock_identity

    def test_baseline_does_not_start_scorer(self):
        """Baseline mode does NOT create ScorerLifecycleManager."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                scorer_created = False
                def track_scorer(*args, **kwargs):
                    nonlocal scorer_created
                    scorer_created = True
                    return MagicMock()

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "ScorerLifecycleManager", side_effect=track_scorer):
                                        with patch.object(runner, "launch_bounded_afl", return_value=0):
                                            with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                                runner.main()

                assert not scorer_created, "ScorerLifecycleManager should NOT be created in baseline mode"

    def test_baseline_does_not_validate_participation(self):
        """Baseline mode does NOT call validate_model_comparison_participation."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                participation_called = False
                def track_participation(*args, **kwargs):
                    nonlocal participation_called
                    participation_called = True
                    return {"verdict": "PASS"}

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "launch_bounded_afl", return_value=0):
                                        with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                            with patch.object(runner, "validate_model_comparison_participation", side_effect=track_participation):
                                                runner.main()

                assert not participation_called, "validate_model_comparison_participation should NOT be called in baseline"

    def test_baseline_passes_none_as_afl_seed(self):
        """Baseline mode passes None as afl_seed to launch_bounded_afl."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--run-root", tmpdir,
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                captured_seed = "NOT_SET"
                def capture_launch(layout, config_path, child_env, *, max_test_cases, time_budget, afl_seed=None):
                    nonlocal captured_seed
                    captured_seed = afl_seed
                    return 0

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "launch_bounded_afl", side_effect=capture_launch):
                                        with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                            runner.main()

                assert captured_seed is None, f"Baseline should pass None as afl_seed, got {captured_seed}"


class TestMainIntegrationFailClosed:
    """Test fail-closed validation paths."""

    def get_standard_mocks(self):
        """Standard mocks for fail-closed tests."""
        mock_client = MagicMock()
        mock_resolved = {
            "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "folder_id": "12345678-90ab-cdef-1234-567890abcdef",
            "parent_id": "12345678-90ab-cdef-1234-567890abcdef",
            "target_name": "nv-afl-levelc-metadata.txt",
        }
        mock_identity = {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "parentId": "12345678-90ab-cdef-1234-567890abcdef",
            "name": "nv-afl-levelc-metadata.txt",
        }
        return mock_client, mock_resolved, mock_identity

    def test_model_comparison_without_seed_fails_before_scorer(self):
        """Missing --afl-seed fails at parse validation, before scorer start."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--scorer-python", sys.executable,
                "--run-root", tmpdir,
            ]):
                scorer_created = False
                def track_scorer(*args, **kwargs):
                    nonlocal scorer_created
                    scorer_created = True
                    return MagicMock()

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "ScorerLifecycleManager", side_effect=track_scorer):
                        rc = runner.main()

                assert rc == 2, "Should fail with config error"
                assert not scorer_created, "Scorer should NOT be created when config validation fails"

    def test_model_comparison_multipart_fails_before_scorer(self):
        """Multipart scenario fails at scenario validation, before scorer start."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "12345",
                "--scorer-python", sys.executable,
                "--scenario", "multipart_upload",
                "--run-root", tmpdir,
            ]):
                scorer_created = False
                def track_scorer(*args, **kwargs):
                    nonlocal scorer_created
                    scorer_created = True
                    return MagicMock()

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "ScorerLifecycleManager", side_effect=track_scorer):
                        rc = runner.main()

                assert rc == 2, "Should fail with config error"
                assert not scorer_created, "Scorer should NOT be created when scenario validation fails"

    def test_participation_invalid_marks_artifact_contract_failed(self):
        """Invalid participation verdict marks artifact contract as failed."""
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "20260915",
                "--scorer-python", sys.executable,
                "--run-root", str(run_root),
                "--max-test-cases", "1",
            ]):
                mock_client, mock_resolved, mock_identity = self.get_standard_mocks()

                def mock_validate(*args, **kwargs):
                    return {"verdict": "INVALID_FOR_MODEL_COMPARISON", "reason_codes": ["ZERO_SCORER_INVOCATIONS"]}

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value=mock_resolved):
                                with patch.object(runner, "read_only_target_identity", return_value=mock_identity):
                                    with patch.object(runner, "launch_bounded_afl", return_value=0):
                                        with patch.object(runner, "post_execution_readback", return_value={"enabled": True, "applicable": False, "verdict": "not_applicable"}):
                                            with patch.object(runner, "ScorerLifecycleManager"):
                                                with patch.object(runner, "resolve_model_comparison_threshold", return_value={"threshold": 0.95, "threshold_source": "test"}):
                                                    with patch.object(runner, "validate_model_comparison_participation", side_effect=mock_validate):
                                                        with patch.object(runner, "parse_fuzzer_stats", return_value={"body_score_rpc_ok": "0"}):
                                                            with patch.object(runner, "parse_scorer_trace", return_value=[]):
                                                                rc = runner.main()

                # Should fail with artifact contract failure
                assert rc == 4, f"Should fail with artifact contract error (4), got {rc}"


class TestAuthContract:
    """Test auth contract is Alfresco user/pass only."""

    def test_runtime_credentials_reads_alfresco_only(self):
        """runtime_credentials reads ALFRESCO_USER/PASS, not NV_TOKEN."""
        runner = load_runner_module()

        import inspect
        source = inspect.getsource(runner.runtime_credentials)
        assert "ALFRESCO_USER" in source
        assert "ALFRESCO_PASS" in source
        assert "NV_TOKEN" not in source

    def test_model_comparison_env_does_not_read_nv_token(self):
        """build_model_comparison_env does not reference NV_TOKEN."""
        runner = load_runner_module()

        import inspect
        source = inspect.getsource(runner.build_model_comparison_env)
        assert "NV_TOKEN" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
