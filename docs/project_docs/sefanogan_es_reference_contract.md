# Project Canonical SE-fAnoGAN-ES Reference Contract

This document defines the project reference implementation. It is not a claim
of exact reproduction of the underspecified original formula.

- Input: the existing Alfresco fixed 32-dimensional feature vector.
- G and D: the existing `sefanogan_train_gan.py` Generator and Discriminator.
- D output: an unbounded scalar critic output plus an intermediate feature vector.
- WGAN stabilization: WGAN-GP, with `lambda_gp=10.0` and `n_critic=5`.
- E: feature-channel attention over semantic feature channels, followed by a
  projection to the latent vector.
- Stage 1: train G/D on normal-only vectors with WGAN-GP.
- Stage 2: lock G/D and train E using reconstruction MSE plus discriminator
  feature-matching MSE.
- Score: `0.75*sqrt(reconstruction_mse) + 0.25*sqrt(discriminator_feature_mse)`.
- Checkpoints and metadata are generated per run and are not production primary
  artifacts.
- AE v1 remains the default and primary model. SE-fAnoGAN-ES is an explicit
  opt-in, optional research backend; it is never selected implicitly.

## Backend selectors

There are two ways to select the SE-fAnoGAN-ES reference scorer at runtime.
Both require a valid checkpoint and metadata path, both resolve to the same
canonical `model_stage.sefanogan_es_reference.ReferenceScorer` implementation,
and both fail closed when artifacts are missing or malformed.

- **Canonical selector**: `NV_VALIDITY_BACKEND=sefanogan_es_reference`, with
  `SEFANOGAN_REFERENCE_CHECKPOINT` and `SEFANOGAN_REFERENCE_META_PATH`. This is
  the production backend-selection path used by
  `model_stage/nv_valid_server_real.py:load_validity_backend()` and by the
  bounded feedback runner (`scripts/run_alfresco_bounded_feedback.py`).
- **Legacy compatibility selector**: `SEFANOGAN_MODE=se_fanogan_es_reference`,
  with `SEFANOGAN_MODEL_PATH` and `SEFANOGAN_REFERENCE_META_PATH`. This path is
  preserved for backward compatibility only; it internally delegates to the
  same `load_validity_backend()` loader as the canonical selector, so it
  cannot silently diverge from the canonical scorer.

Prefer `NV_VALIDITY_BACKEND=sefanogan_es_reference` for new integrations. The
legacy `SEFANOGAN_MODE` selector exists only so that older callers keep
working.

The training metadata records a hash of the no-raw-content provenance manifest,
the checkpoint hash, split role, sample counts, and feature representation.
