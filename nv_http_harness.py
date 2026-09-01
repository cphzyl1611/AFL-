#!/usr/bin/env python3
import sys, json, urllib.request, urllib.error,time,os,zlib
import base64
import hashlib
import fcntl
from nv_state_probe import update_state
from urllib.parse import urlparse
from nv_body_valid import body_validate
from nv_http_body_adapter import HttpBodyAdapterError, extract_http_body
STATUS_PATH = os.getenv("NV_STATUS_PATH", "/tmp/nv_http_status.json")

DEFAULT_CFG = {
    "base": "http://127.0.0.1:8080",
    "health": "/health",
    "endpoints": [
        {"method": "POST", "path": "/api/doc/create"},
    ],
    "biz_fields": ["code", "errCode", "errorCode", "status", "message", "msg"],
}

def resolve_health_url(cfg):
    health_url = str(cfg.get("health_url", "")).strip()
    if health_url:
        return health_url
    return str(cfg.get("base", DEFAULT_CFG["base"])).rstrip("/") + str(
        cfg.get("health", DEFAULT_CFG["health"])
    )

def load_target_config():
    cfg_path = os.getenv("NV_TARGET_CONFIG", "").strip()
    cfg = dict(DEFAULT_CFG)
    if cfg_path:
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if isinstance(user_cfg, dict):
                cfg.update({k: user_cfg[k] for k in user_cfg.keys()})
        except Exception as e:
            # 配置坏了也别崩：回退默认
            pass

    # 规范化 base（去掉末尾 /）
    base = str(cfg.get("base", DEFAULT_CFG["base"])).rstrip("/")
    cfg["base"] = base if base else DEFAULT_CFG["base"]

    # 规范化 health
    health = str(cfg.get("health", DEFAULT_CFG["health"]))
    if not health.startswith("/"):
        health = "/" + health
    cfg["health"] = health

    # 生成白名单：按 endpoints 的 path
    eps = cfg.get("endpoints", DEFAULT_CFG["endpoints"])
    allowed = set()
    if isinstance(eps, list):
        for it in eps:
            if isinstance(it, dict):
                p = str(it.get("path", "")).strip()
                if p and not p.startswith("/"):
                    p = "/" + p
                if p:
                    allowed.add(p)
    # health 永远允许
    allowed.add(cfg["health"])
    cfg["_allowed_paths"] = allowed

    # 允许 methods（按 endpoints 里的 method 汇总；为空则默认常用）
    allowed_methods = set()
    if isinstance(eps, list):
        for it in eps:
            if isinstance(it, dict):
                m = str(it.get("method", "")).upper().strip()
                if m:
                    allowed_methods.add(m)
    if not allowed_methods:
        allowed_methods = {"GET", "POST", "PUT", "DELETE", "PATCH"}
    cfg["_allowed_methods"] = allowed_methods

    # biz_fields 规范化
    bfs = cfg.get("biz_fields", DEFAULT_CFG["biz_fields"])
    if not isinstance(bfs, list) or not bfs:
        bfs = DEFAULT_CFG["biz_fields"]
    cfg["biz_fields"] = [str(x) for x in bfs]

    return cfg

def get_named_endpoint(cfg, endpoint_name: str):
    eps = cfg.get("endpoints", [])
    for ep in eps:
        if not isinstance(ep, dict):
            continue
        if str(ep.get("name", "")).strip() == endpoint_name:
            method = str(ep.get("method", "POST")).upper().strip()
            path = str(ep.get("path", "/")).strip()
            if not path.startswith("/"):
                path = "/" + path
            return method, path
    raise RuntimeError(f"endpoint not found: {endpoint_name}")

AUTH_ALLOWED_KEYS = {
    # "none" assembles no credential at all, so the bearer-shaped keys that
    # tracked configs still carry beside it (header/prefix/token_env) name
    # nothing that is ever read.  They stay accepted for backward
    # compatibility; every other key -- credential-like or merely unknown --
    # is still rejected by the same strict schema check.
    "none": frozenset({"type", "header", "prefix", "token_env"}),
    "basic": frozenset({"type", "header", "username_env", "password_env"}),
    "bearer": frozenset({"type", "header", "token_env", "prefix"}),
    "raw_token": frozenset({"type", "header", "token_env", "also_cookie"}),
}


def _require_runtime_credential(var_name: str) -> str:
    """Read one credential part from the environment, or abort.

    Fail-closed by construction: there is no default and no fallback, and the
    abort message names only the variable -- never its value.
    """
    value = os.getenv(var_name)
    if value is None or not value.strip():
        raise RuntimeError(
            f"{var_name} must be supplied through the runtime environment "
            f"(missing, empty or whitespace-only); no fallback credential exists"
        )
    return value


def _normalized_auth(auth: dict, atype: str) -> dict:
    normalized = {str(key).casefold(): value for key, value in auth.items()}
    allowed = AUTH_ALLOWED_KEYS.get(atype)
    if allowed is None:
        raise RuntimeError(f"unsupported auth type: {atype}")
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise RuntimeError(
            "auth config contains unknown or credential-like keys: "
            + ", ".join(unknown)
        )
    return normalized


