import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProjectConfigsTest(unittest.TestCase):
    def assert_json_file(self, path: Path) -> object:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_schemas_parse(self) -> None:
        schemas = sorted((REPO_ROOT / "schemas").glob("*.schema.json"))
        self.assertGreaterEqual(len(schemas), 4)
        for path in schemas:
            with self.subTest(path=path):
                data = self.assert_json_file(path)
                self.assertIsInstance(data, dict)

    def test_fuzz_submit_demo_parse(self) -> None:
        data = self.assert_json_file(REPO_ROOT / "docs/integration/examples/fuzz_submit_demo.json")
        self.assertIsInstance(data, dict)
        self.assertIn("target_type", data)

    def test_platform_profiles_parse(self) -> None:
        profiles = sorted((REPO_ROOT / "integration/platform_profiles").glob("*.json"))
        self.assertGreater(len(profiles), 0)
        for path in profiles:
            with self.subTest(path=path):
                data = self.assert_json_file(path)
                self.assertIsInstance(data, dict)
                self.assertTrue("profile" in data or "platform" in data)

    def test_validity_rules_parse(self) -> None:
        rules = sorted((REPO_ROOT / "validity").glob("*.json"))
        self.assertGreater(len(rules), 0)
        for path in rules:
            with self.subTest(path=path):
                data = self.assert_json_file(path)
                self.assertIsInstance(data, (dict, list))

    def test_seed_json_parse(self) -> None:
        seeds = sorted((REPO_ROOT / "in").glob("**/*.json"))
        self.assertGreater(len(seeds), 0)
        for path in seeds:
            with self.subTest(path=path):
                self.assert_json_file(path)


if __name__ == "__main__":
    unittest.main()
