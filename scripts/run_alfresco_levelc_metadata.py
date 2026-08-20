#!/usr/bin/env python3
"""Alfresco Level-C metadata-update launcher.

What this is
------------
The committed target template ``targets/alfresco_metadata_update.json``
describes the Alfresco metadata-update request shape but deliberately carries
*no* credential and *no* concrete node id -- it ends in the placeholder
``__ALFRESCO_NODE_ID__``.  This launcher supplies both at runtime and then runs
the *production* harness, ``nv_http_harness.py``, unmodified:

    validate credentials (env only, fail-closed)
      -> sanitize the child environment of every ambient proxy variable
      -> preflight the real service (unauthenticated 401, authenticated 200)
      -> resolve exactly one dedicated folder + file, creating them if absent
      -> render a run-scoped config with the resolved node id (outside Git)
      -> run nv_http_harness.py once per marker round
      -> read the metadata back and check the current marker
      -> emit a sanitized summary

What this is NOT
----------------
It is not a fuzzing campaign: no afl-fuzz, no mutation, no scheduler, no MAB
and no reward feedback.  Those stay in the existing AFL++ chain.  This is a
bounded production-harness smoke over one dedicated test node.

Credential containment
----------------------
``ALFRESCO_USER``/``ALFRESCO_PASS`` are read from the environment, handed
straight to the child process environment, and never written to argv, stdout,
the rendered config or the evidence.  The Basic header is assembled inside the
production harness (and, for the launcher's own read-only calls, in-process);
it is never logged.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "targets" / "alfresco_metadata_update.json"
HARNESS_PATH = REPO_ROOT / "nv_http_harness.py"
BODY_RULES_PATH = REPO_ROOT / "validity" / "alfresco_metadata_update_rules.json"

NODE_ID_PLACEHOLDER = "__ALFRESCO_NODE_ID__"
ENDPOINT_NAME = "metadata_update"

API_BASE = "/alfresco/api/-default-/public/alfresco/versions/1"
ROOT_PROBE_PATH = API_BASE + "/nodes/-root-"

# The dedicated Level-C namespace.  Nothing outside it is ever read, written
# or created; see resolve_dedicated_node().
DEDICATED_PARENT = "-my-"
DEDICATED_FOLDER_NAME = "NV_AFL_REAL_PLATFORM_CALIBRATION"
DEDICATED_FILE_NAME = "nv-afl-levelc-metadata.txt"

CREDENTIAL_ENV_NAMES = ("ALFRESCO_USER", "ALFRESCO_PASS")

# urllib inherits these from the ambient environment and does *not* honour the
# ``127.*`` glob form this machine's no_proxy uses, so a loopback request would
# silently leave through the proxy.  Every one of them is stripped, and
# no_proxy is rewritten to explicit hosts urllib does match.
PROXY_ENV_NAMES = (
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY",
)
NO_PROXY_VALUE = "127.0.0.1,localhost"

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

REQUIRED_CONTAINERS = ("alfresco", "postgres", "proxy")


class LevelCAbort(RuntimeError):
    """A Level-C precondition failed.  Never carries a credential value."""


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
def require_credentials(env: dict | None = None) -> tuple[str, str]:
    """Return (user, password) from the environment, or abort.

    Fail-closed: missing, empty and whitespace-only are all aborts, and the
    message names only the variable -- never its value.  There is no default
    and no fallback, so a misconfigured run can never turn into a silent 401
    campaign against the real service.
    """
    source = os.environ if env is None else env
    values = []
    for name in CREDENTIAL_ENV_NAMES:
        raw = source.get(name)
        if raw is None or not str(raw).strip():
            raise LevelCAbort(
                f"{name} must be supplied through the runtime environment "
                f"(missing, empty or whitespace-only); no fallback credential exists"
            )
        values.append(str(raw))
    return values[0], values[1]


def _basic_header(credentials: tuple[str, str]) -> str:
    user, password = credentials
    blob = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return "Basic " + blob


# ---------------------------------------------------------------------------
# Proxy sanitation
# ---------------------------------------------------------------------------
def sanitize_child_env(ambient: dict | None = None) -> dict:
    """A copy of the environment with every proxy variable neutralised."""
    child = dict(os.environ if ambient is None else ambient)
    for name in PROXY_ENV_NAMES:
        child.pop(name, None)
    child["no_proxy"] = NO_PROXY_VALUE
    child["NO_PROXY"] = NO_PROXY_VALUE
    return child


def build_direct_opener() -> urllib.request.OpenerDirector:
    """An opener for the launcher's own calls that never consults a proxy.

    ``ProxyHandler({})`` is the only reliable way to stop urllib reading the
    ambient proxy variables; no_proxy matching is not enough here.
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ---------------------------------------------------------------------------
# Run-scoped, non-committed paths
# ---------------------------------------------------------------------------
def run_scoped_dir(pid: int | None = None) -> Path:
    return Path("/tmp") / f"nv-alfresco-levelc-{os.getpid() if pid is None else pid}"