def _basic_auth_header(auth: dict) -> str:
    """Assemble a Basic credential in-process from environment values only."""
    user_env = str(auth["username_env"]).strip()
    pass_env = str(auth["password_env"]).strip()
    if not user_env or not pass_env:
        raise RuntimeError(
            "basic auth config must declare username_env and password_env"
        )
    user = _require_runtime_credential(user_env)
    password = _require_runtime_credential(pass_env)
    blob = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return "Basic " + blob


def apply_auth_headers(cfg, headers: dict) -> dict:
    auth = cfg.get("auth", {})
    if not isinstance(auth, dict):
        return headers

    auth_keys = {str(key).casefold(): value for key, value in auth.items()}
    atype = str(auth_keys.get("type", "none")).lower().strip()
    auth = _normalized_auth(auth_keys, atype)
    if atype == "none":
        return headers

    if atype == "basic":
        hname = str(auth.get("header", "Authorization")).strip() or "Authorization"
        headers[hname] = _basic_auth_header(auth)
        return headers

    token_env = str(auth.get("token_env", "NV_TOKEN")).strip() or "NV_TOKEN"
    token = _require_runtime_credential(token_env).strip()

    if atype == "bearer":
        hname = str(auth.get("header", "Authorization")).strip() or "Authorization"
        prefix = str(auth.get("prefix", "Bearer "))
        headers[hname] = f"{prefix}{token}"
        return headers

    if atype == "raw_token":
        hname = str(auth.get("header", "Authorization")).strip() or "Authorization"
        headers[hname] = token

        also_cookie = str(auth.get("also_cookie", "")).strip()
        if also_cookie:
            old_cookie = headers.get("Cookie", "").strip()
            new_cookie = f"{also_cookie}={token}"
            headers["Cookie"] = f"{old_cookie}; {new_cookie}" if old_cookie else new_cookie
        return headers

    return headers

SEQ = 0
ALLOWED_PATHS = {
  "/health",
  "/api/login",
  "/api/doc/create",
  "/api/doc/submit",
  "/api/doc/approve",
  "/api/doc/query",
}

def status_ledger_path() -> str:
    return os.getenv("NV_STATUS_LEDGER_PATH", STATUS_PATH + ".jsonl")


def append_status_record(record: dict) -> None:
    payload = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    path = status_ledger_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise OSError("status ledger short write")
            offset += written
        os.fsync(fd)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def seq_sidecar_path() -> str:
    """Where this status namespace keeps its execution counter.

    One sidecar per NV_STATUS_PATH, so instances with separate status paths
    (see fuzz_gui.py, which gives every instance its own) never share a
    counter.
    """
    return STATUS_PATH + ".seq"


def next_exec_seq() -> int:
    """Allocate the execution identity for this target execution.

    AFL++ runs this harness as ``-- python3 nv_http_harness.py``: a *fresh
    process per execution*, with no persistent-mode loop.  A module-level
    counter therefore restarts at 1 every time and cannot identify an
    execution -- which is exactly what the legacy ``SEQ`` field does.  The
    counter has to outlive the process, so it lives in a sidecar file next to
    the status document.

    Allocation is read-increment-persist under an exclusive ``flock`` so two
    harness processes sharing one status namespace can never be handed the
    same id.  The lock is held on the sidecar itself, so no extra lock file
    appears next to the evidence.

    Returns 0 if the counter cannot be maintained (unwritable directory).  The
    C consumer reads 0 as "not reported" and falls back to the legacy
    ``ts_ms ^ body_hash16`` stamp, so a degraded environment loses execution
    identity rather than the whole observation.
    """
    try:
        fd = os.open(seq_sidecar_path(), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        return 0

    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            raw = os.read(fd, 64).decode("utf-8", errors="ignore").strip()
        except OSError:
            raw = ""

        try:
            current = int(raw or "0")
        except ValueError:
            current = 0
        if current < 0:
            current = 0

        nxt = current + 1
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, str(nxt).encode("ascii"))
        os.fsync(fd)
        return nxt
    except OSError:
        return 0
    finally:
        # Neither unlock nor close may raise out of here: this sits on the
        # execution path of every request, and losing the identity is a
        # fallback, not a reason to fail the execution.
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass


