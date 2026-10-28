"""Configuration validation for the Deep2Fuzz command-line interface."""

from .validator import ConfigValidationResult, validate_config

__all__ = ["ConfigValidationResult", "validate_config"]
