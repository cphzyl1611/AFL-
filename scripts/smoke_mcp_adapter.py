#!/usr/bin/env python3
"""Smoke test for the local MCP adapter prototype."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integration import mcp_adapter  # noqa: E402


class SmokeError(RuntimeError):
    pass


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def call(tool: str, arguments: dict | None = None) -> dict:
    return mcp_adapter.handle_request({"tool": tool, "arguments": arguments or {}})


def run_smoke() -> None:
    capabilities = call("get_capabilities")
    expect(capabilities.get("status") == "ok", "get_capabilities failed")
    tool_names = {item.get("name") for item in capabilities.get("tools", []) if isinstance(item, dict)}
    expect("score_alfresco_ae_v1_sample" in tool_names, "capabilities missing scoring tool")

    metadata = call(
        "score_alfresco_ae_v1_sample",
        {
            "scenario": "metadata_update",
            "payload": {
                "name": "official_doc.txt",
                "properties": {
                    "cm:title": "标题",
                    "cm:description": "说明",
                },
            },
        },
    )
    expect(metadata.get("status") == "ok", "metadata score failed")
    expect("score" in metadata, "metadata score missing score")
    expect(metadata.get("decision") in {"pass", "reject"}, "metadata score decision mismatch")
    expect(metadata.get("model_type") == "ae_like_statistical_baseline", "metadata model_type mismatch")

    content = call("score_alfresco_ae_v1_sample", {"scenario": "content_update", "content": "正文内容"})
    expect(content.get("status") == "ok", "content score failed")
    expect("score" in content and content.get("decision") in {"pass", "reject"}, "content score invalid")

    upload = call(
        "score_alfresco_ae_v1_sample",
        {
            "scenario": "multipart_upload",
            "filename": "official_doc.txt",
            "fields": {
                "nodeType": "cm:content",
                "autoRename": "true",
            },
            "content": "上传文件内容",
        },
    )
    expect(upload.get("status") == "ok", "multipart score failed")
    expect("score" in upload and upload.get("decision") in {"pass", "reject"}, "multipart score invalid")

    reports = call("list_reports")
    expect(reports.get("status") == "ok", "list_reports failed")
    report_paths = {item.get("path") for item in reports.get("reports", []) if isinstance(item, dict)}
    expect("docs/review/Alfresco_AE_v1轻量API接入报告.md" in report_paths, "list_reports missing API report")

    evidence = call("query_evidence", {"path": "out/alfresco_ae_v1_service_compare/summary.csv"})
    expect(evidence.get("status") == "ok", "query_evidence failed")
    expect(evidence.get("exists") is True, "query_evidence summary missing")
    expect("mode" in evidence.get("header", []), "query_evidence header missing mode")
    expect(int(evidence.get("row_count", 0)) >= 1, "query_evidence row_count invalid")

    bad_tool = call("run_shell", {"cmd": "date"})
    expect(bad_tool.get("status") == "reject", "non-whitelist tool was not rejected")

    bad_path = call("query_evidence", {"path": "/etc/passwd"})
    expect(bad_path.get("status") == "reject", "arbitrary evidence path was not rejected")


def main() -> int:
    try:
        run_smoke()
    except Exception as exc:  # noqa: BLE001 - CLI should report any failure.
        print(f"MCP_ADAPTER_SMOKE_FAIL: {exc}", file=sys.stderr)
        return 1
    print("MCP_ADAPTER_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
