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
