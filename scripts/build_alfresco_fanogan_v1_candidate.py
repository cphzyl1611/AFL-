#!/usr/bin/env python3
"""Build Alfresco fAnoGAN v1 candidate metadata.

This is an offline candidate builder. It does not contact Alfresco and does
not download models. If PyTorch is unavailable, it emits a documented
GAN-style statistical candidate meta file.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_fanogan_v1_candidate import DEFAULT_META_PATH, torch_available, write_candidate_meta  # noqa: E402


def main() -> int:
    meta = write_candidate_meta(DEFAULT_META_PATH)
    print(f"[OK] torch_available={torch_available()}")
    print(f"[OK] model_type={meta['model_type']}")
    print(f"[OK] train_sample_count={meta['train_sample_count']}")
    print(f"[OK] augmentation_count={meta['augmentation_count']}")
    print(f"[OK] threshold_low={meta['threshold_low']}")
    print(f"[OK] threshold_high={meta['threshold_high']}")
    print(f"[OK] wrote {DEFAULT_META_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