def write_status(method, path, http_code, timeout=False, recovered=False, latency_ms=0,
                 body_hash16=0, ncov_delta=0, ncov_total=0, nall=0,
                 is_exception=0, recover_ms=0, validation_reject=0):
    global SEQ

    # class
    if timeout:
        cls = "timeout"
        code = -1
    else:
        code = int(http_code)
        if code == -2:
            cls = "conn_refused"
        elif 200 <= code < 300: cls = "2xx"
        elif 300 <= code < 400: cls = "3xx"
        elif 400 <= code < 500: cls = "4xx"
        elif 500 <= code < 600: cls = "5xx"
        else: cls = "other"

    # build payload first (st must exist before using it)
    SEQ += 1
    st = {
        # Legacy per-process counter.  Kept for historical evidence and older
        # consumers; it is always 1 because the process is per-execution.
        # exec_seq below is the real execution identity.
        "seq": SEQ,
        # One identity per target execution, allocated here so that every
        # outcome that reaches this function -- 2xx/3xx/4xx/5xx, timeout,
        # conn_refused, request exception -- carries one, and exactly one.
        # Testcases rejected by the validity layer return before reaching
        # write_status(), so they never mint an execution identity.
        "exec_seq": next_exec_seq(),
        "method": method,
        "path": path,
        "http_code": code,
        "class": cls,
        "timeout": 1 if timeout else 0,
        "recovered": 1 if recovered else 0,
        "latency_ms": int(latency_ms),
        "body_hash16": int(body_hash16),
        "ncov_delta": int(ncov_delta),
        "ncov_total": int(ncov_total),
        "nall": int(nall),
        "ts_ms": int(time.time() * 1000),
        "is_exception": int(is_exception),
        "recover_ms": int(recover_ms),
        "validation_reject": 1 if validation_reject else 0,
    }

    # atomic write
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, STATUS_PATH)
    append_status_record(st)
    return st


class AlfrescoMultipartClient:
    """Small proxy-free client for the multipart children endpoint."""

    def __init__(self, base: str, parent_node_id: str):
        self.base = str(base).rstrip("/")
        self.parent_node_id = str(parent_node_id).strip()
        if not self.parent_node_id or any(char in self.parent_node_id for char in ("/", "\\", "?", "#")):
            raise ValueError("MULTIPART_PARENT_REQUIRED")

    def _request_json(self, method: str, path: str) -> tuple[int, dict]:
        user = _require_runtime_credential("ALFRESCO_USER")
        password = _require_runtime_credential("ALFRESCO_PASS")
        auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            self.base + path,
            method=method,
            headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
                return int(response.getcode()), payload if isinstance(payload, dict) else {}
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
            except Exception:
                payload = {}
            return int(exc.code), payload

    def get_node(self, node_id: str) -> dict:
        code, payload = self._request_json(
            "GET", f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}?include=properties"
        )
        if code != 200 or not isinstance(payload.get("entry"), dict):
            raise RuntimeError("MULTIPART_READBACK_METADATA_FAILED")
        return payload["entry"]

    def get_content_bytes(self, node_id: str) -> bytes:
        user = _require_runtime_credential("ALFRESCO_USER")
        password = _require_runtime_credential("ALFRESCO_PASS")
        auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            self.base + f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}/content",
            method="GET",
            headers={"Authorization": f"Basic {auth}", "Accept": "application/octet-stream"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=5) as response:
                if int(response.getcode()) != 200:
                    raise RuntimeError("MULTIPART_READBACK_CONTENT_FAILED")
                return response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError("MULTIPART_READBACK_CONTENT_FAILED") from exc

    def upload_multipart(self, *, fields: dict, filename: str, file_bytes: bytes) -> dict:
        boundary = "----nv-alfresco-" + hashlib.sha256(
            file_bytes + filename.encode("utf-8")
        ).hexdigest()[:24]
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend([
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                str(value).encode("utf-8"),
                b"\r\n",
            ])
        chunks.extend([
            f"--{boundary}\r\n".encode("ascii"),
            f'Content-Disposition: form-data; name="filedata"; filename="{filename}"\r\n'.encode("utf-8"),
            b"Content-Type: application/octet-stream\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("ascii"),
        ])
        body = b"".join(chunks)
        user = _require_runtime_credential("ALFRESCO_USER")
        password = _require_runtime_credential("ALFRESCO_PASS")
        auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            self.base + f"/alfresco/api/-default-/public/alfresco/versions/1/nodes/{self.parent_node_id}/children",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=5) as response:
                return {
                    "status": int(response.getcode()),
                    "body": json.loads(response.read().decode("utf-8", errors="replace") or "{}"),
                }
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
            except Exception:
                payload = {}
            return {"status": int(exc.code), "body": payload}


def _multipart_upload_record_path() -> str:
    return os.getenv("NV_MULTIPART_UPLOADS_PATH", "/tmp/nv_multipart_uploads.jsonl")


