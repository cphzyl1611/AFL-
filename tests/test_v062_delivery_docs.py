import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class V062DeliveryDocsTest(unittest.TestCase):
    def test_final_acceptance_docs_exist(self) -> None:
        required = [
            REPO_ROOT / "docs/review/v0.6.2最终验收一页式总结.md",
            REPO_ROOT / "docs/review/真实Alfresco与本地mock_target差异说明.md",
            REPO_ROOT / "docs/review/API_MCP原型安全边界说明.md",
            REPO_ROOT / "docs/review/v0.6.1代码结构与执行链路说明.md",
        ]
        missing = [path.relative_to(REPO_ROOT).as_posix() for path in required if not path.is_file()]
        self.assertFalse(missing, f"missing docs: {missing}")

    def test_codegraph_index_is_ignored(self) -> None:
        gitignore = REPO_ROOT / ".gitignore"
        self.assertTrue(gitignore.is_file(), ".gitignore missing")
        lines = gitignore.read_text(encoding="utf-8").splitlines()
        self.assertIn(".codegraph/", lines)


if __name__ == "__main__":
    unittest.main()
