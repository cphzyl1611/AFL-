#!/usr/bin/env python3
import json
import socket
import struct
from typing import Any, Dict, Optional


def json_depth(value: Any, depth: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return depth + 1
        return max(json_depth(item, depth + 1) for item in value.values())
    if isinstance(value, list):
        if not value:
            return depth + 1
        return max(json_depth(item, depth + 1) for item in value)
    return depth + 1


def json_key_count(value: Any) -> int:
    if isinstance(value, dict):
        total = len(value)
        for item in value.values():
            total += json_key_count(item)
        return total
    if isinstance(value, list):
        return sum(json_key_count(item) for item in value)
    return 0


def max_string_len_in_json(value: Any) -> int:
    max_len = 0

    def walk(item: Any):
        nonlocal max_len
        if isinstance(item, dict):
            for key, sub_value in item.items():
                if isinstance(key, str):
                    max_len = max(max_len, len(key))
                walk(sub_value)
        elif isinstance(item, list):
            for sub_value in item:
                walk(sub_value)
        elif isinstance(item, str):
            max_len = max(max_len, len(item))

    walk(value)
    return max_len


def _as_string_list(value: Any):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def load_profile_decision_config(profile_path: str) -> Dict[str, Any]:
    with open(profile_path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    decision = obj.get("decision", {})
    if not isinstance(decision, dict):
        raise ValueError(f"invalid decision config in profile: {profile_path}")
    return decision


class DecisionEngine:
    def __init__(self, config):
        if not isinstance(config, dict):
            raise ValueError("decision config must be a dict")

        self.t_low = float(config["t_low"])
        self.t_high = float(config["t_high"])
        if self.t_low > self.t_high:
            raise ValueError("decision config requires t_low <= t_high")

        self.enable_second_stage = bool(config.get("enable_second_stage", False))
        self.second_stage_type = str(config.get("second_stage_type", "rule")).strip().lower() or "rule"
        self.second_stage_threshold = float(config.get("second_stage_threshold", 1.0))
        self.second_stage_endpoint = str(config.get("second_stage_endpoint", "")).strip()
        self.second_stage_default_score = float(config.get("second_stage_default_score", 1.2))
        self.rpc_timeout_sec = float(config.get("rpc_timeout_sec", 1.0))
        self.max_input_bytes = int(config.get("max_input_bytes", 262144))
        self.allowed_process_definition_keys = set(_as_string_list(config.get("allowed_process_definition_keys", [])))
        self.flowable_rule_max_json_depth = int(config.get("flowable_rule_max_json_depth", 6))
        self.flowable_rule_max_string_len = int(config.get("flowable_rule_max_string_len", 512))
        self.flowable_rule_max_total_keys = int(config.get("flowable_rule_max_total_keys", 80))
        self.flowable_rule_max_variables = int(config.get("flowable_rule_max_variables", 50))
        self.flowable_rule_max_variable_name_len = int(config.get("flowable_rule_max_variable_name_len", 128))
        self.flowable_rule_allowed_root_fields = set(_as_string_list(config.get("flowable_rule_allowed_root_fields", [])))
        self.flowable_rule_required_variables_by_key = self._normalize_string_list_map(
            config.get("flowable_rule_required_variables_by_key", {})
        )
        self.flowable_rule_variable_type_hints = self._normalize_string_map_map(
            config.get("flowable_rule_variable_type_hints", {})
        )
        self._last_second_stage_meta: Dict[str, Any] = {}

    def to_config(self) -> Dict[str, Any]:
        return {
            "t_low": self.t_low,
            "t_high": self.t_high,
            "enable_second_stage": self.enable_second_stage,
            "second_stage_type": self.second_stage_type,
            "second_stage_threshold": self.second_stage_threshold,
            "second_stage_endpoint": self.second_stage_endpoint,
            "second_stage_default_score": self.second_stage_default_score,
            "rpc_timeout_sec": self.rpc_timeout_sec,
            "max_input_bytes": self.max_input_bytes,
            "allowed_process_definition_keys": sorted(self.allowed_process_definition_keys),
            "flowable_rule_max_json_depth": self.flowable_rule_max_json_depth,
            "flowable_rule_max_string_len": self.flowable_rule_max_string_len,
            "flowable_rule_max_total_keys": self.flowable_rule_max_total_keys,
            "flowable_rule_max_variables": self.flowable_rule_max_variables,
            "flowable_rule_max_variable_name_len": self.flowable_rule_max_variable_name_len,
            "flowable_rule_allowed_root_fields": sorted(self.flowable_rule_allowed_root_fields),
            "flowable_rule_required_variables_by_key": self.flowable_rule_required_variables_by_key,
            "flowable_rule_variable_type_hints": self.flowable_rule_variable_type_hints,
        }

    def decide(self, ae_score, sample):
        ae_score = float(ae_score)
        if ae_score <= self.t_low:
            return "pass", {"stage": "ae_low", "ae_score": ae_score}

        if ae_score >= self.t_high:
            return "reject", {"stage": "ae_high", "ae_score": ae_score}

        if self.enable_second_stage:
            second_score = self.run_second_stage(sample)
            meta = {
                "ae_score": ae_score,
                "second_score": second_score,
            }
            meta.update(self._last_second_stage_meta)
            if second_score < self.second_stage_threshold:
                meta["stage"] = "second_pass"
                return "pass", meta

            meta["stage"] = "second_reject"
            return "reject", meta

        return "reject", {"stage": "fallback", "ae_score": ae_score}

    def run_second_stage(self, sample):
        self._last_second_stage_meta = {
            "second_stage_type": self.second_stage_type,
            "second_stage_threshold": self.second_stage_threshold,
        }

        if self.second_stage_type == "gan":
            gan_score = self._run_second_stage_rpc(sample)
            if gan_score is not None:
                self._last_second_stage_meta.update({
                    "second_stage_model": "gan",
                    "second_stage_source": "gan_rpc",
                    "second_stage_endpoint": self.second_stage_endpoint,
                })
                return gan_score

            rule_score = self._run_rule_stage(sample)
            self._last_second_stage_meta.update({
                "second_stage_model": "rule",
                "second_stage_source": "rule_fallback",
                "fallback_reason": "gan_rpc_unavailable",
            })
            return rule_score

        if self.second_stage_type == "rule":
            rule_score = self._run_rule_stage(sample)
            self._last_second_stage_meta.update({
                "second_stage_model": "rule",
                "second_stage_source": "local_rule",
            })
            return rule_score

        if self.second_stage_type in {"flowable_rule", "flowable_rule_v1"}:
            rule_score, rule_reason, reject_reason = self._run_flowable_rule_stage(sample)
            self._last_second_stage_meta.update({
                "second_stage_model": "flowable_rule_v1",
                "second_stage_source": "flowable_rule_v1",
                "rule_reason": rule_reason,
            })
            if reject_reason:
                self._last_second_stage_meta["reject_reason"] = reject_reason
            return rule_score

        self._last_second_stage_meta.update({
            "second_stage_model": "default",
            "second_stage_source": "default_score",
        })
        return self.second_stage_default_score

    def _run_second_stage_rpc(self, sample) -> Optional[float]:
        endpoint = self.second_stage_endpoint
        if not endpoint or not endpoint.startswith("unix://"):
            return None

        payload = self._normalize_sample_bytes(sample)
        if payload is None:
            return None

        sock_path = endpoint[len("unix://"):]
        if not sock_path.startswith("/"):
            sock_path = "/" + sock_path

        fd = None
        try:
            fd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            fd.settimeout(self.rpc_timeout_sec)
            fd.connect(sock_path)
            fd.sendall(struct.pack("<I", len(payload)))
            fd.sendall(payload)

            resp = b""
            while True:
                chunk = fd.recv(4096)
                if not chunk:
                    break
                resp += chunk
                if len(resp) > 128:
                    break
        except Exception:
            return None
        finally:
            try:
                fd.close()
            except Exception:
                pass

        text = resp.decode("utf-8", errors="ignore").strip()
        if not text:
            return None

        try:
            return float(text)
        except Exception:
            return None

    def _run_rule_stage(self, sample) -> float:
        normalized = self._normalize_sample_object(sample)
        if normalized is None:
            return self.second_stage_default_score

        body_bytes = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        size_ratio = min(1.0, len(body_bytes) / 4096.0)
        depth_ratio = min(1.0, json_depth(normalized) / 8.0)
        key_ratio = min(1.0, json_key_count(normalized) / 64.0)
        string_ratio = min(1.0, max_string_len_in_json(normalized) / 512.0)

        risk_score = 1.4 * (
            0.35 * size_ratio +
            0.25 * depth_ratio +
            0.20 * key_ratio +
            0.20 * string_ratio
        )
        return round(risk_score, 6)

    def _run_flowable_rule_stage(self, sample):
        payload = self._normalize_sample_bytes(sample)
        if payload is None:
            return self._flowable_rule_reject("invalid_or_oversize_payload")

        try:
            normalized = json.loads(payload.decode("utf-8"))
        except Exception:
            return self._flowable_rule_reject("invalid_json")

        if not isinstance(normalized, dict):
            return self._flowable_rule_reject("root_not_object")

        if self.flowable_rule_allowed_root_fields:
            for key in normalized:
                if key not in self.flowable_rule_allowed_root_fields:
                    return self._flowable_rule_reject(f"unexpected_root_field:{key}")

        if json_depth(normalized) > self.flowable_rule_max_json_depth:
            return self._flowable_rule_reject("json_depth_exceeded")

        if json_key_count(normalized) > self.flowable_rule_max_total_keys:
            return self._flowable_rule_reject("total_keys_exceeded")

        if max_string_len_in_json(normalized) > self.flowable_rule_max_string_len:
            return self._flowable_rule_reject("string_length_exceeded")

        process_key = normalized.get("processDefinitionKey")
        if not isinstance(process_key, str) or not process_key.strip():
            return self._flowable_rule_reject("missing_or_empty_processDefinitionKey")
        process_key = process_key.strip()

        if self.allowed_process_definition_keys and process_key not in self.allowed_process_definition_keys:
            return self._flowable_rule_reject("processDefinitionKey_not_allowed")

        variables = normalized.get("variables", [])
        if variables is None:
            variables = []
        if not isinstance(variables, list):
            return self._flowable_rule_reject("variables_not_array")
        if len(variables) > self.flowable_rule_max_variables:
            return self._flowable_rule_reject("variables_count_exceeded")

        seen_names = set()
        type_hints = self.flowable_rule_variable_type_hints.get(process_key, {})
        for item in variables:
            if not isinstance(item, dict):
                return self._flowable_rule_reject("variable_item_not_object")
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                return self._flowable_rule_reject("variable_name_missing_or_empty")
            name = name.strip()
            if len(name) > self.flowable_rule_max_variable_name_len:
                return self._flowable_rule_reject("variable_name_too_long")
            if "value" not in item:
                return self._flowable_rule_reject("variable_value_missing")
            value = item.get("value")
            if not self._is_simple_flowable_value(value):
                return self._flowable_rule_reject("variable_value_not_simple")
            expected_type = type_hints.get(name)
            if expected_type and not self._flowable_value_matches_type(value, expected_type):
                return self._flowable_rule_reject(f"variable_type_mismatch:{name}")
            seen_names.add(name)

        for required_name in self.flowable_rule_required_variables_by_key.get(process_key, []):
            if required_name not in seen_names:
                return self._flowable_rule_reject(f"missing_required_variable:{required_name}")

        return 0.0, "flowable_process_start_schema_pass", ""

    def _flowable_rule_reject(self, reason: str):
        score = max(self.second_stage_threshold, self.second_stage_default_score)
        return score, reason, reason

    def _is_simple_flowable_value(self, value: Any) -> bool:
        if value is None or isinstance(value, (str, int, float, bool)):
            if isinstance(value, str):
                return len(value) <= self.flowable_rule_max_string_len
            return True
        if isinstance(value, (dict, list)):
            return (
                json_depth(value) <= 3
                and json_key_count(value) <= 20
                and max_string_len_in_json(value) <= self.flowable_rule_max_string_len
            )
        return False

    def _flowable_value_matches_type(self, value: Any, expected_type: str) -> bool:
        expected_type = str(expected_type).strip().lower()
        if expected_type in {"str", "string"}:
            return isinstance(value, str)
        if expected_type in {"number", "numeric"}:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type in {"bool", "boolean"}:
            return isinstance(value, bool)
        if expected_type == "null":
            return value is None
        if expected_type == "scalar":
            return value is None or isinstance(value, (str, int, float, bool))
        if expected_type == "object":
            return isinstance(value, dict)
        if expected_type == "array":
            return isinstance(value, list)
        return True

    def _normalize_string_list_map(self, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result = {}
        for key, items in value.items():
            if isinstance(key, str):
                result[key] = _as_string_list(items)
        return result

    def _normalize_string_map_map(self, value: Any) -> Dict[str, Dict[str, str]]:
        if not isinstance(value, dict):
            return {}
        result = {}
        for outer_key, inner in value.items():
            if not isinstance(outer_key, str) or not isinstance(inner, dict):
                continue
            clean_inner = {}
            for inner_key, inner_value in inner.items():
                if isinstance(inner_key, str) and isinstance(inner_value, str):
                    clean_inner[inner_key] = inner_value
            result[outer_key] = clean_inner
        return result

    def _normalize_sample_bytes(self, sample) -> Optional[bytes]:
        if isinstance(sample, bytes):
            payload = sample
        elif isinstance(sample, str):
            payload = sample.encode("utf-8", errors="ignore")
        else:
            try:
                payload = json.dumps(sample, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            except Exception:
                return None

        if not payload or len(payload) > self.max_input_bytes:
            return None
        return payload

    def _normalize_sample_object(self, sample) -> Optional[Any]:
        if isinstance(sample, (dict, list)):
            return sample

        if isinstance(sample, bytes):
            try:
                return json.loads(sample.decode("utf-8"))
            except Exception:
                return None

        if isinstance(sample, str):
            try:
                return json.loads(sample)
            except Exception:
                return None

        return None
