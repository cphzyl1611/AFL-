#!/usr/bin/env python3
"""O2OA Phase 1 scoped oracle: parser + rule only (offline, no promotion).

This module wraps the existing O2OA v2 input adapter so the terminal-layer
flow can be observed without executing any downstream oracle:

  LAYER_TRANSPORT:
      parser FAIL -> terminal=TRANSPORT, scoped_label=TRANSPORT_MALFORMED
      parser PASS -> continue
  LAYER_RULE:
      rule FAIL   -> terminal=RULE, scoped_label=RULE_CONFIRMED_INVALID
      rule PASS   -> terminal=RULE, scoped_label=TECHNICALLY_VALID_CANDIDATE

The API-contract, semantic, and security oracles are deliberately NOT executed
in Phase 1: their results are recorded as NOT_EXECUTED and never influence the
scoped label.

Reuse policy: the parser hooks, rule validator, contract loader, and hashing
all come from `model_stage/o2oa_v2_input.py`. No second set of rules is copied
here. Fail-closed: any control failure (contract/rule artifact integrity,
endpoint mismatch, feature-vector failure) yields terminal=CONTROL_FAILURE and
scoped_label=UNKNOWN.
"""

from __future__ import annotations

import json
from typing import Any

from model_stage.o2oa_v2_input import (
    O2OAV2InputError,
    _DuplicateKey,
    _load_contract,
    _reject_duplicates,
    _reject_nonfinite,
    _sha256,
    _validate_rules,
    prepare_o2oa_v2_input,
)


# Terminal-layer and scoped-label constants (Phase 1 reachable subset).
TRANSPORT_MALFORMED = "TRANSPORT_MALFORMED"
RULE_CONFIRMED_INVALID = "RULE_CONFIRMED_INVALID"
TECHNICALLY_VALID_CANDIDATE = "TECHNICALLY_VALID_CANDIDATE"
UNKNOWN = "UNKNOWN"

NOT_EXECUTED = "NOT_EXECUTED"
PASS = "PASS"
FAIL = "FAIL"

TERMINAL_TRANSPORT = "TRANSPORT"
TERMINAL_RULE = "RULE"
TERMINAL_CONTROL_FAILURE = "CONTROL_FAILURE"


def _base_result(endpoint_name: str) -> dict[str, Any]:
    return {
        "terminal_layer": None,
        "scoped_label": None,
        "parser_result": NOT_EXECUTED,
        "rule_result": NOT_EXECUTED,
        "api_contract_result": NOT_EXECUTED,
        "semantic_result": NOT_EXECUTED,
        "security_result": NOT_EXECUTED,
        "raw_body_sha256": None,
        "canonical_json_sha256": None,
        "canonical_json_bytes": None,
        "endpoint_name": endpoint_name,
        "contract_id": None,
    }


def _transport_malformed(result: dict[str, Any], raw_body: Any) -> dict[str, Any]:
    result["terminal_layer"] = TERMINAL_TRANSPORT
    result["scoped_label"] = TRANSPORT_MALFORMED
    result["parser_result"] = FAIL
    if isinstance(raw_body, bytes):
        result["raw_body_sha256"] = _sha256(raw_body)
    return result


def _rule_invalid(result: dict[str, Any], raw_body: bytes) -> dict[str, Any]:
    result["terminal_layer"] = TERMINAL_RULE
    result["scoped_label"] = RULE_CONFIRMED_INVALID
    result["parser_result"] = PASS
    result["rule_result"] = FAIL
    result["raw_body_sha256"] = _sha256(raw_body)
    return result


def _control_failure(result: dict[str, Any], contract_id: str | None = None) -> dict[str, Any]:
    result["terminal_layer"] = TERMINAL_CONTROL_FAILURE
    result["scoped_label"] = UNKNOWN
    result["contract_id"] = contract_id
    return result


def evaluate_phase1_scoped(raw_body: Any, endpoint_name: str = "cms_doc_list") -> dict[str, Any]:
    """Evaluate the O2OA v2 cms_doc_list body through parser + rule only.

    Returns a result dict whose `terminal_layer` and `scoped_label` encode the
    deepest layer reached. Downstream oracles are never executed.
    """
    result = _base_result(endpoint_name)

    # Control check: bind the contract and its artifacts before evaluating.
    try:
        contract = _load_contract()
    except (O2OAV2InputError, OSError):
        # O2OAV2InputError = semantic/identity failure; OSError = a bound
        # artifact (contract/parser/extractor/rule) could not be read. Both
        # are control failures and must fail closed to UNKNOWN, never a bare
        # exception. (The loader still leaks OSError for unreadable bound
        # artifacts; this boundary maps it deterministically.)
        return _control_failure(result)

    result["contract_id"] = contract["contract_id"]
    if endpoint_name != contract.get("endpoint_alias", "cms_doc_list"):
        # Oracle is scoped to a single contract endpoint; anything else is
        # out of scope and fails closed.
        return _control_failure(result, contract_id=contract["contract_id"])

    # LAYER_TRANSPORT: strict UTF-8 + strict JSON parse (reused hooks).
    if not isinstance(raw_body, bytes) or not raw_body:
        return _transport_malformed(result, raw_body)
    try:
        text = raw_body.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, _DuplicateKey):
        return _transport_malformed(result, raw_body)

    # LAYER_RULE: deterministic rule validation (reused, not re-implemented).
    try:
        _validate_rules(parsed)
    except O2OAV2InputError:
        return _rule_invalid(result, raw_body)

    # Parser PASS + rule PASS -> TECHNICALLY_VALID_CANDIDATE. Reuse the full
    # adapter so canonical bytes, hashes, and feature vector stay contract-exact.
    try:
        prepared = prepare_o2oa_v2_input(raw_body)
    except (O2OAV2InputError, OSError):
        # Should be unreachable after the checks above; fail closed on any
        # downstream control/feature failure (including a bound artifact that
        # became unreadable between the contract bind and full preparation).
        return _control_failure(result, contract_id=contract["contract_id"])

    result["terminal_layer"] = TERMINAL_RULE
    result["scoped_label"] = TECHNICALLY_VALID_CANDIDATE
    result["parser_result"] = PASS
    result["rule_result"] = PASS
    result["raw_body_sha256"] = prepared.raw_body_sha256
    result["canonical_json_sha256"] = prepared.canonical_json_sha256
    result["canonical_json_bytes"] = prepared.canonical_json_bytes
    result["contract_id"] = prepared.contract_id
    return result
