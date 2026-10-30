"""Invoke the unchanged delivery runner with explicit wheel provenance."""
from __future__ import annotations

import runpy
from pathlib import Path


def main() -> int:
    root = Path(__import__("os").environ["ROOT"])
    runpy.run_path(str(root / "scripts" / "run_task4_sample.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
