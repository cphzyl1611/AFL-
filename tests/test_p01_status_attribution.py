"""P0.1 finding M-2: a calibration re-execution must not become the reward source.

common_fuzz_stuff() runs the target, then calls save_if_interesting(), which
re-executes the target up to CAL_CYCLES times through calibrate_case().  The
status document is a single file, so those re-executions overwrite it.  Reading
the document after save_if_interesting() therefore scores the mutation against
the calibration run's state instead of its own.

The reproduction is an integration run against a real instrumented target, not
a simulation of the call order.  test/p01/status_seq_target.c stamps every
execution with a strictly increasing exec_seq and logs it, and afl-fuzz logs
the exec_seq of every observation it actually consumed
(NV_STATE_TRACE_PATH).  The two logs are then reconciled.

A calibration burst appears in the target log as a run of consecutive
executions of the *same* input: the first is the mutation being scored, the
rest are calibrate_case() re-running it.  So:

    correct   -> the consumed exec_seq is the FIRST execution of its run
    defective -> the consumed exec_seq is the LAST one, and the first is
                 never consumed at all

Counting security states is not enough to tell these apart -- havoc legitimately
regenerates identical inputs, so a "repeat" state is not by itself evidence of
the defect.  Execution identity is.

Evidence is written under out/p01_m2_status_attribution/.
"""

import json
import os
import shutil
import subprocess
import tempfile
import sysconfig
import unittest
from pathlib import Path


def loader_env(extra: dict) -> dict:
    """afl-fuzz links libpython, so the loader needs that interpreter's libdir.

    Derived from sysconfig rather than hardcoded: the binary was linked against
    whichever python3-config was on PATH at build time, which is not always the
    system one (a conda interpreter is the common case).
    """
    env = {**os.environ, **extra}
    libdir = sysconfig.get_config_var("LIBDIR")
    if libdir:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{libdir}:{existing}" if existing else libdir
    return env


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = None
AFL_FUZZ = REPO_ROOT / "afl-fuzz"
AFL_CC = REPO_ROOT / "afl-clang-fast"
TARGET_SRC = REPO_ROOT / "test" / "p01" / "status_seq_target.c"

RUN_SECONDS = 12
HARD_TIMEOUT = 90


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


