from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from types import ModuleType
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run_alfresco_bounded_feedback.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("backend_wiring_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_server():
    old = os.environ.copy()
    os.environ.update(
        {
            "SEFANOGAN_MODE": "ae",
            "SEFANOGAN_MODEL_PATH": str(ROOT / "model_stage/models/sefanogan_ae_model.pt"),
            "SEFANOGAN_AE_META_PATH": str(ROOT / "model_stage/models/sefanogan_ae_meta.json"),
            "NV_VALIDITY_BACKEND": "alfresco_ae_v1",
        }
    )
    try:
        spec = importlib.util.spec_from_file_location(
            "backend_wiring_server", ROOT / "model_stage/nv_valid_server_real.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        os.environ.clear()
        os.environ.update(old)


def reference_artifacts() -> tuple[Path, Path]:
    """Use an existing frozen reference run, never a test-generated model."""

    audit_root = Path("/home/dministrator/alfresco-audit-artifacts")
    checkpoints = sorted(audit_root.glob("sefanogan-es-*/training_runs/seed-*/sefanogan_es_reference.pt"))
    for checkpoint in checkpoints:
        metadata = checkpoint.with_suffix(".json")
        if metadata.is_file():
            return checkpoint, metadata
    raise unittest.SkipTest("frozen SE reference checkpoint/metadata is unavailable")


def load_server_from(source: Path, environment: dict[str, str]):
    """Import the production score service with a caller-selected environment."""

    module_name = f"backend_wiring_server_{id(source)}_{id(environment)}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    with mock.patch.dict(os.environ, environment, clear=True):
        spec.loader.exec_module(module)
    return module


def load_runner_from(source: Path):
    module_name = f"backend_wiring_runner_{id(source)}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def production_environment(backend: str) -> dict[str, str]:
    environment = {
        "SEFANOGAN_MODE": "ae",
        "SEFANOGAN_MODEL_PATH": str(ROOT / "model_stage/models/sefanogan_ae_model.pt"),
        "SEFANOGAN_AE_META_PATH": str(ROOT / "model_stage/models/sefanogan_ae_meta.json"),
        "NV_VALIDITY_BACKEND": backend,
    }
    if backend == "alfresco_ae_v1":
        environment["ALFRESCO_AE_V1_META_PATH"] = str(
            ROOT / "model_stage/models/alfresco_ae_v1_meta.json"
        )
    else:
        checkpoint, metadata = reference_artifacts()
        environment["SEFANOGAN_REFERENCE_CHECKPOINT"] = str(checkpoint)
        environment["SEFANOGAN_REFERENCE_META_PATH"] = str(metadata)
    return environment


def assert_exact_production_backend(test: unittest.TestCase, backend: str):
    server = load_server_from(ROOT / "model_stage/nv_valid_server_real.py", production_environment(backend))
    predictor = server.PREDICTOR
    if backend == "alfresco_ae_v1":
        expected_module = "model_stage.alfresco_ae_v1_scorer"
        expected_name = "AlfrescoAEV1Scorer"
    else:
        expected_module = "model_stage.sefanogan_es_reference"
        expected_name = "ReferenceScorer"
    test.assertEqual(type(predictor).__module__, expected_module)
    test.assertEqual(type(predictor).__name__, expected_name)
    test.assertTrue(Path(predictor.meta_path if backend == "alfresco_ae_v1" else predictor.metadata_path).is_file())
    return server


class BackendSelectorTest(unittest.TestCase):
    def test_backend_alfresco_ae_v1_loads_exact_scorer(self):
        assert_exact_production_backend(self, "alfresco_ae_v1")

    def test_backend_se_reference_loads_canonical_scorer(self):
        assert_exact_production_backend(self, "sefanogan_es_reference")

    def test_backend_se_reference_rejects_missing_artifacts(self):
        server = load_server()
        with self.assertRaises(FileNotFoundError):
                server.load_validity_backend(
                    "sefanogan_es_reference",
                    {"checkpoint": "/missing/checkpoint.pt", "metadata": "/missing/meta.json"},
                )

    def test_legacy_ae_mode_semantics_unchanged(self):
        server = load_server()
        fake_module = ModuleType("sefanogan_infer")
        class FakeAEInfer:
            def __init__(self, *args):
                pass
        fake_module.AEInfer = FakeAEInfer
        fake_module.GANInfer = object
        original = sys.modules.get("sefanogan_infer")
        old_env = os.environ.copy()
        sys.modules["sefanogan_infer"] = fake_module
        os.environ.update(
            {
                "SEFANOGAN_MODE": "ae",
                "SEFANOGAN_MODEL_PATH": "legacy-model.pt",
                "SEFANOGAN_AE_META_PATH": "legacy-meta.json",
            }
        )
        try:
            self.assertEqual(server.build_infer_engine().__class__.__name__, "FakeAEInfer")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            if original is None:
                sys.modules.pop("sefanogan_infer", None)
            else:
                sys.modules["sefanogan_infer"] = original

    def test_unknown_backend_fails_closed(self):
        server = load_server()
        with self.assertRaises(ValueError):
            server.load_validity_backend("unknown")

    def test_se_reference_missing_checkpoint_fails_closed(self):
        server = load_server()
        with self.assertRaises(FileNotFoundError):
            server.load_validity_backend(
                "sefanogan_es_reference",
                {"checkpoint": "/missing/checkpoint.pt", "metadata": "/missing/meta.json"},
            )

    def test_default_backend_remains_ae_v1(self):
        runner = load_runner()
        self.assertEqual(runner.DEFAULT_VALIDITY_BACKEND, "alfresco_ae_v1")

    def test_legacy_se_fanogan_mode_reaches_canonical_reference_scorer(self):
        """The legacy SEFANOGAN_MODE=se_fanogan_es_reference selector must
        reach the same canonical ReferenceScorer as NV_VALIDITY_BACKEND=sefanogan_es_reference,
        not just fail closed on missing artifacts."""
        checkpoint, metadata = reference_artifacts()
        environment = {
            "SEFANOGAN_MODE": "se_fanogan_es_reference",
            "SEFANOGAN_MODEL_PATH": str(checkpoint),
            "SEFANOGAN_REFERENCE_META_PATH": str(metadata),
        }
        server = load_server_from(ROOT / "model_stage/nv_valid_server_real.py", environment)
        predictor = server.PREDICTOR
        scorer = predictor.scorer
        self.assertEqual(type(scorer).__module__, "model_stage.sefanogan_es_reference")
        self.assertEqual(type(scorer).__name__, "ReferenceScorer")
        self.assertTrue(Path(scorer.metadata_path).is_file())


class ScorerTraceTest(unittest.TestCase):
    """Opt-in evidence that a specific backend actually scored a request.

    NV_SCORER_TRACE_PATH is unset by every other test and by production
    defaults, so these are the only tests exercising the trace mechanism.
    """

    def _read_trace(self, trace_path: Path) -> list[dict]:
        if not trace_path.is_file():
            return []
        return [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_ae_scorer_invocation_produces_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "scorer_trace.jsonl"
            environment = {
                "SEFANOGAN_MODE": "ae",
                "SEFANOGAN_MODEL_PATH": str(ROOT / "model_stage/models/sefanogan_ae_model.pt"),
                "SEFANOGAN_AE_META_PATH": str(ROOT / "model_stage/models/sefanogan_ae_meta.json"),
                "NV_SCORER_TRACE_PATH": str(trace_path),
            }
            server = load_server_from(ROOT / "model_stage/nv_valid_server_real.py", environment)

            result = server.score_and_trace(b'{"key": "value"}')

            self.assertIn("score", result)
            records = self._read_trace(trace_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["backend"], "ae")
            self.assertEqual(records[0]["invocation"], 1)
            self.assertTrue(records[0]["success"])
            self.assertNotIn("body", records[0])
            self.assertNotIn("score", records[0])
            self.assertNotIn("token", json.dumps(records[0]).lower())

    def test_se_reference_scorer_invocation_produces_trace(self):
        checkpoint, metadata = reference_artifacts()
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "scorer_trace.jsonl"
            environment = {
                "SEFANOGAN_MODE": "se_fanogan_es_reference",
                "SEFANOGAN_MODEL_PATH": str(checkpoint),
                "SEFANOGAN_REFERENCE_META_PATH": str(metadata),
                "NV_SCORER_TRACE_PATH": str(trace_path),
            }
            server = load_server_from(ROOT / "model_stage/nv_valid_server_real.py", environment)
            # Confirm this really is the canonical reference scorer before
            # trusting the trace it produces.
            self.assertEqual(type(server.PREDICTOR.scorer).__module__, "model_stage.sefanogan_es_reference")
            self.assertEqual(type(server.PREDICTOR.scorer).__name__, "ReferenceScorer")

            result = server.score_and_trace(b'{"key": "value"}')

            self.assertIn("score", result)
            records = self._read_trace(trace_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["backend"], "se_fanogan_es_reference")
            self.assertEqual(records[0]["invocation"], 1)
            self.assertTrue(records[0]["success"])

    def test_missing_artifact_fails_closed_without_false_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "scorer_trace.jsonl"
            environment = {
                "NV_VALIDITY_BACKEND": "sefanogan_es_reference",
                "SEFANOGAN_REFERENCE_CHECKPOINT": "/missing/checkpoint.pt",
                "SEFANOGAN_REFERENCE_META_PATH": "/missing/meta.json",
                "NV_SCORER_TRACE_PATH": str(trace_path),
            }
            with self.assertRaises(FileNotFoundError):
                load_server_from(ROOT / "model_stage/nv_valid_server_real.py", environment)

            # Fail-closed happens at load time, before any request is ever
            # scored -- the trace must not record a phantom success.
            self.assertEqual(self._read_trace(trace_path), [])

    def test_trace_is_noop_when_path_unset(self):
        """Default behavior (no NV_SCORER_TRACE_PATH) must be unchanged."""
        environment = {
            "SEFANOGAN_MODE": "ae",
            "SEFANOGAN_MODEL_PATH": str(ROOT / "model_stage/models/sefanogan_ae_model.pt"),
            "SEFANOGAN_AE_META_PATH": str(ROOT / "model_stage/models/sefanogan_ae_meta.json"),
        }
        server = load_server_from(ROOT / "model_stage/nv_valid_server_real.py", environment)
        self.assertEqual(server.SCORER_TRACE_PATH, "")
        # Must not raise and must not attempt any file write.
        result = server.score_and_trace(b'{"key": "value"}')
        self.assertIn("score", result)


class RealRunnerPropagationTest(unittest.TestCase):
    def _layout(self, runner, directory: str):
        root = Path(directory)
        layout = runner.build_run_layout(root, ROOT)
        layout["task"].parent.mkdir(parents=True, exist_ok=True)
        layout["task"].write_text(json.dumps({"scenario": "metadata_update"}))
        return layout

    def _assert_runner_reaches_exact_scorer(self, scenario: str, backend: str):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            layout = self._layout(runner, directory)
            layout["task"].write_text(json.dumps({"scenario": scenario}))
            environment = production_environment(backend)
            with mock.patch.dict(os.environ, environment, clear=True):
                child_env = runner.runtime_environment(
                    layout,
                    layout["target_config"],
                    layout["task"],
                    ("user", "pass"),
                    validity_backend=backend,
                )
            server = load_server_from(ROOT / "model_stage/nv_valid_server_real.py", child_env)
            predictor = server.PREDICTOR
            expected_module = (
                "model_stage.alfresco_ae_v1_scorer"
                if backend == "alfresco_ae_v1"
                else "model_stage.sefanogan_es_reference"
            )
            expected_name = (
                "AlfrescoAEV1Scorer"
                if backend == "alfresco_ae_v1"
                else "ReferenceScorer"
            )
            self.assertEqual(type(predictor).__module__, expected_module)
            self.assertEqual(type(predictor).__name__, expected_name)

    def test_metadata_runner_reaches_ae_v1_production_scorer(self):
        self._assert_runner_reaches_exact_scorer("metadata_update", "alfresco_ae_v1")

    def test_metadata_runner_reaches_se_reference_production_scorer(self):
        self._assert_runner_reaches_exact_scorer("metadata_update", "sefanogan_es_reference")

    def test_multipart_backend_label_resolves_to_ae_v1_scorer_class(self):
        """multipart_upload runs with enable_validity=0 (see MultipartProfileTest.
        test_multipart_task_payload_preserves_scenario_contract): the score
        service is never invoked during multipart execution. This only proves
        that IF the propagated backend label were handed to the score service
        directly (orchestration/config compatibility), it resolves to the
        correct scorer class -- it is not evidence of per-execution scorer
        participation in multipart traffic."""
        self._assert_runner_reaches_exact_scorer("multipart_upload", "alfresco_ae_v1")

    def test_multipart_backend_label_resolves_to_se_reference_scorer_class(self):
        """See test_multipart_backend_label_resolves_to_ae_v1_scorer_class:
        label-resolution only, not scorer participation -- multipart runs
        with enable_validity=0 and never calls the score service."""
        self._assert_runner_reaches_exact_scorer("multipart_upload", "sefanogan_es_reference")

    def test_metadata_real_runner_propagates_validity_backend(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            layout = self._layout(runner, directory)
            env = runner.runtime_environment(
                layout,
                layout["target_config"],
                layout["task"],
                ("user", "pass"),
                validity_backend="alfresco_ae_v1",
            )
            self.assertEqual(env["NV_VALIDITY_BACKEND"], "alfresco_ae_v1")

    def test_multipart_real_runner_propagates_validity_backend(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            layout = self._layout(runner, directory)
            layout["task"].write_text(json.dumps({"scenario": "multipart_upload"}))
            env = runner.runtime_environment(
                layout,
                layout["target_config"],
                layout["task"],
                ("user", "pass"),
                validity_backend="sefanogan_es_reference",
            )
            self.assertEqual(env["NV_VALIDITY_BACKEND"], "sefanogan_es_reference")

    def test_real_bounded_runner_does_not_route_to_mock_filter(self):
        runner = load_runner()
        self.assertNotIn("online_filter_wrapper", str(runner.HARNESS_PATH))
        self.assertEqual(
            runner.build_harness_command_for_scenario(
                {"scenario": "metadata_update", "input_format": "full_http"}
            ),
            [runner.sys.executable, str(runner.HARNESS_PATH)],
        )


class MutationSensitivityTest(unittest.TestCase):
    def test_mutation_a_wrong_se_selector_is_caught(self):
        source = (ROOT / "model_stage/nv_valid_server_real.py").read_text(encoding="utf-8")
        source = source.replace(
            "return ReferenceScorer(checkpoint, metadata)",
            "return AlfrescoAEV1Scorer()",
        )
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / "nv_valid_server_real.py"
            mutated.write_text(source, encoding="utf-8")
            environment = production_environment("sefanogan_es_reference")
            with self.assertRaises(AssertionError):
                server = load_server_from(mutated, environment)
                self.assertEqual(type(server.PREDICTOR).__module__, "model_stage.sefanogan_es_reference")
                self.assertEqual(type(server.PREDICTOR).__name__, "ReferenceScorer")

    def test_mutation_b_dropped_runner_backend_is_caught(self):
        source = (ROOT / "scripts/run_alfresco_bounded_feedback.py").read_text(encoding="utf-8")
        source = source.replace(
            '"NV_VALIDITY_BACKEND": validity_backend,',
            '"NV_VALIDITY_BACKEND": "alfresco_ae_v1",',
        )
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / "run_alfresco_bounded_feedback.py"
            mutated.write_text(source, encoding="utf-8")
            mutated_runner = load_runner_from(mutated)
            real_runner = load_runner()
            layout = real_runner.build_run_layout(Path(directory) / "run", ROOT)
            layout["task"].parent.mkdir(parents=True, exist_ok=True)
            layout["task"].write_text(json.dumps({"scenario": "metadata_update"}))
            with self.assertRaises(AssertionError):
                env = mutated_runner.runtime_environment(
                    layout, layout["target_config"], layout["task"], ("user", "pass"),
                    validity_backend="sefanogan_es_reference",
                )
                self.assertEqual(env["NV_VALIDITY_BACKEND"], "sefanogan_es_reference")


if __name__ == "__main__":
    unittest.main()
