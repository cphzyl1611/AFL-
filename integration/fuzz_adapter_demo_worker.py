#!/usr/bin/env python3
import json
import os
import signal
import time
from pathlib import Path


STOP = False


def on_stop(_signum, _frame):
    global STOP
    STOP = True


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_artifacts(run_dir: Path, afl_out_dir: Path, task_id: str, state: str):
    now = int(time.time())
    write_text(
        afl_out_dir / "fuzzer_stats",
        "\n".join([
            f"start_time        : {now}",
            f"last_update       : {now}",
            f"fuzzer_pid        : {os.getpid()}",
            f"task_id           : {task_id}",
            f"demo_state        : {state}",
            "cycles_done       : 1",
            "execs_done        : 4",
            "saved_crashes     : 0",
            "saved_hangs       : 0",
            "nv_valid_cnt       : 4",
            "nv_invalid_cnt     : 1",
            "nv_invalid_rate    : 0.200000",
            "nv_total_valid_exec : 4",
            "nv_err_exec         : 0",
            "nv_err_rate         : 0.000000",
            "nv_rec_total        : 0",
            "nv_rec_success      : 0",
            "nv_rec_rate         : 0.000000",
            "",
        ]),
    )
    write_text(
        afl_out_dir / "eval_report.json",
        json.dumps({
            "task": {
                "source": "adapter_demo",
                "source_note": "Synthetic runner/adapter integration smoke; not fuzzing evidence.",
                "target_type_name": "demo",
                "target_type": 0,
                "target_endpoint": "adapter_demo",
                "enable_validity": 0,
            },
            "cov": {"bitmap_cvg": 0.0, "edges_found": 0},
            "validity": {
                "valid_cnt": 4,
                "invalid_cnt": 1,
                "invalid_rate": 0.2,
                "invalid_parse_cnt": 1,
                "invalid_rule_cnt": 0,
                "invalid_rpc_fail_cnt": 0,
            },
            "err": {"err_exec": 0, "err_rate": 0.0},
            "rec": {"rec_total": 0, "rec_success": 0, "rec_rate": 0.0, "rec_avg_ms": 0.0},
            "exec": {"valid_exec": 4, "total_execs": 5},
        }, ensure_ascii=False, indent=2),
    )
    write_text(
        run_dir / "summary_dur20.csv",
        "\n".join([
            "mode,nv_total_valid_exec,nv_err_exec,nv_err_rate,saved_hangs,saved_crashes,last_http_code,last_latency_ms,last_ncov_total,body_rule_pass,body_rule_reject,body_score_pass,body_score_reject,body_score_rpc_ok,body_score_rpc_fail,summary_source,execution_scope,metric_semantics",
            "adapter_demo,4,0,0.000000,0,0,200,1,0,4,1,4,1,0,0,adapter_demo,runner_adapter_integration_demo,Synthetic runner adapter integration smoke not fuzzing evidence",
            "",
        ]),
    )


def main():
    signal.signal(signal.SIGINT, on_stop)
    signal.signal(signal.SIGTERM, on_stop)

    run_dir = Path(os.environ["RUN_DIR"])
    afl_out_dir = Path(os.environ["AFL_OUT_DIR"])
    task_id = os.environ.get("TASK_ID", "adapter-demo")
    duration = float(os.environ.get("DEMO_DURATION_SEC", "20"))

    deadline = time.time() + duration
    while not STOP and time.time() < deadline:
        write_artifacts(run_dir, afl_out_dir, task_id, "running")
        time.sleep(0.5)

    write_artifacts(run_dir, afl_out_dir, task_id, "stopped" if STOP else "exited")


if __name__ == "__main__":
    main()
