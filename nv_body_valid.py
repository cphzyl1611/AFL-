import json
import os
import socket
import struct
import sys
from typing import Any, Dict, Optional, Tuple

from integration.decision_engine import DecisionEngine, load_profile_decision_config


def load_validity_rules(path: str) -> Dict[str, Any]:
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return obj if isinstance(obj, dict) else {}


def normalize_json_body_or_none(data: bytes) -> Optional[bytes]:
    if not data:
        return b"{}"

    try:
        text = data.decode("utf-8", errors="strict")
    except Exception:
        return None

    text = text.strip()
    if not text:
        return b"{}"

    if not (text.startswith("{") or text.startswith("[")):
        return None

    try:
        obj = json.loads(text)
    except Exception:
        return None

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def json_depth(x: Any, d: int = 0) -> int:
    if isinstance(x, dict):
        if not x:
            return d + 1
        return max(json_depth(v, d + 1) for v in x.values())
    if isinstance(x, list):
        if not x:
            return d + 1
        return max(json_depth(v, d + 1) for v in x)
    return d + 1


def json_key_count(x: Any) -> int:
    if isinstance(x, dict):
        total = len(x)
        for v in x.values():
            total += json_key_count(v)
        return total
    if isinstance(x, list):
        return sum(json_key_count(v) for v in x)
    return 0


def max_string_len_in_json(x: Any) -> int:
    max_len = 0

    def walk(v: Any):
        nonlocal max_len
        if isinstance(v, dict):
            for k, vv in v.items():
                if isinstance(k, str):
                    max_len = max(max_len, len(k))
                walk(vv)
        elif isinstance(v, list):
            for vv in v:
                walk(vv)
        elif isinstance(v, str):
            max_len = max(max_len, len(v))

    walk(x)
    return max_len


def check_type(value: Any, typ: str) -> bool:
    if typ == "object":
        return isinstance(value, dict)
    if typ == "array":
        return isinstance(value, list)
    if typ == "string":
        return isinstance(value, str)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "boolean":
        return isinstance(value, bool)
    if typ == "null":
        return value is None
    return True


def get_common_rules(rules_all: Dict[str, Any]) -> Dict[str, Any]:
    common = rules_all.get("common", {})
    if not isinstance(common, dict):
        common = {}

    return {
        "max_bytes": int(common.get("max_bytes", 16384)),
        "max_depth": int(common.get("max_depth", 8)),
        "max_keys": int(common.get("max_keys", 128)),
        "max_string": int(common.get("max_string", 2048)),
    }


def get_endpoint_rules(rules_all: Dict[str, Any], endpoint_name: str) -> Dict[str, Any]:
    endpoints = rules_all.get("endpoints", {})
    if not isinstance(endpoints, dict):
        return {}
    ep_rules = endpoints.get(endpoint_name, {})
    return ep_rules if isinstance(ep_rules, dict) else {}


def validate_common_limits(norm_body: bytes, obj: Any, common_rules: Dict[str, Any]) -> Tuple[bool, str]:
    max_bytes = int(common_rules.get("max_bytes", 16384))
    max_depth = int(common_rules.get("max_depth", 8))
    max_keys = int(common_rules.get("max_keys", 128))
    max_string = int(common_rules.get("max_string", 2048))

    if len(norm_body) > max_bytes:
        return False, "too_large"

    if json_depth(obj) > max_depth:
        return False, "too_deep"

    if json_key_count(obj) > max_keys:
        return False, "too_many_keys"

    if max_string_len_in_json(obj) > max_string:
        return False, "string_too_long"

    return True, "ok"


def validate_endpoint_type(obj: Any, ep_rules: Dict[str, Any]) -> Tuple[bool, str]:
    top_type = ep_rules.get("type")
    if top_type and not check_type(obj, str(top_type)):
        return False, "wrong_top_type"
    return True, "ok"


