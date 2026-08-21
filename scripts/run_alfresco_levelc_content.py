#!/usr/bin/env python3
"""Alfresco Level-C content-overwrite launcher.

What this is
------------
The committed target ``targets/alfresco_content_update.json`` describes the
Alfresco *content* overwrite request shape but deliberately carries no
credential and no concrete node id -- it ends in the placeholder
``__ALFRESCO_NODE_ID__``.  This launcher supplies both at runtime and then runs
the *production* harness, ``nv_http_harness.py``, unmodified:

    validate credentials (env only, fail-closed)
      -> sanitize the child environment of every ambient proxy variable
      -> preflight the real service (unauthenticated 401, authenticated 200)
      -> resolve the one dedicated file (never creating a node here)
      -> render a run-scoped config with the resolved node id (outside Git)
      -> feed nv_http_harness.py one ``.http`` seed per payload
      -> download the content back and compare bytes/length/SHA-256
      -> emit a sanitized summary

Why the ``.http`` seed mode and not ``body_only_mode``
-----------------------------------------------------
``body_only_mode`` routes the stdin bytes through ``body_validate`` ->
``normalize_json_body_or_none``, which returns ``None`` for anything that is
not JSON; the harness then returns without issuing a request.  It also pins
``Content-Type: application/json``.  Raw content therefore cannot survive that
mode.  The harness's other input representation -- a ``.http`` seed of
request-line / headers / blank line / body -- carries an arbitrary body and an
explicit Content-Type, so the content path uses that, with no harness change.

Known harness transform (see harness_safe_payload)
--------------------------------------------------
``parse_http_seed`` does ``text.splitlines()`` then ``"\n".join(...)``.  That
normalises CRLF to LF, drops a trailing newline, and decodes with
``errors="ignore"`` (so it is not binary-safe).  Rather than pretend otherwise,
this launcher refuses to send any payload the harness would alter, so
"bytes sent" and "bytes intended" are always the same object.

Reuse
-----
The credential gate, proxy sanitation, dedicated-node resolution and preflight
are imported unchanged from the independently verified metadata launcher.  That
file is not modified by this round.

What this is NOT
----------------
Not a fuzzing campaign: no afl-fuzz, no mutation, no scheduler, no MAB, no
reward feedback.  Not multipart upload.  No node is created, renamed or
deleted, and no metadata property is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_alfresco_levelc_metadata as metadata  # noqa: E402  (verified helpers)

# --- reused, independently verified contracts ------------------------------
LevelCAbort = metadata.LevelCAbort
require_credentials = metadata.require_credentials
sanitize_child_env = metadata.sanitize_child_env
build_direct_opener = metadata.build_direct_opener
resolve_dedicated_node = metadata.resolve_dedicated_node
preflight = metadata.preflight
docker_health = metadata.docker_health
harness_command = metadata.harness_command
status_path_for = metadata.status_path_for
run_scoped_dir = metadata.run_scoped_dir

UUID_RE = metadata.UUID_RE
API_BASE = metadata.API_BASE
DEDICATED_PARENT = metadata.DEDICATED_PARENT
DEDICATED_FOLDER_NAME = metadata.DEDICATED_FOLDER_NAME
DEDICATED_FILE_NAME = metadata.DEDICATED_FILE_NAME
NODE_ID_PLACEHOLDER = metadata.NODE_ID_PLACEHOLDER
PROXY_ENV_NAMES = metadata.PROXY_ENV_NAMES

# --- content-specific ------------------------------------------------------
TEMPLATE_PATH = REPO_ROOT / "targets" / "alfresco_content_update.json"
HARNESS_PATH = REPO_ROOT / "nv_http_harness.py"
ENDPOINT_NAME = "content_update"
CONTENT_SUFFIX = "/content"
CONTENT_TYPE = "text/plain; charset=utf-8"


def content_path_for(node_id: str) -> str:
    return f"{API_BASE}/nodes/{node_id}{CONTENT_SUFFIX}"


def render_target_config(node_id: str, out_path: Path,
                         template_path: Path = TEMPLATE_PATH) -> Path:
    """Substitute the resolved node id into a run-scoped copy of the template.

    The committed template is read-only here: substitution happens exactly
    once, into a file outside the repository.  A node id that is not a bare
    UUID is refused, so a path fragment can never be spliced into the URL.
    """
    node_id = str(node_id).strip()
    if not UUID_RE.match(node_id):
        raise LevelCAbort("resolved node id is not a bare Alfresco UUID")

    out_path = Path(out_path)
    if str(out_path.resolve()).startswith(str(REPO_ROOT.resolve()) + os.sep):
        raise LevelCAbort(
            f"rendered config must stay outside the committed tree: {out_path}")

    text = Path(template_path).read_text(encoding="utf-8")
    occurrences = text.count(NODE_ID_PLACEHOLDER)
    if occurrences != 1:
        raise LevelCAbort(
            f"template must carry exactly one {NODE_ID_PLACEHOLDER} "
            f"(found {occurrences})")

    rendered = text.replace(NODE_ID_PLACEHOLDER, node_id, 1)
    if NODE_ID_PLACEHOLDER in rendered:
        raise LevelCAbort("placeholder survived rendering")

    cfg = json.loads(rendered)
    if cfg["endpoints"][0]["path"] != content_path_for(node_id):
        raise LevelCAbort("rendered endpoint path does not target the node's content")
    if int(cfg.get("body_only_mode", 0)) == 1:
        raise LevelCAbort("content path cannot run under JSON body_only_mode")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    return out_path


def harness_env(ambient: dict, config_path: Path, run_dir: Path,
                credentials: tuple[str, str]) -> dict:
    env = sanitize_child_env(ambient)
    env["NV_TARGET_CONFIG"] = str(config_path)
    env["NV_STATUS_PATH"] = str(status_path_for(run_dir))
    env["NV_PROBE_PATH"] = str(run_dir / "nv_probe.json")
    env["NV_STATE_DB"] = str(run_dir / "nv_state_db.json")
    env["NV_CTX_PATH"] = str(run_dir / "nv_ctx.json")
    env["NV_ERR_DIR"] = str(run_dir / "err_cases")
    env["ALFRESCO_USER"], env["ALFRESCO_PASS"] = credentials
    return env


# ---------------------------------------------------------------------------
# Payloads and the .http seed
# ---------------------------------------------------------------------------
PAYLOAD_SPECS = {
    "A": ("NV_LEVELC_CONTENT_SELFTEST_A", 2, 24),
    "B": ("NV_LEVELC_CONTENT_SELFTEST_B", 9, 52),
    "C": ("NV_LEVELC_CONTENT_SELFTEST_C", 1, 12),
}


def build_payload(marker: str, filler_lines: int, width: int) -> bytes:
    """Deterministic, obviously synthetic, LF-only, no trailing newline."""
    lines = [marker]
    lines += [f"line{i:03d}-" + ("x" * width) for i in range(filler_lines)]
    return "\n".join(lines).encode("utf-8")


def payload_for(label: str) -> bytes:
    return build_payload(*PAYLOAD_SPECS[label])


def harness_delivered_bytes(payload: bytes) -> bytes:
    """Model nv_http_harness.parse_http_seed's splitlines()/join transform."""
    text = payload.decode("utf-8", errors="ignore")
    return "\n".join(text.splitlines()).encode("utf-8")


