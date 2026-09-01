"""Offline contracts for the O2OA manifest_156 canonical seed binding."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / "integration/platform_profiles/o2oa_default.json"
TEMPLATE_PATH = REPO_ROOT / "runner/templates/task_ae_default.json"
ADAPTER_PATH = REPO_ROOT / "integration/fuzz_adapter.py"
RUNNER_PATH = REPO_ROOT / "runner/fuzz_test_runner.py"
MANIFEST_REL = "model_stage/manifests/dataset_manifest_156.txt"
SEED_DIR_REL = "in/o2oa_body_cms_score"
COMPARE_DIR_REL = "in/o2oa_body_model_compare"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest_rows() -> list[list[str]]:
    rows = []
    for raw in (REPO_ROOT / MANIFEST_REL).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            rows.append([part.strip() for part in line.split(",")])
    return rows


class O2OACanonicalSeedBindingTest(unittest.TestCase):
    def test_o2oa_profile_uses_manifest_156_seed_dir(self) -> None:
        profile = load_json(PROFILE_PATH)
        self.assertEqual(profile["seed_dir"], SEED_DIR_REL)
        self.assertEqual(profile["manifest"], MANIFEST_REL)

    def test_o2oa_task_template_declares_manifest_156(self) -> None:
        template = load_json(TEMPLATE_PATH)
        self.assertEqual(template["seed_dir"], SEED_DIR_REL)
        self.assertEqual(template["manifest"], MANIFEST_REL)

    def test_o2oa_adapter_passes_canonical_seed_dir_and_manifest(self) -> None:
        adapter = load_module(ADAPTER_PATH, "o2oa_canonical_adapter")
        profile = adapter.load_profile("o2oa_default", REPO_ROOT)
        task = adapter.build_runner_task({}, profile, REPO_ROOT)
        self.assertEqual(task["seed_dir"], SEED_DIR_REL)
        self.assertEqual(task["manifest"], MANIFEST_REL)
        self.assertEqual(task["integration_request"]["seed_location"], SEED_DIR_REL)

    def test_manifest_156_has_156_entries(self) -> None:
        self.assertEqual(len(manifest_rows()), 156)

    def test_all_manifest_156_entries_exist_in_canonical_seed_dir(self) -> None:
        seed_dir = (REPO_ROOT / SEED_DIR_REL).resolve()
        missing = [row[0] for row in manifest_rows() if not (seed_dir / row[0]).is_file()]
        self.assertEqual(missing, [])

    def test_manifest_entries_are_unique(self) -> None:
        names = [row[0] for row in manifest_rows()]
        self.assertEqual(len(names), len(set(names)))

    def test_manifest_paths_stay_inside_canonical_seed_dir(self) -> None:
        seed_dir = (REPO_ROOT / SEED_DIR_REL).resolve()
        for row in manifest_rows():
            self.assertFalse(Path(row[0]).is_absolute(), row[0])
            self.assertTrue((seed_dir / row[0]).resolve().is_relative_to(seed_dir), row[0])

    def test_manifest_hash_or_size_matches_when_declared(self) -> None:
        seed_dir = REPO_ROOT / SEED_DIR_REL
        for row in manifest_rows():
            metadata = dict(
                part.split("=", 1) for part in row[2:] if "=" in part
            )
            path = seed_dir / row[0]
            if "size" in metadata:
                self.assertEqual(path.stat().st_size, int(metadata["size"]))
            if "sha256" in metadata:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(digest, metadata["sha256"])

    def test_model_compare_subset_is_not_canonical_real_seed_dir(self) -> None:
        profile = load_json(PROFILE_PATH)
        compare_files = {path.name for path in (REPO_ROOT / COMPARE_DIR_REL).iterdir()}
        manifest_files = {row[0] for row in manifest_rows()}
        self.assertEqual(len(compare_files), 18)
        self.assertNotEqual(compare_files, manifest_files)
        self.assertNotEqual(profile["seed_dir"], COMPARE_DIR_REL)

    def test_probe_extras_are_not_loaded_by_manifest_runner(self) -> None:
        manifest_files = {row[0] for row in manifest_rows()}
        compare_files = {path.name for path in (REPO_ROOT / COMPARE_DIR_REL).iterdir()}
        self.assertEqual(
            compare_files - manifest_files,
            {"grey_probe_0.json", "grey_probe_1.json", "grey_probe_2.json"},
        )

    def test_canonical_manifest_controls_loaded_seed_set(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_materialize")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            run_dir = root / "run"
            seed_dir = repo / "in/seeds"
            manifest = repo / "manifest.txt"
            seed_dir.mkdir(parents=True)
            run_dir.mkdir()
            (seed_dir / "first.json").write_text("{}", encoding="utf-8")
            (seed_dir / "second.json").write_text("{}", encoding="utf-8")
            (seed_dir / "extra.json").write_text("{}", encoding="utf-8")
            manifest.write_text("first.json,normal\nsecond.json,border\n", encoding="utf-8")

            view = runner.materialize_manifest_seed_dir(
                {"seed_dir": "in/seeds", "manifest": "manifest.txt"},
                repo_root=repo,
                run_dir=run_dir,
            )

            self.assertEqual({path.name for path in view.iterdir()}, {"0001__first.json", "0002__second.json"})
            self.assertNotIn("0003__extra.json", {path.name for path in view.iterdir()})
            self.assertTrue(all(path.is_file() for path in view.iterdir()))
            self.assertTrue(all(not path.is_symlink() for path in view.iterdir()))
            self.assertEqual(
                (view / "0001__first.json").read_bytes(),
                (seed_dir / "first.json").read_bytes(),
            )
            self.assertEqual(
                (view / "0002__second.json").read_bytes(),
                (seed_dir / "second.json").read_bytes(),
            )

    def test_manifest_seed_view_contains_regular_files(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_regular_files")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            run_dir = root / "external" / "runs" / "task"
            seed_dir = repo / "in/seeds"
            seed_dir.mkdir(parents=True)
            run_dir.mkdir(parents=True)
            (seed_dir / "one.json").write_bytes(b"one\n")
            (seed_dir / "two.json").write_bytes(b"two\x00\n")
            (seed_dir / "extra.json").write_bytes(b"extra\n")
            (repo / "manifest.txt").write_text(
                "one.json,normal\ntwo.json,border\n", encoding="utf-8"
            )
            before = {
                path.name: path.read_bytes()
                for path in seed_dir.iterdir()
            }

            view = runner.materialize_manifest_seed_dir(
                {"seed_dir": "in/seeds", "manifest": "manifest.txt"},
                repo_root=repo,
                run_dir=run_dir,
            )

            entries = list(view.iterdir())
            self.assertEqual({path.name for path in entries}, {"0001__one.json", "0002__two.json"})
            self.assertEqual(len(entries), 2)
            self.assertTrue(all(path.is_file() for path in entries))
            self.assertTrue(all(not path.is_symlink() for path in entries))
            self.assertTrue(view.is_relative_to(run_dir))
            self.assertEqual(
                {path.name: path.read_bytes() for path in entries},
                {"0001__one.json": b"one\n", "0002__two.json": b"two\x00\n"},
            )
            self.assertEqual(
                {path.name: path.read_bytes() for path in seed_dir.iterdir()}, before
            )
            self.assertFalse((view / "0003__extra.json").exists())
            self.assertFalse((view / "extra.json").exists())

    def test_manifest_seed_view_rejects_symlink_source(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_source_symlink")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            seed_dir = repo / "in/seeds"
            run_dir = root / "external"
            seed_dir.mkdir(parents=True)
            run_dir.mkdir()
            outside = root / "outside.json"
            outside.write_bytes(b"outside")
            (seed_dir / "link.json").symlink_to(outside)
            (repo / "manifest.txt").write_text("link.json,normal\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                runner.materialize_manifest_seed_dir(
                    {"seed_dir": "in/seeds", "manifest": "manifest.txt"},
                    repo_root=repo,
                    run_dir=run_dir,
                )

    def test_seed_directory_symlink_is_rejected(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_seed_dir_symlink")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            real_seed_dir = repo / "real-seeds"
            seed_dir = repo / "in" / "seeds"
            run_dir = root / "external"
            real_seed_dir.mkdir(parents=True)
            run_dir.mkdir()
            (real_seed_dir / "seed.json").write_bytes(b"seed")
            seed_dir.parent.mkdir()
            seed_dir.symlink_to(real_seed_dir, target_is_directory=True)
            (repo / "manifest.txt").write_text("seed.json,normal\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                runner.materialize_manifest_seed_dir(
                    {"seed_dir": "in/seeds", "manifest": "manifest.txt"},
                    repo_root=repo,
                    run_dir=run_dir,
                )
            self.assertFalse((run_dir / "manifest_seeds").exists())
            self.assertEqual((real_seed_dir / "seed.json").read_bytes(), b"seed")

    def test_seed_directory_component_symlink_is_rejected(self) -> None:
        runner = load_module(
            RUNNER_PATH, "o2oa_canonical_runner_seed_component_symlink"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            real_in = repo / "real-in"
            seed_dir = repo / "in" / "seeds"
            run_dir = root / "external"
            (real_in / "seeds").mkdir(parents=True)
            run_dir.mkdir()
            (real_in / "seeds" / "seed.json").write_bytes(b"seed")
            seed_dir.parent.symlink_to(real_in, target_is_directory=True)
            (repo / "manifest.txt").write_text("seed.json,normal\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                runner.materialize_manifest_seed_dir(
                    {"seed_dir": "in/seeds", "manifest": "manifest.txt"},
                    repo_root=repo,
                    run_dir=run_dir,
                )
            self.assertFalse((run_dir / "manifest_seeds").exists())
            self.assertEqual((real_in / "seeds" / "seed.json").read_bytes(), b"seed")

    def test_manifest_seed_views_are_isolated_between_run_roots(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_run_isolation")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            seed_dir = repo / "in/seeds"
            seed_dir.mkdir(parents=True)
            (seed_dir / "seed.json").write_bytes(b"seed")
            (repo / "manifest.txt").write_text("seed.json,normal\n", encoding="utf-8")
            run_a = root / "run-A"
            run_b = root / "run-B"

            view_a = runner.materialize_manifest_seed_dir(
                {"seed_dir": "in/seeds", "manifest": "manifest.txt"},
                repo_root=repo,
                run_dir=run_a,
            )
            view_b = runner.materialize_manifest_seed_dir(
                {"seed_dir": "in/seeds", "manifest": "manifest.txt"},
                repo_root=repo,
                run_dir=run_b,
            )

            self.assertNotEqual(view_a, view_b)
            self.assertTrue(view_a.is_relative_to(run_a))
            self.assertTrue(view_b.is_relative_to(run_b))
            self.assertEqual((view_a / "0001__seed.json").read_bytes(), b"seed")
            self.assertEqual((view_b / "0001__seed.json").read_bytes(), b"seed")
            self.assertFalse((view_a / "0001__seed.json").is_symlink())
            self.assertFalse((view_b / "0001__seed.json").is_symlink())

    def test_manifest_order_prefix_maps_queue_ids_to_manifest_entries(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_order_prefix")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            seed_dir = repo / "in/seeds"
            seed_dir.mkdir(parents=True)
            (seed_dir / "fuzz_bad_1.json").write_bytes(b"bad")
            (seed_dir / "seed_ok_0.json").write_bytes(b"good")
            (repo / "manifest.txt").write_text(
                "seed_ok_0.json,normal\nfuzz_bad_1.json,abnormal\n", encoding="utf-8"
            )
            view = runner.materialize_manifest_seed_dir(
                {"seed_dir": "in/seeds", "manifest": "manifest.txt"},
                repo_root=repo,
                run_dir=root / "run",
            )
            entries = sorted(entry.name for entry in view.iterdir())
            self.assertEqual(entries, ["0001__seed_ok_0.json", "0002__fuzz_bad_1.json"])
            self.assertEqual((view / "0001__seed_ok_0.json").read_bytes(), b"good")

    def test_default_runner_command_uses_manifest_seed_view(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_command")
        task = load_json(TEMPLATE_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            run_dir = run_root / "run"
            out_dir = run_root / "out"
            run_dir.mkdir()
            out_dir.mkdir()
            command = runner.build_launch_cmd(
                task,
                "offline",
                run_dir,
                out_dir,
                repo_root=REPO_ROOT,
                run_root=run_root,
            )
            view = run_dir / "manifest_seeds"
            self.assertEqual(len(list(view.iterdir())), 156)
            self.assertIn(f'IN_DIR="{view}"', command[2])
            self.assertNotIn(f'IN_DIR="{REPO_ROOT / SEED_DIR_REL}"', command[2])

    def test_ae_meta_declares_156_dataset_semantics(self) -> None:
        meta = load_json(REPO_ROOT / "model_stage/models/sefanogan_ae_meta.json")
        self.assertEqual(meta["train_count"] + meta["val_count"], 156)
        self.assertEqual(meta["train_normal_count"], meta["train_count"])
        self.assertEqual(meta["train_normal_recon"]["count"], meta["train_count"])
        validation_count = sum(
            meta[name]["count"]
            for name in ("val_normal_recon", "val_border_recon", "val_abnormal_recon")
        )
        self.assertEqual(validation_count, meta["val_count"])

    def test_profile_seed_set_matches_model_dataset_binding(self) -> None:
        profile = load_json(PROFILE_PATH)
        meta = load_json(REPO_ROOT / "model_stage/models/sefanogan_ae_meta.json")
        self.assertEqual(profile["seed_dir"], SEED_DIR_REL)
        self.assertEqual(profile["manifest"], MANIFEST_REL)
        self.assertEqual(len(manifest_rows()), meta["train_count"] + meta["val_count"])

    def test_o2oa_seed_dir_is_repo_root_relative(self) -> None:
        value = load_json(PROFILE_PATH)["seed_dir"]
        self.assertFalse(Path(value).is_absolute())
        self.assertNotIn("..", Path(value).parts)

    def test_o2oa_manifest_is_repo_root_relative(self) -> None:
        value = load_json(PROFILE_PATH)["manifest"]
        self.assertFalse(Path(value).is_absolute())
        self.assertNotIn("..", Path(value).parts)

    def test_o2oa_seed_paths_reject_traversal(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_traversal")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            seed_dir = repo / "in/seeds"
            seed_dir.mkdir(parents=True)
            (repo / "manifest.txt").write_text("../outside.json,normal\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                runner.resolve_manifest_seed_paths(
                    "in/seeds", "manifest.txt", repo_root=repo
                )

    def test_o2oa_seed_paths_do_not_escape_repo_root(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_escape")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            outside = root / "outside.json"
            seed_dir = repo / "in/seeds"
            seed_dir.mkdir(parents=True)
            outside.write_text("{}", encoding="utf-8")
            (seed_dir / "link.json").symlink_to(outside)
            (repo / "manifest.txt").write_text("link.json,normal\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                runner.resolve_manifest_seed_paths(
                    "in/seeds", "manifest.txt", repo_root=repo
                )

    def test_o2oa_output_paths_remain_run_root_relative(self) -> None:
        runner = load_module(RUNNER_PATH, "o2oa_canonical_runner_output")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            run_root = Path(tmp) / "external"
            repo.mkdir()
            (repo / ".git").mkdir()
            layout = runner.build_run_layout(run_root, repo, "manifest-task")
            for name in ("task_dir", "run_dir", "afl_out_dir", "evidence"):
                self.assertTrue(layout[name].is_relative_to(run_root.resolve()), name)
                self.assertFalse(layout[name].is_relative_to(repo.resolve()), name)


if __name__ == "__main__":
    unittest.main()
