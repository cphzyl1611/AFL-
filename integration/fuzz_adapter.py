#!/usr/bin/env python3
import argparse
import copy
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from decision_engine import DecisionEngine
except ImportError:
    from integration.decision_engine import DecisionEngine


ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = ROOT / "integration" / "platform_profiles"
GENERATED_TASKS_DIR = ROOT / "integration" / "generated_tasks"
RUNNER_CLI = ROOT / "runner" / "fuzz_test_runner.py"
TASK_ID_PREFIX = "fuzz-task-"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_repo_path(path_value: str) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p
    return ROOT / p


def public_task_id(raw_task_id: str) -> str:
    raw = str(raw_task_id)
    if raw.startswith(TASK_ID_PREFIX):
        return raw
    return f"{TASK_ID_PREFIX}{raw}"


def raw_task_id(task_id: str) -> str:
    value = str(task_id)
    if value.startswith(TASK_ID_PREFIX):
        return value[len(TASK_ID_PREFIX):]
    return value


def error_response(action: str, message: str, **extra):
    obj = {
        "process_result": 0,
        "action": action,
        "error_message": message,
    }
    obj.update(extra)
    return obj


def success_response(action: str, **extra):
    obj = {
        "process_result": 1,
        "action": action,
    }
    obj.update(extra)
    return obj


def read_request(args):
    if getattr(args, "request_json", None):
        return load_json(resolve_repo_path(args.request_json))
    if getattr(args, "json", None):
        return json.loads(args.json)
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return json.loads(data)
    return {}


def profile_path(profile_name: str) -> Path:
    return PROFILES_DIR / f"{profile_name}.json"


def load_profile(profile_name: str):
    path = profile_path(profile_name)
    if not path.exists():
        raise FileNotFoundError(f"profile not found: {profile_name}")
    profile = load_json(path)
    decision = profile.get("decision")
    if isinstance(decision, dict):
        profile["decision"] = DecisionEngine(decision).to_config()
    profile["_profile_path"] = str(path)
    return profile


def list_profiles():
    profiles = []
    if not PROFILES_DIR.exists():
        return profiles
    for path in sorted(PROFILES_DIR.glob("*.json")):
        obj = load_json(path)
        profiles.append({
            "profile": obj.get("profile", path.stem),
            "platform": obj.get("platform", ""),
            "scene": obj.get("scene", ""),
            "model_route": obj.get("model_route", ""),
            "threshold": obj.get("threshold", ""),
            "template": obj.get("template", ""),
            "is_mainline": bool(obj.get("is_mainline", False)),
            "validation_scope": obj.get("validation_scope", ""),
            "decision": obj.get("decision", {}),
        })
    return profiles


def normalize_duration_plan(request: dict, profile: dict, template: dict):
    if request.get("duration_plan"):
        values = request["duration_plan"]
        if not isinstance(values, list):
            raise ValueError("duration_plan must be a list of seconds")
        return [int(x) for x in values]
    if request.get("time_budget"):
        return [int(request["time_budget"])]
    if profile.get("duration_plan"):
        return [int(x) for x in profile["duration_plan"]]
    return [int(x) for x in template.get("duration_plan", [20, 60])]


def replace_env_assignment(command: str, name: str, value: str) -> str:
    pattern = rf'{re.escape(name)}="[^"]*"'
    replacement = f'{name}="{value}"'
    if re.search(pattern, command):
        return re.sub(pattern, replacement, command)
    return command


def prepend_env_assignments(command: str, env_map: dict[str, str]) -> str:
    prefix = " ".join(
        f"{name}={shlex.quote(str(value))}"
        for name, value in env_map.items()
        if value not in (None, "")
    )
    if not prefix:
        return command
    return f"{prefix} {command}"