def harness_safe_payload(payload: bytes) -> bytes:
    """Refuse anything the harness's seed parser would silently alter.

    ``parse_http_seed`` decodes with ``errors="ignore"``, splits on
    ``splitlines()`` and rejoins with ``\\n``.  That drops a trailing newline,
    folds CRLF to LF and discards undecodable bytes.  Rather than claim a
    byte-exactness the harness cannot deliver, refuse such payloads outright.
    """
    if not payload:
        raise LevelCAbort("empty content payload")
    if harness_delivered_bytes(payload) != payload:
        raise LevelCAbort(
            "payload would be altered by the harness seed parser "
            "(CRLF, trailing newline or non-UTF-8 bytes are not preserved)")
    return payload


def build_http_seed(path: str, payload: bytes,
                    content_type: str = CONTENT_TYPE) -> bytes:
    """One request-line / headers / blank line / body seed for the harness."""
    harness_safe_payload(payload)
    if payload.startswith(b"\n"):
        raise LevelCAbort("payload may not begin with a blank line")
    head = f"PUT {path}\nContent-Type: {content_type}\n\n"
    return head.encode("utf-8") + payload


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compare_content(expected: bytes, observed: bytes) -> dict:
    """Byte, length and SHA-256 comparison -- never substring containment."""
    return {
        "expected_len": len(expected),
        "observed_len": len(observed),
        "length_match": len(expected) == len(observed),
        "expected_sha256": sha256(expected),
        "observed_sha256": sha256(observed),
        "sha256_match": sha256(expected) == sha256(observed),
        "bytes_exact": expected == observed,
    }


