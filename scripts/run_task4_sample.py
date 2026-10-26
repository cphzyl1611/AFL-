#!/usr/bin/env python3
"""Run and validate the bounded, deterministic offline delivery sample."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(os.environ.get("ROOT", Path(__file__).resolve().parents[1])).resolve()
OUT = Path(os.environ.get("OUT_DIR", "")).resolve()
PYTHON = Path(os.environ.get("PYTHON_BIN", sys.executable)).resolve()


def stats(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def required_int(values: dict[str, str], key: str) -> int:
    try:
        return int(values[key])
    except (KeyError, ValueError) as exc:
        raise SystemExit(f"invalid sample stats field: {key}") from exc


def main() -> int:
    if not OUT or OUT == ROOT or OUT.exists():
        raise SystemExit("OUT_DIR must be a new directory outside the source tree")
    if not (ROOT / "afl-fuzz").is_file():
        raise SystemExit("afl-fuzz is missing; run make -j2 afl-fuzz first")

    source_seeds = ROOT / "in/p0_o2oa_cms_doc_list"
    if not source_seeds.is_dir():
        raise SystemExit(f"missing sample seeds: {source_seeds}")
    OUT.mkdir(parents=True)
    task = OUT / "task.json"
    target = OUT / "target.json"
    task.write_text(json.dumps({
        "target_type": "http_api",
        "target_endpoint": "p0_offline_o2oa_shape",
        "seed_source": "seed_file",
        "seed_location": "in/p0_o2oa_cms_doc_list",
        "mutation_scope": ["field_value", "boundary", "structure"],
        "max_test_cases": int(os.environ.get("MAX_TEST_CASES", "8")),
        "time_budget": int(os.environ.get("TIME_BUDGET", "5")),
        "enable_validity": 1,
    }, indent=2) + "\n", encoding="utf-8")
    target.write_text(json.dumps({"endpoints": [{
        "method": "PUT",
        "path": "/x_cms_assemble_control/jaxrs/document/filter/list",
    }]}, indent=2) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "AFL_NO_UI": "1",
        "AFL_SKIP_CPUFREQ": "1",
        "AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1",
        "AFL_PYTHON_MODULE": "nv_json_mutator",
        "PYTHONPATH": str(ROOT),
        "NV_TASK_PATH": str(task),
        "NV_TARGET_CONFIG": str(target),
        "NV_STATUS_PATH": str(OUT / "nv_http_status.json"),
        "NV_P0_STATE_LOG": str(OUT / "security_states.jsonl"),
        "NV_P0_PROFILE": "o2oa_cms_doc_list",
    })
    libdir = subprocess.check_output(
        [str(PYTHON), "-c", "import sysconfig; print(sysconfig.get_config_var('LIBDIR') or '')"],
        text=True,
    ).strip()
    if libdir:
        env["LD_LIBRARY_PATH"] = libdir + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")

    command = [
        "timeout", f"{os.environ.get('HARD_TIMEOUT', '20')}s",
        str(ROOT / "afl-fuzz"), "-n", "-m", "none", "-s",
        os.environ.get("AFL_RAND_SEED", "20261026"),
        "-i", str(source_seeds), "-o", str(OUT), "--",
        str(PYTHON), str(ROOT / "targets/nv_p0_deterministic_target.py"), "@@",
    ]
    run = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, timeout=40)
    (OUT / "afl_console.log").write_text(run.stdout, encoding="utf-8")
    if run.returncode not in (0, 124):
        raise SystemExit(f"AFL delivery smoke failed with status {run.returncode}")

    summary_env = dict(env, OUT_DIR=str(OUT))
    summary = subprocess.run(
        [str(PYTHON), str(ROOT / "scripts/summarize_p0_mab_feedback.py")],
        cwd=ROOT, env=summary_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, check=False,
    )
    (OUT / "summary_writer.log").write_text(summary.stdout, encoding="utf-8")
    if summary.returncode != 0:
        raise SystemExit("sample summary generation failed")

    stats_path = OUT / "fuzzer_stats"
    eval_path = OUT / "eval_report.json"
    summary_path = OUT / "summary.csv"
    if not stats_path.is_file() or not eval_path.is_file() or not summary_path.is_file():
        raise SystemExit("sample did not produce the required raw artifacts")
    values = stats(stats_path)
    score = subprocess.run(
        [str(PYTHON), str(ROOT / "scripts/compute_formal_security_score.py"),
         str(stats_path), "0.3333333333333333", "0.3333333333333333", "0.3333333333333334"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if score.returncode != 0:
        raise SystemExit("formal score computation failed")
    score_json = json.loads(score.stdout)
    raw_eval = json.loads(eval_path.read_text(encoding="utf-8"))
    summary_row = next(csv.DictReader(summary_path.open(encoding="utf-8", newline="")))

    report = {
        "task_id": "offline-p0-mab-validity",
        "run_id": OUT.name,
        "platform": "o2oa-shaped-local-deterministic-target",
        "scenario": "offline_deterministic_feedback_smoke",
        "endpoint": "p0_offline_o2oa_shape",
        "seed_source": "in/p0_o2oa_cms_doc_list",
        "validity_enabled": required_int(values, "nv_enable_validity") == 1,
        "valid_exec": required_int(values, "nv_total_valid_exec"),
        "validity": raw_eval.get("validity"),
        "coverage_rate": score_json["provenance"]["normalized_metrics"]["Cov"],
        "anomaly_rate": score_json["provenance"]["normalized_metrics"]["Err"],
        "recovery_rate": score_json["provenance"]["normalized_metrics"]["R_rec"],
        "overall_score": score_json["formal_security_score"],
        "security_state_total": required_int(values, "security_state_total"),
        "security_state_new_total": required_int(values, "security_state_new_total"),
        "security_state_observations": required_int(values, "security_state_observations"),
        "security_state_capacity": required_int(values, "security_state_capacity"),
        "mab_total_pulls": required_int(values, "nv_mab_total_pulls"),
        "mab_arm_pulls": [required_int(values, f"nv_mab_arm{i}_pulls") for i in range(3)],
        "seed_scheduler_selected_sum": required_int(values, "ss_selected_sum"),
        "seed_scheduler_credit_sum": required_int(values, "ss_cov_sum"),
        "formal_score_provenance": {k: v for k, v in score_json["provenance"].items() if k != "stats_path"},
        "summary_source": summary_row["summary_source"],
        "execution_scope": summary_row["execution_scope"],
        "metric_semantics": summary_row["metric_semantics"],
        "delivery_smoke_only": True,
        "not_for_performance_claim": True,
        "evidence_boundary": "DELIVERY_SMOKE_ONLY; NOT_FOR_PERFORMANCE_CLAIM; no real platform or network",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    files = ["sample_eval_report.json", "sample_fuzzer_stats.txt", "sample_summary.md", "sample_metadata.json"]
    (OUT / "sample_eval_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "sample_fuzzer_stats.txt").write_text(stats_path.read_text(encoding="utf-8"), encoding="utf-8")
    (OUT / "sample_summary.md").write_text(
        "# Offline End-to-End Sample\n\n"
        "`DELIVERY_SMOKE_ONLY`; `NOT_FOR_PERFORMANCE_CLAIM`.\n\n"
        f"- task_id: `{report['task_id']}`\n"
        f"- validity_enabled: `{report['validity_enabled']}`\n"
        f"- valid_exec: `{report['valid_exec']}`\n"
        f"- Cov proxy: `{report['coverage_rate']}`\n"
        f"- Err: `{report['anomaly_rate']}`\n"
        f"- Rec: `{report['recovery_rate']}`\n"
        f"- overall score: `{report['overall_score']}`\n\n"
        "Cov is the bounded security-state proxy, not theoretical total-system coverage.\n",
        encoding="utf-8",
    )
    metadata = {
        "delivery_smoke_only": True,
        "not_for_performance_claim": True,
        "network": "none",
        "live_service": False,
        "fresh_output": True,
        "required_fields": ["coverage_rate", "anomaly_rate", "recovery_rate", "overall_score", "task_id", "endpoint", "seed_source"],
        "files": files,
    }
    (OUT / "sample_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    required = metadata["required_fields"]
    if any(field not in report for field in required):
        raise SystemExit("sample report is missing a required field")
    if any("/home/cphzy/AFL-" in (OUT / name).read_text(encoding="utf-8", errors="replace") for name in files):
        raise SystemExit("sample output contains an old absolute worktree path")
    print(json.dumps({"sample_dir": str(OUT), "required_fields": len(required), "valid_exec": report["valid_exec"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
