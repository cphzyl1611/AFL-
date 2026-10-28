"""Read-only evidence validation for Deep2Fuzz-ES runs."""

from .verifier import EvidenceInputError, VerificationResult, verify_evidence

__all__ = ["EvidenceInputError", "VerificationResult", "verify_evidence"]
