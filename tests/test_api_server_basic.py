import unittest


class ApiServerBasicTest(unittest.TestCase):
    def test_import_and_capabilities(self) -> None:
        import integration.api_server as api_server

        scenarios = set(api_server.SCENARIOS)
        self.assertIn("nv_mab_smoke", scenarios)
        self.assertIn("nv_mab_stability", scenarios)
        self.assertIn("nv_mab_ablation", scenarios)
        self.assertIn("alfresco_ae_v1_score_service", scenarios)
        self.assertEqual(api_server.ALFRESCO_AE_V1_SCORE_CAPABILITY["endpoint"], "POST /score/alfresco_ae_v1")

    def test_default_bind_is_localhost(self) -> None:
        import integration.api_server as api_server

        self.assertEqual(api_server.DEFAULT_HOST, "127.0.0.1")

    def test_alfresco_ae_v1_score_adapter(self) -> None:
        import integration.api_server as api_server

        result = api_server.score_alfresco_ae_v1_sample(
            {
                "scenario": "metadata_update",
                "payload": {
                    "name": "official_doc.txt",
                    "properties": {
                        "cm:title": "标题",
                        "cm:description": "说明",
                    },
                },
            }
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["tool"], "alfresco_ae_v1_score")
        self.assertEqual(result["model_type"], "ae_like_statistical_baseline")
        self.assertIn(result["decision"], {"pass", "reject"})


if __name__ == "__main__":
    unittest.main()
