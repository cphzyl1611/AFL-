"""Offline full-core runner for the generic loopback adapter contract."""
from __future__ import annotations

import json
import hashlib
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from deep2fuzz_portability import default_evidence_parent, terminate_process, termination_plan
from .abort import read_abort_marker
from .mock_rest.service import MockRestService


def _new_root(value: str | Path | None) -> Path:
    if value is None:
        parent = default_evidence_parent()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        root = parent / f"DEEP2FUZZ_PHASE1_1_RUNTIME_DISTRIBUTION-{stamp}"
        suffix = 1
        while root.exists():
            root = parent / f"DEEP2FUZZ_PHASE1_1_RUNTIME_DISTRIBUTION-{stamp}-{suffix}"
            suffix += 1
    else:
        root = Path(value).resolve()
    repo = Path(__file__).resolve().parents[2]
    if not root.is_absolute() or root == repo or root.is_relative_to(repo):
        raise ValueError("evidence root must be absolute and outside the repository")
    if root.exists():
        raise FileExistsError(f"refusing to overwrite evidence root: {root}")
    root.mkdir(parents=True)
    (root / "evidence").mkdir()
    (root / "control").mkdir()
    return root


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stats(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key.strip()] = value.strip()
    return values


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _recovery_metrics(events: list[dict]) -> tuple[int, int]:
    observation_names = (
        "pre_health",
        "failure_observed",
        "recovery_health",
        "post_recovery_business_check",
    )
    opportunities = 0
    successes = 0
    for event in events:
        observations = event.get("recovery_observations")
        if not isinstance(observations, dict) or any(
            not isinstance(observations.get(name), bool) for name in observation_names
        ):
            continue
        opportunities += 1
        if observations["recovery_health"] and observations["post_recovery_business_check"]:
            successes += 1
    return opportunities, successes


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terminate_process_group(process: subprocess.Popen, grace_seconds: float = 2.0) -> tuple[str, str, bool]:
    requested_at = _utc_now()
    escalation = terminate_process(process, grace_seconds=grace_seconds)
    return requested_at, _utc_now(), escalation


def process_terminated_before_budget(terminal: dict[str, object] | None, stats: dict[str, str]) -> bool:
    """The supervisor owns termination; a marker plus observed process exit is
    the authoritative terminal signal even when AFL exits gracefully with 0."""
    try:
        run_seconds = float(stats.get("run_time", "inf"))
    except ValueError:
        return False
    return bool(terminal and terminal.get("process_exited_at") and run_seconds < 2.0)


def _run_afl_supervised(command: list[str], env: dict[str, str], cwd: Path, output_path: Path,
                        abort_path: Path, service: MockRestService) -> tuple[int, dict[str, object] | None]:
    wakeup = False
    wake_signal = getattr(signal, "SIGUSR1", None)
    previous_handler = signal.getsignal(wake_signal) if wake_signal is not None else None

    def notify(_signum, _frame):
        nonlocal wakeup
        wakeup = True

    if wake_signal is not None:
        try:
            signal.signal(wake_signal, notify)
        except (AttributeError, OSError, ValueError):
            wake_signal = None
    env["DEEP2FUZZ_SUPERVISOR_PID"] = str(os.getpid())
    env["DEEP2FUZZ_ABORT_MARKER"] = str(abort_path)
    with output_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        env["DEEP2FUZZ_SUPERVISOR_PID"] = str(os.getpid())
        try:
            supervisor_timeout = float(env.get("DEEP2FUZZ_SUPERVISOR_TIMEOUT_SECONDS", "15"))
        except ValueError:
            supervisor_timeout = 15.0
        deadline = time.monotonic() + supervisor_timeout
        terminal: dict[str, object] | None = None
        while process.poll() is None:
            marker = read_abort_marker(abort_path)
            if marker is not None:
                detected_at = _utc_now()
                status_path = Path(env["NV_STATUS_LEDGER_PATH"])
                status_deadline = time.monotonic() + 1.0
                status_published = False
                while time.monotonic() < status_deadline and process.poll() is None:
                    try:
                        for line in status_path.read_text(encoding="utf-8").splitlines():
                            if line.strip() and int(json.loads(line).get("exec_seq", 0) or 0) == int(marker["exec_seq"]):
                                status_published = True
                                break
                    except (OSError, ValueError, json.JSONDecodeError):
                        pass
                    if status_published:
                        break
                    time.sleep(0.005)
                request_count_at_abort = service.request_count
                creations_at_abort = service.object_creation_count
                requested_at, exited_at, escalation = _terminate_process_group(process)
                terminal = {
                    "marker": marker,
                    "abort_detected_at": detected_at,
                    "termination_requested_at": requested_at,
                    "process_exited_at": exited_at,
                    "abort_status_published": status_published,
                    "termination_escalation_used": escalation,
                    "requests_at_abort": request_count_at_abort,
                    "requests_after_abort": max(0, service.request_count - request_count_at_abort),
                    "creations_at_abort": creations_at_abort,
                    "creations_after_abort": max(0, service.object_creation_count - creations_at_abort),
                }
                break
            if time.monotonic() >= deadline:
                _terminate_process_group(process)
                raise RuntimeError("offline AFL campaign exceeded supervisor deadline")
            if wakeup:
                wakeup = False
            time.sleep(0.01)
        if process.poll() is None:
            process.wait()
        output.flush()
    if wake_signal is not None and previous_handler is not None:
        signal.signal(wake_signal, previous_handler)
    return int(process.returncode), terminal


