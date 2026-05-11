#!/usr/bin/env python3
import argparse
import csv
import json
import os
import shlex
import shutil
import signal
import subprocess
import uuid
from datetime import datetime
from pathlib import Path


ROOT = Path.home() / "AFLplusplus"
RUNNER_DIR = ROOT / "runner"
TASKS_DIR = RUNNER_DIR / "tasks"
RUNS_DIR = RUNNER_DIR / "runs"

TASKS_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_under_root(p: str) -> Path:
    pth = Path(p)
    if pth.is_absolute():
        return pth
    return ROOT / pth


def path_exists_str(p: str) -> bool:
    if not p:
        return False
    return resolve_under_root(p).exists()


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True




def infer_summary_source(path: Path, context: dict | None = None):
    context = context or {}
    haystack = " ".join([
        str(path),
        str(context.get("model_name", "")),
        str(context.get("manifest", "")),
        str(context.get("notes", "")),
        str(context.get("task_json", "")),
    ]).lower()
    if "flowable" in haystack:
        return {
            "summary_source": "python_static_loop",
            "execution_scope": "flowable_min_calibration",
            "metric_semantics": (
                "Flowable summary comes from a Python static-loop request replay over "
                "the Flowable seed dataset; nv_total_valid_exec is the replay loop count, "
                "not a full AFL++ mutation-chain execution count."
            ),
        }
    if "o2oa" in haystack or "cms_body_valid" in haystack:
        return {
            "summary_source": "aflpp_harness",
            "execution_scope": "o2oa_aflpp_body_harness",
            "metric_semantics": (
                "O2OA summary combines AFL++ fuzzer_stats with nv_http_harness "
                "body validity counters."
            ),
        }
    return {
        "summary_source": "summary_csv",
        "execution_scope": "unspecified",
        "metric_semantics": "Summary CSV source was not classified; inspect task notes and artifacts.",
    }


def find_afl_artifact(afl_out_dir: str, name: str) -> Path | None:
    if not afl_out_dir:
        return None
    base = Path(afl_out_dir)
    for p in [base / "default" / name, base / name]:
        if p.exists():
            return p
    return None


def read_summary_csv(path: Path, context: dict | None = None, preferred_mode: str = "rule_score"):
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return None
        row = None
        if preferred_mode:
            row = next((r for r in rows if r.get("mode") == preferred_mode), None)
        if row is None:
            row = rows[0]

        def to_int(name: str) -> int:
            try:
                return int(float(row.get(name, 0) or 0))
            except Exception:
                return 0

        def to_float_str(name: str) -> str:
            v = row.get(name, "")
            if v == "":
                return "0.000000"
            return str(v)

        source = infer_summary_source(path, context)
        return {
            "source_file": str(path),
            "summary_source": row.get("summary_source") or source["summary_source"],
            "execution_scope": row.get("execution_scope") or source["execution_scope"],
            "metric_semantics": row.get("metric_semantics") or source["metric_semantics"],
            "available_modes": [r.get("mode", "") for r in rows],
            "selected_mode": row.get("mode", ""),
            "mode": row.get("mode", ""),
            "nv_total_valid_exec": to_int("nv_total_valid_exec"),
            "nv_err_exec": to_int("nv_err_exec"),
            "nv_err_rate": to_float_str("nv_err_rate"),
            "saved_hangs": to_int("saved_hangs"),
            "saved_crashes": to_int("saved_crashes"),
            "last_http_code": to_int("last_http_code"),
            "last_latency_ms": to_int("last_latency_ms"),
            "last_ncov_total": to_int("last_ncov_total"),
            "body_rule_pass": to_int("body_rule_pass"),
            "body_rule_reject": to_int("body_rule_reject"),
            "body_score_pass": to_int("body_score_pass"),
            "body_score_reject": to_int("body_score_reject"),
            "body_score_rpc_ok": to_int("body_score_rpc_ok"),
            "body_score_rpc_fail": to_int("body_score_rpc_fail"),
        }
    except Exception:
        return None


def read_fuzzer_stats(path: Path):
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out

def build_decision_summary(status: dict, summary_20: dict, summary_60: dict):
    def fmt_sr(s: dict):
        if not s:
            return ""
        p = s.get("body_score_pass", 0)
        r = s.get("body_score_reject", 0)
        return f"{p}/{r}"

    rpc_fail_total = 0
    if summary_20:
        rpc_fail_total += int(summary_20.get("body_score_rpc_fail", 0))
    if summary_60:
        rpc_fail_total += int(summary_60.get("body_score_rpc_fail", 0))

    return {
        "model": status.get("model_name", ""),
        "threshold": status.get("threshold", ""),
        "status": status.get("status", ""),
        "dur20_pass_reject": fmt_sr(summary_20),
        "dur60_pass_reject": fmt_sr(summary_60),
        "rpc_fail_total": rpc_fail_total,
        "has_dur20": bool(summary_20),
        "has_dur60": bool(summary_60),
        "summary_source": (summary_60 or summary_20 or {}).get("summary_source", ""),
        "execution_scope": (summary_60 or summary_20 or {}).get("execution_scope", ""),
    }


