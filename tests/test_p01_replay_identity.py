"""P0.1 finding M-3: replay protection must reject re-reads, not real executions.

The pre-P0.1 check keyed replay on the status document's *content*:

    stamp = ts_ms ^ (body_hash16 << 32)

Two distinct executions that produce the same body and the same response in
the same millisecond therefore collided, and the second was silently dropped
as a "replay".  The extreme case is a harness that does not report ts_ms at
all: the stamp folds to a constant and every observation after the first is
discarded for the rest of the campaign.

This runs the real fuzzer against test/p01/status_seq_target.c with
NV_P01_STATIC_STAMP=1, which pins ts_ms and body_hash16 so every execution is
byte-identical under the legacy rule while still carrying a distinct exec_seq.
A correct replay check consumes essentially every execution; the defective one
consumes exactly one.

Evidence is written under out/p01_m3_replay/.
"""

import json
import os
import shutil
import subprocess
import tempfile
import sysconfig
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = None
AFL_FUZZ = REPO_ROOT / "afl-fuzz"
AFL_CC = REPO_ROOT / "afl-clang-fast"
TARGET_SRC = REPO_ROOT / "test" / "p01" / "status_seq_target.c"

RUN_SECONDS = 10
HARD_TIMEOUT = 90

# The consumed-to-executed ratio a working replay check must reach.  It is not
# 1.0: dry-run, calibration and trim executions legitimately never reach
# common_fuzz_stuff, so a slice of executions is never offered for consumption.
MIN_CONSUMPTION_RATIO = 0.90


def evidence_root(name: str) -> Path:
    """Where this test writes its artifacts.

    Committed evidence under out/ is a deliverable, so a plain test run must
    not overwrite or delete it.  The suite writes to a scratch directory by
    default; regenerating the tracked evidence is a deliberate act:

        NV_P01_WRITE_EVIDENCE=1 python3 -m unittest tests.<module>
    """
    if os.environ.get("NV_P01_WRITE_EVIDENCE") == "1":
        return REPO_ROOT / "out" / name
    return Path(tempfile.mkdtemp(prefix=f"{name}_"))



def curate_evidence(root: Path, logs: list) -> None:
    """Shrink multi-MB execution logs to a bounded, auditable sample.

    Only applies when writing into the tracked out/ tree: the full logs run to
    several megabytes per run and are regenerable from this test, so what gets
    committed is the head and tail plus an explicit record count.
    """
    if root.parent.name != "out":
        return
    for name in logs:
        src = root / name
        if not src.is_file():
            continue
        lines = src.read_text(encoding="utf-8").splitlines()
        marker = json.dumps({
            "_truncated": True,
            "total_records": len(lines),
            "kept": "first 200 + last 50",
            "regenerate": "NV_P01_WRITE_EVIDENCE=1 python3 -m unittest "
                          "tests.test_p01_status_attribution "
                          "tests.test_p01_replay_identity",
        })
        sample = lines[:200] + [marker] + lines[-50:]
        (root / name.replace(".jsonl", ".sample.jsonl")).write_text(
            "\n".join(sample) + "\n", encoding="utf-8"
        )
        src.unlink()
    for junk in ("status_seq_target", "seen.bin", "seq.bin"):
        p = root / junk
        if p.exists():
            p.unlink()
    stats = root / "afl" / "default" / "fuzzer_stats"
    if not stats.is_file():
        stats = root / "afl" / "fuzzer_stats"
    if stats.is_file():
        shutil.copy(stats, root / "fuzzer_stats")
    for d in ("afl", "in"):
        if (root / d).exists():
            shutil.rmtree(root / d)


