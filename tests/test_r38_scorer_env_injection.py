"""R38 STEP 8: RED test for scorer env var injection.

Test that ScorerLifecycleManager injects required env vars for sefanogan_es_reference backend.
"""

import tempfile
import unittest
from pathlib import Path

# Import from parent directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.run_alfresco_bounded_feedback import ScorerLifecycleManager


class ScorerEnvVarInjectionTest(unittest.TestCase):
    """RED test: Scorer lifecycle must inject SE reference artifact env vars."""

    def test_sefanogan_es_reference_backend_receives_checkpoint_and_meta_env_vars(self):
        """
        RED TEST for R38 root cause: ENV_VAR_NOT_PROVIDED.

        ScorerLifecycleManager.start() must inject these env vars when
        backend='sefanogan_es_reference':
          - SEFANOGAN_REFERENCE_CHECKPOINT (path to .pt model file)
          - SEFANOGAN_REFERENCE_META_PATH (path to meta.json)

        Without these, the scorer subprocess exits immediately with ValueError
        at line 37 of nv_valid_server_real.py, preventing socket creation.
        """
        repo_root = Path(__file__).parent.parent
        scorer_python = "/home/dministrator/miniconda3/envs/aflpp-se-calib-pip/bin/python3"
        scorer_script = repo_root / "model_stage" / "nv_valid_server_real.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = Path(tmpdir) / "test_scorer.sock"
            trace_path = Path(tmpdir) / "test_trace.jsonl"

            manager = ScorerLifecycleManager(
                scorer_python=scorer_python,
                scorer_script=scorer_script,
                socket_path=socket_path,
                backend="sefanogan_es_reference",
                timeout=5.0,
                trace_path=trace_path,
            )

            # RED: This should fail because env vars are not injected
            try:
                manager.start()

                # If we reach here, scorer started successfully
                self.assertTrue(
                    socket_path.exists(),
                    "Socket must exist after successful scorer startup"
                )

                # Clean shutdown
                manager.stop()

            except (RuntimeError, TimeoutError) as exc:
                # Expected to fail in RED state
                error_msg = str(exc)

                # Fail the test with clear diagnostic
                self.fail(
                    f"RED TEST CONFIRMED: Scorer startup failed as expected.\n"
                    f"Error: {error_msg}\n\n"
                    f"ROOT CAUSE: ScorerLifecycleManager.start() does not inject:\n"
                    f"  - SEFANOGAN_REFERENCE_CHECKPOINT\n"
                    f"  - SEFANOGAN_REFERENCE_META_PATH\n\n"
                    f"The scorer subprocess exits with ValueError at line 37 of\n"
                    f"nv_valid_server_real.py before creating the socket.\n\n"
                    f"REPAIR REQUIRED: Inject these env vars in start() method."
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
