from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from compute_formal_security_score import (
    FormalScoreConfig,
    compute_formal_score,
    compute_from_stats,
    compute_recovery_rate,
)
from integration.platforms import core_runner


ROOT = Path(__file__).resolve().parents[1]
CONFIG = FormalScoreConfig(1 / 3, 1 / 3, 1 / 3)


def _write_stats(path: Path, opportunities: int, successes: int, raw_total: int = 0) -> Path:
    path.write_text(
        "\n".join((
            "nv_err_rate: 0.25",
            f"nv_rec_total: {raw_total}",
            "nv_rec_success: 0",
            "recovery_opportunity_count: " + str(opportunities),
            "recovery_success_count: " + str(successes),
            "security_state_new_total: 2",
            "security_state_capacity: 65536",
            "",
        )),
        encoding="utf-8",
    )
    return path


def test_no_recovery_opportunity_returns_python_none_and_json_null(tmp_path: Path) -> None:
    stats = _write_stats(tmp_path / "fuzzer_stats", opportunities=0, successes=0, raw_total=1)
    score, provenance = compute_from_stats(stats, CONFIG)

    assert compute_recovery_rate(0, 0) is None
    assert compute_formal_score(CONFIG, 2 / 65536, 0.25, None) is None
    assert score is None
    assert provenance["normalized_metrics"]["R_rec"] is None
    assert provenance["status"] == "undefined"
    serialized = json.loads(json.dumps({"recovery_rate": provenance["normalized_metrics"]["R_rec"], "overall_score": score}))
    assert serialized == {"recovery_rate": None, "overall_score": None}


def test_real_opportunity_with_zero_success_is_numeric_zero(tmp_path: Path) -> None:
    stats = _write_stats(tmp_path / "fuzzer_stats", opportunities=2, successes=0)
    score, provenance = compute_from_stats(stats, CONFIG)

    assert compute_recovery_rate(0, 2) == 0.0
    assert score is not None
    assert provenance["normalized_metrics"]["R_rec"] == 0.0
    assert provenance["recovery_source"]["denominator_value"] == 2


def test_partial_recovery_is_one_half(tmp_path: Path) -> None:
    stats = _write_stats(tmp_path / "fuzzer_stats", opportunities=2, successes=1)
    _score, provenance = compute_from_stats(stats, CONFIG)

    assert provenance["normalized_metrics"]["R_rec"] == 0.5


def test_full_recovery_is_one(tmp_path: Path) -> None:
    stats = _write_stats(tmp_path / "fuzzer_stats", opportunities=2, successes=2)
    _score, provenance = compute_from_stats(stats, CONFIG)

    assert provenance["normalized_metrics"]["R_rec"] == 1.0


def test_recovery_opportunity_requires_all_four_observations() -> None:
    events = [
        {"recovery_observations": {
            "pre_health": True,
            "failure_observed": True,
            "recovery_health": True,
            "post_recovery_business_check": True,
        }},
        {"recovery_observations": {
            "pre_health": True,
            "failure_observed": True,
            "recovery_health": True,
            "post_recovery_business_check": False,
        }},
        {"recovery_observations": {"pre_health": True, "failure_observed": True}},
    ]

    recovery_metrics = getattr(core_runner, "_recovery_metrics", None)
    assert callable(recovery_metrics)
    assert recovery_metrics(events) == (2, 1)


def test_generic_mock_success_reports_null_without_changing_core_accounting(tmp_path: Path) -> None:
    evidence = tmp_path / "generic_success"
    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "deep2fuzz"), "platform", "run", "mock_rest", "--evidence-root", str(evidence)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=25,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    report = json.loads((evidence / "eval_report.json").read_text(encoding="utf-8"))
    overall = json.loads((evidence / "formal_security_score.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["security_state_seed_credit"] == 1
    assert summary["EXECUTION_IDENTITY_RECONCILIATION"] == "PASS"
    assert summary["STATE_ACCOUNTING_RECONCILIATION"] == "PASS"
    assert summary["MAB_ATTRIBUTION_RECONCILIATION"] == "PASS"
    assert summary["SEED_ACCOUNTING_RECONCILIATION"] == "PASS"
    assert summary["CLEANUP_RECONCILIATION"] == "PASS"
    assert summary["COV_BEHAVIOR_UNCHANGED"] == "PASS"
    assert summary["ERR_BEHAVIOR_UNCHANGED"] == "PASS"
    assert report["rec"]["recovery_opportunity_count"] == 0
    assert report["rec"]["rec_rate"] is None
    assert report["formal_security_score"] is None
    assert overall["formal_security_score"] is None
    assert overall["provenance"]["normalized_metrics"]["R_rec"] is None
    assert summary["REPORT_ACCOUNTING_RECONCILIATION"] == "PASS"


def test_generic_semantic_failure_err_does_not_fake_recovery_opportunity(tmp_path: Path) -> None:
    evidence = tmp_path / "semantic_failure"
    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "deep2fuzz"), "platform", "run", "mock_rest", "--scenario", "semantic_failure",
         "--evidence-root", str(evidence)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=25,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    report = json.loads((evidence / "eval_report.json").read_text(encoding="utf-8"))
    overall = json.loads((evidence / "formal_security_score.json").read_text(encoding="utf-8"))
    assert summary["nv_err_exec"] > 0
    assert summary["ERR_BEHAVIOR_UNCHANGED"] == "PASS"
    assert report["rec"]["rec_total"] > 0  # Preserve the raw AFL counter.
    assert report["rec"]["recovery_opportunity_count"] == 0
    assert report["rec"]["rec_rate"] is None
    assert overall["formal_security_score"] is None


def test_delivery_sample_reports_null_without_recovery_observations(tmp_path: Path) -> None:
    sample = tmp_path / "delivery_sample"
    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)
    env.update({"ROOT": str(ROOT), "OUT_DIR": str(sample), "PYTHON_BIN": sys.executable})
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_task4_sample.py")],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False, timeout=40,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((sample / "sample_eval_report.json").read_text(encoding="utf-8"))
    eval_report = json.loads((sample / "eval_report.json").read_text(encoding="utf-8"))
    assert report["recovery_opportunity_count"] == 0
    assert report["recovery_success_count"] == 0
    assert report["recovery_rate"] is None
    assert report["overall_score"] is None
    assert eval_report["rec"]["recovery_opportunity_count"] == 0
    assert eval_report["rec"]["recovery_success_count"] == 0
    assert eval_report["rec"]["rec_rate"] is None
    assert eval_report["formal_security_score"] is None
    summary = (sample / "sample_summary.md").read_text(encoding="utf-8")
    assert "- Rec: `null`" in summary
    assert "- overall score: `null`" in summary


def test_recovery_opportunity_success_count_comes_from_complete_evidence() -> None:
    events = [
        {"recovery_observations": {
            "pre_health": True,
            "failure_observed": True,
            "recovery_health": True,
            "post_recovery_business_check": True,
        }},
        {"recovery_observations": {
            "pre_health": True,
            "failure_observed": True,
            "recovery_health": False,
            "post_recovery_business_check": False,
        }},
    ]

    recovery_metrics = getattr(core_runner, "_recovery_metrics", None)
    assert callable(recovery_metrics)
    assert recovery_metrics(events) == (2, 1)
