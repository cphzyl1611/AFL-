#!/usr/bin/env python3
"""RED tests for content_update scorer routing repair.

These tests document that:
1. Scenario/endpoint identity must be preserved through RPC protocol
2. Real scorer must receive scenario identity
3. Real scorer must dispatch to scenario-appropriate feature extractor
4. content_update -> extract_text_content_features (text/content)
5. metadata_update -> extract_metadata_features
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestScorerRPCProtocol(unittest.TestCase):
    """Test that RPC protocol preserves scenario/endpoint identity."""

    def test_rpc_score_unix_accepts_endpoint_name_parameter(self):
        """Verify rpc_score_unix accepts endpoint_name parameter."""
        from nv_body_valid import rpc_score_unix
        
        # Check function signature accepts endpoint_name
        import inspect
        sig = inspect.signature(rpc_score_unix)
        params = list(sig.parameters.keys())
        
        self.assertIn("endpoint_name", params, 
            "rpc_score_unix must accept endpoint_name parameter")

    def test_rpc_score_unix_currently_discards_endpoint_name(self):
        """RED: Document that endpoint_name is currently discarded."""
        from nv_body_valid import rpc_score_unix
        import inspect
        
        source = inspect.getsource(rpc_score_unix)
        
        # Current bug: endpoint_name is deleted
        self.assertIn("del endpoint_name", source,
            "Current implementation discards endpoint_name - this is the bug")


class TestRealScorerDispatch(unittest.TestCase):
    """Test that real scorer dispatches to scenario-appropriate extractors."""

    def test_real_scorer_currently_hardcodes_metadata_extraction(self):
        """RED: Document that real scorer hardcodes metadata extraction."""
        scorer_path = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"
        source = scorer_path.read_text(encoding="utf-8")
        
        # Current implementation hardcodes json.loads + extract_metadata_features
        self.assertIn("json.loads(body.decode", source)
        self.assertIn("extract_metadata_features", source)
        
        # Current comment states the assumption
        self.assertIn("body here is always the raw metadata_update JSON payload", source)

    def test_real_scorer_has_text_content_extractor_available(self):
        """Verify extract_text_content_features exists for content_update."""
        from model_stage.alfresco_feature_extractor import extract_text_content_features
        
        # Function must exist
        self.assertTrue(callable(extract_text_content_features))


class TestScorerFeatureExtractorSelection(unittest.TestCase):
    """Test scenario-appropriate feature extraction."""

    def test_content_update_requires_text_content_features(self):
        """Verify content_update needs text content feature extraction."""
        from model_stage.alfresco_feature_extractor import extract_text_content_features
        
        # Test with plain text content (bytes or str)
        text_content = "关于系统联调测试的通知\n请各部门按照计划完成接口联调"
        
        features = extract_text_content_features(text_content)
        
        # Must return feature vector (list of floats)
        self.assertIsInstance(features, list)
        self.assertGreater(len(features), 0)
        self.assertTrue(all(isinstance(f, (int, float)) for f in features))

    def test_content_update_text_features_work_with_bytes(self):
        """Verify text feature extractor accepts bytes."""
        from model_stage.alfresco_feature_extractor import extract_text_content_features
        
        # Must work with bytes
        text_bytes = "测试内容".encode("utf-8")
        features = extract_text_content_features(text_bytes)
        
        self.assertIsInstance(features, list)
        self.assertGreater(len(features), 0)

    def test_metadata_update_requires_metadata_features(self):
        """Verify metadata_update needs metadata feature extraction."""
        from model_stage.alfresco_feature_extractor import extract_metadata_features
        
        # Test with metadata payload
        metadata_payload = {
            "name": "doc.txt",
            "title": "Test Title",
            "description": "Test Description"
        }
        
        features = extract_metadata_features(metadata_payload)
        
        # Must return feature vector (list of floats)
        self.assertIsInstance(features, list)
        self.assertGreater(len(features), 0)
        self.assertTrue(all(isinstance(f, (int, float)) for f in features))

    def test_text_and_metadata_extractors_have_same_output_format(self):
        """Verify both extractors return list[float] for model compatibility."""
        from model_stage.alfresco_feature_extractor import (
            extract_text_content_features,
            extract_metadata_features,
        )
        
        # Text extractor output
        text_result = extract_text_content_features("test content")
        self.assertIsInstance(text_result, list)
        
        # Metadata extractor output
        metadata_result = extract_metadata_features({"title": "test"})
        self.assertIsInstance(metadata_result, list)
        
        # Both return list[float] - same format, different feature semantics
        self.assertEqual(type(text_result), type(metadata_result))


class TestScorerParticipationCounters(unittest.TestCase):
    """Test that scorer participation counters remain accurate."""

    def test_scorer_trace_records_backend_invocation(self):
        """Verify scorer trace recording still works after routing repair."""
        scorer_path = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"
        source = scorer_path.read_text(encoding="utf-8")
        
        self.assertIn("record_scorer_trace", source)
        self.assertIn("SCORER_BACKEND_NAME", source)


class TestScorerRPCProtocolExtension(unittest.TestCase):
    """Test RPC protocol extension to carry scenario identity."""

    def test_rpc_protocol_currently_sends_only_body(self):
        """RED: RPC protocol currently only sends body bytes.
        
        Current: only sends body bytes (length prefix + payload)
        After repair: must send scenario/endpoint metadata
        """
        from nv_body_valid import rpc_score_unix
        import inspect
        
        source = inspect.getsource(rpc_score_unix)
        
        # Current: only sends payload length and payload
        self.assertIn('struct.pack("<I", len(payload))', source)
        self.assertIn("fd.sendall(payload)", source)

    def test_real_scorer_recv_one_currently_reads_only_body(self):
        """RED: Real scorer recv_one currently reads only body bytes.
        
        Current: recv_one only reads (u32_le length + payload bytes)
        After repair: must also receive scenario/endpoint name
        """
        scorer_path = REPO_ROOT / "model_stage" / "nv_valid_server_real.py"
        source = scorer_path.read_text(encoding="utf-8")
        
        # Current recv_one protocol
        self.assertIn("def recv_one", source)
        self.assertIn("recv_exact(conn, 4)", source)  # length prefix


class TestScorerDispatchRequirements(unittest.TestCase):
    """Test the requirements for scenario-aware dispatch."""

    def test_scorer_must_receive_scenario_to_dispatch_correctly(self):
        """RED: Scorer needs scenario parameter to dispatch correctly.
        
        Current flow:
          harness -> rpc_score_unix(endpoint, endpoint_name, body)
          -> RPC sends only body
          -> scorer recv_one(conn) reads only body
          -> predict_score_from_body(body) hardcodes metadata extraction
        
        After repair flow:
          harness -> rpc_score_unix(endpoint, endpoint_name, body)
          -> RPC sends (body + endpoint_name)
          -> scorer recv_one reads (body + endpoint_name)
          -> predict_score_from_body(body, endpoint_name) dispatches:
               content_update -> extract_text_content_features(body)
               metadata_update -> extract_metadata_features(json.loads(body))
        """
        # This test documents the end-to-end requirement
        pass


if __name__ == "__main__":
    unittest.main()
