import py_compile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AlfrescoAEV1ThresholdSweepTest(unittest.TestCase):
    def test_threshold_sweep_script_compiles(self) -> None:
        py_compile.compile(
            str(REPO_ROOT / "scripts/run_alfresco_ae_v1_threshold_sweep.py"),
            doraise=True,
        )


if __name__ == "__main__":
    unittest.main()