def expand_tokens_in_list(items, mapping):
    out = []
    for x in items:
        s = str(x)
        for k, v in mapping.items():
            s = s.replace("{" + k + "}", str(v))
        out.append(s)
    return out


def build_launch_cmd(task_obj: dict, task_id: str, run_dir: Path, afl_out_dir: Path):
    """
    优先使用 task.json 中的 launch_cmd。
    支持两种写法：
      1) launch_cmd: ["bash", "xxx.sh", ...]
      2) launch_cmd: "bash xxx.sh ..."
    可用占位符：
      {ROOT}
      {TASK_ID}
      {RUN_DIR}
      {AFL_OUT_DIR}
      {SEED_DIR}
    """
    launch_cmd = task_obj.get("launch_cmd")
    seed_dir_raw = task_obj.get("seed_dir", "in/o2oa_body_model_compare")
    seed_dir = resolve_under_root(seed_dir_raw)

    mapping = {
        "ROOT": str(ROOT),
        "TASK_ID": task_id,
        "RUN_DIR": str(run_dir),
        "AFL_OUT_DIR": str(afl_out_dir),
        "SEED_DIR": str(seed_dir),
    }

    if launch_cmd:
        if isinstance(launch_cmd, str):
            cmd = shlex.split(launch_cmd)
        elif isinstance(launch_cmd, list):
            cmd = [str(x) for x in launch_cmd]
        else:
            raise ValueError("launch_cmd must be string or list")
        return expand_tokens_in_list(cmd, mapping)

    # fallback：如果没写 launch_cmd，就尝试自动拼一个最小 AFL 命令
    target_cmd = task_obj.get("target_cmd")
    if not target_cmd:
        raise ValueError(
            "task.json must provide launch_cmd, or provide target_cmd for auto AFL launch"
        )

    if isinstance(target_cmd, str):
        target_cmd = shlex.split(target_cmd)
    elif isinstance(target_cmd, list):
        target_cmd = [str(x) for x in target_cmd]
    else:
        raise ValueError("target_cmd must be string or list")

    target_cmd = expand_tokens_in_list(target_cmd, mapping)

    afl_bin = task_obj.get("afl_bin", str(ROOT / "afl-fuzz"))
    afl_bin = expand_tokens_in_list([afl_bin], mapping)[0]

    cmd = [
        afl_bin,
        "-i", str(seed_dir),
        "-o", str(afl_out_dir),
        "--",
    ] + target_cmd
    return cmd


def build_launch_env(task_obj: dict, task_id: str, run_dir: Path, afl_out_dir: Path):
    env = os.environ.copy()

    seed_dir_raw = task_obj.get("seed_dir", "in/o2oa_body_model_compare")
    seed_dir = resolve_under_root(seed_dir_raw)

    mapping = {
        "ROOT": str(ROOT),
        "TASK_ID": task_id,
        "RUN_DIR": str(run_dir),
        "AFL_OUT_DIR": str(afl_out_dir),
        "SEED_DIR": str(seed_dir),
    }

    user_env = task_obj.get("env", {})
    for k, v in user_env.items():
        s = str(v)
        for mk, mv in mapping.items():
            s = s.replace("{" + mk + "}", str(mv))
        env[str(k)] = s

    return env