def update_launch_cmd(task_config: dict, profile: dict, seed_dir: str, threshold: str, duration_plan):
    launch_cmd = task_config.get("launch_cmd")
    if not isinstance(launch_cmd, list):
        return

    plan_text = " ".join(str(x) for x in duration_plan)
    old_seed_values = {
        str(task_config.get("seed_dir", "")),
        str(profile.get("seed_dir", "")),
        str(profile.get("default_seed_dir", "")),
    }
    old_seed_values = {x for x in old_seed_values if x}

    updated = []
    for item in launch_cmd:
        text = str(item)
        text = replace_env_assignment(text, "RUNNER_DURATION_PLAN", plan_text)
        text = replace_env_assignment(text, "NV_BODY_SCORE_THRESHOLD", str(threshold))
        for old_seed in old_seed_values:
            text = text.replace(f"{{ROOT}}/{old_seed}", f"{{ROOT}}/{seed_dir}")
            text = text.replace(str(resolve_repo_path(old_seed)), str(resolve_repo_path(seed_dir)))
        updated.append(text)

    decision_profile_path = profile.get("_profile_path")
    if decision_profile_path and len(updated) >= 3 and updated[1] == "-lc":
        updated[2] = prepend_env_assignments(updated[2], {
            "NV_DECISION_PROFILE_PATH": decision_profile_path,
            "NV_DECISION_PROFILE_NAME": profile.get("profile", ""),
        })

    task_config["launch_cmd"] = updated


def build_runner_task(request: dict, profile: dict):
    template_path = resolve_repo_path(profile["template"])
    if not template_path.exists():
        raise FileNotFoundError(f"runner template not found: {template_path}")

    template = load_json(template_path)
    task_config = copy.deepcopy(template)

    seed_dir = request.get("seed_location") or profile.get("seed_dir") or template.get("seed_dir")
    threshold = str(profile.get("threshold", template.get("threshold", "")))
    duration_plan = normalize_duration_plan(request, profile, template)

    task_config["task_name"] = request.get("task_name", f"{profile['profile']}_{now_str()}")
    task_config["target_type"] = request.get("target_type", profile.get("target_type", template.get("target_type", "")))
    task_config["target_endpoint"] = request.get("target_endpoint", profile.get("target_endpoint", ""))
    task_config["seed_dir"] = seed_dir
    task_config["model_name"] = profile.get("model_name", template.get("model_name", ""))
    task_config["threshold"] = threshold
    task_config["manifest"] = profile.get("manifest", template.get("manifest", ""))
    task_config["duration_plan"] = duration_plan
    task_config["notes"] = profile.get("notes", template.get("notes", ""))
    task_config["integration_profile"] = profile["profile"]
    task_config["decision"] = copy.deepcopy(profile.get("decision", {}))
    task_config["integration_request"] = {
        "task_name": task_config["task_name"],
        "platform": profile["profile"],
        "target_type": task_config["target_type"],
        "target_endpoint": task_config["target_endpoint"],
        "seed_source": request.get("seed_source", "seed_file"),
        "seed_location": seed_dir,
        "mutation_scope": request.get("mutation_scope", []),
        "max_test_cases": request.get("max_test_cases"),
        "time_budget": request.get("time_budget"),
    }
    task_config["integration_profile_summary"] = {
        "platform": profile.get("platform", ""),
        "scene": profile.get("scene", ""),
        "model_route": profile.get("model_route", ""),
        "is_mainline": bool(profile.get("is_mainline", False)),
        "validation_scope": profile.get("validation_scope", ""),
        "decision": copy.deepcopy(profile.get("decision", {})),
    }

    update_launch_cmd(task_config, profile, seed_dir, threshold, duration_plan)
    return task_config


def validate_profile_and_task(profile: dict, task_config: dict):
    checks = []

    def add_check(name: str, path_value: str, required=True):
        if not path_value:
            checks.append({"name": name, "path": "", "exists": False, "required": required})
            return
        p = resolve_repo_path(path_value)
        checks.append({
            "name": name,
            "path": str(p),
            "exists": p.exists(),
            "required": required,
        })

    add_check("runner_template", profile.get("template", ""))
    add_check("seed_dir", task_config.get("seed_dir", ""))
    add_check("manifest", profile.get("manifest", task_config.get("manifest", "")))
    for item in profile.get("model_files", []):
        add_check(item.get("name", "model_file"), item.get("path", ""), required=bool(item.get("required", True)))

    missing_required = [c for c in checks if c["required"] and not c["exists"]]
    return {
        "checks": checks,
        "ready": not missing_required,
        "missing_required": missing_required,
    }


def run_runner(args):
    cmd = [sys.executable, str(RUNNER_CLI)] + args
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip())
    text = proc.stdout.strip()
    if not text:
        return {}
    return json.loads(text)


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")
    return cleaned[:80] or "fuzz_task"