def _append_multipart_upload_record(record: dict) -> None:
    path = _multipart_upload_record_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def run_multipart_seed(data: bytes, *, client, status_writer=None) -> dict:
    """Validate and execute one multipart upload through an injectable client."""

    if status_writer is None:
        status_writer = write_status

    def reject(reason: str, *, path: str = "/alfresco/api/-default-/public/alfresco/versions/1/nodes/-my-/children", body_hash16: int = 0) -> dict:
        status = status_writer(
            method="POST", path=path, http_code=0,
            body_hash16=body_hash16, validation_reject=1,
        )
        result = {
            "validation_reject": True,
            "target_invoked": False,
            "status_observed": False,
            "http_status": 0,
            "exec_seq": status.get("exec_seq") if isinstance(status, dict) else None,
            "reject_reason": reason,
            "response_node_id": "",
        }
        _append_multipart_upload_record(result)
        return result

    try:
        parsed = parse_multipart_http_seed(data)
    except ValueError as exc:
        return reject(str(exc))

    fields = parsed["fields"]
    filename = str(parsed["filename"])
    file_bytes = bytes(parsed["file_bytes"])
    body_hash16 = int(zlib.crc32(file_bytes) & 0xffff)
    if fields.get("name") != filename:
        return reject("MULTIPART_NAME_FILENAME_MISMATCH", path=parsed["path"], body_hash16=body_hash16)
    if fields.get("nodeType") != "cm:content":
        return reject("MULTIPART_NODE_TYPE_INVALID", path=parsed["path"], body_hash16=body_hash16)
    if not file_bytes:
        return reject("MULTIPART_FILEDATA_EMPTY", path=parsed["path"], body_hash16=body_hash16)
    if len(file_bytes) > 4096 or b"\x00" in file_bytes:
        return reject("MULTIPART_FILEDATA_INVALID", path=parsed["path"], body_hash16=body_hash16)
    try:
        file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return reject("MULTIPART_FILEDATA_INVALID_UTF8", path=parsed["path"], body_hash16=body_hash16)

    response = client.upload_multipart(
        fields=dict(fields), filename=filename, file_bytes=file_bytes
    )
    if not isinstance(response, dict):
        raise ValueError("MULTIPART_UPLOAD_RESPONSE_INVALID")
    http_status = int(response.get("status", response.get("http_code", 0)) or 0)
    body = response.get("body", {})
    if not isinstance(body, dict):
        body = {}
    entry = body.get("entry") if isinstance(body.get("entry"), dict) else body
    response_node_id = str(entry.get("id", "")) if isinstance(entry, dict) else ""
    server_name = str(entry.get("name", "")) if isinstance(entry, dict) else ""
    if not (200 <= http_status < 300):
        status = status_writer(
            method=parsed["method"], path=parsed["path"], http_code=http_status,
            body_hash16=body_hash16, validation_reject=0,
        )
        result = {
            "validation_reject": False,
            "target_invoked": True,
            "status_observed": True,
            "http_status": http_status,
            "exec_seq": status.get("exec_seq") if isinstance(status, dict) else None,
            "response_node_id": "",
            "filename": filename,
            "uploaded_name": filename,
            "file_size": len(file_bytes),
            "file_sha256": "sha256:" + hashlib.sha256(file_bytes).hexdigest(),
            "upload_error": True,
        }
        _append_multipart_upload_record(result)
        return result
    if not response_node_id or not server_name:
        raise ValueError("MULTIPART_UPLOAD_IDENTITY_MISSING")

    status = status_writer(
        method=parsed["method"],
        path=parsed["path"],
        http_code=http_status,
        body_hash16=int(zlib.crc32(file_bytes) & 0xffff),
        validation_reject=0,
    )
    exec_seq = status.get("exec_seq") if isinstance(status, dict) else None
    if exec_seq is None or int(exec_seq) <= 0:
        raise ValueError("MULTIPART_EXEC_SEQ_MISSING")
    result = {
        "validation_reject": False,
        "target_invoked": True,
        "status_observed": True,
        "http_status": http_status,
        "exec_seq": int(exec_seq),
        "response_node_id": response_node_id,
        "filename": filename,
        "uploaded_name": server_name,
        "file_bytes": file_bytes,
        "file_size": len(file_bytes),
        "file_sha256": "sha256:" + hashlib.sha256(file_bytes).hexdigest(),
    }
    record = dict(result)
    record.pop("file_bytes", None)
    record["parent_node_id"] = str(getattr(client, "parent_node_id", ""))
    _append_multipart_upload_record(record)
    return result


def body_valid_stats_path() -> str:
    return os.getenv("NV_BODY_VALID_STATS", "/tmp/nv_body_valid_stats.json")


def bump_body_valid_stat(kind: str) -> None:
    path = body_valid_stats_path()
    stats = {
        "body_rule_pass": 0,
        "body_rule_reject": 0,
        "body_score_pass": 0,
        "body_score_reject": 0,
        "body_score_rpc_ok": 0,
        "body_score_rpc_fail": 0
    }

    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict):
                for k in stats:
                    try:
                        stats[k] = int(old.get(k, 0))
                    except Exception:
                        pass
    except Exception:
        pass

    if kind in stats:
        stats[kind] += 1

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False)
    except Exception:
        pass

# 配置：你平台地址
BASE = "http://127.0.0.1:8080"

ERR_DIR = os.getenv("NV_ERR_DIR", "/tmp/nv_err_cases")