def submit(task_json_path: str):
    src = Path(task_json_path)
    if not src.exists():
        raise FileNotFoundError(f"task json not found: {src}")

    task_obj = load_json(src)

    task_id = uuid.uuid4().hex[:12]
    task_dir = TASKS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    run_dir = RUNS_DIR / task_id
    run_dir.mkdir(parents=True, exist_ok=True)

    afl_out_dir_raw = task_obj.get("out_dir", "")
    if afl_out_dir_raw:
        afl_out_dir = resolve_under_root(afl_out_dir_raw)
    else:
        afl_out_dir = run_dir / "afl_out"
    afl_out_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"

    dst_task = task_dir / "task.json"
    shutil.copy2(src, dst_task)

    cmd = build_launch_cmd(task_obj, task_id, run_dir, afl_out_dir)
    env = build_launch_env(task_obj, task_id, run_dir, afl_out_dir)

    with stdout_path.open("ab") as so, stderr_path.open("ab") as se:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=so,
            stderr=se,
            start_new_session=True,
        )

    status = {
        "task_id": task_id,
        "status": "running",
        "created_at": now_str(),
        "updated_at": now_str(),
        "start_time": now_str(),
        "task_json": str(dst_task),
        "report_json": str(task_dir / "report.json"),
        "experiment_dir": task_obj.get("experiment_dir", ""),
        "model_name": task_obj.get("model_name", ""),
        "threshold": str(task_obj.get("threshold", "")),
        "manifest": task_obj.get("manifest", ""),
        "duration_plan": task_obj.get("duration_plan", []),
        "notes": task_obj.get("notes", ""),
        "pid": proc.pid,
        "run_dir": str(run_dir),
        "afl_out_dir": str(afl_out_dir),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "command": cmd,
        "result_summary_csv": task_obj.get("result_summary_csv", ""),
        "result_stats_json": task_obj.get("result_stats_json", ""),
    }
    save_json(task_dir / "status.json", status)

    print(json.dumps({
        "ok": True,
        "task_id": task_id,
        "pid": proc.pid,
        "run_dir": str(run_dir),
        "afl_out_dir": str(afl_out_dir),
    }, ensure_ascii=False))


def query(task_id: str):
    task_dir = TASKS_DIR / task_id
    status_path = task_dir / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"task not found: {task_id}")

    status = load_json(status_path)

    pid = status.get("pid")
    live = False
    if isinstance(pid, int):
        live = is_pid_alive(pid)

    current_status = status.get("status", "")
    if current_status == "running" and not live:
        current_status = "exited"
    elif current_status == "stopping" and not live:
        current_status = "stopped"

    fuzzer_stats = {}
    eval_report = {}
    afl_out_dir = status.get("afl_out_dir", "")
    if afl_out_dir:
        stats_path = find_afl_artifact(afl_out_dir, "fuzzer_stats")
        if stats_path:
            fuzzer_stats = read_fuzzer_stats(stats_path)
        eval_path = find_afl_artifact(afl_out_dir, "eval_report.json")
        if eval_path:
            try:
                eval_report = load_json(eval_path)
            except Exception:
                eval_report = {}

    out = dict(status)
    out["status"] = current_status
    out["pid_alive"] = live
    out["fuzzer_stats"] = fuzzer_stats
    out["eval_report"] = eval_report
    out["metric_sources"] = {
        "fuzzer_stats": "aflpp_native_or_demo" if fuzzer_stats else "not_available",
        "eval_report": (
            eval_report.get("task", {}).get("source", "aflpp_eval_report")
            if eval_report else "not_available"
        ),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))


def stop(task_id: str):
    task_dir = TASKS_DIR / task_id
    status_path = task_dir / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"task not found: {task_id}")

    status = load_json(status_path)
    pid = status.get("pid")

    sent = False
    if isinstance(pid, int) and is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGINT)
            sent = True
        except ProcessLookupError:
            sent = False

    status["status"] = "stopping" if sent else "stopped"
    status["updated_at"] = now_str()
    save_json(status_path, status)

    print(json.dumps({
        "ok": True,
        "task_id": task_id,
        "status": status["status"],
        "pid": pid,
        "signal_sent": sent,
    }, ensure_ascii=False))


