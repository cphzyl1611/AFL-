#!/usr/bin/env python3
"""Local Alfresco AE v1 engineering scorer.

This module reads ``model_stage/models/alfresco_ae_v1_meta.json`` and scores
Alfresco metadata, text content, and multipart upload samples. It is an
AE-like statistical baseline and does not implement GAN/fAnoGAN inference.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_feature_extractor import (  # noqa: E402
    extract_metadata_features,
    extract_multipart_upload_features,
    extract_text_content_features,
)


DEFAULT_META_PATH = ROOT / "model_stage" / "models" / "alfresco_ae_v1_meta.json"


class AlfrescoAEV1Scorer:
    def __init__(self, meta_path: str | Path = DEFAULT_META_PATH) -> None:
        self.meta_path = Path(meta_path)
        with self.meta_path.open("r", encoding="utf-8") as fh:
            self.meta = json.load(fh)
        self.feature_names = list(self.meta["feature_names"])
        self.mean = [float(value) for value in self.meta["mean"]]
        self.std = [float(value) if abs(float(value)) > 1e-9 else 1.0 for value in self.meta["std"]]
        self.threshold_low = float(self.meta.get("threshold_low", 0.0))
        self.threshold_high = float(self.meta["threshold_high"])
        if not (len(self.feature_names) == len(self.mean) == len(self.std)):
            raise ValueError("alfresco AE v1 meta has inconsistent feature lengths")

    def score_vector(self, vector: list[float]) -> float:
        if len(vector) != len(self.mean):
            raise ValueError(f"feature vector length mismatch: {len(vector)} != {len(self.mean)}")
        z_values = [(float(value) - mu) / sigma for value, mu, sigma in zip(vector, self.mean, self.std)]
        return math.sqrt(sum(value * value for value in z_values) / len(z_values))

    def result(self, vector: list[float]) -> dict[str, Any]:
        score = self.score_vector(vector)
        ae_pass = score <= self.threshold_high
        if ae_pass:
            reason = "score_within_threshold"
            decision = "pass"
        else:
            reason = "score_above_threshold"
            decision = "reject"
        return {
            "score": round(score, 6),
            "pass": ae_pass,
            "decision": decision,
            "reason": reason,
            "feature_vector": [round(float(value), 6) for value in vector],
            "threshold_low": self.threshold_low,
            "threshold_high": self.threshold_high,
            "model_name": self.meta.get("model_name", "alfresco_ae_v1"),
            "model_type": self.meta.get("model_type", "ae_like_statistical_baseline"),
        }

    def score_metadata_payload(self, payload: dict) -> dict[str, Any]:
        return self.result(extract_metadata_features(payload))

    def score_text_content(self, text: str | bytes) -> dict[str, Any]:
        return self.result(extract_text_content_features(text))

    def score_multipart_upload(self, filename: str, content: bytes, fields: dict) -> dict[str, Any]:
        return self.result(extract_multipart_upload_features(filename, content, fields))

    def score_sample(self, sample: dict[str, Any]) -> dict[str, Any]:
        scenario = str(sample.get("scenario", "")).strip()
        if scenario == "metadata_update":
            payload = sample.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("metadata_update sample requires object payload")
            return self.score_metadata_payload(payload)
        if scenario == "content_update":
            content = sample.get("content", "")
            if isinstance(content, str):
                return self.score_text_content(content)
            raise ValueError("content_update sample requires string content")
        if scenario == "multipart_upload":
            filename = str(sample.get("filename", "sample.txt"))
            fields = sample.get("fields", {})
            if not isinstance(fields, dict):
                fields = {}
            if "content_b64" in sample:
                content = base64.b64decode(str(sample["content_b64"]))
            else:
                content = str(sample.get("content", "")).encode("utf-8")
            return self.score_multipart_upload(filename, content, fields)
        raise ValueError(f"unsupported scenario: {scenario}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one Alfresco AE v1 sample from JSON stdin.")
    parser.add_argument("--meta", default=str(DEFAULT_META_PATH), help="Path to alfresco_ae_v1_meta.json")
    args = parser.parse_args()

    sample = json.load(sys.stdin)
    scorer = AlfrescoAEV1Scorer(args.meta)
    result = scorer.score_sample(sample)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
