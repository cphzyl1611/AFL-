#!/usr/bin/env python3
"""O2OA Phase 1 scoped oracle tests (RED phase).

Verifies the terminal-layer flow:
  LAYER_TRANSPORT: parser FAIL -> terminal=TRANSPORT, TRANSPORT_MALFORMED
                   parser PASS -> continue
  LAYER_RULE:      rule FAIL   -> terminal=RULE, RULE_CONFIRMED_INVALID
                   rule PASS   -> terminal=RULE, TECHNICALLY_VALID_CANDIDATE

Phase 1 executes ONLY the parser and rule oracles. API contract, semantic,
and security oracles are NOT_EXECUTED and must never influence the label.
"""

import json

import pytest

from scripts.o2oa_phase1_scoped_oracle import evaluate_phase1_scoped


# ---------------------------------------------------------------------------
# LAYER_TRANSPORT — parser FAIL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw_body", [
    b"\xff\xfe invalid UTF-8",
    b"",
])
def test_parser_fail_is_transport_malformed(raw_body):
    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "TRANSPORT"
    assert result["scoped_label"] == "TRANSPORT_MALFORMED"
    assert result["parser_result"] == "FAIL"
    assert result["rule_result"] == "NOT_EXECUTED"


def test_parser_rejects_duplicate_keys():
    raw_body = b'{"key":"a","key":"b","docStatusList":[],"categoryIdList":[]}'

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "TRANSPORT"
    assert result["scoped_label"] == "TRANSPORT_MALFORMED"
    assert result["parser_result"] == "FAIL"
    assert result["rule_result"] == "NOT_EXECUTED"


@pytest.mark.parametrize("token", [b"NaN", b"Infinity", b"-Infinity"])
def test_parser_rejects_nonfinite_constants(token):
    raw_body = b'{"docStatusList":[],"categoryIdList":[],"key":' + token + b"}"

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "TRANSPORT"
    assert result["scoped_label"] == "TRANSPORT_MALFORMED"
    assert result["parser_result"] == "FAIL"
    assert result["rule_result"] == "NOT_EXECUTED"


def test_parser_rejects_non_bytes_input():
    result = evaluate_phase1_scoped("not bytes", endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "TRANSPORT"
    assert result["scoped_label"] == "TRANSPORT_MALFORMED"
    assert result["parser_result"] == "FAIL"


# ---------------------------------------------------------------------------
# LAYER_RULE — parser PASS + rule FAIL
# ---------------------------------------------------------------------------

def test_rule_fail_missing_required_field():
    raw_body = b'{"docStatusList":[],"categoryIdList":[]}'  # missing "key"

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "RULE"
    assert result["scoped_label"] == "RULE_CONFIRMED_INVALID"
    assert result["parser_result"] == "PASS"
    assert result["rule_result"] == "FAIL"


def test_rule_fail_oversized_array():
    raw_body = json.dumps({
        "docStatusList": list(range(21)),  # maxItems=20
        "categoryIdList": [],
        "key": "test",
    }).encode("utf-8")

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "RULE"
    assert result["scoped_label"] == "RULE_CONFIRMED_INVALID"
    assert result["parser_result"] == "PASS"
    assert result["rule_result"] == "FAIL"


def test_rule_fail_oversized_string():
    raw_body = json.dumps({
        "docStatusList": [],
        "categoryIdList": [],
        "key": "x" * 257,  # maxLength=256
    }).encode("utf-8")

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "RULE"
    assert result["scoped_label"] == "RULE_CONFIRMED_INVALID"
    assert result["parser_result"] == "PASS"
    assert result["rule_result"] == "FAIL"


def test_rule_fail_wrong_type():
    raw_body = b'{"docStatusList":"not_an_array","categoryIdList":[],"key":"test"}'

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "RULE"
    assert result["scoped_label"] == "RULE_CONFIRMED_INVALID"
    assert result["parser_result"] == "PASS"
    assert result["rule_result"] == "FAIL"


def test_rule_fail_exceeded_depth():
    deep_obj = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": 1}}}}}}}}}
    raw_body = json.dumps({
        "docStatusList": [],
        "categoryIdList": [],
        "key": "test",
        "deep": deep_obj,
    }).encode("utf-8")

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "RULE"
    assert result["scoped_label"] == "RULE_CONFIRMED_INVALID"
    assert result["parser_result"] == "PASS"
    assert result["rule_result"] == "FAIL"


# ---------------------------------------------------------------------------
# LAYER_RULE — parser PASS + rule PASS
# ---------------------------------------------------------------------------

def test_both_pass_is_technically_valid_candidate():
    raw_body = b'{"docStatusList":[],"categoryIdList":[],"key":""}'

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "RULE"
    assert result["scoped_label"] == "TECHNICALLY_VALID_CANDIDATE"
    assert result["parser_result"] == "PASS"
    assert result["rule_result"] == "PASS"


def test_both_pass_with_optional_unknown_fields():
    # allow_unknown=true, so extra fields do not break the rule oracle
    raw_body = json.dumps({
        "docStatusList": ["draft", "published"],
        "categoryIdList": ["cat1", "cat2"],
        "key": "search_term",
        "page": 1,
        "limit": 20,
    }).encode("utf-8")

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "RULE"
    assert result["scoped_label"] == "TECHNICALLY_VALID_CANDIDATE"
    assert result["parser_result"] == "PASS"
    assert result["rule_result"] == "PASS"


# ---------------------------------------------------------------------------
# Schema completeness + fail-closed
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "terminal_layer",
    "scoped_label",
    "parser_result",
    "rule_result",
    "api_contract_result",
    "semantic_result",
    "security_result",
    "raw_body_sha256",
    "canonical_json_sha256",
    "endpoint_name",
    "contract_id",
}