def report(task_id: str):
    task_dir = TASKS_DIR / task_id
    status_path = task_dir / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"task not found: {task_id}")

    status = load_json(status_path)

    exp_dir = status.get("experiment_dir", "")
    exp_path = resolve_under_root(exp_dir) if exp_dir else None

    artifacts = {}
    summary_20 = {}
    summary_60 = {}
    run_dir = status.get("run_dir", "")
    run_path = Path(run_dir) if run_dir else None

    if run_path and run_path.exists():
        p20 = run_path / "summary_dur20.csv"
        p60 = run_path / "summary_dur60.csv"

        s20 = read_summary_csv(p20, status)
        s60 = read_summary_csv(p60, status)

        if s20:
            summary_20 = s20
            artifacts[p20.name] = str(p20)

        if s60:
            summary_60 = s60
            artifacts[p60.name] = str(p60)

        for name in ["body_valid_stats_dur20.json", "body_valid_stats_dur60.json"]:
            p = run_path / name
            if p.exists():
                artifacts[p.name] = str(p)
    result_summary_csv = status.get("result_summary_csv", "")
    result_stats_json = status.get("result_stats_json", "")

    if not summary_20 and result_summary_csv:
        p = resolve_under_root(result_summary_csv)
        s = read_summary_csv(p, status)
        if s:
            summary_20 = s
            artifacts[p.name] = str(p)

    if result_stats_json:
        p = resolve_under_root(result_stats_json)
        if p.exists():
            artifacts[p.name] = str(p)

    # 实验目录里的结果
    if exp_path and exp_path.exists():
        p20 = exp_path / "summary_dur20.csv"
        p60 = exp_path / "summary_dur60.csv"
        s20 = read_summary_csv(p20, status)
        s60 = read_summary_csv(p60, status)
        if s20:
            summary_20 = s20
        if s60:
            summary_60 = s60

        for name in [
            "summary_dur20.csv",
            "summary_dur60.csv",
            "sefanogan_ae_meta.json",
            "sefanogan_gan_meta.json",
            "README.md",
        ]:
            p = exp_path / name
            if p.exists():
                artifacts[name] = str(p)

    # 运行目录里的文件
    for k in ["stdout_log", "stderr_log"]:
        p = status.get(k, "")
        if p and Path(p).exists():
            artifacts[Path(p).name] = p

    afl_out_dir = status.get("afl_out_dir", "")
    if afl_out_dir:
        for name in ["fuzzer_stats", "eval_report.json"]:
            p = find_afl_artifact(afl_out_dir, name)
            if p and p.exists():
                artifacts[name] = str(p)

    fuzzer_stats = {}
    eval_report = {}
    if afl_out_dir:
        stats_path = find_afl_artifact(afl_out_dir, "fuzzer_stats")
        if stats_path:
            fuzzer_stats = read_fuzzer_stats(stats_path)
        eval_path = find_afl_artifact(afl_out_dir, "eval_report.json")
        if eval_path:
            try:
                eval_report = load_json(eval_path)
            except Exception:
                eval_report = {}
    
    pid = status.get("pid")
    live = False
    if isinstance(pid, int):
        live = is_pid_alive(pid)

    current_status = status.get("status", "")
    if current_status == "running" and not live:
        current_status = "exited"
    elif current_status == "stopping" and not live:
        current_status = "stopped"

    if current_status != status.get("status"):
        status["status"] = current_status
        status["updated_at"] = now_str()
        save_json(status_path, status)

    decision_summary = build_decision_summary(status, summary_20, summary_60)
    metric_sources = {
        "fuzzer_stats": "aflpp_native" if fuzzer_stats else "not_available",
        "eval_report": (
            eval_report.get("task", {}).get("source", "aflpp_eval_report")
            if eval_report else "not_available"
        ),
        "summary_dur20": summary_20.get("summary_source", "not_available") if summary_20 else "not_available",
        "summary_dur60": summary_60.get("summary_source", "not_available") if summary_60 else "not_available",
    }
    integration_boundary = (
        "runner/adapter-level task semantics; this report is not proof of a deployed HTTP/RPC gateway service"
    )

    report_obj = {
        "task_id": task_id,
        "status": current_status,
        "task_json": status.get("task_json"),
        "report_json": status.get("report_json"),
        "experiment_dir": exp_dir,
        "model_name": status.get("model_name", ""),
        "threshold": status.get("threshold", ""),
        "manifest": status.get("manifest", ""),
        "duration_plan": status.get("duration_plan", []),
        "notes": status.get("notes", ""),
        "pid": status.get("pid"),
        "run_dir": status.get("run_dir", ""),
        "afl_out_dir": status.get("afl_out_dir", ""),
        "command": status.get("command", []),
        "artifacts": artifacts,
        "summary_dur20": summary_20,
        "summary_dur60": summary_60,
        "fuzzer_stats": fuzzer_stats,
        "eval_report": eval_report,
        "metric_sources": metric_sources,
        "integration_boundary": integration_boundary,
        "generated_at": now_str(),
        "decision_summary": decision_summary,
    }

    report_path = task_dir / "report.json"
    save_json(report_path, report_obj)
    print(json.dumps(report_obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--task-json", required=True)

    p_query = sub.add_parser("query")
    p_query.add_argument("--task-id", required=True)

    p_stop = sub.add_parser("stop")
    p_stop.add_argument("--task-id", required=True)

    p_report = sub.add_parser("report")
    p_report.add_argument("--task-id", required=True)

    args = parser.parse_args()

    if args.cmd == "submit":
        submit(args.task_json)
    elif args.cmd == "query":
        query(args.task_id)
    elif args.cmd == "stop":
        stop(args.task_id)
    elif args.cmd == "report":
        report(args.task_id)
    else:
        raise RuntimeError(f"unknown cmd: {args.cmd}")


if __name__ == "__main__":
    main()
