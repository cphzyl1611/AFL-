# nv_neuron_probe.py
import json, os, time
from typing import Dict, Any, List, Optional

try:
    import torch
    import torch.nn as nn
except Exception:
    torch = None
    nn = None

class NeuronCoverageProbe:
    """
    简化版神经元覆盖探针（PyTorch）：
    - 覆盖定义：某层输出张量中，某个“神经元位置”激活值 > threshold 即视为覆盖
    - 以“抽样/降维”的方式控制开销：对输出做 channel-wise 或 flatten 抽样
    """
    def __init__(self, model, threshold: float = 0.0, sample_per_layer: int = 2048,
                 probe_path: Optional[str] = None):
        if torch is None:
            raise RuntimeError("PyTorch not available")
        self.model = model
        self.threshold = float(threshold)
        self.sample_per_layer = int(sample_per_layer)
        self.probe_path = probe_path or os.getenv("NV_PROBE_PATH", "/tmp/nv_probe.json")

        self._handles = []
        self._covered = set()  # store (layer_name, idx)
        self._nall = 0
        self._last_total = 0

    def _hook(self, name: str):
        def fn(module, inputs, output):
            # output 可能是 tuple/list
            out = output[0] if isinstance(output, (tuple, list)) else output
            if not torch.is_tensor(out):
                return

            with torch.no_grad():
                t = out.detach()
                # 只取前 sample_per_layer 个元素，避免开销爆炸
                flat = t.reshape(-1)
                n = min(flat.numel(), self.sample_per_layer)
                if n <= 0:
                    return
                vals = flat[:n]
                # 覆盖判定：> threshold
                mask = vals > self.threshold
                # 记录覆盖点
                idxs = torch.nonzero(mask, as_tuple=False).reshape(-1).tolist()
                for i in idxs:
                    self._covered.add((name, int(i)))
        return fn

    def attach(self, layer_types=(nn.Conv2d, nn.Linear, nn.ReLU, nn.GELU)):
        # 给常见层挂 hook；你也可以只挂 Conv/Linear 降低开销
        for name, m in self.model.named_modules():
            if isinstance(m, layer_types):
                h = m.register_forward_hook(self._hook(name))
                self._handles.append(h)
        # 粗略估计 N_all：每层 sample_per_layer 作为“可统计神经元总量”
        # 更严格可以按真实神经元数，但开销会更大
        self._nall = len(self._handles) * self.sample_per_layer

    def detach(self):
        for h in self._handles:
            try: h.remove()
            except Exception: pass
        self._handles.clear()

    def flush(self):
        total = len(self._covered)
        delta = max(0, total - self._last_total)
        self._last_total = total

        data: Dict[str, Any] = {
            "ts_ms": int(time.time() * 1000),
            "ncov_total": int(total),
            "ncov_delta": int(delta),
            "nall": int(self._nall if self._nall > 0 else 1),
        }
        tmp = self.probe_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.probe_path)
        return data