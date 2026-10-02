#!/usr/bin/env python3
"""Phase 1B CLI wiring integration tests.

Tests that the runner CLI exposes model-comparison flags and that main()
actually invokes the model-comparison orchestration path.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_alfresco_bounded_feedback.py"


class TestCLIFlags:
    """Test that model-comparison flags are exposed and accepted."""

    def test_help_includes_model_comparison_flag(self):
        """--model-comparison appears in --help output."""
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "--model-comparison" in result.stdout

    def test_help_includes_afl_seed_flag(self):
        """--afl-seed appears in --help output."""
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "--afl-seed" in result.stdout

    def test_help_includes_scorer_python_flag(self):
        """--scorer-python appears in --help output."""
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "--scorer-python" in result.stdout

    def test_help_includes_scorer_ready_timeout_flag(self):
        """--scorer-ready-timeout appears in --help output."""
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "--scorer-ready-timeout" in result.stdout


class TestModelComparisonValidation:
    """Test model-comparison mode validation at parse time."""

    def test_model_comparison_without_afl_seed_fails(self):
        """--model-comparison without --afl-seed is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--run-root", tmpdir,
            ]):
                # Import and call main
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)

                spec.loader.exec_module(runner)

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client"):
                        with patch.object(runner, "perform_preflight"):
                            rc = runner.main()
                            assert rc == 2  # config failure

    def test_model_comparison_with_multipart_fails(self):
        """model-comparison with multipart scenario is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "12345",
                "--scenario", "multipart_upload",
                "--run-root", tmpdir,
            ]):
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)

                spec.loader.exec_module(runner)

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client"):
                        with patch.object(runner, "perform_preflight"):
                            rc = runner.main()
                            assert rc == 2

    def test_baseline_mode_accepts_no_afl_seed(self):
        """Baseline mode (no --model-comparison) does not require --afl-seed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"

            with patch("sys.argv", [
                str(RUNNER),
                "--run-root", str(run_root),
                "--max-test-cases", "1",
            ]):
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)

                # Mock the entire flow to avoid real execution
                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "12345678-1234-1234-1234-123456789abc",
                    "parentId": "87654321-4321-4321-4321-cba987654321",
                    "name": "nv-afl-levelc-metadata.txt",
                }
                mock_client.list_children.return_value = [
                    {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "nv-afl-bounded", "isFolder": True, "parentId": "shared"},
                    {"id": "12345678-1234-1234-1234-123456789abc", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
                ]

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "resolve_existing_dedicated_node", return_value={
                                "folder_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 
                                "file_id": "12345678-1234-1234-1234-123456789abc",
                                "parent_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 
                                "target_name": "nv-afl-levelc-metadata.txt",
                                "aspect_names": [],
                            }):
                                with patch.object(runner, "read_only_target_identity", return_value={
                                    "id": "12345678-1234-1234-1234-123456789abc", 
                                    "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 
                                    "name": "nv-afl-levelc-metadata.txt",
                                }):
                                    with patch.object(runner, "launch_bounded_afl", return_value=0):
                                        with patch.object(runner, "post_execution_readback") as mock_readback:
                                            mock_readback.return_value = {
                                                "enabled": True, "applicable": False, "verdict": "not_applicable",
                                                "attempted": False, "present": False, "reconciled": False,
                                                "valid_execution_count": 0,
                                            }
                                            rc = runner.main()
                                            # Should not fail on missing --afl-seed
                                            assert rc in (0, 4, 5)  # may fail artifacts, but not parse


