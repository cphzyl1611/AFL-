#!/usr/bin/env python3
import os
import json
import math
from pathlib import Path
from typing import Dict, Optional, List

from score_json_offline import score_from_features


class SEFanoGANPredictor:
    """
    统一评分后端接口层。

    支持三种模式：
    1. heuristic: 当前启发式/过渡评分
    2. model: 中心距离占位模型
    3. ae: 小型 Autoencoder 占位模型
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        model_path: Optional[str] = None,
        scaler_path: Optional[str] = None,
    ):
        self.mode = (mode or os.getenv("SEFANOGAN_MODE", "heuristic")).strip().lower()
        self.model_path = model_path or os.getenv("SEFANOGAN_MODEL_PATH", "").strip()
        self.scaler_path = scaler_path or os.getenv("SEFANOGAN_SCALER_PATH", "").strip()

        self.model = None
        self.ae_model = None
        self.ae_meta = None
        self.torch = None
        self.nn = None

        if self.mode == "model":
            self._load_model()
        elif self.mode == "ae":
            self._load_ae_model()

    def _load_model(self):
        """
        加载中心距离占位模型：
        sefanogan_placeholder_model.json
        """
        if not self.model_path:
            raise ValueError("SEFANOGAN_MODEL_PATH is required when mode=model")

        p = Path(self.model_path)
        if not p.is_file():
            raise FileNotFoundError(f"model file not found: {p}")

        with open(p, "r", encoding="utf-8") as f:
            model = json.load(f)

        required = ["model_type", "feature_order", "means", "stds", "center"]
        for k in required:
            if k not in model:
                raise ValueError(f"invalid model file, missing key: {k}")

        if model["model_type"] != "placeholder_center_distance":
            raise ValueError(f"unsupported model_type: {model['model_type']}")

        if not (
            len(model["feature_order"]) ==
            len(model["means"]) ==
            len(model["stds"]) ==
            len(model["center"])
        ):
            raise ValueError("model dimensions mismatch")

        self.model = model

    def _load_ae_model(self):
        """
        加载 AE 模型：
        - pt 权重文件
        - 对应 meta.json
        """
        if not self.model_path:
            raise ValueError("SEFANOGAN_MODEL_PATH is required when mode=ae")

        pt_path = Path(self.model_path)
        if not pt_path.is_file():
            raise FileNotFoundError(f"AE model file not found: {pt_path}")

        meta_path_env = os.getenv("SEFANOGAN_AE_META_PATH", "").strip()
        if meta_path_env:
            meta_path = Path(meta_path_env)
        else:
            # 默认同目录下用固定文件名
            meta_path = pt_path.parent / "sefanogan_ae_meta.json"

        if not meta_path.is_file():
            raise FileNotFoundError(f"AE meta file not found: {meta_path}")

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        required = ["model_type", "feature_order", "input_dim", "latent_dim", "means", "stds"]
        for k in required:
            if k not in meta:
                raise ValueError(f"invalid AE meta file, missing key: {k}")

        if meta["model_type"] != "small_autoencoder":
            raise ValueError(f"unsupported AE model_type: {meta['model_type']}")

        import torch
        import torch.nn as nn

        class SmallAE(nn.Module):
            def __init__(self, input_dim: int, latent_dim: int = 8):
                super().__init__()
                self.encoder = nn.Sequential(
                    nn.Linear(input_dim, 24),
                    nn.ReLU(),
                    nn.Linear(24, latent_dim),
                )
                self.decoder = nn.Sequential(
                    nn.Linear(latent_dim, 24),
                    nn.ReLU(),
                    nn.Linear(24, input_dim),
                )

            def forward(self, x):
                z = self.encoder(x)
                out = self.decoder(z)
                return out

        model = SmallAE(
            input_dim=int(meta["input_dim"]),
            latent_dim=int(meta["latent_dim"]),
        )
        state = torch.load(pt_path, map_location="cpu")
        model.load_state_dict(state)
        model.eval()

        self.torch = torch
        self.nn = nn
        self.ae_model = model
        self.ae_meta = meta

    def _predict_heuristic(self, feat: Dict[str, float]) -> float:
        return float(score_from_features(feat))

    def _predict_model(self, feat: Dict[str, float]) -> float:
        """
        中心距离模型推理：
        1. 按 feature_order 组向量
        2. 用 means/stds 标准化
        3. 计算到 center 的欧氏距离
        """
        if self.model is None:
            raise RuntimeError("model mode selected but model is not loaded")

        order = self.model["feature_order"]
        means = self.model["means"]
        stds = self.model["stds"]
        center = self.model["center"]

        vec = [float(feat.get(k, 0.0)) for k in order]
        z = [(vec[i] - means[i]) / stds[i] for i in range(len(vec))]
        dist = math.sqrt(sum((z[i] - center[i]) ** 2 for i in range(len(z))))
        return float(dist)

    def _predict_ae(self, feat: Dict[str, float]) -> float:
        """
        AE 模型推理：
        1. 按 feature_order 组向量
        2. 用 means/stds 标准化
        3. AE 重建
        4. 用 MSE reconstruction error 作为异常分数
        """
        if self.ae_model is None or self.ae_meta is None or self.torch is None:
            raise RuntimeError("ae mode selected but AE model is not loaded")

        order = self.ae_meta["feature_order"]
        means = self.ae_meta["means"]
        stds = self.ae_meta["stds"]

        vec = [float(feat.get(k, 0.0)) for k in order]
        z = [(vec[i] - means[i]) / stds[i] for i in range(len(vec))]

        x = self.torch.tensor([z], dtype=self.torch.float32)
        with self.torch.no_grad():
            recon = self.ae_model(x)
            err = self.torch.mean((recon - x) ** 2, dim=1).item()

        return float(err)

    def predict_score(self, feat: Dict[str, float]) -> float:
        if self.mode == "heuristic":
            return self._predict_heuristic(feat)
        elif self.mode == "model":
            return self._predict_model(feat)
        elif self.mode == "ae":
            return self._predict_ae(feat)
        else:
            raise ValueError(f"unsupported SEFanoGAN mode: {self.mode}")


def build_predictor_from_env() -> SEFanoGANPredictor:
    return SEFanoGANPredictor()


if __name__ == "__main__":
    import sys
    from feature_extract import extract_features_from_bytes

    if len(sys.argv) != 2:
        print("usage: python3 sefanogan_predict.py <json_file>")
        raise SystemExit(1)

    with open(sys.argv[1], "rb") as f:
        body = f.read()

    feat = extract_features_from_bytes(body)
    predictor = build_predictor_from_env()
    score = predictor.predict_score(feat)

    print(json.dumps({
        "mode": predictor.mode,
        "score": score,
        "features": feat,
    }, ensure_ascii=False, indent=2))