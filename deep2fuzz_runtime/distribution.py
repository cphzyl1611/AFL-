"""Narrow adapters for source-identity limits in a wheel installation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _source_record(run_root: str | Path) -> dict[str, Any] | None:
    root = Path(run_root)
    for name in ("sample_eval_report.json", "eval_report.json"):
        try:
            report = json.loads((root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue
        if isinstance(report, dict):
            provenance = report.get("provenance")
            source = provenance.get("source") if isinstance(provenance, dict) else None
            if isinstance(source, dict):
                return source
    return None


def verify_distribution_evidence(run_root: str | Path):
    """Run the existing verifier with its scorer rooted in packaged assets."""
    import deep2fuzz_evidence.verifier as verifier

    module_file = verifier.__file__
    assets = Path(__file__).resolve().parent / "assets"
    verifier.__file__ = str(assets / "deep2fuzz_evidence" / "verifier.py")
    try:
        result = verifier.verify_evidence(run_root)
    finally:
        verifier.__file__ = module_file

    source = _source_record(run_root)
    if source and source.get("git_commit") is None and source.get("git_tree") is None:
        if source.get("dirty") is False and source.get("dirty_fingerprint_sha256") is None:
            for check in result.checks:
                if check.name in {
                    "SOURCE_COMMIT_MISMATCH",
                    "SOURCE_TREE_MISMATCH",
                    "SOURCE_DIRTY_FINGERPRINT_MISMATCH",
                }:
                    check.status = "NOT_APPLICABLE"
                    check.message = "Git identity is unavailable in a wheel; recorded source identity is declared-only"
                    check.verification_level = "DECLARED_ONLY"
    return result
