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
- The online backend is selected only with
  `SEFANOGAN_MODE=se_fanogan_es_reference` and requires both checkpoint and
  metadata paths. Missing or malformed artifacts fail closed.
- AE v1 remains the default and primary model.

The training metadata records a hash of the no-raw-content provenance manifest,
the checkpoint hash, split role, sample counts, and feature representation.