def save_err_case(raw_input: bytes, cls: str, code: int):
    os.makedirs(ERR_DIR, exist_ok=True)
    ts = int(time.time() * 1000)
    fn = f"{ts}_{cls}_{code}.http"
    p = os.path.join(ERR_DIR, fn)
    with open(p, "wb") as f:
        f.write(raw_input)

    # 复现命令（stdin 重放）
    cmd = f'NV_STATUS_PATH="{os.getenv("NV_STATUS_PATH","/tmp/nv_http_status.json")}" ' \
          f'NV_PROBE_PATH="{os.getenv("NV_PROBE_PATH","/tmp/nv_probe.json")}" ' \
          f'NV_STATE_DB="{os.getenv("NV_STATE_DB","/tmp/nv_state_db.json")}" ' \
          f'python3 "{os.path.abspath(__file__)}" < "{p}"\n'
    with open(p + ".cmd", "w", encoding="utf-8") as f:
        f.write(cmd)

    meta = {
    "ts_ms": ts, "cls": cls, "http_code": code,
    "base": BASE
    }
    with open(p + ".meta.json","w",encoding="utf-8") as f:
        json.dump(meta,f,ensure_ascii=False,indent=2)

    return p

def parse_http_seed(data: bytes):
    text = data.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if not lines:
        return "POST", "/api/doc/create", {}, b""

    # ✅ 跳过开头空行（变异可能插入空行）
    i0 = 0
    while i0 < len(lines) and lines[i0].strip() == "":
        i0 += 1
    if i0 >= len(lines):
        return "POST", "/api/doc/create", {}, b""

    first = lines[i0].strip().split()

    # ✅ 兜底默认值（用你当前场景更合理的 POST + create）
    method = first[0] if len(first) >= 1 else "POST"
    path = first[1] if len(first) >= 2 else "/api/doc/create"

    headers = {}
    i = i0 + 1  # ✅ headers 从第一行后开始读
    while i < len(lines) and lines[i].strip() != "":
        if ":" in lines[i]:
            k, v = lines[i].split(":", 1)
            headers[k.strip()] = v.strip()
        i += 1

    while i < len(lines) and lines[i].strip() == "":
        i += 1

    body = "\n".join(lines[i:]).encode("utf-8") if i < len(lines) else b""
    return method, path, headers, body

def parse_multipart_http_seed(data: bytes) -> dict:
    """Parse one full HTTP multipart seed while preserving file bytes."""

    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("MULTIPART_INPUT_NOT_BYTES")
    raw = bytes(data)
    header_separator = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
    if header_separator not in raw:
        raise ValueError("MULTIPART_HTTP_HEADERS_MISSING")
    header_bytes, body = raw.split(header_separator, 1)
    line_separator = b"\r\n" if b"\r\n" in header_bytes else b"\n"
    header_lines = header_bytes.split(line_separator)
    if not header_lines:
        raise ValueError("MULTIPART_REQUEST_LINE_MISSING")
    try:
        request_line = header_lines[0].decode("ascii").split()
    except UnicodeDecodeError as exc:
        raise ValueError("MULTIPART_REQUEST_LINE_INVALID") from exc
    if len(request_line) != 3 or request_line[2] != "HTTP/1.1":
        raise ValueError("MULTIPART_REQUEST_LINE_INVALID")
    method, path = request_line[0], request_line[1]
    if method != "POST" or not path.startswith("/"):
        raise ValueError("MULTIPART_REQUEST_CONTRACT_INVALID")

    headers: dict[str, str] = {}
    for line in header_lines[1:]:
        if b":" not in line:
            raise ValueError("MULTIPART_HEADER_INVALID")
        key, value = line.split(b":", 1)
        try:
            key_text = key.decode("ascii").strip().lower()
            value_text = value.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("MULTIPART_HEADER_INVALID") from exc
        if not key_text or key_text in headers:
            raise ValueError("MULTIPART_HEADER_INVALID")
        headers[key_text] = value_text

    content_type_parts = [part.strip() for part in headers.get("content-type", "").split(";")]
    if not content_type_parts or content_type_parts[0].lower() != "multipart/form-data":
        raise ValueError("MULTIPART_CONTENT_TYPE_INVALID")
    boundary = ""
    for part in content_type_parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip().lower() == "boundary":
                boundary = value.strip().strip('"')
                break
    if not boundary or any(ord(char) < 0x21 or ord(char) > 0x7e for char in boundary):
        raise ValueError("MULTIPART_BOUNDARY_INVALID")

    delimiter = b"--" + boundary.encode("ascii")
    if not body.startswith(delimiter + b"\r\n") and not body.startswith(delimiter + b"\n"):
        raise ValueError("MULTIPART_BOUNDARY_MISMATCH")
    segments = body.split(delimiter)
    if len(segments) < 3 or segments[0] != b"":
        raise ValueError("MULTIPART_BOUNDARY_MISMATCH")
    if segments[-1] not in (b"--", b"--\r\n", b"--\n"):
        raise ValueError("MULTIPART_TERMINATOR_MISSING")

    fields: dict[str, str] = {}
    file_parts: list[tuple[str, str, bytes]] = []
    for segment in segments[1:-1]:
        if segment.startswith(b"\r\n"):
            segment = segment[2:]
        elif segment.startswith(b"\n"):
            segment = segment[1:]
        part_separator = b"\r\n\r\n" if b"\r\n\r\n" in segment else b"\n\n"
        if part_separator not in segment:
            raise ValueError("MULTIPART_PART_HEADERS_MISSING")
        part_header_bytes, part_body = segment.split(part_separator, 1)
        if part_body.endswith(b"\r\n"):
            part_body = part_body[:-2]
        elif part_body.endswith(b"\n"):
            part_body = part_body[:-1]
        part_headers: dict[str, str] = {}
        part_line_separator = b"\r\n" if b"\r\n" in part_header_bytes else b"\n"
        for line in part_header_bytes.split(part_line_separator):
            if b":" not in line:
                raise ValueError("MULTIPART_PART_HEADER_INVALID")
            key, value = line.split(b":", 1)
            try:
                part_headers[key.decode("ascii").strip().lower()] = value.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise ValueError("MULTIPART_PART_HEADER_INVALID") from exc
        disposition_parts = [part.strip() for part in part_headers.get("content-disposition", "").split(";")]
        if not disposition_parts or disposition_parts[0].lower() != "form-data":
            raise ValueError("MULTIPART_DISPOSITION_INVALID")
        params: dict[str, str] = {}
        for item in disposition_parts[1:]:
            if "=" in item:
                key, value = item.split("=", 1)
                params[key.strip().lower()] = value.strip().strip('"')
        field_name = params.get("name", "")
        if not field_name:
            raise ValueError("MULTIPART_FIELD_NAME_MISSING")
        filename = params.get("filename")
        if filename is not None:
            if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
                raise ValueError("MULTIPART_FILENAME_INVALID")
            if any(ord(char) < 0x20 or ord(char) == 0x7f for char in filename):
                raise ValueError("MULTIPART_FILENAME_INVALID")
            file_parts.append((field_name, filename, part_body))
        else:
            if field_name in fields:
                raise ValueError("MULTIPART_FIELD_DUPLICATE")
            try:
                fields[field_name] = part_body.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("MULTIPART_FIELD_INVALID_UTF8") from exc

    filedata_parts = [part for part in file_parts if part[0] == "filedata"]
    if len(filedata_parts) != 1 or len(file_parts) != 1:
        raise ValueError("MULTIPART_FILEDATA_INVALID")
    _, filename, file_bytes = filedata_parts[0]
    return {
        "method": method,
        "path": path,
        "headers": headers,
        "boundary": boundary,
        "fields": fields,
        "filename": filename,
        "file_bytes": file_bytes,
    }


