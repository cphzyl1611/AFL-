import unittest


class ApiServerBasicTest(unittest.TestCase):
    def test_import_and_capabilities(self) -> None:
        import integration.api_server as api_server

        scenarios = set(api_server.SCENARIOS)
        self.assertIn("nv_mab_smoke", scenarios)
        self.assertIn("nv_mab_stability", scenarios)
        self.assertIn("nv_mab_ablation", scenarios)

    def test_default_bind_is_localhost(self) -> None:
        import integration.api_server as api_server

        self.assertEqual(api_server.DEFAULT_HOST, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
