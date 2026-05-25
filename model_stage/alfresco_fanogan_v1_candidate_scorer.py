#!/usr/bin/env python3
"""Local scorer for the Alfresco fAnoGAN v1 candidate.

The scorer supports the same Alfresco metadata/content/upload scenarios as AE
v1. In this repository state the model type is a GAN-style statistical
candidate, not a full fAnoGAN or SE-fAnoGAN-ES model.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_fanogan_v1_candidate import (  # noqa: E402
    DEFAULT_META_PATH,
    DEFAULT_WEIGHT_PATH,
    _make_torch_models,
    _normalized_vectors,
    _torch_score_tensor,
    candidate_score,
)
from model_stage.alfresco_feature_extractor import (  # noqa: E402
    extract_metadata_features,
    extract_multipart_upload_features,
    extract_text_content_features,
)


class AlfrescoFanoganV1CandidateScorer:
    def __init__(self, meta_path: str | Path = DEFAULT_META_PATH) -> None:
        self.meta_path = Path(meta_path)
        with self.meta_path.open("r", encoding="utf-8") as fh:
            self.meta = json.load(fh)

        self.feature_names = list(self.meta["feature_names"])
        self.model_type = str(self.meta.get("model_type", "gan_style_statistical_candidate"))
        self.mean = [float(value) for value in self.meta["mean"]]
        self.std = [float(value) if abs(float(value)) > 1e-9 else 1.0 for value in self.meta["std"]]
        self.normal_vectors = [
            [float(value) for value in vector]
            for vector in self.meta.get("normal_vectors", [])
        ]
        self.threshold_low = float(self.meta.get("threshold_low", 0.0))
        self.threshold_high = float(self.meta["threshold_high"])
        self.entropy_baseline = float(self.meta.get("entropy_baseline", 0.0))
        self.entropy_scale = float(self.meta.get("entropy_scale", 1.0))
        if not self.normal_vectors:
            raise ValueError("fAnoGAN candidate meta is missing normal_vectors")
        if not (len(self.feature_names) == len(self.mean) == len(self.std)):
            raise ValueError("fAnoGAN candidate meta has inconsistent feature lengths")
        self.torch_backend_error = ""
        self._torch_backend: tuple[Any, Any, Any, Any] | None = None
        if self.model_type == "torch_fanogan_style_candidate":
            self._try_load_torch_backend()

    def _try_load_torch_backend(self) -> None:
        try:
            torch = importlib.import_module("torch")
            nn = importlib.import_module("torch.nn")
            weight_path_value = str(self.meta.get("weight_path") or DEFAULT_WEIGHT_PATH)
            weight_path = Path(weight_path_value)
            if not weight_path.is_absolute():
                weight_path = ROOT / weight_path
            if not weight_path.is_file():
                raise FileNotFoundError(weight_path)
            device = torch.device("cpu")
            state = torch.load(weight_path, map_location=device)
            hidden_dim = int(state.get("hidden_dim", self.meta.get("hidden_dim", max(32, len(self.feature_names) * 2))))
            latent_dim = int(state.get("latent_dim", self.meta.get("latent_dim", 8)))
            generator, critic, encoder = _make_torch_models(torch, nn, len(self.feature_names), latent_dim, hidden_dim)
            generator.load_state_dict(state["generator"])
            critic.load_state_dict(state["critic"])
            encoder.load_state_dict(state["encoder"])
            generator.eval()
            critic.eval()
            encoder.eval()
            self._torch_backend = (torch, generator, critic, encoder)
        except Exception as exc:  # noqa: BLE001 - fallback is intentional for non-torch environments.
            self.torch_backend_error = str(exc)
            self._torch_backend = None

    def score_vector(self, vector: list[float]) -> float:
        if len(vector) != len(self.mean):
            raise ValueError(f"feature vector length mismatch: {len(vector)} != {len(self.mean)}")
        if self._torch_backend is not None:
            torch, generator, critic, encoder = self._torch_backend
            normalized = _normalized_vectors([vector], self.mean, self.std)
            x_tensor = torch.tensor(normalized, dtype=torch.float32)
            with torch.no_grad():
                score = _torch_score_tensor(torch, generator, critic, encoder, x_tensor)
            return float(score.detach().cpu().tolist()[0])
        return candidate_score(
            vector,
            self.mean,
            self.std,
            self.normal_vectors,
            self.entropy_baseline,
            self.entropy_scale,
        )

    def result(self, vector: list[float]) -> dict[str, Any]:
        score = self.score_vector(vector)
        score_pass = score <= self.threshold_high
        return {
            "score": round(score, 6),
            "pass": score_pass,
            "decision": "pass" if score_pass else "reject",
            "reason": "score_within_threshold" if score_pass else "score_above_threshold",
            "feature_vector": [round(float(value), 6) for value in vector],
            "threshold_low": self.threshold_low,
            "threshold_high": self.threshold_high,
            "model_name": self.meta.get("model_name", "alfresco_fanogan_v1_candidate"),
            "model_type": self.model_type,
            "scoring_backend": "torch" if self._torch_backend is not None else "statistical_fallback",
        }

    def score_metadata_payload(self, payload: dict) -> dict[str, Any]:
        return self.result(extract_metadata_features(payload if isinstance(payload, dict) else {}))

    def score_text_content(self, text: str | bytes) -> dict[str, Any]:
        return self.result(extract_text_content_features(text))

    def score_multipart_upload(self, filename: str, content: bytes, fields: dict) -> dict[str, Any]:
        return self.result(extract_multipart_upload_features(filename, content, fields if isinstance(fields, dict) else {}))

    def score_sample(self, sample: dict[str, Any]) -> dict[str, Any]:
        scenario = str(sample.get("scenario", "")).strip()
        if scenario == "metadata_update":
            payload = sample.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("metadata_update sample requires object payload")
            return self.score_metadata_payload(payload)
        if scenario == "content_update":
            content: str | bytes
            if "content_b64" in sample:
                content = base64.b64decode(str(sample["content_b64"]))
            else:
                content = str(sample.get("content", ""))
            return self.score_text_content(content)
        if scenario == "multipart_upload":
            filename = str(sample.get("filename", "sample.txt"))
            fields = sample.get("fields", {})
            if not isinstance(fields, dict):
                fields = {}
            if "content_b64" in sample:
                content_bytes = base64.b64decode(str(sample["content_b64"]))
            else:
                content_bytes = str(sample.get("content", "")).encode("utf-8")
            return self.score_multipart_upload(filename, content_bytes, fields)
        raise ValueError(f"unsupported scenario: {scenario}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one Alfresco fAnoGAN candidate sample from JSON stdin.")
    parser.add_argument("--meta", default=str(DEFAULT_META_PATH), help="Path to alfresco_fanogan_v1_candidate_meta.json")
    args = parser.parse_args()

    sample = json.load(sys.stdin)
    scorer = AlfrescoFanoganV1CandidateScorer(args.meta)
    print(json.dumps(scorer.score_sample(sample), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
