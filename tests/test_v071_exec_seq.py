"""v0.7.1 -- execution identity for the real HTTP harness.

Every test here drives the *real* ``nv_http_harness.py`` as a separate OS
process against a real local HTTP server, because that is exactly how AFL++
runs it:

    afl-fuzz -n -i <in> -o <out> -- python3 nv_http_harness.py

The harness is never mocked.  Only the far end of the socket is local.

Why execution identity is needed at all: the C consumer
(``nv_status_is_fresh`` in ``src/afl-fuzz-nv-covset.c``) must consume one
status document per target execution.  Without ``exec_seq`` it falls back to
``ts_ms ^ (body_hash16 << 32)``, so two executions that send the same body and
get the same response inside one millisecond collide and the second is
discarded as a replay.
"""

import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "nv_http_harness.py"


# --------------------------------------------------------------------------
# local deterministic HTTP server
# --------------------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    """Routes by path so one server covers 2xx / 4xx / 5xx / slow."""

    protocol_version = "HTTP/1.1"

    def _respond(self, code: int, payload: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self) -> None:
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)

        self.server.hit_count += 1

        if path == "/slow":
            time.sleep(self.server.slow_seconds)
            self._respond(200, b'{"code":0,"message":"slow ok"}')
        elif path == "/bad":
            self._respond(400, b'{"code":400,"message":"bad request"}')
        elif path == "/boom":
            self._respond(500, b'{"code":500,"message":"server error"}')
        else:
            self._respond(200, b'{"code":0,"message":"ok"}')

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle

    def log_message(self, *args):  # keep the test output pristine
        return


