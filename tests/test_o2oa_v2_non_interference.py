import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


EXPECTED = {
    "model_stage/feature_extract.py": "ae447f89b7899188e562a7d0aeadbaa8fa194e8908c8db2b977b45c255e97d2b",
    "nv_body_valid.py": "a0d06c63ae26cde707c1e58e97859d751f3f3e20cf12772235f822ebf46336a5",
    "targets/o2oa_query.json": "a73f1d9deaaaeebedb0af0bbbcc037fa42d47cf6b2f9ad7e198e0d0e128ee022",
    "validity/o2oa_query_rules.json": "042f51e08194337e5fe9e8c4ecff4222842f572eb12bd0c9b1602dd8f8d28f35",
    "model_stage/models/sefanogan_ae_model.pt": "5de67e66e28af65fdf6adb5c506c91148fcc356accd49113c267896bbd69d3dc",
    "model_stage/models/sefanogan_ae_meta.json": "208daf66d82873dec8c19923d9c0a5a6b82ca36c512de52b0ff16b24ecb7acf2",
    "model_stage/models/sefanogan_gan_model.pt": "205a6a20a499a39b994a7ea5a770d0f701fcaba37cd9328da7e71d4aaf856624",
    "model_stage/models/sefanogan_gan_meta.json": "87d189dde54ac578d170850d090032d3268887517d259ad5fc96855a15b9c495",
}


class O2OAV2NonInterferenceTest(unittest.TestCase):
    def test_legacy_o2oa_and_model_files_are_unchanged(self):
        for relative, expected in EXPECTED.items():
            digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(digest, expected, relative)

    def test_v2_contract_does_not_define_model_state(self):
        contract = json.loads((ROOT / "model_stage/contracts/o2oa_cms_doc_list_fixed_38.json").read_text())
        for forbidden in ("normalization_mean", "normalization_std", "checkpoint_sha256", "threshold"):
            self.assertNotIn(forbidden, contract)


if __name__ == "__main__":
    unittest.main()