@pytest.mark.parametrize("raw_body,endpoint", [
    (b'{"docStatusList":[],"categoryIdList":[],"key":"test"}', "cms_doc_list"),
    (b'{"docStatusList":[],"categoryIdList":[]}', "cms_doc_list"),
    (b"\xff", "cms_doc_list"),
])
def test_result_schema_is_complete(raw_body, endpoint):
    result = evaluate_phase1_scoped(raw_body, endpoint_name=endpoint)
    assert REQUIRED_FIELDS.issubset(result.keys())


def test_downstream_oracles_are_never_executed():
    raw_body = b'{"docStatusList":[],"categoryIdList":[],"key":"test"}'

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["api_contract_result"] == "NOT_EXECUTED"
    assert result["semantic_result"] == "NOT_EXECUTED"
    assert result["security_result"] == "NOT_EXECUTED"


def test_fail_closed_on_unknown_endpoint():
    raw_body = b'{"field":"value"}'

    result = evaluate_phase1_scoped(raw_body, endpoint_name="nonexistent_endpoint")

    assert result["scoped_label"] == "UNKNOWN"
    assert result["terminal_layer"] == "CONTROL_FAILURE"


def test_canonicalization_recorded():
    raw_body = b'  {"key":"v","docStatusList":[],"categoryIdList":[]}  '

    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["scoped_label"] == "TECHNICALLY_VALID_CANDIDATE"
    assert result["raw_body_sha256"] is not None
    assert result["canonical_json_sha256"] is not None
    assert result["canonical_json_sha256"] != result["raw_body_sha256"]
    canonical = result["canonical_json_bytes"]
    assert canonical is not None
    assert b"  " not in canonical              # compact separators
    assert canonical.startswith(b'{"categoryIdList"')  # sorted keys
    assert result["contract_id"] == "o2oa_cms_doc_list_fixed_38"


def test_fail_closed_on_missing_bound_artifact(monkeypatch):
    # A bound artifact (parser/extractor/rule) that cannot be read must fail
    # closed to CONTROL_FAILURE/UNKNOWN, never a valid/invalid label and never
    # a bare OSError. Simulated via monkeypatch so no real file is deleted.
    import pathlib

    real_read_bytes = pathlib.Path.read_bytes

    def _read_bytes_missing_extractor(self):
        if self.name == "feature_extract.py":
            raise FileNotFoundError(f"[Errno 2] No such file: {self}")
        return real_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", _read_bytes_missing_extractor)

    raw_body = b'{"docStatusList":[],"categoryIdList":[],"key":"test"}'
    result = evaluate_phase1_scoped(raw_body, endpoint_name="cms_doc_list")

    assert result["terminal_layer"] == "CONTROL_FAILURE"
    assert result["scoped_label"] == "UNKNOWN"
    assert result["scoped_label"] not in (
        "TRANSPORT_MALFORMED",
        "RULE_CONFIRMED_INVALID",
        "TECHNICALLY_VALID_CANDIDATE",
    )
