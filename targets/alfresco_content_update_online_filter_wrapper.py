#!/usr/bin/env python3
"""SE-fAnoGAN-ES-style online filter prototype for Alfresco content_update.

This wrapper is used by a representative AFL++ mutation-chain smoke. It reads
the AFL++ @@ input, applies rule / AE v1 / optional fAnoGAN candidate decisions,
and only sends accepted inputs to the local mock target classifier.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer  # noqa: E402
from model_stage.alfresco_fanogan_v1_candidate_scorer import (  # noqa: E402
    AlfrescoFanoganV1CandidateScorer,
)
from targets.alfresco_content_update_mock import classify_content  # noqa: E402


VALID_MODES = {"rule_only", "rule_ae", "rule_fanogan", "rule_ae_fanogan"}
_AE_SCORER: AlfrescoAEV1Scorer | None = None
_FANOGAN_SCORER: AlfrescoFanoganV1CandidateScorer | None = None


def read_input() -> bytes:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        return Path(sys.argv[1]).read_bytes()
    return sys.stdin.buffer.read()


def decode_for_scoring(data: bytes) -> str | bytes:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data


def get_ae_scorer() -> AlfrescoAEV1Scorer:
    global _AE_SCORER
    if _AE_SCORER is None:
        _AE_SCORER = AlfrescoAEV1Scorer()
    return _AE_SCORER


def get_fanogan_scorer() -> AlfrescoFanoganV1CandidateScorer:
    global _FANOGAN_SCORER
    if _FANOGAN_SCORER is None:
        _FANOGAN_SCORER = AlfrescoFanoganV1CandidateScorer()
    return _FANOGAN_SCORER


def append_filter_stats(record: dict[str, Any]) -> None:
    stats_path = os.environ.get("ONLINE_FILTER_STATS_PATH")
    if not stats_path:
        return
    with open(stats_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def score_ae(data: bytes) -> dict[str, Any]:
    return get_ae_scorer().score_text_content(decode_for_scoring(data))


def score_fanogan(data: bytes) -> dict[str, Any]:
    return get_fanogan_scorer().score_text_content(decode_for_scoring(data))


def evaluate(data: bytes, mode: str, fanogan_enabled: bool) -> dict[str, Any]:
    start = time.perf_counter()
    rule_pass, rule_reason = classify_content(data)
    ae_result: dict[str, Any] | None = None
    fanogan_result: dict[str, Any] | None = None
    reject_reason = ""
    final_pass = False
    sent_to_target = False
    target_valid: bool | None = None

    if not rule_pass:
        reject_reason = f"rule_{rule_reason}"
    else:
        final_pass = True

    if final_pass and mode in {"rule_ae", "rule_ae_fanogan"}:
        try:
            ae_result = score_ae(data)
            final_pass = bool(ae_result.get("pass"))
            if not final_pass:
                reject_reason = "ae_" + str(ae_result.get("reason", "reject"))
        except Exception as exc:  # noqa: BLE001 - online filter reject is controlled.
            final_pass = False
            ae_result = {"score": None, "decision": "reject", "pass": False, "reason": str(exc)}
            reject_reason = "ae_scoring_error"

    fanogan_should_run = fanogan_enabled and mode in {"rule_fanogan", "rule_ae_fanogan"}
    if final_pass and fanogan_should_run:
        try:
            fanogan_result = score_fanogan(data)
            final_pass = bool(fanogan_result.get("pass"))
            if not final_pass:
                reject_reason = "fanogan_" + str(fanogan_result.get("reason", "reject"))
        except Exception as exc:  # noqa: BLE001 - candidate failure must not crash AFL++.
            final_pass = False
            fanogan_result = {"score": None, "decision": "reject", "pass": False, "reason": str(exc)}
            reject_reason = "fanogan_scoring_error"

    if final_pass:
        sent_to_target = True
        target_valid, target_reason = classify_content(data)
        if not target_valid:
            reject_reason = "target_" + target_reason
            final_pass = False

    latency_ms = int((time.perf_counter() - start) * 1000)
    return {
        "mode": mode,
        "rule_pass": rule_pass,
        "ae_score": ae_result.get("score") if ae_result else None,
        "ae_decision": ae_result.get("decision") if ae_result else "not_run",
        "fanogan_score": fanogan_result.get("score") if fanogan_result else None,
        "fanogan_decision": fanogan_result.get("decision") if fanogan_result else "not_run",
        "final_decision": "pass" if final_pass else "reject",
        "sent_to_target": sent_to_target,
        "target_valid": target_valid,
        "reject_reason": reject_reason,
        "content_size": len(data),
        "latency_ms": latency_ms,
    }


def main() -> int:
    mode = os.environ.get("ONLINE_FILTER_MODE", "rule_ae").strip() or "rule_ae"
    if mode not in VALID_MODES:
        mode = "rule_ae"
    fanogan_enabled = os.environ.get("FANOGAN_ENABLED", "0").strip().lower() in {"1", "true", "yes", "y"}
    if mode in {"rule_fanogan", "rule_ae_fanogan"}:
        fanogan_enabled = True

    data = read_input()
    record = evaluate(data, mode, fanogan_enabled)
    append_filter_stats(record)
    print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
