import hashlib
import json
import unittest
from pathlib import Path

from model_stage.o2oa_v2_input import O2OAV2InputError, prepare_o2oa_v2_input


BASE = '{"docStatusList":[],"categoryIdList":[],"key":"notice"}'


class O2OAV2InputContractTest(unittest.TestCase):
    def test_contract_binds_v2_parser_identity(self):
        contract_path = Path("model_stage/contracts/o2oa_cms_doc_list_fixed_38.json")
        parser_path = Path("model_stage/o2oa_v2_input.py")
        contract = json.loads(contract_path.read_text(encoding="utf-8"))

        self.assertEqual(contract["parser_contract_path"], str(parser_path))
        self.assertTrue(parser_path.is_file())
        self.assertEqual(
            contract["parser_contract_sha256"],
            hashlib.sha256(parser_path.read_bytes()).hexdigest(),
        )

    def test_rejects_invalid_utf8(self):
        with self.assertRaises(O2OAV2InputError):
            prepare_o2oa_v2_input(b"\xff")

    def test_rejects_duplicate_keys(self):
        body = b'{"key":"a","key":"b","docStatusList":[],"categoryIdList":[]}'
        with self.assertRaises(O2OAV2InputError):
            prepare_o2oa_v2_input(body)

    def test_rejects_nonfinite_numbers(self):
        for token in (b"NaN", b"Infinity", b"-Infinity"):
            body = b'{"docStatusList":[],"categoryIdList":[],"key":' + token + b"}"
            with self.subTest(token=token):
                with self.assertRaises(O2OAV2InputError):
                    prepare_o2oa_v2_input(body)

    def test_canonicalizes_order_and_whitespace_but_preserves_raw_hash(self):
        first = prepare_o2oa_v2_input(BASE.encode("utf-8"))
        second_raw = b'{ "key": "notice", "categoryIdList": [], "docStatusList": [] }'
        second = prepare_o2oa_v2_input(second_raw)

        self.assertNotEqual(first.raw_body_sha256, second.raw_body_sha256)
        self.assertEqual(first.canonical_json_bytes, second.canonical_json_bytes)
        self.assertEqual(first.canonical_json_sha256, second.canonical_json_sha256)
        self.assertEqual(first.feature_vector, second.feature_vector)
        self.assertEqual(first.feature_vector_sha256, second.feature_vector_sha256)

    def test_body_bytes_is_canonical_json_length(self):
        result = prepare_o2oa_v2_input(b'{ "docStatusList": [], "categoryIdList": [], "key": "notice" }')
        self.assertEqual(result.feature_vector[0], len(result.canonical_json_bytes))
        self.assertNotEqual(result.feature_vector[0], len(result.raw_body))

    def test_exact_contract_dimension_and_order(self):
        result = prepare_o2oa_v2_input(BASE.encode("utf-8"))
        contract = json.loads(Path("model_stage/contracts/o2oa_cms_doc_list_fixed_38.json").read_text())
        self.assertEqual(result.contract_id, "o2oa_cms_doc_list_fixed_38")
        self.assertEqual(len(result.feature_vector), 38)
        self.assertEqual(contract["input_dim"], 38)
        self.assertEqual(contract["feature_order"], list(result.feature_names))
        self.assertTrue(all(map(lambda value: value == value and abs(value) != float("inf"), result.feature_vector)))

    def test_rejects_invalid_json_and_wrong_root(self):
        for body in (b"not json", b"[]", b"{}"):
            with self.subTest(body=body):
                with self.assertRaises(O2OAV2InputError):
                    prepare_o2oa_v2_input(body)

    def test_rejects_rule_invalid_field_types(self):
        body = b'{"docStatusList":"draft","categoryIdList":[],"key":"notice"}'
        with self.assertRaises(O2OAV2InputError):
            prepare_o2oa_v2_input(body)

    def test_hashes_are_sha256_of_reported_bytes(self):
        result = prepare_o2oa_v2_input(BASE.encode("utf-8"))
        self.assertEqual(result.raw_body_sha256, hashlib.sha256(result.raw_body).hexdigest())
        self.assertEqual(result.canonical_json_sha256, hashlib.sha256(result.canonical_json_bytes).hexdigest())
        feature_bytes = json.dumps(list(result.feature_vector), separators=(",", ":")).encode("utf-8")
        self.assertEqual(result.feature_vector_sha256, hashlib.sha256(feature_bytes).hexdigest())


    def test_adapter_fails_closed_on_missing_contract_artifact(self):
        """Missing contract file must raise O2OAV2InputError, not bare OSError."""
        from unittest.mock import patch

        original_read_text = Path.read_text

        def mock_read_text_contract_missing(self, *args, **kwargs):
            """Raise FileNotFoundError for the contract JSON file."""
            if "o2oa_cms_doc_list_fixed_38.json" in str(self):
                raise FileNotFoundError(f"contract file {self} missing")
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", mock_read_text_contract_missing):
            with self.assertRaises(O2OAV2InputError) as ctx:
                prepare_o2oa_v2_input(BASE.encode("utf-8"))
            # Should NOT raise bare FileNotFoundError or OSError
            self.assertIn("contract", str(ctx.exception).lower())

    def test_adapter_fails_closed_on_missing_parser_bound_artifact(self):
        """Missing parser-bound artifact must raise O2OAV2InputError, not bare OSError."""
        from unittest.mock import patch, MagicMock
        from pathlib import Path

        def mock_read_bytes_parser_missing():
            """Simulate parser file (o2oa_v2_input.py) missing during hash validation."""
            raise FileNotFoundError("parser artifact missing")

        with patch("pathlib.Path.read_bytes", side_effect=mock_read_bytes_parser_missing):
            with self.assertRaises(O2OAV2InputError) as ctx:
                prepare_o2oa_v2_input(BASE.encode("utf-8"))
            # Should NOT raise bare FileNotFoundError

    def test_adapter_fails_closed_on_missing_extractor_bound_artifact(self):
        """Missing extractor-bound artifact must raise O2OAV2InputError, not bare OSError."""
        from unittest.mock import patch

        original_read_bytes = Path.read_bytes

        def mock_read_bytes_extractor_missing(self):
            """Raise FileNotFoundError only for feature_extract.py during hash check."""
            if "feature_extract.py" in str(self):
                raise FileNotFoundError(f"extractor artifact {self} missing")
            return original_read_bytes(self)

        with patch.object(Path, "read_bytes", mock_read_bytes_extractor_missing):
            with self.assertRaises(O2OAV2InputError) as ctx:
                prepare_o2oa_v2_input(BASE.encode("utf-8"))
            # Should NOT raise bare FileNotFoundError

    def test_adapter_fails_closed_on_missing_rule_bound_artifact(self):
        """Missing rule-bound artifact must raise O2OAV2InputError, not bare OSError."""
        from unittest.mock import patch

        original_read_bytes = Path.read_bytes

        def mock_read_bytes_rule_missing(self):
            """Raise FileNotFoundError only for o2oa_query_rules.json during hash check."""
            if "o2oa_query_rules.json" in str(self):
                raise FileNotFoundError(f"rule artifact {self} missing")
            return original_read_bytes(self)

        with patch.object(Path, "read_bytes", mock_read_bytes_rule_missing):
            with self.assertRaises(O2OAV2InputError) as ctx:
                prepare_o2oa_v2_input(BASE.encode("utf-8"))
            # Should NOT raise bare FileNotFoundError

    def test_adapter_fails_closed_on_permission_denied(self):
        """Bound artifact permission failure must raise O2OAV2InputError, not bare PermissionError."""
        from unittest.mock import patch

        original_read_bytes = Path.read_bytes

        def mock_read_bytes_permission_denied(self):
            """Raise PermissionError for feature_extract.py."""
            if "feature_extract.py" in str(self):
                raise PermissionError(f"permission denied: {self}")
            return original_read_bytes(self)

        with patch.object(Path, "read_bytes", mock_read_bytes_permission_denied):
            with self.assertRaises(O2OAV2InputError) as ctx:
                prepare_o2oa_v2_input(BASE.encode("utf-8"))
            # Should NOT raise bare PermissionError


if __name__ == "__main__":
    unittest.main()