def classify(code: int, timeout_flag: bool) -> str:
    if timeout_flag:
        return "timeout"
    if code == -2:
        return "conn_refused"
    if 200 <= code < 300: return "2xx"
    if 300 <= code < 400: return "3xx"
    if 400 <= code < 500: return "4xx"
    if 500 <= code < 600: return "5xx"
    return "other"

def extract_biz_code(resp_body: bytes, http_code: int, cls: str, biz_fields) -> str:
    try:
        s = resp_body.decode("utf-8", errors="ignore").strip()
        if s.startswith("{") and s.endswith("}"):
            obj = json.loads(s)
            for k in biz_fields:
                if k in obj and obj[k] is not None:
                    return f"{k}:{obj[k]}"
    except Exception:
        pass
    return f"http_{http_code}_{cls}"

CTX_PATH = os.getenv("NV_CTX_PATH", "/tmp/nv_ctx.json")

def ctx_load() -> dict:
    try:
        with open(CTX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def ctx_save(d: dict):
    tmp = CTX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, CTX_PATH)

def inject_ctx_placeholders(body: bytes, ctx: dict) -> bytes:
    """
    Replace {{docId}} in body with ctx["docId"] if present.
    If body is not JSON, return original.
    """
    if not body:
        return body
    try:
        s = body.decode("utf-8", errors="ignore")
        if "{{docId}}" not in s:
            return body
        doc_id = str(ctx.get("docId", "")).strip()
        if not doc_id:
            return body
        s = s.replace("{{docId}}", doc_id)
        return s.encode("utf-8")
    except Exception:
        return body

def health_check(health_url: str, timeout_sec=1.0) -> bool:
    try:
        with open_direct(health_url, timeout=timeout_sec) as r:
            return 200 <= r.getcode() < 400
    except Exception:
        return False


