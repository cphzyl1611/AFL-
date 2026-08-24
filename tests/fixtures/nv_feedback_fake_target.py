#!/usr/bin/env python3
"""TEST FIXTURE ONLY.

NO NETWORK.
NOT ALFRESCO.
NOT REAL-SERVICE VERIFICATION.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nv_http_body_adapter import HttpBodyAdapterError, extract_http_body
from nv_body_valid import body_validate
from nv_http_harness import write_status


def main() -> int:
    testcase = sys.stdin.buffer.read()
    try:
        body = extract_http_body(testcase)
    except HttpBodyAdapterError as exc:
        print(f"representation reject: {exc}", file=sys.stderr)
        return 2

    validation = body_validate(
        endpoint_name="metadata_update",
        raw_body=body,
        rules_path=os.environ.get("NV_BODY_RULES", ""),
        score_endpoint=None,
        score_threshold=None,
    )
    if not validation["ok"]:
        print(f"body reject: {validation['reason']}", file=sys.stderr)
        return 3

    write_status(
        method="PUT",
        path="/offline/fake-target",
        http_code=204,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
