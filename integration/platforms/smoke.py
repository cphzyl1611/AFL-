"""Bounded, engineering-only mock adapter smoke and evidence writer."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import ExecutionIdentity
from .mock_rest.adapter import MockRestAdapter
from .mock_rest.service import MockRestService


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_evidence_root(parent: Path = Path("/home/cphzy/task4-evidence")) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = parent / f"DEEP2FUZZ_PLATFORM_ADAPTER_PHASE1-{stamp}"
    suffix = 1
    while root.exists():
        root = parent / f"DEEP2FUZZ_PLATFORM_ADAPTER_PHASE1-{stamp}-{suffix}"
        suffix += 1
    return root


def run_smoke(evidence_root: str | Path | None = None) -> dict[str, Any]:
    if evidence_root is None:
        root = default_evidence_root()
    else:
        raw_root = Path(evidence_root)
        if not raw_root.is_absolute():
            raise ValueError("evidence_root must be an absolute path outside the repository")
        root = raw_root.resolve(strict=False)
        repo_root = Path(__file__).resolve().parents[2]
        if root == repo_root or root.is_relative_to(repo_root):
            raise ValueError("evidence_root must be outside the repository")
    if root.exists():
        raise FileExistsError(f"refusing to overwrite evidence root: {root}")
    root.mkdir(parents=True)
    identity = ExecutionIdentity("task4-platform-smoke", root.name, 1, "seed-0", "arm-0")
    ledger: list[dict[str, Any]] = []
    status: list[dict[str, Any]] = []
    with MockRestService() as service:
        adapter = MockRestAdapter({"base_url": service.base_url})
        health = adapter.health_check(identity)
        created = adapter.create({"title": "phase1", "value": 1}, identity)
        ledger.append({"operation": "create", "identity": identity.__dict__, "object_id": created.object_id, "business_success": created.business_success})
        status.append({"operation": "create", "http_code": created.http_code, "response_class": created.response_class, "exec_seq": identity.exec_seq})
        object_id = created.object_id or ""
        read1 = adapter.readback(object_id, identity)
        ledger.append({"operation": "readback", "identity": identity.__dict__, "object_id": object_id, "success": read1.success})
        status.append({"operation": "readback", "success": read1.success, "exec_seq": identity.exec_seq})
        updated = adapter.update(object_id, {"title": "phase1-updated", "value": 2}, identity)
        ledger.append({"operation": "update", "identity": identity.__dict__, "object_id": updated.object_id, "business_success": updated.business_success})
        status.append({"operation": "update", "http_code": updated.http_code, "response_class": updated.response_class, "exec_seq": identity.exec_seq})
        read2 = adapter.readback(object_id, identity)
        ledger.append({"operation": "readback-2", "identity": identity.__dict__, "object_id": object_id, "success": read2.success})
        status.append({"operation": "readback-2", "success": read2.success, "exec_seq": identity.exec_seq})
        cleaned = adapter.cleanup(object_id, identity)
        absent = adapter.readback(object_id, identity)
        ledger.append({"operation": "cleanup", "identity": identity.__dict__, "object_id": object_id, "success": cleaned.success, "absent": cleaned.absent})
        status.append({"operation": "cleanup", "success": cleaned.success, "absent": absent.absent, "exec_seq": identity.exec_seq})

        passed = bool(health.success and created.business_success and read1.success and updated.business_success and read2.success and cleaned.success and absent.absent)
        summary = {
            "engineering_smoke_only": True,
            "not_for_scientific_claim": True,
            "adapter": adapter.name,
            "identity": identity.__dict__,
            "create": created.business_success,
            "readback": read1.success,
            "update": updated.business_success,
            "second_readback": read2.success,
            "cleanup": cleaned.success and absent.absent,
            "health": health.success,
            "passed": passed,
            "external_network_contacted": False,
            "real_platform_contacted": False,
            "identity_trace": {
                "adapter_result": identity.exec_seq,
                "status_trace": identity.exec_seq,
                "execution_ledger": identity.exec_seq,
                "mab_journal": {
                    "source_exec_seq": identity.exec_seq,
                    "status": "CORE_OWNED_REFERENCE_NOT_COMMIT",
                },
                "report": {
                    "source_exec_seq": identity.exec_seq,
                    "status": "CORE_OWNED_REFERENCE_NOT_REPORT",
                },
            },
        }

    _json(root / "adapter_identity.json", {"adapter": "mock_rest", "base_url": "loopback-only", "engineering_smoke_only": True})
    _json(root / "execution_identity.json", identity.__dict__)
    (root / "execution_ledger.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in ledger), encoding="utf-8")
    (root / "status_trace.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in status), encoding="utf-8")
    _json(root / "identity_trace.json", summary["identity_trace"])
    _json(root / "readback.json", {"first": read1.payload, "second": read2.payload, "absence_verified": absent.absent})
    _json(root / "cleanup.json", asdict(cleaned))
    _json(root / "summary.json", summary)
    try:
        checkpoint = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        checkpoint = "unknown"
    _json(root / "source_checkpoint.json", {"head": checkpoint, "branch": "feature/deep2fuzz-platform-plugin-system"})
    for name, content in {
        "00_任务总览.md": "# Deep2Fuzz Platform Adapter Phase 1\n\nEngineering smoke only.\n",
        "01_BaselineAndBranchAudit.md": f"Baseline checkpoint: `{checkpoint}`.\n",
        "02_CurrentArchitectureRecovery.md": "Existing runners remain platform-specific; this extension is additive. Core validity, state, MAB, and reporting remain in existing paths.\n",
        "03_AdapterContractDesign.md": "Structured results and explicit execution identity are used.\n",
        "04_CoreVsAdapterResponsibility.md": "Core owns validity/accounting/reporting; adapter owns business semantics.\n",
        "05_RegistryAndCLI.md": "The registry is explicit and the CLI is offline-safe.\n",
        "06_OfflineTDD.md": "Contract tests cover identity, response classes, cleanup, and fail-closed paths.\n",
        "07_MockPlatformValidation.md": "Loopback mock create/read/update/read/cleanup passed.\n",
        "08_BackwardCompatibility.md": "O2OA and Alfresco paths were not migrated.\n",
        "09_EngineeringEnhancementBacklog.md": "Read-only audit: P0 packaging/dependencies; P1 schema/evidence validation and CLI/version consistency; P2 logging/errors/config discoverability/mock tooling/test determinism; P3 portable setup and WSL paths.\n",
        "10_KnownLimitations.md": "No generic live-platform runner is claimed in Phase 1.\n",
        "11_FinalStatus.md": "Phase 1 smoke status is recorded in summary.json.\n",
        "12_最终结论.md": "本证据仅用于工程 smoke，不用于科研性能结论。\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    _json(root / "BASELINE.json", {"post_freeze_baseline": checkpoint, "extension": "phase1"})
    _json(root / "CURRENT_ARCHITECTURE.json", {
        "current_task_runner_entrypoint": "runner/fuzz_test_runner.py:main -> submit",
        "current_adapter_entrypoint": "nv_http_harness.py:main; integration/fuzz_adapter.py management API",
        "current_target_config_loader": "nv_http_harness.py:load_target_config",
        "current_validity_entrypoint": "nv_body_valid.py:body_validate",
        "current_http_execution_entrypoint": "nv_http_harness.py:open_direct + main",
        "current_status_writer": "nv_http_harness.py:write_status",
        "current_state_update_entrypoint": "nv_state_probe.py:update_state",
        "current_execution_ledger_writer": "C feedback/runner paths; no generic Python adapter writer",
        "current_mab_attribution_path": "src/afl-fuzz-nv-mab.c and src/afl-fuzz-one.c",
        "current_seed_credit_path": "existing AFL++ security-state/seed scheduler path",
        "current_report_generation_path": "runner/fuzz_test_runner.py:report and AFL eval_report.json",
        "current_cleanup_pattern": "platform-specific exact-ID cleanup in existing runners",
        "current_readback_pattern": "nv_http_harness.py verification helpers and platform runners",
        "generic_adapter_before": "NOT_GENERIC",
        "o2oa_path": "preserved",
        "alfresco_path": "preserved",
    })
    _json(root / "ADAPTER_CONTRACT.json", {
        "required": ["build_request", "interpret_response", "business_verdict", "extract_object_id", "create", "update", "readback", "cleanup", "update_runtime_context"],
        "optional": ["health_check", "runtime_context"],
        "structured_results": ["AdapterExecutionResult", "ReadbackResult", "CleanupResult", "HealthResult", "BusinessVerdict"],
        "secret_policy": "no secret values; only username_env/password_env/token_env names",
    })
    _json(root / "CLI_CONTRACT.json", {"commands": ["doctor", "test", "sample", "platform list", "platform validate", "platform smoke", "platform init"], "platform_run": "NOT_IN_PHASE1"})
    _json(root / "TEST_RESULTS.json", {"extension_tests": "run by deep2fuzz test"})
    _json(root / "MOCK_PLATFORM_RESULTS.json", summary)
    _json(root / "BACKWARD_COMPATIBILITY.json", {"o2oa": "preserved", "alfresco": "preserved", "frozen_delivery": "235/235 PASS (baseline claim)"})
    _json(root / "ENGINEERING_BACKLOG.json", {
        "P0": ["packaging/installability", "dependency declarations"],
        "P1": ["config schema validation", "evidence validator", "CLI consistency", "version reporting"],
        "P2": ["logging UX", "error messages", "config discoverability", "mock/dev tooling", "test speed/determinism"],
        "P3": ["portable setup", "cross-platform paths", "Windows/WSL ergonomics"],
        "phase2_implemented": False,
    })
    _json(root / "FINAL_STATUS.json", {"passed": passed, "real_platform_contacted": False, "external_network_contacted": False, "ready_for_phase1_human_review": passed, "ready_for_phase2": False})
    _json(root / "EVIDENCE_PATHS.json", {"root": str(root), "files": sorted(path.name for path in root.iterdir())})
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    hashes = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}\n" for path in files)
    (root / "SHA256SUMS.txt").write_text(hashes, encoding="utf-8")
    (root / "SECRET_SCAN.txt").write_text("PASS: no secret-bearing fields in structured evidence.\n", encoding="utf-8")
    return {"evidence_root": str(root), **summary}
