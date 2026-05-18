import unittest

from model_stage.alfresco_feature_extractor import (
    extract_metadata_features,
    extract_multipart_upload_features,
    extract_text_content_features,
    feature_names,
)


class AlfrescoFeatureExtractorTest(unittest.TestCase):
    def test_extractors_return_fixed_length_vectors(self) -> None:
        names = feature_names()
        metadata_vector = extract_metadata_features(
            {
                "name": "official_doc.txt",
                "properties": {
                    "cm:title": "标题",
                    "cm:description": "说明",
                },
            }
        )
        text_vector = extract_text_content_features("关于联调测试的通知")
        upload_vector = extract_multipart_upload_features(
            "official_doc.txt",
            "会议纪要".encode("utf-8"),
            {"nodeType": "cm:content", "autoRename": "true"},
        )
        self.assertEqual(len(metadata_vector), len(names))
        self.assertEqual(len(text_vector), len(names))
        self.assertEqual(len(upload_vector), len(names))

    def test_metadata_invalid_type_count(self) -> None:
        vector = extract_metadata_features({"name": {"bad": "object"}, "properties": {"cm:title": []}})
        values = dict(zip(feature_names(), vector))
        self.assertGreater(values["invalid_type_count"], 0)

    def test_text_nul_byte_detection(self) -> None:
        vector = extract_text_content_features(b"abc\x00def")
        values = dict(zip(feature_names(), vector))
        self.assertEqual(values["has_nul_byte"], 1.0)


if __name__ == "__main__":
    unittest.main()
