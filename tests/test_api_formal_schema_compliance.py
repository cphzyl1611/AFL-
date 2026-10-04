"""Test formal API schema compliance with design specification.

This test verifies that the public API contract exactly matches the
formal design specification, not implementation-internal values.
"""
import pytest
from integration.fuzz_api import (
    ALLOWED_TARGET_TYPES,
    ALLOWED_SEED_SOURCES,
    ALLOWED_MUTATION_SCOPES,
    TARGET_TYPE_CAPABILITY,
    SEED_SOURCE_CAPABILITY,
    validate_submit_request,
)


class TestFormalSchemaCompliance:
    """Verify API advertises and accepts exactly the formal design enums."""

    def test_target_type_formal_values(self):
        """target_type must include formal design values."""
        # Formal design requires these exact values
        assert "http_api" in ALLOWED_TARGET_TYPES
        assert "file_upload" in ALLOWED_TARGET_TYPES
        assert "protocol_message" in ALLOWED_TARGET_TYPES

        # No legacy values should remain
        assert "rest_api" not in ALLOWED_TARGET_TYPES

    def test_seed_source_formal_values(self):
        """seed_source must include formal design values."""
        # Formal design requires these exact values
        assert "captured_traffic" in ALLOWED_SEED_SOURCES
        assert "seed_file" in ALLOWED_SEED_SOURCES
        assert "manual" in ALLOWED_SEED_SOURCES

        # No implementation-internal values should be public
        assert "seed_dir" not in ALLOWED_SEED_SOURCES
        assert "template" not in ALLOWED_SEED_SOURCES

    def test_mutation_scope_formal_values(self):
        """mutation_scope must match design (already correct)."""
        assert "field_value" in ALLOWED_MUTATION_SCOPES
        assert "boundary" in ALLOWED_MUTATION_SCOPES
        assert "structure" in ALLOWED_MUTATION_SCOPES
        assert len(ALLOWED_MUTATION_SCOPES) == 3

    def test_http_api_operational(self):
        """http_api target_type must be operational."""
        assert TARGET_TYPE_CAPABILITY["http_api"] == "OPERATIONAL"

    def test_file_upload_operational(self):
        """file_upload target_type must be operational (maps to multipart_upload)."""
        assert TARGET_TYPE_CAPABILITY["file_upload"] == "OPERATIONAL"

    def test_seed_file_operational(self):
        """seed_file seed_source must be operational."""
        assert SEED_SOURCE_CAPABILITY["seed_file"] == "OPERATIONAL"

    def test_manual_operational(self):
        """manual seed_source must be operational."""
        assert SEED_SOURCE_CAPABILITY["manual"] == "OPERATIONAL"

    def test_unimplemented_target_types_rejected(self):
        """Unimplemented target_types must be rejected at capability check (after schema validation)."""
        req = {
            "target_type": "protocol_message",  # Changed from file_upload to protocol_message
            "target_endpoint": "test",
            "seed_source": "seed_file",
            "seed_location": "in/test",
            "mutation_scope": ["field_value"],
            "max_test_cases": 10,
            "time_budget": 60,
        }
        with pytest.raises(ValueError, match="not yet implemented"):
            validate_submit_request(req)

    def test_unimplemented_seed_sources_rejected(self):
        """Unimplemented seed_sources must be rejected with clear error."""
        req = {
            "target_type": "http_api",
            "target_endpoint": "test",
            "seed_source": "captured_traffic",
            "seed_location": "in/test",
            "mutation_scope": ["field_value"],
            "max_test_cases": 10,
            "time_budget": 60,
        }
        with pytest.raises(ValueError, match="not yet implemented"):
            validate_submit_request(req)

    def test_operational_request_accepted(self):
        """Request with operational enums must be accepted."""
        req = {
            "target_type": "http_api",
            "target_endpoint": "test",
            "seed_source": "seed_file",
            "seed_location": "in/test",
            "mutation_scope": ["field_value", "boundary"],
            "max_test_cases": 10,
            "time_budget": 60,
        }
        validated = validate_submit_request(req)
        assert validated["target_type"] == "http_api"
        assert validated["seed_source"] == "seed_file"

    def test_manual_seed_source_accepted(self):
        """manual seed_source (formal name) must be accepted."""
        req = {
            "target_type": "http_api",
            "target_endpoint": "test",
            "seed_source": "manual",
            "seed_location": "in/test",
            "mutation_scope": ["structure"],
            "max_test_cases": 5,
            "time_budget": 30,
        }
        validated = validate_submit_request(req)
        assert validated["seed_source"] == "manual"

    def test_file_upload_request_accepted(self):
        """file_upload target_type must be accepted (maps to multipart_upload scenario)."""
        req = {
            "target_type": "file_upload",
            "target_endpoint": "test",
            "seed_source": "seed_file",
            "seed_location": "in/test",
            "mutation_scope": ["field_value"],
            "max_test_cases": 10,
            "time_budget": 60,
        }
        validated = validate_submit_request(req)
        assert validated["target_type"] == "file_upload"


class TestCapabilityTable:
    """Verify capability table is honest and complete."""

    def test_all_target_types_have_capability_status(self):
        """Every formal target_type must have a capability entry."""
        for tt in ALLOWED_TARGET_TYPES:
            assert tt in TARGET_TYPE_CAPABILITY
            assert TARGET_TYPE_CAPABILITY[tt] in ["OPERATIONAL", "NOT_IMPLEMENTED"]

    def test_all_seed_sources_have_capability_status(self):
        """Every formal seed_source must have a capability entry."""
        for ss in ALLOWED_SEED_SOURCES:
            assert ss in SEED_SOURCE_CAPABILITY
            assert SEED_SOURCE_CAPABILITY[ss] in ["OPERATIONAL", "NOT_IMPLEMENTED"]

    def test_exactly_one_target_type_operational(self):
        """http_api and file_upload should be operational currently."""
        operational = [k for k, v in TARGET_TYPE_CAPABILITY.items() if v == "OPERATIONAL"]
        assert "http_api" in operational
        assert "file_upload" in operational
        assert len(operational) == 2

    def test_seed_file_and_manual_operational(self):
        """seed_file and manual should be operational."""
        operational = [k for k, v in SEED_SOURCE_CAPABILITY.items() if v == "OPERATIONAL"]
        assert "seed_file" in operational
        assert "manual" in operational

    def test_captured_traffic_not_implemented(self):
        """captured_traffic should be documented as not implemented."""
        assert SEED_SOURCE_CAPABILITY["captured_traffic"] == "NOT_IMPLEMENTED"