def describe_status(status: dict, report: dict | None = None):
    raw_status = status.get("status", "")
    status_map = {
        "running": "执行中",
        "exited": "已完成",
        "stopped": "已停止",
        "stopping": "停止中",
        "submitted": "已提交",
        "failed": "失败",
    }
    desc = status_map.get(raw_status, raw_status or "未知")
    model = status.get("model_name", "")
    threshold = status.get("threshold", "")
    if model or threshold:
        desc += f"；model={model}，threshold={threshold}"
    decision = (report or {}).get("decision_summary", {})
    if decision:
        d20 = decision.get("dur20_pass_reject", "")
        d60 = decision.get("dur60_pass_reject", "")
        rpc = decision.get("rpc_fail_total", "")
        parts = []
        if d20:
            parts.append(f"20s pass/reject={d20}")
        if d60:
            parts.append(f"60s pass/reject={d60}")
        if rpc != "":
            parts.append(f"rpc_fail_total={rpc}")
        if parts:
            desc += "；" + "，".join(parts)
    return desc


def read_existing_report(status: dict):
    report_path = status.get("report_json")
    if not report_path:
        return None
    path = Path(report_path)
    if not path.exists():
        return None
    return load_json(path)


def action_submit(request: dict, dry_run=False):
    profile_name = request.get("platform") or request.get("profile")
    if not profile_name:
        raise ValueError("submit request must include platform")

    profile = load_profile(profile_name)
    task_config = build_runner_task(request, profile)
    validation = validate_profile_and_task(profile, task_config)

    if dry_run:
        return success_response(
            "submit",
            dry_run=True,
            task_id=None,
            profile=profile_name,
            validation=validation,
            mapped_runner_task=task_config,
        )

    if not validation["ready"]:
        return error_response(
            "submit",
            "profile validation failed; required files are missing",
            profile=profile_name,
            validation=validation,
        )

    GENERATED_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = sanitize_name(task_config.get("task_name", profile_name))
    task_path = GENERATED_TASKS_DIR / f"{stamp}_{profile_name}_{name}.json"
    save_json(task_path, task_config)

    runner_out = run_runner(["submit", "--task-json", str(task_path)])
    runner_task_id = runner_out.get("task_id")
    return success_response(
        "submit",
        task_id=public_task_id(runner_task_id),
        runner_task_id=runner_task_id,
        task_name=task_config.get("task_name", ""),
        profile=profile_name,
        runner_task_json=str(task_path),
        run_dir=runner_out.get("run_dir"),
        afl_out_dir=runner_out.get("afl_out_dir"),
    )


def action_query(request: dict):
    task_id = request.get("task_id")
    if not task_id:
        raise ValueError("query request must include task_id")
    raw_id = raw_task_id(task_id)
    status = run_runner(["query", "--task-id", raw_id])
    report = read_existing_report(status)
    return success_response(
        "query",
        task_id=public_task_id(raw_id),
        runner_task_id=raw_id,
        query_description=describe_status(status, report),
        status=status.get("status", ""),
        pid_alive=bool(status.get("pid_alive", False)),
        runner_status=status,
    )


def action_stop(request: dict, dry_run=False):
    task_id = request.get("task_id")
    if not task_id:
        raise ValueError("stop request must include task_id")
    raw_id = raw_task_id(task_id)

    if dry_run:
        status_path = ROOT / "runner" / "tasks" / raw_id / "status.json"
        return success_response(
            "stop",
            dry_run=True,
            task_id=public_task_id(raw_id),
            runner_task_id=raw_id,
            task_exists=status_path.exists(),
            query_description="停止路径静态验证完成；dry-run 未发送停止信号。",
        )

    runner_out = run_runner(["stop", "--task-id", raw_id])
    return success_response(
        "stop",
        task_id=public_task_id(raw_id),
        runner_task_id=raw_id,
        status=runner_out.get("status", ""),
        signal_sent=bool(runner_out.get("signal_sent", False)),
    )


def load_status(raw_id: str):
    status_path = ROOT / "runner" / "tasks" / raw_id / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"task not found: {public_task_id(raw_id)}")
    return load_json(status_path)


