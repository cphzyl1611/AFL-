"""P1.3-shaped provenance for the packaged offline sample runtime."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from deep2fuzz_config.validator import config_fingerprint_sha256
from deep2fuzz_provenance import (
    ADAPTER_CONTRACT_VERSIONS,
    EVIDENCE_SCHEMA_VERSION,
    PRODUCT_NAME,
    PROVENANCE_SCHEMA_VERSION,
    SCORER_CONTRACT_FILES,
    SCORER_CONTRACT_ID,
)
from deep2fuzz_version import __version__


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scorer_fingerprint(root: Path) -> str:
    records = []
    for relative in SCORER_CONTRACT_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("packaged scorer contract is unavailable")
        records.append({"path": relative, "sha256": _sha256(path)})
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_provenance(
    root: str | Path,
    *,
    config_snapshot: Mapping[str, Any],
    adapter: str,
    run_id: str,
    task_id: str,
    evidence_profile: str,
) -> dict[str, Any]:
    if adapter not in ADAPTER_CONTRACT_VERSIONS:
        raise ValueError("unsupported adapter identity")
    return {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "product": {"name": PRODUCT_NAME, "version": __version__},
        "source": {"git_commit": None, "git_tree": None, "dirty": False, "dirty_fingerprint_sha256": None},
        "config": {
            "schema_version": str(config_snapshot.get("schema_version", "")),
            "fingerprint_sha256": config_fingerprint_sha256(config_snapshot),
        },
        "platform": {"adapter": adapter, "adapter_contract_version": ADAPTER_CONTRACT_VERSIONS[adapter]},
        "scoring": {
            "contract_id": SCORER_CONTRACT_ID,
            "contract_files": list(SCORER_CONTRACT_FILES),
            "contract_fingerprint_sha256": _scorer_fingerprint(Path(root).resolve()),
        },
        "run": {
            "run_id": run_id,
            "task_id": task_id,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "evidence": {"profile": evidence_profile, "schema_version": EVIDENCE_SCHEMA_VERSION},
    }