# ---------------------------------------------------------------------------
# Client: the verified read/create client plus a raw content download
# ---------------------------------------------------------------------------
class ContentClient(metadata.AlfrescoClient):
    """Adds a raw byte download; inherits the verified proxy-free opener."""

    def get_content_bytes(self, node_id: str) -> tuple[int, bytes]:
        req = urllib.request.Request(
            self.base + content_path_for(node_id), method="GET",
            headers={"Authorization": self._auth})
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.getcode(), resp.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()
        except urllib.error.URLError as exc:
            raise LevelCAbort(f"content download unreachable: {exc.reason}")


# ---------------------------------------------------------------------------
# One bounded round through the production harness
# ---------------------------------------------------------------------------
def run_round(label: str, config_path: Path, run_dir: Path,
              credentials: tuple[str, str], client: ContentClient,
              node_id: str) -> dict:
    payload = payload_for(label)
    seed = build_http_seed(content_path_for(node_id), payload)
    env = harness_env(dict(os.environ), config_path, run_dir, credentials)

    proc = subprocess.Popen(harness_command(), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    _, err = proc.communicate(input=seed, timeout=120)

    status_file = status_path_for(run_dir)
    if not status_file.is_file():
        raise LevelCAbort(f"harness wrote no status document for round {label}")
    status = json.loads(status_file.read_text(encoding="utf-8"))

    readback_code, downloaded = client.get_content_bytes(node_id)
    node = client.get_node(node_id)
    return {
        "label": label,
        "marker": PAYLOAD_SPECS[label][0],
        "harness_returncode": proc.returncode,
        "harness_stderr_bytes": len(err),
        "method": status.get("method"),
        "http_code": status.get("http_code"),
        "class": status.get("class"),
        "exec_seq": status.get("exec_seq"),
        "latency_ms": status.get("latency_ms"),
        "readback_http": readback_code,
        "readback": compare_content(payload, downloaded),
        "node_name": node.get("name"),
        "aspects": sorted(node.get("aspectNames") or []),
        "version_count": client.version_count(node_id),
    }


# ---------------------------------------------------------------------------
# State guards
# ---------------------------------------------------------------------------
def assert_reused_existing_node(node: dict) -> None:
    """This round writes content only; it must never bring a node into being."""
    if node.get("created_folder") or node.get("created_file"):
        raise LevelCAbort(
            "content round must reuse the existing dedicated resource; "
            "resolution created a node instead")


def assert_not_versionable(node: dict) -> None:
    if "cm:versionable" in (node.get("aspect_names") or []):
        raise LevelCAbort(
            "dedicated node carries cm:versionable; content overwrite would "
            "grow version history")


def assert_name_unchanged(before: str, after: str) -> None:
    if before != after:
        raise LevelCAbort(f"cm:name changed during the run: {before!r} -> {after!r}")


def assert_no_version_growth(before: int, after: int) -> None:
    if after > before:
        raise LevelCAbort(f"version history grew from {before} to {after}")


def sanitized_summary(credentials, node: dict, rounds: list, **extra) -> dict:
    """The summary shape.  Credentials and node ids never appear."""
    del credentials  # accepted so callers cannot forget to route them here
    summary = {
        "credentials": "REDACTED",
        "auth_header": "REDACTED",
        "node": {
            "file": "<RESOURCE-ID-REDACTED>",
            "folder": "<RESOURCE-ID-REDACTED>",
            "created_folder": node.get("created_folder"),
            "created_file": node.get("created_file"),
            "aspects_at_resolution": sorted(node.get("aspect_names") or []),
        },
        "rounds": [dict(r) for r in rounds],
    }
    summary.update(extra)
    return summary


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
ROUND_LABELS = ("A", "B", "C")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alfresco Level-C content smoke")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--keep-run-dir", action="store_true")
    args = parser.parse_args(argv)

    credentials = require_credentials()          # fail-closed, before any I/O
    base = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))["base"]
    client = ContentClient(base, credentials)

    run_dir = Path(args.run_dir) if args.run_dir else run_scoped_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence = Path(args.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)

    try:
        pre = preflight(client)
        node = resolve_dedicated_node(client)
        assert_reused_existing_node(node)
        assert_not_versionable(node)

        node_id = node["file_id"]
        config_path = render_target_config(node_id, run_dir / "target.json")

        before_node = client.get_node(node_id)
        before_versions = client.version_count(node_id)
        _, before_bytes = client.get_content_bytes(node_id)

        rounds = [run_round(label, config_path, run_dir, credentials, client, node_id)
                  for label in ROUND_LABELS]

        after_node = client.get_node(node_id)
        after_versions = client.version_count(node_id)
        _, after_bytes = client.get_content_bytes(node_id)

        assert_name_unchanged(before_node.get("name"), after_node.get("name"))
        assert_no_version_growth(before_versions, after_versions)

        summary = sanitized_summary(
            credentials, node, rounds,
            preflight=pre, base=base, endpoint=ENDPOINT_NAME,
            harness=str(HARNESS_PATH.relative_to(REPO_ROOT)),
            rendered_config=str(config_path),
            status_path=str(status_path_for(run_dir)),
            state={
                "name_before": before_node.get("name"),
                "name_after": after_node.get("name"),
                "name_unchanged": before_node.get("name") == after_node.get("name"),
                "aspects_before": sorted(before_node.get("aspectNames") or []),
                "aspects_after": sorted(after_node.get("aspectNames") or []),
                "versionable_introduced":
                    "cm:versionable" in (after_node.get("aspectNames") or []),
                "version_count_before": before_versions,
                "version_count_after": after_versions,
                "content_len_before": len(before_bytes),
                "content_len_after": len(after_bytes),
                "content_sha256_before": sha256(before_bytes),
                "content_sha256_after": sha256(after_bytes),
                "final_equals_round_c": after_bytes == payload_for("C"),
                "final_sha256_expected": sha256(payload_for("C")),
            },
        )
        (evidence / "content_launcher_run.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))

        bad = [r for r in rounds
               if r["http_code"] != 200 or not r["readback"]["bytes_exact"]
               or not r["exec_seq"] or r["harness_returncode"] != 0]
        if bad:
            print(f"LEVEL_C_CONTENT = FAIL ({len(bad)} bad rounds)", file=sys.stderr)
            return 1

        seqs = [r["exec_seq"] for r in rounds]
        if len(set(seqs)) != len(seqs) or seqs != sorted(seqs):
            print(f"LEVEL_C_CONTENT = FAIL (exec_seq {seqs})", file=sys.stderr)
            return 1
        if not summary["state"]["final_equals_round_c"]:
            print("LEVEL_C_CONTENT = FAIL (final bytes are not round C)", file=sys.stderr)
            return 1

        print("LEVEL_C_CONTENT = PASS")
        return 0
    finally:
        if not args.keep_run_dir:
            shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