class TestMainOrchestration:
    """Test that main() actually invokes the model-comparison path."""

    def test_model_comparison_mode_passes_seed_to_afl(self):
        """main() passes --afl-seed to AFL argv when model-comparison is on."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"

            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "99999",
                "--scorer-python", sys.executable,
                "--run-root", str(run_root),
                "--max-test-cases", "1",
            ]):
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)

                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "12345678-1234-1234-1234-123456789abc", 
                    "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 
                    "name": "nv-afl-levelc-metadata.txt",
                }
                
                def mock_list_children(parent_id):
                    if parent_id == "-my-":
                        return [{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "parentId": "-my-"}]
                    elif parent_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa":
                        return [{"id": "12345678-1234-1234-1234-123456789abc", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}]
                    return []
                mock_client.list_children.side_effect = mock_list_children

                captured_seed = None
                def capture_launch(layout, config, env, *, max_test_cases, time_budget, afl_seed=None):
                    nonlocal captured_seed
                    captured_seed = afl_seed
                    return 0

                mock_scorer_mgr = MagicMock()
                mock_scorer_mgr.start.return_value = MagicMock(poll=MagicMock(return_value=None))

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "launch_bounded_afl", side_effect=capture_launch):
                                with patch.object(runner, "post_execution_readback"):
                                    with patch.object(runner, "ScorerLifecycleManager", return_value=mock_scorer_mgr):
                                        runner.main()

                assert captured_seed == 99999

    def test_model_comparison_mode_starts_scorer(self):
        """main() starts scorer process when --model-comparison is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"

            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "12345",
                "--scorer-python", sys.executable,
                "--run-root", str(run_root),
                "--max-test-cases", "1",
            ]):
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)

                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "12345678-1234-1234-1234-123456789abc", 
                    "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 
                    "name": "nv-afl-levelc-metadata.txt",
                }
                
                def mock_list_children(parent_id):
                    if parent_id == "-my-":
                        return [{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "parentId": "-my-"}]
                    elif parent_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa":
                        return [{"id": "12345678-1234-1234-1234-123456789abc", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}]
                    return []
                mock_client.list_children.side_effect = mock_list_children

                scorer_started = False
                def track_scorer_instantiation(*args, **kwargs):
                    nonlocal scorer_started
                    scorer_started = True
                    mock_mgr = MagicMock()
                    mock_mgr.start.return_value = MagicMock(poll=MagicMock(return_value=None))
                    return mock_mgr

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "launch_bounded_afl", return_value=0):
                                with patch.object(runner, "post_execution_readback"):
                                    with patch.object(runner, "ScorerLifecycleManager", side_effect=track_scorer_instantiation):
                                        runner.main()

                assert scorer_started, "Scorer process should have been started"

    def test_model_comparison_mode_validates_participation(self):
        """main() validates scorer participation after run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"

            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "12345",
                "--scorer-python", sys.executable,
                "--run-root", str(run_root),
                "--max-test-cases", "1",
            ]):
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)

                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "12345678-1234-1234-1234-123456789abc", 
                    "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 
                    "name": "nv-afl-levelc-metadata.txt",
                }
                
                def mock_list_children(parent_id):
                    if parent_id == "-my-":
                        return [{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "parentId": "-my-"}]
                    elif parent_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa":
                        return [{"id": "12345678-1234-1234-1234-123456789abc", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}]
                    return []
                mock_client.list_children.side_effect = mock_list_children

                participation_validated = False
                def mock_validate(*args, **kwargs):
                    nonlocal participation_validated
                    participation_validated = True
                    return {"verdict": "PASS", "reason_codes": []}

                mock_scorer_mgr = MagicMock()
                mock_scorer_mgr.start.return_value = MagicMock(poll=MagicMock(return_value=None))

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "launch_bounded_afl", return_value=0):
                                with patch.object(runner, "post_execution_readback"):
                                    with patch.object(runner, "ScorerLifecycleManager", return_value=mock_scorer_mgr):
                                        with patch.object(runner, "parse_fuzzer_stats", return_value={"execs_done": 100}):
                                            with patch.object(runner, "parse_scorer_trace", return_value=[{"payload_id": "1"}]):
                                                with patch.object(runner, "validate_model_comparison_participation", side_effect=mock_validate):
                                                    runner.main()

                assert participation_validated, "Participation should have been validated"

    def test_model_comparison_mode_writes_validity_artifact(self):
        """main() writes model_comparison_validity.json after run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"

            with patch("sys.argv", [
                str(RUNNER),
                "--model-comparison",
                "--afl-seed", "12345",
                "--scorer-python", sys.executable,
                "--run-root", str(run_root),
                "--max-test-cases", "1",
            ]):
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)

                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "12345678-1234-1234-1234-123456789abc", "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "nv-afl-levelc-metadata.txt",
                }
                # list_children is called twice: first for DEDICATED_PARENT (to find folder), then for folder_id (to find file)
                def mock_list_children(parent_id):
                    if parent_id == "-my-":  # DEDICATED_PARENT from levelc
                        return [{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "parentId": "-my-"}]
                    elif parent_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa":  # folder_id
                        return [{"id": "12345678-1234-1234-1234-123456789abc", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}]
                    return []
                mock_client.list_children.side_effect = mock_list_children

                validity_written = False
                def mock_write(*args, **kwargs):
                    nonlocal validity_written
                    validity_written = True
                    return Path("/tmp/validity.json")

                mock_scorer_mgr = MagicMock()
                mock_scorer_mgr.start.return_value = MagicMock(poll=MagicMock(return_value=None))

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "launch_bounded_afl", return_value=0):
                                with patch.object(runner, "post_execution_readback"):
                                    with patch.object(runner, "ScorerLifecycleManager", return_value=mock_scorer_mgr):
                                        with patch.object(runner, "parse_fuzzer_stats", return_value={"execs_done": 100}):
                                            with patch.object(runner, "parse_scorer_trace", return_value=[{"payload_id": "1"}]):
                                                with patch.object(runner, "validate_model_comparison_participation", return_value={"verdict": "PASS"}):
                                                    with patch.object(runner, "write_model_comparison_validity", side_effect=mock_write):
                                                        runner.main()

                assert validity_written, "Validity artifact should have been written"

    def test_baseline_mode_does_not_start_scorer(self):
        """Baseline mode (no --model-comparison) does NOT start scorer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"

            with patch("sys.argv", [
                str(RUNNER),
                "--run-root", str(run_root),
                "--max-test-cases", "1",
            ]):
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)

                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "12345678-1234-1234-1234-123456789abc", "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "nv-afl-levelc-metadata.txt",
                }
                # list_children is called twice: first for DEDICATED_PARENT (to find folder), then for folder_id (to find file)
                def mock_list_children(parent_id):
                    if parent_id == "-my-":  # DEDICATED_PARENT from levelc
                        return [{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "parentId": "-my-"}]
                    elif parent_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa":  # folder_id
                        return [{"id": "12345678-1234-1234-1234-123456789abc", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}]
                    return []
                mock_client.list_children.side_effect = mock_list_children

                scorer_started = False
                def mock_start_scorer(*args, **kwargs):
                    nonlocal scorer_started
                    scorer_started = True
                    return MagicMock()

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "launch_bounded_afl", return_value=0):
                                with patch.object(runner, "post_execution_readback"):
                                    with patch.object(runner, "ScorerLifecycleManager", side_effect=mock_start_scorer):
                                        runner.main()

                assert not scorer_started, "Scorer should NOT have been started in baseline mode"

    def test_baseline_mode_does_not_validate_participation(self):
        """Baseline mode does NOT call validate_model_comparison_participation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"

            with patch("sys.argv", [
                str(RUNNER),
                "--run-root", str(run_root),
                "--max-test-cases", "1",
            ]):
                import importlib.util
                spec = importlib.util.spec_from_file_location("runner", RUNNER)
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)

                mock_client = MagicMock()
                mock_client.get_node.return_value = {
                    "id": "12345678-1234-1234-1234-123456789abc", "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "nv-afl-levelc-metadata.txt",
                }
                # list_children is called twice: first for DEDICATED_PARENT (to find folder), then for folder_id (to find file)
                def mock_list_children(parent_id):
                    if parent_id == "-my-":  # DEDICATED_PARENT from levelc
                        return [{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "NV_AFL_REAL_PLATFORM_CALIBRATION", "isFolder": True, "parentId": "-my-"}]
                    elif parent_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa":  # folder_id
                        return [{"id": "12345678-1234-1234-1234-123456789abc", "name": "nv-afl-levelc-metadata.txt", "isFile": True, "parentId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}]
                    return []
                mock_client.list_children.side_effect = mock_list_children

                participation_validated = False
                def mock_validate(*args, **kwargs):
                    nonlocal participation_validated
                    participation_validated = True
                    return {"verdict": "PASS"}

                with patch.object(runner, "runtime_credentials", return_value=("u", "p")):
                    with patch.object(runner, "build_alfresco_client", return_value=mock_client):
                        with patch.object(runner, "perform_preflight"):
                            with patch.object(runner, "launch_bounded_afl", return_value=0):
                                with patch.object(runner, "post_execution_readback"):
                                    with patch.object(runner, "validate_model_comparison_participation", side_effect=mock_validate):
                                        runner.main()

                assert not participation_validated, "Participation should NOT be validated in baseline mode"


class TestAuthContract:
    """Test that Alfresco runner uses only ALFRESCO_USER/PASS, never NV_TOKEN."""

    def test_alfresco_runner_reads_alfresco_credentials_only(self):
        """Runner reads ALFRESCO_USER/PASS, not NV_TOKEN."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("runner", RUNNER)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)

        # Static analysis: runtime_credentials should only check ALFRESCO_*
        import inspect
        source = inspect.getsource(runner.runtime_credentials)
        assert "ALFRESCO_USER" in source
        assert "ALFRESCO_PASS" in source
        assert "NV_TOKEN" not in source

    def test_model_comparison_does_not_introduce_nv_token(self):
        """Model-comparison path does not reference NV_TOKEN."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("runner", RUNNER)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)

        import inspect

        # Check build_model_comparison_env
        source = inspect.getsource(runner.build_model_comparison_env)
        assert "NV_TOKEN" not in source

        # Check validate_model_comparison_config
        source = inspect.getsource(runner.validate_model_comparison_config)
        assert "NV_TOKEN" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
