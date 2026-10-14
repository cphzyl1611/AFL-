"""Offline regressions for the content_update transport and readback contract."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import types
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import nv_http_harness as harness
from scripts import run_alfresco_bounded_feedback as runner


CONTENT_TYPE = "text/plain; charset=utf-8"


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self) -> int:
        return 200

    def read(self, limit: int = 4096) -> bytes:
        del limit
        return b"{}"


def test_canonical_content_update_keeps_content_type_through_outbound_request(
    tmp_path: Path,
) -> None:
    config = runner.render_content_update_runtime_config(
        "11111111-2222-3333-4444-555555555555",
        tmp_path / "target.json",
    )
    seed = runner.write_initial_seed(config, tmp_path / "seed", "content_update")
    raw_request = seed.read_bytes()
    expected_body = raw_request.split(b"\r\n\r\n", 1)[1]
    captured: dict[str, object] = {}

    def open_direct(request, timeout):
        del timeout
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = request.data
        return _Response()

    env = {
        "NV_TARGET_CONFIG": str(config),
        "NV_ENDPOINT_NAME": "content_update",
        "NV_BODY_RULES": str(runner.BODY_RULES_PATH),
        "NV_BODY_VALID_STATS": str(tmp_path / "body-valid.json"),
        "NV_STATUS_PATH": str(tmp_path / "status.json"),
        "NV_PROBE_PATH": str(tmp_path / "probe.json"),
        "NV_STATE_DB": str(tmp_path / "state.json"),
        "ALFRESCO_USER": "offline-user",
        "ALFRESCO_PASS": "offline-pass",
    }
    stdin = types.SimpleNamespace(buffer=io.BytesIO(raw_request))
    with (
        mock.patch.dict(harness.os.environ, env, clear=True),
        mock.patch.object(harness.sys, "stdin", stdin),
        mock.patch.object(harness, "open_direct", side_effect=open_direct),
        mock.patch.object(
            harness,
            "update_state",
            return_value={"ncov_delta": 0, "ncov_total": 0, "nall": 0},
        ),
    ):
        return_code = harness.main()

    assert return_code == 0
    assert captured["body"] == expected_body
    assert captured["content_type"] == CONTENT_TYPE
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["content_sha256"] == (
        "sha256:" + hashlib.sha256(expected_body).hexdigest()
    )
    assert status["content_length"] == len(expected_body)


def _content_layout(
    tmp_path: Path,
    *,
    expected_body: bytes,
    include_executed_identity: bool = True,
) -> dict[str, Path]:
    layout = runner.build_run_layout(tmp_path / "run", REPO_ROOT)
    layout["run_root"].mkdir(parents=True)
    layout["evidence"].mkdir()
    layout["afl_output"].mkdir()
    layout["task"].write_text(
        json.dumps({"scenario": "content_update", "readback": "byte_exact_content"}),
        encoding="utf-8",
    )
    status: dict[str, object] = {
        "exec_seq": 7,
        "method": "PUT",
        "path": "/alfresco/api/-default-/public/alfresco/versions/1/nodes/11111111-2222-3333-4444-555555555555/content",
        "http_code": 200,
        "validation_reject": 0,
    }
    if include_executed_identity:
        status.update(
            {
                "content_sha256": "sha256:" + hashlib.sha256(expected_body).hexdigest(),
                "content_length": len(expected_body),
            }
        )
    layout["status"].write_text(json.dumps(status), encoding="utf-8")
    layout["status_seq"].write_text("7", encoding="utf-8")
    layout["state_trace"].write_text(
        json.dumps(
            {
                "exec_seq": 7,
                "state": "PUT /nodes/content|2xx",
                "state_id": "1",
                "new": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (layout["afl_output"] / "fuzzer_stats").write_text(
        "nv_total_valid_exec : 1\n",
        encoding="utf-8",
    )
    return layout


def _identity() -> dict[str, str]:
    return {
        "node_id": "11111111-2222-3333-4444-555555555555",
        "parent_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "name": "content.txt",
    }


class _ContentClient:
    def __init__(self, content: bytes):
        self.content = content
        self.calls = 0

    def get_content_bytes(self, node_id: str) -> bytes:
        assert node_id == _identity()["node_id"]
        self.calls += 1
        return self.content


def test_content_readback_passes_when_executed_and_observed_bytes_match(
    tmp_path: Path,
) -> None:
    layout = _content_layout(tmp_path, expected_body=b"alpha")
    client = _ContentClient(b"alpha")

    result = runner.post_execution_readback(client, _identity(), layout)
    artifact = json.loads(layout["readback"].read_text(encoding="utf-8"))

    assert client.calls == 1
    assert result["status"] == 200
    assert result["content_effect_match"] is True
    assert result["verdict"] == "pass"
    assert result["reconciled"] is True
    assert artifact["request"] == {"method": "GET", "status": 200}
    assert artifact["result"]["content_effect_match"] is True


def test_content_readback_fails_when_executed_and_observed_bytes_differ(
    tmp_path: Path,
) -> None:
    layout = _content_layout(tmp_path, expected_body=b"alpha")
    client = _ContentClient(b"bravo")

    result = runner.post_execution_readback(client, _identity(), layout)
    artifact = json.loads(layout["readback"].read_text(encoding="utf-8"))

    assert client.calls == 1
    assert result["status"] == 200
    assert result["content_hash_match"] is False
    assert result["content_length_match"] is True
    assert result["content_effect_match"] is False
    assert result["verdict"] == "content_mismatch"
    assert result["reconciled"] is False
    assert artifact["request"] == {"method": "GET", "status": 200}
    assert artifact["result"]["content_effect_match"] is False


def test_content_readback_fails_when_executed_length_identity_differs(
    tmp_path: Path,
) -> None:
    layout = _content_layout(tmp_path, expected_body=b"alpha")
    status = json.loads(layout["status"].read_text(encoding="utf-8"))
    status["content_length"] = len(b"alpha") + 1
    layout["status"].write_text(json.dumps(status), encoding="utf-8")
    client = _ContentClient(b"alpha")

    result = runner.post_execution_readback(client, _identity(), layout)

    assert client.calls == 1
    assert result["status"] == 200
    assert result["content_hash_match"] is True
    assert result["content_length_match"] is False
    assert result["content_effect_match"] is False
    assert result["verdict"] == "content_mismatch"
    assert result["reconciled"] is False


def test_content_readback_fails_closed_without_executed_body_identity(
    tmp_path: Path,
) -> None:
    layout = _content_layout(
        tmp_path,
        expected_body=b"alpha",
        include_executed_identity=False,
    )
    client = _ContentClient(b"alpha")

    result = runner.post_execution_readback(client, _identity(), layout)
    artifact = json.loads(layout["readback"].read_text(encoding="utf-8"))

    assert client.calls == 1
    assert result["status"] == 200
    assert result["content_effect_match"] is False
    assert result["verdict"] == "executed_content_identity_unavailable"
    assert result["reconciled"] is False
    assert artifact["request"] == {"method": "GET", "status": 200}
    assert artifact["result"]["expected_content_hash"] is None
    assert artifact["result"]["content_effect_match"] is False


def test_content_readback_fails_closed_when_execution_cannot_be_correlated(
    tmp_path: Path,
) -> None:
    layout = _content_layout(tmp_path, expected_body=b"alpha")
    layout["state_trace"].write_text(
        json.dumps(
            {
                "exec_seq": 8,
                "state": "PUT /nodes/content|2xx",
                "state_id": "1",
                "new": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    client = _ContentClient(b"alpha")

    result = runner.post_execution_readback(client, _identity(), layout)

    assert client.calls == 0
    assert result["attempted"] is False
    assert result["reconciled"] is False
    assert "FINAL_EXECUTION_SEQ_MISMATCH" in result["verdict"]
    assert not layout["readback"].exists()


def test_content_readback_cannot_pass_without_a_real_target_invocation(
    tmp_path: Path,
) -> None:
    layout = _content_layout(tmp_path, expected_body=b"alpha")
    (layout["afl_output"] / "fuzzer_stats").write_text(
        "nv_total_valid_exec : 0\n",
        encoding="utf-8",
    )
    client = _ContentClient(b"alpha")

    result = runner.post_execution_readback(client, _identity(), layout)

    assert client.calls == 0
    assert result["applicable"] is False
    assert result["attempted"] is False
    assert result["reconciled"] is False
    assert result["verdict"] == "not_applicable"
    assert not layout["readback"].exists()
