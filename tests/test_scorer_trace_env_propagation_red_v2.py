"""GREEN test: ScorerLifecycleManager propagates trace_path to scorer subprocess."""
import subprocess
import sys
from pathlib import Path


def test_scorer_lifecycle_propagates_trace_path_explicit():
    """ScorerLifecycleManager must propagate explicit trace_path to subprocess.
    
    The trace path is NOT in os.environ during normal operation.
    It's built by build_model_comparison_env() and passed to AFL's child_env.
    The manager must accept and propagate it explicitly.
    """
    import tempfile
    from scripts.run_alfresco_bounded_feedback import ScorerLifecycleManager
    
    # Create a fake scorer that prints its NV_SCORER_TRACE_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        fake_scorer = tmpdir_path / "fake_scorer.py"
        fake_scorer.write_text(
            "import os, sys\n"
            "trace_path = os.environ.get('NV_SCORER_TRACE_PATH', 'MISSING')\n"
            "print(f'TRACE_PATH={trace_path}', flush=True)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        
        socket_path = tmpdir_path / "fake.sock"
        expected_trace = tmpdir_path / "expected_trace.jsonl"
        
        # After repair: __init__ accepts trace_path parameter
        manager = ScorerLifecycleManager(
            scorer_python=sys.executable,
            scorer_script=fake_scorer,
            socket_path=socket_path,
            backend="test_backend",
            timeout=1.0,
            trace_path=expected_trace,  # REPAIRED API
        )
        
        # Manager stores trace_path as instance attribute
        assert hasattr(manager, 'trace_path'), (
            "Manager must have trace_path attribute after repair"
        )
        assert manager.trace_path == expected_trace, (
            f"Expected trace_path={expected_trace}, got {manager.trace_path}"
        )
        
        # Start will fail because no socket, but we can still read stdout
        try:
            manager.start()
        except (TimeoutError, RuntimeError):
            pass  # Expected: no socket created
        
        # After repair, trace path MUST be in subprocess environment
        if manager.proc:
            stdout, _ = manager.proc.communicate(timeout=2.0)
            stdout_text = stdout if isinstance(stdout, str) else stdout.decode()
            
            # The repaired manager propagates trace_path to subprocess
            assert f"TRACE_PATH={expected_trace}" in stdout_text, (
                f"Expected NV_SCORER_TRACE_PATH={expected_trace} in subprocess, "
                f"but got: {stdout_text}"
            )
            
            manager.stop()


def test_scorer_lifecycle_omits_trace_path_when_none():
    """When trace_path=None, manager does not set NV_SCORER_TRACE_PATH."""
    import tempfile
    from scripts.run_alfresco_bounded_feedback import ScorerLifecycleManager
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        fake_scorer = tmpdir_path / "fake_scorer.py"
        fake_scorer.write_text(
            "import os, sys\n"
            "trace_path = os.environ.get('NV_SCORER_TRACE_PATH', 'MISSING')\n"
            "print(f'TRACE_PATH={trace_path}', flush=True)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        
        socket_path = tmpdir_path / "fake.sock"
        
        # No trace_path provided (None is the default)
        manager = ScorerLifecycleManager(
            scorer_python=sys.executable,
            scorer_script=fake_scorer,
            socket_path=socket_path,
            backend="test_backend",
            timeout=1.0,
            trace_path=None,
        )
        
        assert manager.trace_path is None, (
            "Manager trace_path should be None when not provided"
        )
        
        try:
            manager.start()
        except (TimeoutError, RuntimeError):
            pass
        
        if manager.proc:
            stdout, _ = manager.proc.communicate(timeout=2.0)
            stdout_text = stdout if isinstance(stdout, str) else stdout.decode()
            
            # When trace_path is None, NV_SCORER_TRACE_PATH should not be set
            assert "TRACE_PATH=MISSING" in stdout_text, (
                f"Expected NV_SCORER_TRACE_PATH to be unset when trace_path=None, "
                f"but got: {stdout_text}"
            )
            
            manager.stop()