class LocalServer:
    """A real HTTP server on 127.0.0.1 and an ephemeral port."""

    def __init__(self, slow_seconds: float = 8.0):
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.hit_count = 0
        self.httpd.slow_seconds = slow_seconds
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def hit_count(self) -> int:
        """Requests actually served -- proves whether a request was sent."""
        return self.httpd.hit_count

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def free_port() -> int:
    """A port with nothing listening on it, for connection-refused tests."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --------------------------------------------------------------------------
# harness driver
# --------------------------------------------------------------------------

def harness_env(status_path: Path, config_path: Path, **extra) -> dict:
    """Environment for one harness execution.

    The proxy variables are cleared explicitly: this machine exports
    ``http_proxy`` with a glob-style ``no_proxy`` that urllib cannot match, so
    without this the harness would talk to a proxy instead of the local server
    and every test would observe a 502.  Hermetic beats ambient.
    """
    env = dict(os.environ)
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(var, None)
    env["no_proxy"] = "127.0.0.1,localhost"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["NV_STATUS_PATH"] = str(status_path)
    env["NV_TARGET_CONFIG"] = str(config_path)
    env.update({k: str(v) for k, v in extra.items()})
    return env


def run_harness(status_path: Path, config_path: Path, body: bytes,
                timeout: float = 60.0, **extra):
    """One harness execution == one fresh OS process, exactly like AFL++.

    Popen rather than subprocess.run so the test can observe the real OS pid
    and prove the executions were separate processes.  The harness itself
    needs no test-only hook for that.
    """
    proc = subprocess.Popen(
        [sys.executable, str(HARNESS)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=harness_env(status_path, config_path, **extra),
    )
    pid = proc.pid
    try:
        proc.communicate(input=body, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    return pid


def read_status(status_path: Path) -> dict:
    with open(status_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_config(path: Path, base: str, method: str = "POST",
                 endpoint_path: str = "/api/doc/query", **extra) -> None:
    cfg = {
        "target_type": "http_api",
        "base": base,
        "health": "/health",
        "endpoints": [{"name": "probe", "method": method, "path": endpoint_path}],
    }
    cfg.update(extra)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)


SEED = b'POST /api/doc/query HTTP/1.1\r\n\r\n{"k":"v"}'


class ExecSeqTestBase(unittest.TestCase):

    slow_seconds = 8.0

    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(slow_seconds=cls.slow_seconds)
        cls.tmp = Path(tempfile.mkdtemp(prefix="v071_exec_seq_"))
        cls.status = cls.tmp / "nv_http_status.json"
        cls.config = cls.tmp / "task.json"
        write_config(cls.config, cls.server.base)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# Test 1 -- identical executions must still be distinguishable
# --------------------------------------------------------------------------

class IdenticalExecutionsTest(ExecSeqTestBase):

    def test_identical_requests_get_distinct_exec_seq(self):
        """The defect this whole change exists for.

        Two executions with the same request and the same response are
        indistinguishable under the legacy stamp.  They must differ in
        exec_seq.
        """
        run_harness(self.status, self.config, SEED)
        first = read_status(self.status)

        run_harness(self.status, self.config, SEED)
        second = read_status(self.status)

        self.assertIn("exec_seq", first, "harness did not report exec_seq")
        self.assertIn("exec_seq", second, "harness did not report exec_seq")

        # Same request, same response: the legacy identity really does collide.
        self.assertEqual(first["body_hash16"], second["body_hash16"])
        self.assertEqual(first["class"], second["class"])
        self.assertEqual(first["http_code"], second["http_code"])

        self.assertNotEqual(
            first["exec_seq"], second["exec_seq"],
            "two distinct target executions shared one execution identity",
        )

    def test_exec_seq_is_stable_across_rereads(self):
        """Re-reading one document must not mint a new identity."""
        run_harness(self.status, self.config, SEED)
        a = read_status(self.status)
        b = read_status(self.status)
        self.assertEqual(a["exec_seq"], b["exec_seq"])

    def test_legacy_identity_fields_are_preserved(self):
        """Additive change: historical evidence and the fallback still work."""
        run_harness(self.status, self.config, SEED)
        st = read_status(self.status)
        for field in ("ts_ms", "body_hash16", "method", "path", "class",
                      "http_code", "timeout", "recovered", "latency_ms",
                      "ncov_delta", "ncov_total", "nall", "is_exception",
                      "recover_ms", "seq"):
            self.assertIn(field, st, f"legacy field {field} disappeared")


# --------------------------------------------------------------------------
# Test 2 + 3 -- uniqueness across many separate processes
# --------------------------------------------------------------------------

class UniquenessAcrossProcessesTest(ExecSeqTestBase):

    N = 100

    def test_no_duplicate_exec_seq_over_many_separate_processes(self):
        seqs = []
        pids = set()
        for _ in range(self.N):
            pids.add(run_harness(self.status, self.config, SEED))
            seqs.append(read_status(self.status)["exec_seq"])

        self.assertEqual(len(seqs), self.N)
        self.assertEqual(len(set(seqs)), self.N,
                         f"duplicate exec_seq among {self.N} executions")

        # Proof that these really were separate OS processes, not one process
        # calling a function N times.  Pids can be recycled, so allow a margin.
        self.assertGreater(len(pids), self.N // 2,
                           "executions did not run as distinct processes")

    def test_exec_seq_is_strictly_increasing(self):
        seqs = []
        for _ in range(10):
            run_harness(self.status, self.config, SEED)
            seqs.append(read_status(self.status)["exec_seq"])
        for i in range(len(seqs) - 1):
            self.assertGreater(seqs[i + 1], seqs[i],
                               f"exec_seq went backwards at index {i}: {seqs}")


# --------------------------------------------------------------------------
# Test 4 -- restart
# --------------------------------------------------------------------------

class RestartTest(ExecSeqTestBase):

    def test_restart_of_the_sequence_store_restarts_and_advances_allocator(self):
        """A lost sidecar restarts allocation but does not repeat one id.

        The C consumer treats values at or below its high-water mark as stale,
        so deleting this sidecar while that consumer remains alive interrupts
        fresh observations until the allocator passes the old high-water mark.
        """
        for _ in range(3):
            run_harness(self.status, self.config, SEED)
        before = read_status(self.status)["exec_seq"]

        for sidecar in self.tmp.glob("nv_http_status.json*"):
            if sidecar != self.status:
                sidecar.unlink()

        run_harness(self.status, self.config, SEED)
        after_restart = read_status(self.status)["exec_seq"]

        run_harness(self.status, self.config, SEED)
        after_next = read_status(self.status)["exec_seq"]

        self.assertNotEqual(
            after_restart, after_next,
            "after a restart the harness kept reissuing one identity",
        )
        self.assertLess(after_restart, before)
        self.assertGreater(after_next, after_restart)


# --------------------------------------------------------------------------
# Test 5 -- error paths
# --------------------------------------------------------------------------

class ErrorPathTest(ExecSeqTestBase):

    slow_seconds = 8.0  # urlopen timeout inside the harness is 5s

    def _exec_seq_for(self, endpoint_path: str, base: str = None) -> dict:
        slug = endpoint_path.strip("/").replace("/", "_") or "root"
        cfg = self.tmp / f"task_{slug}.json"
        write_config(cfg, base or self.server.base, endpoint_path=endpoint_path)
        seed = f"POST {endpoint_path} HTTP/1.1\r\n\r\n{{\"k\":\"v\"}}".encode()
        run_harness(self.status, cfg, seed)
        return read_status(self.status)

    def test_4xx_response_carries_exec_seq(self):
        st = self._exec_seq_for("/bad")
        self.assertEqual(st["class"], "4xx")
        self.assertIn("exec_seq", st)
        self.assertGreater(st["exec_seq"], 0)

    def test_5xx_response_carries_exec_seq(self):
        st = self._exec_seq_for("/boom")
        self.assertEqual(st["class"], "5xx")
        self.assertIn("exec_seq", st)
        self.assertGreater(st["exec_seq"], 0)

    def test_connection_refused_carries_exec_seq(self):
        dead = f"http://127.0.0.1:{free_port()}"
        st = self._exec_seq_for("/api/doc/query", base=dead)
        self.assertEqual(st["class"], "conn_refused")
        self.assertIn("exec_seq", st)
        self.assertGreater(st["exec_seq"], 0)

    def test_timeout_carries_exec_seq(self):
        st = self._exec_seq_for("/slow")
        self.assertEqual(st["class"], "timeout")
        self.assertIn("exec_seq", st)
        self.assertGreater(st["exec_seq"], 0)

    def test_error_paths_do_not_reuse_one_identity(self):
        seqs = [
            self._exec_seq_for("/bad")["exec_seq"],
            self._exec_seq_for("/boom")["exec_seq"],
            self._exec_seq_for("/bad")["exec_seq"],
        ]
        self.assertEqual(len(set(seqs)), 3, f"error paths shared identity: {seqs}")


# --------------------------------------------------------------------------
# Test 6 -- validity reject must not fabricate an execution
# --------------------------------------------------------------------------

class ValidityRejectTest(ExecSeqTestBase):

    def test_validity_reject_does_not_write_a_status_document(self):
        """No HTTP request happened, so no execution identity may be issued."""
        cfg = self.tmp / "task_bodyonly.json"
        # body_only_mode resolves the endpoint by name, so the name in the
        # config has to be the one the rules file describes.
        write_config(cfg, self.server.base, body_only_mode=1,
                     default_endpoint="cms_doc_list",
                     endpoints=[{"name": "cms_doc_list", "method": "POST",
                                 "path": "/api/doc/query"}])
        rules = REPO_ROOT / "validity" / "o2oa_query_rules.json"

        # A valid body first, to establish a baseline document.
        good = json.dumps({
            "docStatusList": ["published"],
            "categoryIdList": ["c1"],
            "key": "kw",
        }).encode()
        run_harness(self.status, cfg, good,
                    NV_ENDPOINT_NAME="cms_doc_list", NV_BODY_RULES=str(rules))
        baseline = read_status(self.status)
        hits_before = self.server.hit_count

        # Missing every required field -> rejected before the request.
        bad = b'{"unexpected": 1}'
        run_harness(self.status, cfg, bad,
                    NV_ENDPOINT_NAME="cms_doc_list", NV_BODY_RULES=str(rules))
        after = read_status(self.status)

        self.assertEqual(
            baseline["exec_seq"], after["exec_seq"],
            "a validity-rejected testcase minted a target execution identity",
        )
        self.assertEqual(self.server.hit_count, hits_before,
                         "validity-rejected testcase still reached the server")


# --------------------------------------------------------------------------
# Test 7 -- the document the C side reads is never half written
# --------------------------------------------------------------------------

class AtomicWriteTest(ExecSeqTestBase):

    def test_status_document_is_never_observed_partially_written(self):
        stop = threading.Event()
        broken = []

        def reader():
            while not stop.is_set():
                try:
                    with open(self.status, "r", encoding="utf-8") as fh:
                        payload = fh.read()
                    if payload:
                        obj = json.loads(payload)
                        if "exec_seq" not in obj:
                            broken.append("missing exec_seq")
                except FileNotFoundError:
                    pass
                except json.JSONDecodeError as exc:
                    broken.append(f"torn read: {exc}")

        run_harness(self.status, self.config, SEED)  # ensure the file exists
        watcher = threading.Thread(target=reader, daemon=True)
        watcher.start()
        try:
            for _ in range(25):
                run_harness(self.status, self.config, SEED)
        finally:
            stop.set()
            watcher.join(timeout=5)

        self.assertEqual(broken, [], f"status document was read torn: {broken[:3]}")


if __name__ == "__main__":
    unittest.main()
