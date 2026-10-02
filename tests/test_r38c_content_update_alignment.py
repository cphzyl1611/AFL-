#!/usr/bin/env python3
"""R38C: Verify content_update feature vector aligns with canonical 32D model."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "model_stage"))

from model_stage.alfresco_feature_extractor import extract_text_content_features

# Reference seed: minimal valid content_update body
CONTENT_UPDATE_REFERENCE_SEED = b"test content for alfresco file update"


def test_content_update_feature_alignment():
    """Verify content_update feature vector matches canonical 32D contract."""

    # Extract features using production path
    feature_vector = extract_text_content_features(CONTENT_UPDATE_REFERENCE_SEED)

    print(f"CONTENT_UPDATE_FEATURE_VECTOR_LENGTH = {len(feature_vector)}")
    print(f"CONTENT_UPDATE_FEATURE_CONTRACT = alfresco_fixed_32")

    # Check metadata-specific features (indices 0-5)
    # For content_update scenario: feature[0]=0, feature[1]=1 (scenario indicator), rest=0
    metadata_features = feature_vector[:6]
    expected_pattern = (
        abs(metadata_features[0]) < 1e-9 and
        abs(metadata_features[1] - 1.0) < 1e-9 and
        all(abs(f) < 1e-9 for f in metadata_features[2:6])
    )
    print(f"METADATA_SPECIFIC_FEATURES_ZEROED = {'YES' if expected_pattern else 'NO'}")

    # Verify canonical checkpoint INPUT_DIM using canonical Python
    canonical_python = (
        Path.home() / "miniconda3" / "envs" / "aflpp-se-calib-pip" / "bin" / "python3"
    )
    canonical_checkpoint = (
        Path.home()
        / "alfresco-audit-artifacts"
        / "sefanogan-es-round3-20260901-"
        / "training_runs"
        / "seed-20260519"
        / "sefanogan_es_reference.pt"
    )

    check_script = f"""
import torch
checkpoint = torch.load('{canonical_checkpoint}', map_location='cpu')
if 'encoder' in checkpoint:
    encoder_state = checkpoint['encoder']
    first_weight_key = [k for k in encoder_state.keys() if 'weight' in k][0]
    input_dim = encoder_state[first_weight_key].shape[1]
    print(input_dim)
else:
    print('UNKNOWN')
"""

    result = subprocess.run(
        [str(canonical_python), "-c", check_script],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        input_dim_str = result.stdout.strip()
        try:
            input_dim = int(input_dim_str)
            print(f"CHECKPOINT_INPUT_DIM = {input_dim}")
        except ValueError:
            print(f"CHECKPOINT_INPUT_DIM = {input_dim_str}")
            input_dim = None
    else:
        print("CHECKPOINT_INPUT_DIM = UNKNOWN")
        input_dim = None

    # Validation
    if len(feature_vector) == 32 and input_dim == 32:
        return 0
    else:
        print("ALIGNMENT_FAILURE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(test_content_update_feature_alignment())