def status_path_for(run_dir: Path) -> Path:
    return run_dir / "nv_http_status.json"


def render_target_config(node_id: str, out_path: Path,
                         template_path: Path = TEMPLATE_PATH) -> Path:
    """Substitute the resolved node id into a run-scoped copy of the template.

    The committed template is read-only here: substitution happens exactly
    once, into a file outside the repository.  A node id that is not a bare
    UUID is refused, so a path fragment can never be spliced into the request
    URL.
    """
    node_id = str(node_id).strip()
    if not UUID_RE.match(node_id):
        raise LevelCAbort("resolved node id is not a bare Alfresco UUID")

    out_path = Path(out_path)
    if str(out_path.resolve()).startswith(str(REPO_ROOT.resolve()) + os.sep):
        raise LevelCAbort(
            "rendered config must stay outside the committed tree: " f"{out_path}"
        )

    text = Path(template_path).read_text(encoding="utf-8")
    occurrences = text.count(NODE_ID_PLACEHOLDER)
    if occurrences != 1:
        raise LevelCAbort(
            f"template must carry exactly one {NODE_ID_PLACEHOLDER} "
            f"(found {occurrences})"
        )

    rendered = text.replace(NODE_ID_PLACEHOLDER, node_id, 1)
    if NODE_ID_PLACEHOLDER in rendered:
        raise LevelCAbort("placeholder survived rendering")

    cfg = json.loads(rendered)  # must still be a valid harness config
    expected = f"{API_BASE}/nodes/{node_id}"
    if cfg["endpoints"][0]["path"] != expected:
        raise LevelCAbort("rendered endpoint path does not target the resolved node")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# The production harness
# ---------------------------------------------------------------------------
def harness_command() -> list[str]:
    """The one HTTP target this repository has.  No mock, no replacement."""
    return [sys.executable, str(HARNESS_PATH.resolve())]


def harness_env(ambient: dict, config_path: Path, run_dir: Path,
                credentials: tuple[str, str]) -> dict:
    env = sanitize_child_env(ambient)
    env["NV_TARGET_CONFIG"] = str(config_path)
    env["NV_ENDPOINT_NAME"] = ENDPOINT_NAME
    env["NV_BODY_RULES"] = str(BODY_RULES_PATH)
    env["NV_STATUS_PATH"] = str(status_path_for(run_dir))
    env["NV_PROBE_PATH"] = str(run_dir / "nv_probe.json")
    env["NV_STATE_DB"] = str(run_dir / "nv_state_db.json")
    env["NV_CTX_PATH"] = str(run_dir / "nv_ctx.json")
    env["NV_ERR_DIR"] = str(run_dir / "err_cases")
    env["NV_BODY_VALID_STATS"] = str(run_dir / "nv_body_valid_stats.json")
    env["ALFRESCO_USER"], env["ALFRESCO_PASS"] = credentials
    return env


# ---------------------------------------------------------------------------
# Request body / read-back contract
# ---------------------------------------------------------------------------
def expected_properties(marker: str) -> dict:
    """The full metadata state one round writes.

    Only cm:title and cm:description.  cm:name is never touched, so the node
    can never be renamed or collide with a sibling.
    """
    return {"cm:title": f"{marker} title", "cm:description": f"{marker} description"}


def metadata_body(marker: str) -> str:
    return json.dumps({"properties": expected_properties(marker)},
                      ensure_ascii=False, separators=(",", ":"))


def marker_matches(node: dict, marker: str) -> bool:
    """Exact equality, not containment: the round is a full overwrite."""
    props = node.get("properties") or {}
    return all(props.get(key) == value
               for key, value in expected_properties(marker).items())