def parse_key_value(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip()
    return out


def loader_env(extra: dict) -> dict:
    env = {**os.environ, **extra}
    libdir = sysconfig.get_config_var("LIBDIR")
    if libdir:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{libdir}:{existing}" if existing else libdir
    return env


class P01ReplayIdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not AFL_FUZZ.is_file():
            raise unittest.SkipTest("afl-fuzz is not built")
        if not AFL_CC.is_file():
            raise unittest.SkipTest("afl-clang-fast is not built")

        global EVIDENCE
        EVIDENCE = evidence_root("p01_m3_replay")
        if EVIDENCE.exists():
            shutil.rmtree(EVIDENCE)
        EVIDENCE.mkdir(parents=True)

        target = EVIDENCE / "status_seq_target"
        build = subprocess.run(
            [str(AFL_CC), "-O1", str(TARGET_SRC), "-o", str(target)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
            env=loader_env({"AFL_QUIET": "1"}),
        )
        if build.returncode != 0:
            raise AssertionError(f"target build failed:\n{build.stderr}")

        seeds = EVIDENCE / "in"
        seeds.mkdir()
        (seeds / "seed_a").write_bytes(b"A---")
        (seeds / "seed_z").write_bytes(b"Z---")

        out = EVIDENCE / "afl"
        proc = subprocess.run(
            [
                str(AFL_FUZZ), "-m", "none", "-s", "20260816",
                "-V", str(RUN_SECONDS),
                "-i", str(seeds), "-o", str(out),
                "--", str(target), "@@",
            ],
            capture_output=True, text=True, timeout=HARD_TIMEOUT,
            cwd=str(REPO_ROOT),
            env=loader_env({
                "AFL_NO_UI": "1",
                "AFL_SKIP_CPUFREQ": "1",
                "AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1",
                "NV_STATUS_PATH": str(EVIDENCE / "nv_http_status.json"),
                "NV_P01_SEEN_PATH": str(EVIDENCE / "seen.bin"),
                "NV_P01_SEQ_PATH": str(EVIDENCE / "seq.bin"),
                "NV_P01_EXEC_LOG": str(EVIDENCE / "target_executions.jsonl"),
                "NV_P01_STATIC_STAMP": "1",
            }),
        )
        (EVIDENCE / "afl_stdout.log").write_text(
            proc.stdout + "\n" + proc.stderr, encoding="utf-8"
        )

        stats_path = out / "default" / "fuzzer_stats"
        if not stats_path.is_file():
            stats_path = out / "fuzzer_stats"
        if not stats_path.is_file():
            raise AssertionError(
                f"afl-fuzz produced no fuzzer_stats (rc={proc.returncode}):\n"
                f"{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
            )
        cls.stats = parse_key_value(stats_path)

        log = EVIDENCE / "target_executions.jsonl"
        cls.target_execs = sum(
            1 for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ) if log.is_file() else 0

        cls.observations = int(cls.stats["security_state_observations"])
        cls.ratio = (
            cls.observations / cls.target_execs if cls.target_execs else 0.0
        )

        (EVIDENCE / "summary.json").write_text(
            json.dumps(
                {
                    "finding": "M-3 replay identity",
                    "target": "test/p01/status_seq_target.c",
                    "mode": "NV_P01_STATIC_STAMP=1 (legacy stamp is constant)",
                    "execution_scope": "p01_deterministic_integration_test",
                    "boundary": (
                        "local instrumented target; not a platform experiment; "
                        "not a real O2OA/Alfresco/Flowable service"
                    ),
                    "target_executions": cls.target_execs,
                    "security_state_observations": cls.observations,
                    "consumption_ratio": round(cls.ratio, 4),
                    "security_state_replays": cls.stats.get(
                        "security_state_replays"
                    ),
                    "security_state_total": cls.stats.get(
                        "security_state_total"
                    ),
                    "security_state_reward_src_seq": cls.stats.get(
                        "security_state_reward_src_seq"
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        curate_evidence(EVIDENCE, ["target_executions.jsonl"])

    def test_the_run_actually_stressed_the_replay_check(self) -> None:
        self.assertGreater(
            self.target_execs, 100,
            "too few executions to say anything about replay handling",
        )

    def test_distinct_executions_are_not_dropped_as_replays(self) -> None:
        self.assertGreaterEqual(
            self.ratio, MIN_CONSUMPTION_RATIO,
            "distinct executions were discarded as replays purely because "
            "their status documents looked identical: "
            f"{self.observations} observations from {self.target_execs} "
            f"executions (ratio {self.ratio:.4f})",
        )

    def test_replay_counter_is_reported(self) -> None:
        self.assertIn("security_state_replays", self.stats)
        self.assertGreaterEqual(int(self.stats["security_state_replays"]), 0)

    def test_reward_source_execution_is_recorded(self) -> None:
        """The audit record M-2 needs: which execution fed the last reward."""
        self.assertIn("security_state_reward_src_seq", self.stats)


if __name__ == "__main__":
    unittest.main()