def normalize_report(raw_id: str, report: dict, status: dict | None = None):
    status = status or {}
    task_json_path = status.get("task_json") or report.get("task_json")
    task_name = ""
    if task_json_path and Path(task_json_path).exists():
        try:
            task_obj = load_json(Path(task_json_path))
            task_name = task_obj.get("task_name") or task_obj.get("integration_request", {}).get("task_name", "")
        except Exception:
            task_name = ""
    if not task_name:
        task_name = status.get("task_name", "") or report.get("task_name", "") or public_task_id(raw_id)

    report_path = report.get("report_json") or status.get("report_json") or str(ROOT / "runner" / "tasks" / raw_id / "report.json")
    return {
        "task_id": public_task_id(raw_id),
        "runner_task_id": raw_id,
        "task_name": task_name,
        "report_name": f"fuzz_report_{raw_id}.json",
        "generate_time": report.get("generated_at") or status.get("updated_at") or status.get("created_at", ""),
        "download_url": report_path,
        "local_report_path": report_path,
        "status": report.get("status") or status.get("status", ""),
        "decision_summary": report.get("decision_summary", {}),
        "artifacts": report.get("artifacts", {}),
    }


def in_time_range(generate_time: str, start_time: str | None, end_time: str | None):
    if not generate_time:
        return True
    if start_time and generate_time < start_time:
        return False
    if end_time and generate_time > end_time:
        return False
    return True


def action_report_query(request: dict, refresh=True):
    reports = []
    task_id = request.get("task_id")
    task_name_filter = request.get("task_name")
    start_time = request.get("start_time")
    end_time = request.get("end_time")

    if task_id:
        raw_id = raw_task_id(task_id)
        status = load_status(raw_id)
        if refresh:
            report = run_runner(["report", "--task-id", raw_id])
        else:
            report = read_existing_report(status)
            if report is None:
                raise FileNotFoundError(f"report not found for task: {public_task_id(raw_id)}")
        reports.append(normalize_report(raw_id, report, status))
    else:
        task_root = ROOT / "runner" / "tasks"
        if not task_root.exists():
            reports = []
        else:
            for report_path in sorted(task_root.glob("*/report.json")):
                raw_id = report_path.parent.name
                status = {}
                status_path = report_path.parent / "status.json"
                if status_path.exists():
                    status = load_json(status_path)
                report = load_json(report_path)
                item = normalize_report(raw_id, report, status)
                if task_name_filter and task_name_filter not in item.get("task_name", ""):
                    continue
                if not in_time_range(item.get("generate_time", ""), start_time, end_time):
                    continue
                reports.append(item)

    return success_response(
        "report_query",
        total_count=len(reports),
        report_list=reports,
    )


def build_parser():
    parser = argparse.ArgumentParser(description="Unified integration adapter for the fuzz testing module.")
    sub = parser.add_subparsers(dest="action", required=True)

    p_profiles = sub.add_parser("profiles")

    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--request-json")
    p_submit.add_argument("--json")
    p_submit.add_argument("--dry-run", action="store_true")

    p_query = sub.add_parser("query")
    p_query.add_argument("--request-json")
    p_query.add_argument("--json")
    p_query.add_argument("--task-id")

    p_stop = sub.add_parser("stop")
    p_stop.add_argument("--request-json")
    p_stop.add_argument("--json")
    p_stop.add_argument("--task-id")
    p_stop.add_argument("--dry-run", action="store_true")

    p_report = sub.add_parser("report_query")
    p_report.add_argument("--request-json")
    p_report.add_argument("--json")
    p_report.add_argument("--task-id")
    p_report.add_argument("--task-name")
    p_report.add_argument("--start-time")
    p_report.add_argument("--end-time")
    p_report.add_argument("--no-refresh", action="store_true")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.action == "profiles":
            result = success_response("profiles", profiles=list_profiles())
        else:
            request = read_request(args)
            if getattr(args, "task_id", None):
                request["task_id"] = args.task_id
            if getattr(args, "task_name", None):
                request["task_name"] = args.task_name
            if getattr(args, "start_time", None):
                request["start_time"] = args.start_time
            if getattr(args, "end_time", None):
                request["end_time"] = args.end_time

            if args.action == "submit":
                result = action_submit(request, dry_run=args.dry_run)
            elif args.action == "query":
                result = action_query(request)
            elif args.action == "stop":
                result = action_stop(request, dry_run=args.dry_run)
            elif args.action == "report_query":
                result = action_report_query(request, refresh=not args.no_refresh)
            else:
                result = error_response(args.action, f"unknown action: {args.action}")
    except Exception as exc:
        result = error_response(args.action, str(exc))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("process_result") != 1:
        sys.exit(1)


if __name__ == "__main__":
    main()