# ---------------------------------------------------------------------------
# Alfresco client (read/create only, inside the dedicated namespace)
# ---------------------------------------------------------------------------
class AlfrescoClient:
    def __init__(self, base: str, credentials: tuple[str, str], timeout: float = 15.0):
        self.base = base.rstrip("/")
        self._auth = _basic_header(credentials)
        self.timeout = timeout
        self.opener = build_direct_opener()

    def request(self, method: str, path: str, body: dict | None = None,
                authenticated: bool = True) -> tuple[int, dict]:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if authenticated:
            headers["Authorization"] = self._auth

        req = urllib.request.Request(self.base + path, data=data,
                                     method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                code = resp.getcode()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            code = int(exc.code)
        except urllib.error.URLError as exc:
            raise LevelCAbort(f"Alfresco {method} {path} unreachable: {exc.reason}")

        try:
            payload = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except Exception:
            payload = {}
        return code, payload if isinstance(payload, dict) else {}

    def _entries(self, payload: dict) -> list[dict]:
        listing = payload.get("list") or {}
        return [item.get("entry", {}) for item in listing.get("entries", [])]

    def list_children(self, parent_id: str) -> list[dict]:
        out: list[dict] = []
        skip = 0
        while True:
            code, payload = self.request(
                "GET",
                f"{API_BASE}/nodes/{parent_id}/children"
                f"?maxItems=100&skipCount={skip}&include=aspectNames,properties",
            )
            if code != 200:
                raise LevelCAbort(f"listing children of {parent_id} returned HTTP {code}")
            batch = self._entries(payload)
            out.extend(batch)
            pagination = (payload.get("list") or {}).get("pagination") or {}
            if not pagination.get("hasMoreItems"):
                break
            skip += len(batch) or 100
        return out

    def create_child(self, parent_id: str, name: str, node_type: str) -> dict:
        code, payload = self.request(
            "POST", f"{API_BASE}/nodes/{parent_id}/children",
            body={"name": name, "nodeType": node_type},
        )
        if code not in (200, 201):
            raise LevelCAbort(f"creating dedicated {node_type} returned HTTP {code}")
        return payload.get("entry", {})

    def get_node(self, node_id: str) -> dict:
        code, payload = self.request(
            "GET", f"{API_BASE}/nodes/{node_id}?include=aspectNames,properties")
        if code != 200:
            raise LevelCAbort(f"reading node returned HTTP {code}")
        return payload.get("entry", {})

    def version_count(self, node_id: str) -> int:
        code, payload = self.request("GET", f"{API_BASE}/nodes/{node_id}/versions")
        if code != 200:
            return -1
        return len(self._entries(payload))


# ---------------------------------------------------------------------------
# Dedicated node resolution
# ---------------------------------------------------------------------------
def _unique_match(entries: list[dict], name: str, *, want_folder: bool,
                  kind: str) -> dict | None:
    key = "isFolder" if want_folder else "isFile"
    matches = [e for e in entries
               if str(e.get("name", "")) == name and bool(e.get(key))]
    if len(matches) > 1:
        raise LevelCAbort(
            f"{len(matches)} dedicated {kind} entries named {name!r}; refusing to "
            f"guess which one is the Level-C test node"
        )
    return matches[0] if matches else None


def resolve_dedicated_node(client) -> dict:
    """Find -- or, only inside the dedicated namespace, create -- the test node.

    Exactly one folder and exactly one file may match.  Zero is a controlled
    create; more than one is an abort, because an ambiguous match could put a
    write on an unknown historical node.  Nothing outside the dedicated folder
    is ever selected, and cm:name is never modified.
    """
    siblings = client.list_children(DEDICATED_PARENT)
    folder = _unique_match(siblings, DEDICATED_FOLDER_NAME,
                           want_folder=True, kind="folder")
    created_folder = folder is None
    if created_folder:
        folder = client.create_child(DEDICATED_PARENT, DEDICATED_FOLDER_NAME, "cm:folder")
    folder_id = str(folder.get("id", ""))
    if not folder_id:
        raise LevelCAbort("dedicated folder has no node id")

    children = client.list_children(folder_id)
    node = _unique_match(children, DEDICATED_FILE_NAME, want_folder=False, kind="file")
    created_file = node is None
    if created_file:
        node = client.create_child(folder_id, DEDICATED_FILE_NAME, "cm:content")
    file_id = str(node.get("id", ""))
    if not file_id:
        raise LevelCAbort("dedicated file has no node id")

    parent_id = str(node.get("parentId", "") or "")
    if parent_id and parent_id != folder_id:
        raise LevelCAbort(
            "resolved file is not a child of the dedicated folder; refusing to "
            "write to a node of unknown ownership"
        )

    return {
        "folder_id": folder_id,
        "file_id": file_id,
        "created_folder": created_folder,
        "created_file": created_file,
        "aspect_names": list(node.get("aspectNames") or []),
    }


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
def sanitized_summary(credentials: tuple[str, str], node: dict,
                      rounds: list[dict], **extra) -> dict:
    """The summary shape.  Credentials are replaced, never formatted in."""
    del credentials  # accepted so callers cannot forget to route them here
    summary = {
        "credentials": "REDACTED",
        "auth_header": "REDACTED",
        "node": dict(node),
        "rounds": [dict(r) for r in rounds],
    }
    summary.update(extra)
    return summary


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
def docker_health() -> list[dict]:
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout
    except Exception as exc:
        raise LevelCAbort(f"docker inspection failed: {exc}")

    rows = [line.split("\t") for line in out.splitlines() if "\t" in line]
    found = []
    for needle in REQUIRED_CONTAINERS:
        # The Alfresco compose stack only; the co-located O2OA stack has its
        # own postgres and must never satisfy this check.
        hit = [r for r in rows if needle in r[0] and not r[0].startswith("o2oa")]
        if not hit:
            raise LevelCAbort(f"required container not running: {needle}")
        name, status = hit[0][0], hit[0][1]
        if "Up" not in status:
            raise LevelCAbort(f"container {name} is not Up: {status}")
        found.append({"name": name, "status": status})
    return found


def preflight(client: AlfrescoClient) -> dict:
    containers = docker_health()

    code, _ = client.request("GET", ROOT_PROBE_PATH, authenticated=False)
    if code != 401:
        raise LevelCAbort(f"unauthenticated root probe returned {code}, expected 401")

    auth_code, _ = client.request("GET", ROOT_PROBE_PATH)
    if auth_code != 200:
        raise LevelCAbort(f"authenticated root probe returned {auth_code}, expected 200")

    return {
        "containers": containers,
        "unauthenticated_root": code,
        "authenticated_root": auth_code,
    }


# ---------------------------------------------------------------------------
# Bounded production-harness smoke
# ---------------------------------------------------------------------------
def run_round(marker: str, config_path: Path, run_dir: Path,
              credentials: tuple[str, str], client: AlfrescoClient,
              node_id: str) -> dict:
    body = metadata_body(marker).encode("utf-8")
    env = harness_env(dict(os.environ), config_path, run_dir, credentials)

    proc = subprocess.Popen(harness_command(), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    _, err = proc.communicate(input=body, timeout=120)

    status_file = status_path_for(run_dir)
    if not status_file.is_file():
        raise LevelCAbort(f"harness wrote no status document for {marker}")
    status = json.loads(status_file.read_text(encoding="utf-8"))

    node = client.get_node(node_id)
    return {
        "marker": marker,
        "harness_returncode": proc.returncode,
        "harness_stderr_bytes": len(err),
        "method": status.get("method"),
        "path_tail": str(status.get("path", "")).rsplit("/", 1)[-1],
        "http_code": status.get("http_code"),
        "class": status.get("class"),
        "exec_seq": status.get("exec_seq"),
        "latency_ms": status.get("latency_ms"),
        "readback_match": marker_matches(node, marker),
        "readback_aspects": list(node.get("aspectNames") or []),
        "version_count": client.version_count(node_id),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--evidence-dir", default=str(REPO_ROOT / "out" / "alfresco_levelc_metadata"))
    parser.add_argument("--keep-run-dir", action="store_true")
    args = parser.parse_args(argv)

    credentials = require_credentials()
    base = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))["base"]
    client = AlfrescoClient(base, credentials)

    run_dir = run_scoped_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence = Path(args.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)

    try:
        pre = preflight(client)
        node = resolve_dedicated_node(client)
        if "cm:versionable" in node["aspect_names"]:
            raise LevelCAbort(
                "dedicated node carries cm:versionable; Option-C assumes metadata "
                "updates do not grow version history"
            )

        config_path = render_target_config(node["file_id"], run_dir / "target.json")
        baseline_versions = client.version_count(node["file_id"])

        rounds = []
        for index in range(1, args.rounds + 1):
            rounds.append(run_round(f"NV_LEVELC_SMOKE_{index}", config_path, run_dir,
                                    credentials, client, node["file_id"]))

        summary = sanitized_summary(
            credentials, node, rounds,
            preflight=pre,
            base=base,
            endpoint=ENDPOINT_NAME,
            harness=str(HARNESS_PATH.relative_to(REPO_ROOT)),
            rendered_config=str(config_path),
            status_path=str(status_path_for(run_dir)),
            baseline_version_count=baseline_versions,
        )
        (evidence / "launcher_run.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))

        failures = [r for r in rounds
                    if r["http_code"] != 200 or not r["readback_match"]
                    or not r["exec_seq"]]
        if failures:
            print(f"LEVEL_C = FAIL ({len(failures)} bad rounds)", file=sys.stderr)
            return 1
        if len({r["exec_seq"] for r in rounds}) != len(rounds):
            print("LEVEL_C = FAIL (exec_seq collision)", file=sys.stderr)
            return 1
        print("LEVEL_C = PASS")
        return 0
    finally:
        if not args.keep_run_dir:
            shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
