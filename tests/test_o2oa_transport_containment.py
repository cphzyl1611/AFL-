"""Offline contracts for O2OA direct transport and child proxy containment."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import nv_http_harness as harness


REPO_ROOT = Path(__file__).parents[1]
PLAN_SCRIPT = REPO_ROOT / "scripts" / "run_runner_real_fuzz_plan.sh"
PROXY_ENV_NAMES = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
)
LOOPBACK_BYPASS = "127.0.0.1,localhost"


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self) -> int:
        return 200

    def read(self, limit: int) -> bytes:
        del limit
        return b"{}"


class DirectTransportTest(unittest.TestCase):
    def test_health_check_uses_explicit_direct_opener(self) -> None:
        hostile_env = {name: "http://proxy.invalid:9" for name in PROXY_ENV_NAMES}

        with (
            mock.patch.dict(harness.os.environ, hostile_env, clear=False),
            mock.patch.object(harness.urllib.request, "build_opener") as build_opener,
            mock.patch.object(harness.urllib.request, "urlopen", return_value=_Response()),
        ):
            self.assertTrue(harness.health_check("http://offline.invalid/health", 1.0))

        handler, = build_opener.call_args.args
        self.assertEqual(handler.proxies, {})

    def test_business_request_uses_explicit_direct_opener(self) -> None:
        with tempfile.TemporaryDirectory(prefix="o2oa_transport_") as directory:
            tmp = Path(directory)
            config = tmp / "target.json"
            config.write_text(
                json.dumps(
                    {
                        "base": "http://offline.invalid",
                        "health": "/health",
                        "auth": {"type": "none"},
                        "endpoints": [{"method": "GET", "path": "/probe"}],
                    }
                ),
                encoding="utf-8",
            )
            stdin = types.SimpleNamespace(buffer=io.BytesIO(b"GET /probe\n\n"))
            hostile_env = {
                "NV_TARGET_CONFIG": str(config),
                "NV_STATUS_LEDGER_PATH": str(tmp / "ledger.jsonl"),
                **{name: "http://proxy.invalid:9" for name in PROXY_ENV_NAMES},
            }
            with (
                mock.patch.dict(harness.os.environ, hostile_env, clear=True),
                mock.patch.object(harness, "STATUS_PATH", str(tmp / "status.json")),
                mock.patch.object(harness.sys, "stdin", stdin),
                mock.patch.object(harness, "update_state", return_value={}),
                mock.patch.object(harness.urllib.request, "build_opener") as build_opener,
                mock.patch.object(harness.urllib.request, "urlopen", return_value=_Response()) as urlopen,
            ):
                self.assertEqual(harness.main(), 0)

        handler, = build_opener.call_args.args
        self.assertEqual(handler.proxies, {})
        request, = urlopen.call_args.args
        self.assertEqual(request.full_url, "http://offline.invalid/probe")
        self.assertEqual(urlopen.call_args.kwargs, {"timeout": 5})


class ChildProxySanitationTest(unittest.TestCase):
    def test_plan_child_strips_proxies_and_sets_loopback_bypass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="o2oa_child_env_") as directory:
            base = Path(directory)
            root = base / "root"
            run_dir = base / "run"
            (root / "scripts").mkdir(parents=True)
            (root / "targets").mkdir()
            (root / "seeds").mkdir()
            (run_dir / "manifest_seeds").mkdir(parents=True)
            shutil.copy2(PLAN_SCRIPT, root / "scripts" / PLAN_SCRIPT.name)
            (root / "targets" / "target.json").write_text("{}", encoding="utf-8")
            (root / "seeds" / "manifest.json").write_text("{}", encoding="utf-8")
            capture = run_dir / "child-env.json"
            child = root / "scripts" / "run_runner_real_fuzz.sh"
            child.write_text(
                "#!/usr/bin/env bash\n"
                "python3 - \"$CAPTURE_PATH\" <<'PY'\n"
                "import json, os, sys\n"
                "names = ('http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'no_proxy', 'NO_PROXY')\n"
                "with open(sys.argv[1], 'w', encoding='utf-8') as out:\n"
                "    json.dump({name: os.environ.get(name) for name in names}, out)\n"
                "PY\n"
                "mkdir -p \"$OUT_ROOT\"\n"
                "printf 'summary\\n' > \"$OUT_ROOT/summary.csv\"\n"
                "printf '{}' > \"$BODY_VALID_STATS\"\n",
                encoding="utf-8",
            )
            child.chmod(0o755)
            env = {
                "PATH": os.environ["PATH"],
                "ROOT": str(root),
                "CFG": str(root / "targets" / "target.json"),
                "IN_DIR": str(run_dir / "manifest_seeds"),
                "SEED_MANIFEST": str(root / "seeds" / "manifest.json"),
                "OUT_ROOT": str(run_dir / "out"),
                "BODY_VALID_STATS": str(run_dir / "body-valid-stats.json"),
                "STATUS_PATH": str(run_dir / "status.json"),
                "RUNNER_RUN_DIR": str(run_dir),
                "RUNNER_DURATION_PLAN": "1",
                "NV_TOKEN": "offline-placeholder",
                "NV_BODY_SCORE_ENDPOINT": "unix:///offline/not-contacted.sock",
                "NV_BODY_SCORE_THRESHOLD": "1.0",
                "CAPTURE_PATH": str(capture),
                **{name: "http://proxy.invalid:9" for name in PROXY_ENV_NAMES},
                "no_proxy": "127.*",
                "NO_PROXY": "127.*",
            }
            result = subprocess.run(
                [str(root / "scripts" / PLAN_SCRIPT.name)],
                cwd=base,
                env=env,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            child_env = json.loads(capture.read_text(encoding="utf-8"))

        for name in PROXY_ENV_NAMES:
            self.assertIsNone(child_env[name], f"{name} survived child sanitation")
        self.assertEqual(child_env["no_proxy"], LOOPBACK_BYPASS)
        self.assertEqual(child_env["NO_PROXY"], LOOPBACK_BYPASS)


if __name__ == "__main__":
    unittest.main()