def open_direct(request, timeout):
    """Open an HTTP request without consulting ambient proxy settings."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    previous = getattr(urllib.request, "_opener", None)
    urllib.request._opener = opener
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    finally:
        urllib.request._opener = previous

def normalize_json_body_or_none(data: bytes):
    if not data:
        return b"{}"
    try:
        text = data.decode("utf-8", errors="strict")
    except Exception:
        return None

    text = text.strip()
    if not text:
        return b"{}"

    if not (text.startswith("{") or text.startswith("[")):
        return None

    try:
        obj = json.loads(text)
    except Exception:
        return None

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

def has_http_request_line(data: bytes) -> bool:
    request_line = data.split(b"\n", 1)[0].removesuffix(b"\r")
    request_parts = request_line.split()
    return len(request_parts) >= 2 and request_parts[1].startswith(b"/")

def main():
    data = sys.stdin.buffer.read()

    # --- load cfg once ---
    cfg = load_target_config()
    BASE = cfg.get("base", "http://127.0.0.1:8080").rstrip("/")
    if cfg.get("scenario") == "multipart_upload":
        parent_node_id = str(cfg.get("parent_node_id", "")).strip()
        if not parent_node_id:
            raise RuntimeError("MULTIPART_PARENT_REQUIRED")
        multipart_client = AlfrescoMultipartClient(BASE, parent_node_id)

        def multipart_status_writer(**kwargs):
            method = str(kwargs.get("method", "POST"))
            path = str(kwargs.get("path", ""))
            code = int(kwargs.get("http_code", 0) or 0)
            validation_reject = int(kwargs.get("validation_reject", 0) or 0)
            try:
                cls = classify(code, code < 0)
                biz_code = f"http_{code}_{cls}"
                probe = update_state(method, path, cls, biz_code=biz_code)
            except Exception:
                probe = {"ncov_delta": 0, "ncov_total": 0, "nall": 0}
            return write_status(
                method,
                path,
                code,
                body_hash16=int(kwargs.get("body_hash16", 0) or 0),
                ncov_delta=int(probe.get("ncov_delta", 0)),
                ncov_total=int(probe.get("ncov_total", 0)),
                nall=int(probe.get("nall", 0)),
                validation_reject=validation_reject,
            )

        result = run_multipart_seed(
            data,
            client=multipart_client,
            status_writer=multipart_status_writer,
        )
        if result.get("validation_reject"):
            bump_body_valid_stat("body_rule_reject")
            return 0
        return 0 if int(result.get("http_status", 0)) < 400 else 1

    ALLOWED_PATHS = cfg.get("_allowed_paths", set())
    ALLOWED_METHODS = cfg.get("_allowed_methods", {"GET", "POST"})
    BIZ_FIELDS = cfg.get("biz_fields", ["code", "message", "msg"])
    HEALTH_URL = resolve_health_url(cfg)

    # default endpoint fallback
    eps = cfg.get("endpoints", [])
    if eps and isinstance(eps, list) and isinstance(eps[0], dict):
        default_method = str(eps[0].get("method", "POST")).upper().strip() or "POST"
        default_path = str(eps[0].get("path", "/")).strip() or "/"
        if not default_path.startswith("/"):
            default_path = "/" + default_path
    else:
        default_method = "POST"
        default_path = "/"

    # --- parse seed OR body-only mode ---
    body_only_mode = int(cfg.get("body_only_mode", 0)) == 1

    if body_only_mode:
        endpoint_name = os.getenv("NV_ENDPOINT_NAME", str(cfg.get("default_endpoint", "")).strip())
        if not endpoint_name:
            raise RuntimeError("body_only_mode enabled but no NV_ENDPOINT_NAME/default_endpoint provided")

        method, path = get_named_endpoint(cfg, endpoint_name)
        headers = {"Content-Type": "application/json"}

        rules_path = os.getenv(
            "NV_BODY_RULES",
            os.path.join(os.path.dirname(__file__), "validity", "o2oa_query_rules.json")
        )

        score_endpoint = os.getenv("NV_BODY_SCORE_ENDPOINT", "").strip() or None

        score_threshold = None
        sth = os.getenv("NV_BODY_SCORE_THRESHOLD", "").strip()
        if sth:
            try:
                score_threshold = float(sth)
            except Exception:
                score_threshold = None

        validation_body = data
        if has_http_request_line(data):
            try:
                validation_body = extract_http_body(data)
            except HttpBodyAdapterError:
                bump_body_valid_stat("body_rule_reject")
                return 0

        vr = body_validate(
            endpoint_name=endpoint_name,
            raw_body=validation_body,
            rules_path=rules_path,
            score_endpoint=score_endpoint,
            score_threshold=score_threshold,
        )

        if os.getenv("NV_DEBUG_BODY_VALID") == "1":
            sys.stderr.write(
                f"[BODY_VALID] endpoint={endpoint_name} ok={vr['ok']} reason={vr['reason']} score={vr['score']}\n"
            )

        # 先按 reason 判定
        if not vr["ok"]:
            if vr["reason"] == "score_reject":
                bump_body_valid_stat("body_rule_pass")
                bump_body_valid_stat("body_score_rpc_ok")
                bump_body_valid_stat("body_score_reject")
            else:
                bump_body_valid_stat("body_rule_reject")
            # Every body-only invocation must leave a terminal record so the
            # append-only status consumer can associate the execution.  A
            # rule reject with no normalized body (malformed JSON) is still a
            # validation reject, never a target execution.
            write_status(
                method,
                path,
                0,
                body_hash16=int(zlib.crc32(validation_body) & 0xffff),
                validation_reject=1,
            )
            return 0

        bump_body_valid_stat("body_rule_pass")

        if score_endpoint:
            if vr.get("score_rpc_ok", False):
                bump_body_valid_stat("body_score_rpc_ok")
                bump_body_valid_stat("body_score_pass")
            else:
                bump_body_valid_stat("body_score_rpc_fail")

        body = vr["norm_body"]
    else:
        method, path, headers, body = parse_http_seed(data)

        # sanitize method/path only in .http mode
        method = (method or "").upper().strip()
        path = (path or "").strip()

        if method not in ALLOWED_METHODS:
            method = default_method

        if not path.startswith("/"):
            path = default_path

        if ALLOWED_PATHS and path not in ALLOWED_PATHS:
            path = default_path

        # --- ctx placeholder injection (legacy/mock doc flow only) ---
        # 对真实 O2OA body-only 模式不启用
        ctx = ctx_load()
        if method in ("POST", "GET") and path in ("/api/doc/submit", "/api/doc/approve", "/api/doc/query"):
            body = inject_ctx_placeholders(body, ctx)

    url = BASE + path

    # Content-Type only when we have a body
    if body and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    # inject auth
    headers = apply_auth_headers(cfg, headers)

    if os.getenv("NV_DEBUG_AUTH") == "1":
        sys.stderr.write(f"[DBG] {method} {path} headers={headers}\n")

    req = urllib.request.Request(
        url=url,
        data=body if body else None,
        method=method,
        headers=headers
    )

    t0 = time.time()
    body_hash16 = int(zlib.crc32(body) & 0xffff) if body else 0

    timeout_flag = False
    code = None
    resp_body = b""

    try:
        with open_direct(req, timeout=5) as resp:
            code = resp.getcode()
            resp_body = resp.read(4096)

    except urllib.error.HTTPError as e:
        # HTTP 层返回错误码（4xx/5xx）: 不算连接失败
        code = int(getattr(e, "code", 500) or 500)
        try:
            resp_body = e.read(4096)
        except Exception:
            resp_body = b""

    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)

        if isinstance(reason, ConnectionRefusedError):
            timeout_flag = False
            code = -2
        else:
            rmsg = ""
            try:
                rmsg = str(reason) if reason is not None else str(e)
            except Exception:
                rmsg = ""

            if ("Errno 111" in rmsg) or ("Connection refused" in rmsg):
                timeout_flag = False
                code = -2
            elif ("timed out" in rmsg) or ("Timeout" in rmsg) or isinstance(reason, (TimeoutError,)):
                timeout_flag = True
                code = -1
            else:
                timeout_flag = True
                code = -1

        resp_body = b""

    except Exception:
        timeout_flag = True
        code = -1
        resp_body = b""

    latency_ms = int((time.time() - t0) * 1000)

    cls = classify(int(code), timeout_flag)
    biz_code = extract_biz_code(resp_body, int(code), cls, BIZ_FIELDS)

    # --- legacy/mock ctx update only ---
    if (not body_only_mode) and path == "/api/doc/create" and resp_body and (200 <= int(code) < 400):
        try:
            obj = json.loads(resp_body.decode("utf-8", errors="ignore") or "{}")
            doc_id = obj.get("docId") or obj.get("data", {}).get("docId")
            if doc_id:
                ctx = ctx_load()
                ctx["docId"] = str(doc_id)
                ctx_save(ctx)
        except Exception:
            pass

    try:
        probe = update_state(method, path, cls, biz_code=biz_code)
    except Exception:
        # Status is the execution identity boundary; accounting failure must
        # not erase an already completed HTTP response.
        probe = {"ncov_delta": 0, "ncov_total": 0, "nall": 0}
    is_exception = (cls in ("5xx", "timeout", "conn_refused"))

    recovered = 0
    recover_ms = 0

    if is_exception:
        t_rec0 = time.time()
        for _ in range(3):
            if health_check(HEALTH_URL, timeout_sec=1.0):
                recovered = 1
                break
            time.sleep(0.1)
        recover_ms = int((time.time() - t_rec0) * 1000)

        # 落盘原始输入；body-only 模式下就是原始 JSON body
        save_err_case(data, cls, int(code))

    ncov_delta = int(probe.get("ncov_delta", 0))
    ncov_total = int(probe.get("ncov_total", 0))
    nall = int(probe.get("nall", 100000))

    write_status(
        method, path, int(code),
        timeout=timeout_flag,
        recovered=bool(recovered),
        latency_ms=latency_ms,
        body_hash16=body_hash16,
        ncov_delta=ncov_delta,
        ncov_total=ncov_total,
        nall=nall,
        is_exception=1 if is_exception else 0,
        recover_ms=recover_ms
    )

    if timeout_flag or int(code) == -2:
        return 2
    if 200 <= int(code) < 400:
        return 0
    if 400 <= int(code) < 500:
        return 1
    return 2

if __name__ == "__main__":
    sys.exit(main())
