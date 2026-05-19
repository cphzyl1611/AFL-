import unittest

from integration import mcp_adapter


class MCPAdapterTest(unittest.TestCase):
    def test_get_capabilities(self) -> None:
        result = mcp_adapter.handle_request({"tool": "get_capabilities", "arguments": {}})
        self.assertEqual(result["status"], "ok")
        names = {item["name"] for item in result["tools"]}
        self.assertIn("score_alfresco_ae_v1_sample", names)
        self.assertIn("query_evidence", names)

    def test_score_alfresco_ae_v1_sample(self) -> None:
        result = mcp_adapter.handle_request(
            {
                "tool": "score_alfresco_ae_v1_sample",
                "arguments": {
                    "scenario": "metadata_update",
                    "payload": {
                        "name": "official_doc.txt",
                        "properties": {
                            "cm:title": "标题",
                            "cm:description": "说明",
                        },
                    },
                },
            }
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("score", result)
        self.assertIn(result["decision"], {"pass", "reject"})
        self.assertEqual(result["model_type"], "ae_like_statistical_baseline")

    def test_query_evidence_whitelist(self) -> None:
        result = mcp_adapter.handle_request(
            {
                "tool": "query_evidence",
                "arguments": {"path": "out/alfresco_ae_v1_service_compare/summary.csv"},
            }
        )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["exists"])
        self.assertIn("mode", result["header"])

    def test_query_evidence_rejects_arbitrary_path(self) -> None:
        result = mcp_adapter.handle_request({"tool": "query_evidence", "arguments": {"path": "/etc/passwd"}})
        self.assertEqual(result["status"], "reject")

    def test_rejects_unknown_tool(self) -> None:
        result = mcp_adapter.handle_request({"tool": "run_shell", "arguments": {"cmd": "date"}})
        self.assertEqual(result["status"], "reject")


if __name__ == "__main__":
    unittest.main()