def validate_required_fields(obj: Any, ep_rules: Dict[str, Any]) -> Tuple[bool, str]:
    required = ep_rules.get("required", [])
    if not required:
        return True, "ok"

    if not isinstance(obj, dict):
        return False, "missing_required"

    if not isinstance(required, list):
        return True, "ok"

    for k in required:
        if isinstance(k, str) and k not in obj:
            return False, "missing_required"

    return True, "ok"


def validate_unknown_fields(obj: Any, ep_rules: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return True, "ok"

    allow_unknown = bool(ep_rules.get("allow_unknown", True))
    if allow_unknown:
        return True, "ok"

    properties = ep_rules.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}

    for k in obj.keys():
        if k not in properties:
            return False, "unknown_field"

    return True, "ok"


def validate_properties(obj: Any, ep_rules: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return True, "ok"

    properties = ep_rules.get("properties", {})
    if not isinstance(properties, dict):
        return True, "ok"

    for field, pr in properties.items():
        if field not in obj:
            continue

        if not isinstance(pr, dict):
            continue

        value = obj[field]

        if "type" in pr:
            typ = str(pr["type"])
            if not check_type(value, typ):
                return False, "field_type_mismatch"

        if isinstance(value, str) and "maxLength" in pr:
            try:
                max_len = int(pr["maxLength"])
            except Exception:
                max_len = 0
            if max_len > 0 and len(value) > max_len:
                return False, "field_too_long"

        if isinstance(value, list) and "maxItems" in pr:
            try:
                max_items = int(pr["maxItems"])
            except Exception:
                max_items = 0
            if max_items > 0 and len(value) > max_items:
                return False, "field_too_many_items"

    return True, "ok"


def rpc_score_unix(endpoint: str, endpoint_name: str, norm_body: bytes) -> Tuple[bool, Optional[float]]:
    del endpoint_name  # 当前协议不使用 endpoint_name，但保留参数位以便后续扩展

    if not endpoint:
        return False, None
    if not endpoint.startswith("unix://"):
        return False, None

    sock_path = endpoint[len("unix://"):]
    if not sock_path.startswith("/"):
        sock_path = "/" + sock_path

    try:
        fd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        fd.settimeout(1.0)
        fd.connect(sock_path)

        payload = norm_body

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

        fd.close()

        text = resp.decode("utf-8", errors="ignore").strip()
        if not text:
            return False, None

        return True, float(text)

    except Exception:
        return False, None


def load_runtime_decision_config(
    score_threshold: Optional[float],
) -> Optional[Dict[str, Any]]:
    profile_path = os.getenv("NV_DECISION_PROFILE_PATH", "").strip()
    if profile_path:
        try:
            return load_profile_decision_config(profile_path)
        except Exception:
            pass

    if score_threshold is None:
        return None

    return {
        "t_low": float(score_threshold),
        "t_high": float(score_threshold),
        "enable_second_stage": False,
    }


def runtime_decision_profile_name() -> str:
    profile_name = os.getenv("NV_DECISION_PROFILE_NAME", "").strip()
    if profile_name:
        return profile_name

    profile_path = os.getenv("NV_DECISION_PROFILE_PATH", "").strip()
    if profile_path:
        base_name = os.path.basename(profile_path)
        if base_name.endswith(".json"):
            base_name = base_name[:-5]
        return base_name or "unknown"

    return "threshold"


def debug_field(value: Any) -> str:
    if value is None:
        return "-"
    return str(value).replace("\r", "\\r").replace("\n", "\\n").replace(" ", "_")


def log_body_decision_debug(
    profile_name: str,
    ae_score: Optional[float],
    decision: str,
    decision_meta: Dict[str, Any],
) -> None:
    if os.getenv("NV_DEBUG_BODY_VALID") != "1":
        return

    try:
        ae_score_text = "-" if ae_score is None else f"{float(ae_score):.6f}"
        print(
            "[BODY_DECISION_DBG] "
            f"profile={debug_field(profile_name)} "
            f"ae_score={ae_score_text} "
            f"decision={debug_field(decision)} "
            f"stage={debug_field(decision_meta.get('stage'))} "
            f"second_stage_source={debug_field(decision_meta.get('second_stage_source'))} "
            f"fallback_reason={debug_field(decision_meta.get('fallback_reason'))}",
            file=sys.stderr,
            flush=True,
        )
    except Exception:
        pass


def body_validate(
    endpoint_name: str,
    raw_body: bytes,
    rules_path: str,
    score_endpoint: Optional[str] = None,
    score_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    norm = normalize_json_body_or_none(raw_body)
    if norm is None:
        return {
            "ok": False,
            "reason": "invalid_json",
            "score": None,
            "score_rpc_ok": False,
            "norm_body": None,
        }

    try:
        obj = json.loads(norm.decode("utf-8"))
    except Exception:
        return {
            "ok": False,
            "reason": "invalid_json",
            "score": None,
            "score_rpc_ok": False,
            "norm_body": None,
        }

    rules_all = load_validity_rules(rules_path)
    common_rules = get_common_rules(rules_all)
    ep_rules = get_endpoint_rules(rules_all, endpoint_name)

    ok, reason = validate_common_limits(norm, obj, common_rules)
    if not ok:
        return {
            "ok": False,
            "reason": reason,
            "score": None,
            "score_rpc_ok": False,
            "norm_body": norm,
        }

    ok, reason = validate_endpoint_type(obj, ep_rules)
    if not ok:
        return {
            "ok": False,
            "reason": reason,
            "score": None,
            "score_rpc_ok": False,
            "norm_body": norm,
        }

    ok, reason = validate_required_fields(obj, ep_rules)
    if not ok:
        return {
            "ok": False,
            "reason": reason,
            "score": None,
            "score_rpc_ok": False,
            "norm_body": norm,
        }

    ok, reason = validate_unknown_fields(obj, ep_rules)
    if not ok:
        return {
            "ok": False,
            "reason": reason,
            "score": None,
            "score_rpc_ok": False,
            "norm_body": norm,
        }

    ok, reason = validate_properties(obj, ep_rules)
    if not ok:
        return {
            "ok": False,
            "reason": reason,
            "score": None,
            "score_rpc_ok": False,
            "norm_body": norm,
        }

    score = None
    score_rpc_ok = False
    decision = "pass"
    decision_meta = {"stage": "rules_only"}

    if score_endpoint:
        if os.getenv("NV_DEBUG_BODY_VALID") == "1":
            print(
                f"[BODY_VALID_DBG] endpoint={endpoint_name} "
                f"score_endpoint={score_endpoint} "
                f"threshold={score_threshold}",
                file=sys.stderr,
                flush=True,
            )

        rpc_ok, score = rpc_score_unix(score_endpoint, endpoint_name, norm)
        score_rpc_ok = bool(rpc_ok and score is not None)
        decision_config = load_runtime_decision_config(score_threshold)

        if os.getenv("NV_DEBUG_BODY_VALID") == "1":
            print(
                f"[BODY_VALID_DBG] rpc_ok={rpc_ok} score={score} "
                f"score_rpc_ok={score_rpc_ok}",
                file=sys.stderr,
                flush=True,
            )

        if score_rpc_ok:
            if decision_config is not None:
                decision_engine = DecisionEngine(decision_config)
                decision, meta = decision_engine.decide(score, norm)
                decision_meta = meta
                log_body_decision_debug(
                    runtime_decision_profile_name(),
                    score,
                    decision,
                    decision_meta,
                )
            elif score_threshold is not None and score >= score_threshold:
                decision = "reject"
                decision_meta = {"stage": "ae_high", "ae_score": score}

            if decision != "pass":
                return {
                    "ok": False,
                    "reason": "score_reject",
                    "score": score,
                    "score_rpc_ok": True,
                    "norm_body": norm,
                    "decision": decision,
                    "decision_meta": decision_meta,
                }

    return {
        "ok": True,
        "reason": "ok",
        "score": score,
        "score_rpc_ok": score_rpc_ok,
        "norm_body": norm,
        "decision": decision,
        "decision_meta": decision_meta,
    }
