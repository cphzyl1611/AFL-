#!/usr/bin/env python3
"""MCP-like adapter prototype for the fuzzing module.

This module intentionally does not depend on an external MCP SDK. It exposes a
small whitelist of local tools through Python functions and a JSON stdin/stdout
CLI shape. It does not execute shell commands, does not read arbitrary paths,
and does not contact Alfresco or external services.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer  # noqa: E402


TOOL_GET_CAPABILITIES = "get_capabilities"
TOOL_SCORE_ALFRESCO_AE_V1 = "score_alfresco_ae_v1_sample"
TOOL_LIST_REPORTS = "list_reports"
TOOL_QUERY_EVIDENCE = "query_evidence"

ALLOWED_TOOLS = {
    TOOL_GET_CAPABILITIES,
    TOOL_SCORE_ALFRESCO_AE_V1,
    TOOL_LIST_REPORTS,
    TOOL_QUERY_EVIDENCE,
}

ALLOWED_SCENARIOS = [
    "metadata_update",
    "content_update",
    "multipart_upload",
]

REPORT_WHITELIST = [
    Path("docs/review/Alfresco_AE_v1二阶段有效性判定验证报告.md"),
    Path("docs/review/Alfresco_AE_v1阈值校准与误判分析报告.md"),
    Path("docs/review/Alfresco_AE_v1_score_service联调报告.md"),
    Path("docs/review/Alfresco_AE_v1轻量API接入报告.md"),
    Path("docs/review/O2OA到Alfresco主验证平台迁移说明.md"),
]

EVIDENCE_WHITELIST = [
    Path("out/alfresco_ae_v1_score_compare/summary.csv"),
    Path("out/alfresco_ae_v1_threshold_sweep/summary.csv"),
    Path("out/alfresco_ae_v1_service_compare/summary.csv"),
    Path("out/alfresco_content_update_manual_latest/summary.csv"),
    Path("out/alfresco_multipart_upload_manual_latest/summary.csv"),
]

_SCORER: AlfrescoAEV1Scorer | None = None


def get_scorer() -> AlfrescoAEV1Scorer:
    global _SCORER
    if _SCORER is None:
        _SCORER = AlfrescoAEV1Scorer()
    return _SCORER


def ok(tool: str, **payload: Any) -> dict[str, Any]:
    body = {"status": "ok", "tool": tool}
    body.update(payload)
    return body


def reject(tool: str, message: str, **payload: Any) -> dict[str, Any]:
    body = {"status": "reject", "tool": tool, "error": message}
    body.update(payload)
    return body


def normalize_whitelist_path(path: str) -> Path | None:
    if not isinstance(path, str) or not path:
        return None
    normalized = Path(path)
    if normalized.is_absolute():
        return None
    for allowed in EVIDENCE_WHITELIST:
        if normalized.as_posix() == allowed.as_posix():
            return allowed
    return None


def get_capabilities(_: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok(
        TOOL_GET_CAPABILITIES,
        tools=[
            {
                "name": TOOL_GET_CAPABILITIES,
                "description": "Return MCP adapter prototype capabilities.",
            },
            {
                "name": TOOL_SCORE_ALFRESCO_AE_V1,
                "description": "Score one Alfresco metadata/content/multipart sample with AE v1.",
                "scenarios": ALLOWED_SCENARIOS,
                "model_type": "ae_like_statistical_baseline",
            },
            {
                "name": TOOL_LIST_REPORTS,
                "description": "List fixed review report whitelist.",
            },
            {
                "name": TOOL_QUERY_EVIDENCE,
                "description": "Read header and first row from fixed summary evidence whitelist.",
            },
        ],
        boundaries=[
            "MCP adapter prototype only; not a full MCP Server.",
            "No arbitrary shell execution.",
            "No arbitrary path reads.",
            "Does not access Alfresco service.",
            "Not GAN/fAnoGAN or full SE-fAnoGAN.",
        ],
    )


def score_alfresco_ae_v1_sample(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return reject(TOOL_SCORE_ALFRESCO_AE_V1, "arguments must be an object")
    scenario = str(arguments.get("scenario", "")).strip()
    if scenario not in ALLOWED_SCENARIOS:
        return reject(TOOL_SCORE_ALFRESCO_AE_V1, "unsupported Alfresco AE v1 scenario", scenario=scenario)
    try:
        result = get_scorer().score_sample(arguments)
    except ValueError as exc:
        return reject(TOOL_SCORE_ALFRESCO_AE_V1, str(exc), scenario=scenario, decision="reject")
    return ok(
        TOOL_SCORE_ALFRESCO_AE_V1,
        scenario=scenario,
        score=result["score"],
        passed=bool(result["pass"]),
        decision=result["decision"],
        reason=result["reason"],
        threshold_high=result["threshold_high"],
        model_name=result["model_name"],
        model_type=result["model_type"],
    )


def list_reports(_: dict[str, Any] | None = None) -> dict[str, Any]:
    reports = []
    for rel_path in REPORT_WHITELIST:
        full = REPO_ROOT / rel_path
        reports.append({"path": rel_path.as_posix(), "exists": full.is_file()})
    return ok(TOOL_LIST_REPORTS, reports=reports)


def query_evidence(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return reject(TOOL_QUERY_EVIDENCE, "arguments must be an object")
    requested = arguments.get("path")
    allowed = normalize_whitelist_path(str(requested) if isinstance(requested, str) else "")
    if allowed is None:
        return reject(TOOL_QUERY_EVIDENCE, "evidence path is not in whitelist")

    full = REPO_ROOT / allowed
    if not full.is_file():
        return ok(TOOL_QUERY_EVIDENCE, path=allowed.as_posix(), exists=False, header=[], first_data_row=[], row_count=0)

    with full.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    header = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []
    return ok(
        TOOL_QUERY_EVIDENCE,
        path=allowed.as_posix(),
        exists=True,
        header=header,
        first_data_row=data_rows[0] if data_rows else [],
        row_count=len(data_rows),
    )


def dispatch_tool(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if tool not in ALLOWED_TOOLS:
        return reject(tool or "__missing__", "tool is not in whitelist")
    if tool == TOOL_GET_CAPABILITIES:
        return get_capabilities(arguments)
    if tool == TOOL_SCORE_ALFRESCO_AE_V1:
        return score_alfresco_ae_v1_sample(arguments)
    if tool == TOOL_LIST_REPORTS:
        return list_reports(arguments)
    if tool == TOOL_QUERY_EVIDENCE:
        return query_evidence(arguments)
    return reject(tool, "unhandled tool")


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        return reject("__request__", "request must be an object")
    tool = request.get("tool", request.get("name"))
    if not isinstance(tool, str) or not tool.strip():
        return reject("__request__", "tool is required")
    arguments = request.get("arguments", {})
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return reject(tool, "arguments must be an object")
    return dispatch_tool(tool.strip(), arguments)


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        response = reject("__request__", f"invalid JSON request: {exc}")
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 1

    response = handle_request(request)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
