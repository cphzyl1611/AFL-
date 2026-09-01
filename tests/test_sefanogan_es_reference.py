import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch

from model_stage.sefanogan_es_reference import (
    ChannelAttentionEncoder,
    Discriminator,
    Generator,
    ReferenceScorer,
    anomaly_score,
    gradient_penalty,
    seed_everything,
    train_wgan_step,
)


class SEFanoGANESReferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.input_dim = 32
        self.latent_dim = 8
        self.hidden_dim = 16
        self.x = torch.randn(4, self.input_dim)
        self.g = Generator(self.latent_dim, self.input_dim, self.hidden_dim)
        self.d = Discriminator(self.input_dim, self.hidden_dim)
        self.e = ChannelAttentionEncoder(self.input_dim, self.latent_dim, self.hidden_dim)

    def test_wgan_critic_output_unbounded(self) -> None:
        logits, _ = self.d(self.x)
        self.assertEqual(tuple(logits.shape), (4, 1))
        self.assertIsNone(self.d.output_activation)

    def test_gradient_penalty_finite_nonnegative(self) -> None:
        fake = self.g(torch.randn(4, self.latent_dim)).detach()
        penalty = gradient_penalty(self.d, self.x, fake)
        self.assertTrue(torch.isfinite(penalty).item())
        self.assertGreaterEqual(float(penalty), 0.0)

    def test_wgan_train_step_finite(self) -> None:
        opt_g = torch.optim.Adam(self.g.parameters(), lr=1e-3)
        opt_d = torch.optim.Adam(self.d.parameters(), lr=1e-3)
        result = train_wgan_step(self.g, self.d, opt_g, opt_d, self.x, n_critic=1)
        self.assertTrue(all(torch.isfinite(torch.tensor(v)) for v in result.values()))

    def test_channel_attention_shape_and_range(self) -> None:
        latent, weights = self.e(self.x, return_attention=True)
        self.assertEqual(tuple(latent.shape), (4, self.latent_dim))
        self.assertEqual(tuple(weights.shape), tuple(self.x.shape))
        self.assertTrue(torch.all(torch.isfinite(weights)).item())
        self.assertGreaterEqual(float(weights.min()), 0.0)
        self.assertLessEqual(float(weights.max()), 1.0)

    def test_encoder_gradient_flow(self) -> None:
        loss = self.e(self.x).square().mean()
        loss.backward()
        self.assertTrue(any(p.grad is not None for p in self.e.parameters()))

    def test_anomaly_score_finite_and_ordered(self) -> None:
        normal = torch.zeros(1, self.input_dim)
        anomalous = torch.full((1, self.input_dim), 10.0)
        normal_score = anomaly_score(self.e, self.g, self.d, normal)
        anomalous_score = anomaly_score(self.e, self.g, self.d, anomalous)
        self.assertTrue(torch.isfinite(normal_score).item())
        self.assertTrue(torch.isfinite(anomalous_score).item())
        self.assertGreaterEqual(float(anomalous_score), float(normal_score))

    def test_training_seed_is_deterministic(self) -> None:
        seed_everything(123)
        first = torch.randn(3, 4)
        seed_everything(123)
        second = torch.randn(3, 4)
        self.assertTrue(torch.equal(first, second))

    def test_checkpoint_roundtrip_and_metadata_hash(self) -> None:
        from model_stage.sefanogan_es_reference import save_checkpoint

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.pt"
            metadata = Path(directory) / "model.json"
            save_checkpoint(
                checkpoint,
                metadata,
                self.g,
                self.d,
                self.e,
                {"training_manifest_sha256": "manifest-hash"},
            )
            loaded = ReferenceScorer(checkpoint, metadata)
            self.assertEqual(loaded.input_dim, self.input_dim)
            self.assertTrue(torch.isfinite(torch.tensor(loaded.score([0.0] * 32))).item())
            data = json.loads(metadata.read_text())
            expected = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            self.assertEqual(data["checkpoint_sha256"], expected)

    def test_metadata_required_fields(self) -> None:
        from model_stage.sefanogan_es_reference import save_checkpoint, _validate_metadata

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.pt"
            metadata = Path(directory) / "model.json"
            save_checkpoint(checkpoint, metadata, self.g, self.d, self.e)
            data = json.loads(metadata.read_text())
            for field in ("schema_version", "model_family", "feature_contract", "checkpoint_sha256", "production_primary"):
                self.assertIn(field, data)
            del data["model_family"]
            with self.assertRaises(ValueError):
                _validate_metadata(data, checkpoint)

    def test_dimension_mismatch_fails_closed(self) -> None:
        from model_stage.sefanogan_es_reference import save_checkpoint

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.pt"
            metadata = Path(directory) / "model.json"
            save_checkpoint(checkpoint, metadata, self.g, self.d, self.e)
            data = json.loads(metadata.read_text())
            data["input_dim"] = 31
            metadata.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                ReferenceScorer(checkpoint, metadata)

    def test_invalid_checkpoint_fails_closed(self) -> None:
        from model_stage.sefanogan_es_reference import save_checkpoint

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.pt"
            metadata = Path(directory) / "model.json"
            save_checkpoint(checkpoint, metadata, self.g, self.d, self.e)
            checkpoint.write_bytes(b"not a checkpoint")
            with self.assertRaises(ValueError):
                ReferenceScorer(checkpoint, metadata)

    def test_ae_v1_default_unchanged(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "SEFANOGAN_MODE": "ae",
                "SEFANOGAN_MODEL_PATH": str(Path("model_stage/models/sefanogan_ae_model.pt").resolve()),
                "SEFANOGAN_AE_META_PATH": str(Path("model_stage/models/sefanogan_ae_meta.json").resolve()),
            }
        )
        result = subprocess.run([sys.executable, "-c", "import model_stage.nv_valid_server_real"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reference_backend_opt_in_and_missing_model_fail_closed(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "SEFANOGAN_MODE": "se_fanogan_es_reference",
                "SEFANOGAN_MODEL_PATH": "/tmp/missing-reference-checkpoint.pt",
                "SEFANOGAN_REFERENCE_META_PATH": "/tmp/missing-reference-meta.json",
            }
        )
        result = subprocess.run([sys.executable, "-c", "import model_stage.nv_valid_server_real"], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
