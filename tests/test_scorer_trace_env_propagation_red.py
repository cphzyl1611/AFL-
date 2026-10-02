"""RED test: scorer receives NV_SCORER_TRACE_PATH from runner environment."""
import subprocess
import sys
from pathlib import Path


def test_scorer_lifecycle_propagates_trace_path():
    """ScorerLifecycleManager.start() must propagate NV_SCORER_TRACE_PATH."""
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
        
        # Inject NV_SCORER_TRACE_PATH into the environment that the manager
        # SHOULD propagate to the subprocess
        import os
        original_env = dict(os.environ)
        try:
            os.environ["NV_SCORER_TRACE_PATH"] = str(expected_trace)
            
            manager = ScorerLifecycleManager(
                scorer_python=sys.executable,
                scorer_script=fake_scorer,
                socket_path=socket_path,
                backend="test_backend",
                timeout=1.0,
            )
            
            # Start will fail because no socket, but we can still read stdout
            try:
                manager.start()
            except (TimeoutError, RuntimeError):
                pass  # Expected: no socket created
            
            # Read what the scorer printed
            if manager.proc:
                stdout, _ = manager.proc.communicate(timeout=2.0)
                stdout_text = stdout if isinstance(stdout, str) else stdout.decode()
                
                # The trace path MUST be present in the subprocess environment
                assert f"TRACE_PATH={expected_trace}" in stdout_text, (
                    f"Expected NV_SCORER_TRACE_PATH={expected_trace} in subprocess, "
                    f"but got: {stdout_text}"
                )
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            if manager.proc:
                manager.stop()