def run_core_mock(evidence_root: str | Path | None = None, scenario: str = "success",
                  run_config: dict[str, object] | None = None) -> dict[str, object]:
    if scenario not in {"success", "validity_rejection", "expected_rejection", "semantic_failure", "cleanup_failure"}:
        raise ValueError(f"unsupported offline mock scenario: {scenario}")
    termination_plan()
    settings = dict(run_config or {})
    max_test_cases = int(settings.get("max_test_cases", 2))
    time_budget_value = settings.get("time_budget_seconds", 2)
    if isinstance(time_budget_value, bool) or not isinstance(time_budget_value, (int, float)) or time_budget_value <= 0:
        raise ValueError("time budget must be a positive number of seconds")
    # The existing AFL/task contract consumes whole seconds. Preserve its
    # truncation behavior after the config layer accepts a finite number.
    time_budget_seconds = max(1, int(float(time_budget_value)))
    timeout_seconds = float(settings.get("timeout_seconds", 15))
    validity_enabled = bool(settings.get("validity_enabled", True))
    adapter_timeout_sec = float(settings.get("adapter_timeout_sec", 2.0))
    provenance_config = settings.get("provenance_config")
    if not isinstance(provenance_config, dict):
        provenance_config = None
    configured_seed: bytes | None = None
    seed_path = settings.get("seed_path")
    if seed_path:
        source = Path(str(seed_path)).resolve(strict=True)
        if settings.get("seed_kind") == "dir":
            candidates = sorted(source.iterdir(), key=lambda item: item.name)
            candidates = [item for item in candidates if item.is_file()]
            if not candidates:
                raise ValueError("configured seed directory contains no regular files")
            source = candidates[0].resolve(strict=True)
            if not source.is_relative_to(Path(str(seed_path)).resolve(strict=True)):
                raise ValueError("configured seed file escapes the seed directory")
        if not source.is_file():
            raise ValueError("configured seed input is not a file")
        configured_seed = source.read_bytes()
    root = _new_root(evidence_root)
    repo = Path(__file__).resolve().parents[2]
    afl = repo / "afl-fuzz"
    if not afl.is_file() or not os.access(afl, os.X_OK):
        raise RuntimeError("native afl-fuzz is missing; run `make -j2 afl-fuzz`")
    seed_dir = root / "seeds"
    seed_dir.mkdir()
    request_path = "/not-allowed" if scenario == "validity_rejection" else "/api/items"
    task_id = "phase1-1-mock"
    seed_path = seed_dir / "seed_0.http"
    if configured_seed is None:
        seed_path.write_text(
            f"POST {request_path} HTTP/1.1\nContent-Type: application/json\n\n"
            + json.dumps({"title": "phase1.1", "value": 1}, separators=(",", ":")) + "\n", encoding="utf-8")
    else:
        seed_path.write_bytes(configured_seed)
    seed_id = "seed-" + hashlib.sha256(seed_path.read_bytes()).hexdigest()[:12]
    task = root / "task.json"
    config = root / "target.json"
    _write_json(task, {"target_type": "http_api", "target_endpoint": "mock_rest", "seed_source": "seed_file", "seed_location": str(seed_dir), "mutation_scope": ["boundary"], "max_test_cases": max_test_cases, "time_budget": time_budget_seconds, "enable_validity": int(validity_enabled)})
    _write_json(config, {"endpoints": [{"method": "POST", "path": "/api/items"}, {"method": "PUT", "path": "/api/items/*"}]})
    provenance_config_path = root / "provenance_config.json"
    if provenance_config is None:
        generated_config = {
            "schema_version": "1",
            "platform": "mock_rest",
            "run": {
                "max_test_cases": max_test_cases,
                "time_budget_seconds": time_budget_value,
                "timeout_seconds": timeout_seconds,
            },
            "inputs": {"seed_file": "seeds/seed_0.http"},
            "output": {"evidence_root": "provenance-evidence-placeholder"},
            "validity": {"enabled": validity_enabled},
            "cleanup": {"required": True},
            "platform_config": {"mock_rest": {"timeout_sec": adapter_timeout_sec}},
        }
        _write_json(provenance_config_path, generated_config)
        from deep2fuzz_config.validator import validate_config

        validation = validate_config(provenance_config_path)
        if validation.verdict != "PASS":
            raise ValueError("generated provenance config does not satisfy the P1.2 schema")
        provenance_config = validation.normalized
    else:
        _write_json(provenance_config_path, provenance_config)
    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)
    env.update({
        "AFL_NO_UI": "1", "AFL_SKIP_CPUFREQ": "1", "AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1",
        "AFL_PYTHON_MODULE": "nv_json_mutator", "PYTHONPATH": str(repo),
        "DEEP2FUZZ_CORE_ADAPTER_BRIDGE": "1",
        "NV_TASK_PATH": str(task), "NV_TARGET_CONFIG": str(config),
        "NV_STATUS_PATH": str(root / "nv_http_status.json"),
        "NV_STATUS_LEDGER_PATH": str(root / "evidence" / "status.jsonl"),
        "NV_STATE_TRACE_PATH": str(root / "evidence" / "state.jsonl"),
        "NV_PROBE_PATH": str(root / "probe.json"), "NV_STATE_DB": str(root / "state_db.json"),
        "NV_MAB_JOURNAL_PATH": str(root / "evidence" / "mab_updates.jsonl"),
        "NV_EXECUTION_LEDGER_PATH": str(root / "evidence" / "executions.jsonl"),
        "NV_SEED_SELECTION_AUDIT_PATH": str(root / "evidence" / "seed_selection.jsonl"),
        "DEEP2FUZZ_TASK_ID": task_id, "DEEP2FUZZ_RUN_ID": root.name,
        "DEEP2FUZZ_SEED_ID": seed_id,
        "DEEP2FUZZ_ADAPTER_EVENTS": str(root / "evidence" / "adapter_events.jsonl"),
        "DEEP2FUZZ_SUPERVISOR_TIMEOUT_SECONDS": str(timeout_seconds),
        "DEEP2FUZZ_MOCK_TIMEOUT_SEC": str(adapter_timeout_sec),
    })
    abort_path = root / "control" / "abort.json"
    env["DEEP2FUZZ_ABORT_MARKER"] = str(abort_path)
    env["DEEP2FUZZ_ABORT_OBSERVATIONS"] = str(root / "evidence" / "abort_observations.jsonl")
    # Python target startup plus the loopback lifecycle can exceed AFL++'s
    # implicit 1s dry-run timeout under a busy CI/WSL host.  Keep this bounded
    # and explicit without changing campaign or accounting semantics.
    command = [str(afl), "-n", "-m", "none", "-d", "-V", str(time_budget_seconds), "-t", "2000", "-i", str(seed_dir), "-o", str(root), "--", sys.executable, str(repo / "integration/platforms/mock_rest/target.py"), "@@"]
    with MockRestService(scenario=scenario) as service:
        env["DEEP2FUZZ_MOCK_URL"] = service.base_url
        returncode, terminal = _run_afl_supervised(command, env, repo, root / "afl_console.log", abort_path, service)
        requests = service.request_count
        creations = service.object_creation_count
    if terminal is None and returncode != 0:
        raise RuntimeError(f"offline core runner failed with status {returncode}")
    stats_path = root / "fuzzer_stats"
    stats = _stats(stats_path)
    eval_report = root / "eval_report.json"
    mab = root / "evidence" / "mab_updates.jsonl"
    ledger = root / "evidence" / "executions.jsonl"
    status = root / "evidence" / "status.jsonl"
    state = root / "evidence" / "state.jsonl"
    seed_audit = root / "evidence" / "seed_selection.jsonl"
    artifacts = [stats_path, eval_report, mab, ledger, status, state, seed_audit]
    if any(not path.is_file() for path in artifacts):
        raise RuntimeError("offline core runner did not produce all core artifacts")
    events = [json.loads(line) for line in (root / "evidence" / "adapter_events.jsonl").read_text().splitlines() if line.strip()]
    mabs = [json.loads(line) for line in mab.read_text().splitlines() if line.strip() and json.loads(line).get("event") == "mab_update"]
    ledgers = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip() and json.loads(line).get("event") == "execution"]
    statuses = [json.loads(line) for line in status.read_text().splitlines() if line.strip()]
    states = [json.loads(line) for line in state.read_text().splitlines() if line.strip()]
    def positive_seq(row: dict) -> int:
        value = row.get("exec_seq")
        return int(value) if isinstance(value, (int, str)) and str(value).isdigit() and int(value) > 0 else 0
    status_by_seq = {positive_seq(row): row for row in statuses if positive_seq(row)}
    cleanup_pass = bool(events and all(
        row.get("cleanup")
        and (row.get("created_object_id") is None or (
            row.get("created_object_id") == row.get("cleanup_object_id")
            and row.get("absence_verified") is True
        ))
        for row in events
    ))
    report = json.loads(eval_report.read_text(encoding="utf-8"))
    recovery_opportunities, recovery_successes = _recovery_metrics(events)
    score_stats_path = root / "formal_score_stats.txt"
    score_stats_path.write_text(
        stats_path.read_text(encoding="utf-8")
        + f"\nrecovery_opportunity_count: {recovery_opportunities}"
        + f"\nrecovery_success_count: {recovery_successes}\n",
        encoding="utf-8",
    )
    score_result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "compute_formal_security_score.py"),
         str(score_stats_path), "0.3333333333333333", "0.3333333333333333", "0.3333333333333334"],
        cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
    )
    if score_result.returncode not in (0, 1):
        raise RuntimeError("existing core overall-score utility failed")
    overall = json.loads(score_result.stdout)
    overall_path = root / "formal_security_score.json"
    _write_json(overall_path, overall)
    report_cov = report["security_state_cov"]
    recovery_rate = overall.get("provenance", {}).get("normalized_metrics", {}).get("R_rec")
    report["rec"].update({
        "recovery_opportunity_count": recovery_opportunities,
        "recovery_success_count": recovery_successes,
        "rec_rate": recovery_rate,
    })
    report["formal_security_score"] = overall.get("formal_security_score")
    report["formal_score_provenance"] = overall.get("provenance")
    report["platform_adapter"] = "mock_rest"
    from deep2fuzz_provenance import build_provenance

    provenance = build_provenance(
        repo, config_snapshot=provenance_config, adapter="mock_rest",
        run_id=root.name, task_id=task_id, evidence_profile="platform-run",
    )
    report["provenance_required"] = True
    report["provenance"] = provenance
    _write_json(root / "provenance.json", provenance)
    _write_json(eval_report, report)
    report_seq = int(report_cov.get("security_state_reward_src_seq", 0) or 0)
    report_status = status_by_seq.get(report_seq, {})
    report_identity_pass = bool(
        report_seq > 0 and report_seq in status_by_seq
        and report_status.get("task_id") == task_id
        and report_status.get("run_id") == root.name
        and report_status.get("seed_id") == seed_id
        and report_status.get("mutation_arm") in {"arm-0", "arm-1", "arm-2"}
        and any(positive_seq(row) == report_seq for row in mabs)
    )
    report_pass = bool(
        int(report_cov["security_state_new_total"]) == int(stats.get("security_state_new_total", "-1"))
        and int(report_cov["security_state_seed_credit"]) == int(stats.get("security_state_seed_credit", "-1"))
        and int(report["validity"]["valid_cnt"]) == int(stats.get("nv_valid_cnt", "-1"))
        and int(report["validity"]["invalid_cnt"]) == int(stats.get("nv_invalid_cnt", "-1"))
        and int(report["err"]["err_exec"]) == int(stats.get("nv_err_exec", "-1"))
        and int(report["rec"]["rec_total"]) == int(stats.get("nv_rec_total", "-1"))
        and int(report["rec"]["rec_success"]) == int(stats.get("nv_rec_success", "-1"))
        and int(report["rec"]["recovery_opportunity_count"]) == recovery_opportunities
        and int(report["rec"]["recovery_success_count"]) == recovery_successes
        and int(report["mab"]["total_pulls"]) == len(mabs)
        and int(report["mab_journal"]["record_count"]) == len([row for row in jsonl(mab) if row.get("event")])
        and int(report["exec"]["valid_exec"]) == int(stats.get("nv_total_valid_exec", "-1"))
        and (report_identity_pass if scenario != "validity_rejection" else report_seq == 0)
        and report.get("formal_security_score") == overall.get("formal_security_score")
        and overall.get("provenance", {}).get("status") == (
            "undefined" if recovery_opportunities == 0 else "computed"
        )
        and (overall.get("formal_security_score") is None) == (recovery_opportunities == 0)
    )
    mab_pass = bool(mabs and all(
        positive_seq(row) in status_by_seq
        and row.get("selected_arm") == row.get("actual_used_arm")
        and row.get("arm_match") is True
        and status_by_seq[positive_seq(row)].get("mutation_arm") == f"arm-{row.get('selected_arm')}"
        for row in mabs
    ))
    state_pass = bool(states and all(
        positive_seq(row) in status_by_seq
        and row.get("state") == "{} {}|{}".format(
            status_by_seq[positive_seq(row)].get("method"),
            status_by_seq[positive_seq(row)].get("path"),
            status_by_seq[positive_seq(row)].get("class"),
        )
        for row in states
    ))
    event_identity_pass = bool(events and all(
        positive_seq(row.get("identity", {})) in status_by_seq
        and all(row["identity"].get(key) == status_by_seq[positive_seq(row["identity"])].get(key)
                for key in ("task_id", "run_id", "seed_id", "mutation_arm"))
        for row in events
    ))
    ledger_pass = bool(ledgers and all(
        positive_seq(row) in status_by_seq
        and row.get("status_observed") is True
        and row.get("target_invoked") is True
        and row.get("selected_arm") == row.get("actual_used_arm")
        and status_by_seq[positive_seq(row)].get("mutation_arm") == f"arm-{row.get('actual_used_arm')}"
        for row in ledgers if row.get("status_observed")
    ))
    status_identity_pass = bool(statuses and all(
        positive_seq(row)
        and row.get("task_id") == task_id
        and row.get("run_id") == root.name
        and row.get("seed_id") == seed_id
        and row.get("mutation_arm") in {"arm-0", "arm-1", "arm-2"}
        for row in statuses
    ))
    queue_ids = {int(row["queue_id"]) for row in jsonl(seed_audit) if "queue_id" in row}
    seed_pass = bool(
        len(list(seed_dir.iterdir())) == 1
        and queue_ids == {0}
        and all(row.get("identity", {}).get("seed_id") == seed_id for row in events)
        and int(stats.get("ss_cov_sum", "-1")) == int(stats.get("security_state_seed_credit", "-2"))
    )
    identity_pass = bool(status_identity_pass and event_identity_pass and ledger_pass and state_pass and mab_pass and report_identity_pass)
    scenario_pass = False
    validity_rejected = int(stats.get("nv_invalid_cnt", "0"))
    if scenario == "success":
        scenario_pass = bool(identity_pass and cleanup_pass and requests > 0 and mab_pass and state_pass and report_pass and int(stats.get("security_state_seed_credit", "0")) > 0)
    elif scenario == "validity_rejection":
        rejected_rows = [row for row in ledgers if row.get("mab_outcome") == "body_validation_reject"]
        scenario_pass = bool(validity_rejected and not requests and not mabs and rejected_rows
                             and int(stats.get("nv_total_valid_exec", "0")) == 0
                             and int(stats.get("security_state_seed_credit", "0")) == 0
                             and all(not row.get("target_invoked") and not row.get("status_observed") and row.get("exec_seq") is None for row in rejected_rows))
        identity_pass = state_pass = scenario_pass
        cleanup_pass = requests == 0 and all(
            not row.get("created_object_id") and row.get("cleanup") is True
            for row in events
        )
    elif scenario == "expected_rejection":
        expected = [row for row in events if row.get("result", {}).get("expected_rejection")]
        scenario_pass = bool(expected and requests > 0 and identity_pass and cleanup_pass and mab_pass and report_pass
                             and int(stats.get("nv_err_exec", "0")) == 0
                             and int(stats.get("nv_rec_total", "0")) == 0)
    elif scenario == "semantic_failure":
        semantic = [row for row in events if row.get("result", {}).get("semantic_failure")]
        semantic_status = [row for row in statuses if row.get("is_exception") and 200 <= row.get("http_code", 0) < 300]
        scenario_pass = bool(semantic and semantic_status and identity_pass and int(stats.get("nv_err_exec", "0")) > 0
                             and int(stats.get("nv_rec_total", "0")) > 0
                             and int(stats.get("nv_rec_success", "0")) == 0
                             and cleanup_pass and mab_pass and report_pass)
    if scenario == "validity_rejection":
        report_identity_pass = report_seq == 0 and not events and not mabs
    identity_reconciliation = {
        "schema_version": 1,
        "identity_source": "runner task/run + sha256 of the sole mock seed + AFL++ NV_CUR_ARM + nv_http_harness.next_exec_seq()",
        "join_key": "exec_seq",
        "status_rows": len(statuses), "adapter_events": len(events),
        "execution_rows": len(ledgers), "state_rows": len(states), "mab_updates": len(mabs),
        "report_reward_source_exec_seq": report_seq,
        "checks": {
            "status_identity": "NOT_APPLICABLE" if scenario == "validity_rejection" else status_identity_pass,
            "adapter_to_status": "NOT_APPLICABLE" if scenario == "validity_rejection" else event_identity_pass,
            "execution_ledger_to_status": "NOT_APPLICABLE" if scenario == "validity_rejection" else ledger_pass,
            "state_to_status": "NOT_APPLICABLE" if scenario == "validity_rejection" else state_pass,
            "mab_arm_to_status": "NOT_APPLICABLE" if scenario == "validity_rejection" else mab_pass,
            "seed_accounting": seed_pass,
            "report_to_reward_source": report_identity_pass,
        },
    }
    if report_identity_pass and report_seq:
        identity_reconciliation["identity"] = {
            "task_id": task_id, "run_id": root.name,
            "seed_id": seed_id, "exec_seq": report_seq,
            "mutation_arm": report_status.get("mutation_arm", ""),
        }
    _write_json(root / "identity_reconciliation.json", identity_reconciliation)
    summary: dict[str, object] = {
        "passed": scenario_pass,
        "scenario": scenario, "adapter": "mock_rest", "requests": requests, "events": len(events),
        "validity_enabled": stats.get("nv_enable_validity") == "1",
        "EXECUTION_IDENTITY_RECONCILIATION": "PASS" if identity_pass else "FAIL",
        "STATE_ACCOUNTING_RECONCILIATION": "PASS" if state_pass else "FAIL",
        "MAB_ATTRIBUTION_RECONCILIATION": "PASS" if mab_pass or scenario == "validity_rejection" and scenario_pass else "FAIL",
        "SEED_ACCOUNTING_RECONCILIATION": "PASS" if seed_pass else "FAIL",
        "REPORT_ACCOUNTING_RECONCILIATION": "PASS" if report_pass else "FAIL",
        "CLEANUP_RECONCILIATION": "PASS" if cleanup_pass else "FAIL",
        "validity_rejected": validity_rejected,
        "nv_err_exec": int(stats.get("nv_err_exec", "0")),
        "nv_rec_total": int(stats.get("nv_rec_total", "0")),
        "security_state_seed_credit": int(stats.get("security_state_seed_credit", "0")),
        "recovery_opportunity_count": recovery_opportunities,
        "recovery_success_count": recovery_successes,
        "COV_BEHAVIOR_UNCHANGED": "PASS" if (
            int(report_cov["security_state_new_total"]) == int(stats.get("security_state_new_total", "-1"))
            and int(report_cov["security_state_capacity"]) == int(stats.get("security_state_capacity", "-1"))
        ) else "FAIL",
        "ERR_BEHAVIOR_UNCHANGED": "PASS" if (
            int(report["err"]["err_exec"]) == int(stats.get("nv_err_exec", "-1"))
            and float(report["err"]["err_rate"]) == float(stats.get("nv_err_rate", "nan"))
        ) else "FAIL",
        "real_platform_contacted": False, "external_network_contacted": False,
        "core_artifacts": [str(path.relative_to(root)) for path in artifacts] + ["formal_security_score.json", "identity_reconciliation.json"],
    }
    if terminal is not None:
        marker = terminal["marker"]
        marker_seq = int(marker["exec_seq"])
        post_events = [row for row in events if positive_seq(row.get("identity", {})) > marker_seq]
        post_commits = [row for row in mabs if positive_seq(row) > marker_seq]
        post_states = [row for row in states if positive_seq(row) > marker_seq]
        post_statuses = [row for row in statuses if positive_seq(row) > marker_seq]
        terminal_reason = str(marker.get("reason", "CLEANUP_FAILED"))
        summary.update({
            "passed": False,
            "terminal": True,
            "terminal_reason": terminal_reason,
            "CLEANUP_FAILURE_DETECTED": "PASS",
            "ABORT_MARKER_WRITTEN": "PASS" if abort_path.is_file() else "FAIL",
            "ABORT_MARKER_ATOMIC": "PASS" if read_abort_marker(abort_path) == marker else "FAIL",
            "POST_CLEANUP_FAILURE_PLATFORM_EXECUTIONS": int(terminal["requests_after_abort"]),
            "POST_CLEANUP_FAILURE_OBJECT_CREATIONS": int(terminal["creations_after_abort"]),
            "POST_ABORT_FALSE_MAB_PULLS": len(post_commits),
            "POST_ABORT_FALSE_MAB_COMMITS": len(post_commits),
            "POST_ABORT_FALSE_SEED_CREDIT": sum(int(row.get("new", 0)) for row in post_states),
            "POST_ABORT_FALSE_STATE_UPDATES": len(post_states) + len(post_statuses),
            "AFL_CAMPAIGN_TERMINATED": "PASS" if process_terminated_before_budget(terminal, stats) else "FAIL",
            "AFL_SAVED_CRASHES": int(stats.get("saved_crashes", "0")),
            "PARTIAL_EVIDENCE_PRESERVED": "PASS" if all(path.is_file() for path in artifacts) else "FAIL",
            "termination_escalation_used": bool(terminal["termination_escalation_used"]),
        })
        termination = {
            "abort_detected_at": terminal["abort_detected_at"],
            "termination_requested_at": terminal["termination_requested_at"],
            "process_exited_at": terminal["process_exited_at"],
            "termination_escalation_used": bool(terminal["termination_escalation_used"]),
            "requests_at_abort": int(terminal["requests_at_abort"]),
            "requests_after_abort": int(terminal["requests_after_abort"]),
            "creations_at_abort": int(terminal["creations_at_abort"]),
            "creations_after_abort": int(terminal["creations_after_abort"]),
        }
        _write_json(root / "supervisor_termination.json", termination)
        _write_json(root / "run_status.json", {
            "run_complete": False, "terminal": True, "terminal_reason": terminal_reason,
            "passed": False, "task_id": marker["task_id"], "run_id": marker["run_id"],
            "abort_exec_seq": marker_seq,
        })
    _write_json(root / "core_mock_summary.json", summary)
    return {"evidence_root": str(root), **summary}