class P01StatusAttributionTest(unittest.TestCase):
    """Runs one short instrumented campaign and asserts on its evidence."""

    @classmethod
    def setUpClass(cls) -> None:
        if not AFL_FUZZ.is_file():
            raise unittest.SkipTest("afl-fuzz is not built")
        if not AFL_CC.is_file():
            raise unittest.SkipTest(
                "afl-clang-fast is not built; instrumentation is required to "
                "reach calibrate_case() from save_if_interesting()"
            )

        global EVIDENCE
        EVIDENCE = evidence_root("p01_m2_status_attribution")
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
        env = loader_env({
            "AFL_NO_UI": "1",
            "AFL_SKIP_CPUFREQ": "1",
            "AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1",
            "NV_STATUS_PATH": str(EVIDENCE / "nv_http_status.json"),
            "NV_P01_SEEN_PATH": str(EVIDENCE / "seen.bin"),
            "NV_P01_SEQ_PATH": str(EVIDENCE / "seq.bin"),
            "NV_P01_EXEC_LOG": str(EVIDENCE / "target_executions.jsonl"),
            "NV_STATE_TRACE_PATH": str(EVIDENCE / "consumed_observations.jsonl"),
        })
        proc = subprocess.run(
            [
                str(AFL_FUZZ), "-m", "none", "-s", "20260816",
                "-V", str(RUN_SECONDS),
                "-i", str(seeds), "-o", str(out),
                "--", str(target), "@@",
            ],
            capture_output=True, text=True, timeout=HARD_TIMEOUT,
            cwd=str(REPO_ROOT), env=env,
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

        def load_jsonl(path: Path) -> list:
            rows = []
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            return rows

        cls.execs = load_jsonl(EVIDENCE / "target_executions.jsonl")
        cls.consumed = load_jsonl(EVIDENCE / "consumed_observations.jsonl")

        # exec_seq -> input hash, and the maximal run of consecutive
        # executions of that same input (a calibration burst).
        by_seq = {e["exec_seq"]: e for e in cls.execs}
        ordered = sorted(by_seq)
        run_head = {}          # exec_seq -> exec_seq that started its run
        run_len = {}           # run head  -> length
        head = None
        for seq in ordered:
            prev = by_seq.get(seq - 1)
            same = prev is not None and prev["input_hash"] == by_seq[seq]["input_hash"]
            if not same:
                head = seq
            run_head[seq] = head
            run_len[head] = run_len.get(head, 0) + 1
        cls.by_seq, cls.run_head, cls.run_len = by_seq, run_head, run_len

        consumed_seqs = {c["exec_seq"] for c in cls.consumed if c.get("exec_seq")}
        cls.consumed_seqs = consumed_seqs

        # A burst is a run of >= 2 identical consecutive executions, i.e. one
        # the fuzzer calibrated.  For each burst that the fuzzer consumed
        # anything from, did it consume the head or only a re-execution?
        cls.bursts_head_consumed = 0
        cls.bursts_only_tail_consumed = []
        for h_seq, length in cls.run_len.items():
            if length < 2:
                continue
            members = [h_seq + i for i in range(length)]
            touched = [m for m in members if m in consumed_seqs]
            if not touched:
                continue
            if h_seq in consumed_seqs:
                cls.bursts_head_consumed += 1
            else:
                cls.bursts_only_tail_consumed.append(
                    {"run_head": h_seq, "run_len": length, "consumed": touched}
                )

        (EVIDENCE / "summary.json").write_text(
            json.dumps(
                {
                    "finding": "M-2 execution-status attribution",
                    "target": "test/p01/status_seq_target.c",
                    "execution_scope": "p01_deterministic_integration_test",
                    "boundary": (
                        "local instrumented target; not a platform experiment; "
                        "not a real O2OA/Alfresco/Flowable service"
                    ),
                    "security_state_total": cls.stats.get("security_state_total"),
                    "security_state_observations": cls.stats.get(
                        "security_state_observations"
                    ),
                    "security_state_reward_src_seq": cls.stats.get(
                        "security_state_reward_src_seq"
                    ),
                    "target_executions": len(cls.execs),
                    "target_repeat_executions": sum(
                        1 for e in cls.execs if not e["first"]
                    ),
                    "calibration_bursts": sum(
                        1 for v in cls.run_len.values() if v >= 2
                    ),
                    "consumed_observations": len(cls.consumed),
                    "bursts_where_head_was_consumed": cls.bursts_head_consumed,
                    "bursts_where_only_a_reexecution_was_consumed": len(
                        cls.bursts_only_tail_consumed
                    ),
                    "example_misattributions": cls.bursts_only_tail_consumed[:5],
                    "corpus_count": cls.stats.get("corpus_count"),
                    "edges_found": cls.stats.get("edges_found"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        curate_evidence(EVIDENCE, ["target_executions.jsonl", "consumed_observations.jsonl"])

    def test_calibration_actually_reexecuted_the_target(self) -> None:
        """Guards the test itself: without bursts there is nothing to catch."""
        bursts = sum(1 for v in self.run_len.values() if v >= 2)
        self.assertGreater(
            bursts, 0,
            "the target was never re-executed back to back, so this run "
            "cannot exhibit the calibration-overwrite defect at all",
        )
        self.assertGreater(
            len(self.consumed), 0, "no observation was consumed at all"
        )

    def test_reward_source_is_never_a_calibration_reexecution(self) -> None:
        self.assertEqual(
            self.bursts_only_tail_consumed, [],
            "the fuzzer consumed a re-execution instead of the execution that "
            "started the burst -- the observation scored did not belong to the "
            "mutation being fuzzed. Offenders (run_head, run_len, consumed): "
            f"{self.bursts_only_tail_consumed[:5]}",
        )

    def test_snapshot_matches_the_original_execution(self) -> None:
        """No execution may have its own observation skipped for a later one.

        A consumed observation that is not the head of its same-input run is
        only a defect if the head went unconsumed.  When both are consumed the
        run is not a calibration burst at all -- it is havoc regenerating the
        same input in consecutive executions, and each execution correctly
        produced its own observation.
        """
        skipped = [
            s for s in sorted(self.consumed_seqs)
            if s in self.run_head
            and self.run_head[s] != s
            and self.run_head[s] not in self.consumed_seqs
        ]
        self.assertEqual(
            skipped, [],
            f"{len(skipped)} observations were taken from a re-execution while "
            f"the originating execution was never observed: {skipped[:10]}",
        )

    def test_states_were_actually_observed(self) -> None:
        self.assertGreater(int(self.stats["security_state_observations"]), 0)

    def test_covset_did_not_saturate(self) -> None:
        self.assertEqual(int(self.stats["security_state_saturated"]), 0)
        self.assertEqual(int(self.stats["security_state_dropped"]), 0)


if __name__ == "__main__":
    unittest.main()
