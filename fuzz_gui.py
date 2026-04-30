#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import shlex
import json
import os
import signal
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except Exception as e:
    print("无法导入 tkinter。WSL/最小环境可能未安装 Tk 支持。")
    print("Ubuntu/Debian 可尝试：sudo apt-get update && sudo apt-get install -y python3-tk")
    raise


# =========================
# 3.1.2.2.5 参数（工具定义）
# =========================

SUBMIT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_name": {"type": "string", "description": "模糊测试任务名称，用于区分不同测试任务"},
        "target_type": {"type": "string", "enum": ["http_api", "file_upload", "protocol_message"],
                        "description": "被测目标类型：HTTP接口、文件上传或协议报文"},
        "target_endpoint": {"type": "string", "description": "被测目标地址，如HTTP接口URL或协议服务标识"},
        "seed_source": {"type": "string", "enum": ["captured_traffic", "seed_file", "manual"],
                        "description": "初始种子来源：真实流量抓取、已有种子文件或人工构造"},
        "seed_location": {"type": "string", "description": "种子数据存储位置，如本地路径或对象存储地址"},
        "mutation_scope": {"type": "array", "items": {"type": "string", "enum": ["field_value", "boundary", "structure"]},
                           "description": "启用的变异范围：字段值变异、边界值变异、结构级变异"},
        "max_test_cases": {"type": "integer", "minimum": 1, "description": "单次任务最大测试用例数量"},
        "time_budget": {"type": "integer", "minimum": 1, "description": "最长执行时间（秒）"}
    },
    "required": ["task_name", "target_type", "target_endpoint", "seed_source", "seed_location",
                 "mutation_scope", "max_test_cases", "time_budget"]
}

SUBMIT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "process_result": {"type": "integer", "enum": [1, 0], "description": "1=成功，0=失败"},
        "task_id": {"type": "string", "description": "下发成功的任务唯一标识，失败时为null"}
    },
    "required": ["process_result"]
}


# =========================
# 本地任务数据库（模拟 MCP 工具）
# =========================

APP_DIR = Path.home() / ".fuzz_gui"
TASK_DB = APP_DIR / "tasks.json"


@dataclass
class TaskRecord:
    task_id: str
    task_name: str
    created_at: str
    updated_at: str
    status: str  # running / stopped / finished / failed
    pid: Optional[int]
    work_dir: str
    afl_dir: str
    in_dir: str
    out_dir: str
    instance_id: str
    target_cmd: str
    submit_params: Dict[str, Any]
    afl_cmd: List[str]
    last_error: Optional[str] = None


def load_db() -> Dict[str, Any]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if TASK_DB.exists():
        try:
            return json.loads(TASK_DB.read_text(encoding="utf-8"))
        except Exception:
            return {"tasks": {}}
    return {"tasks": {}}


def save_db(db: Dict[str, Any]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    TASK_DB.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


# =========================
# AFL++ 运行器（本地提交/查询/停止/报告）
# =========================

def set_core_ulimit_unlimited() -> None:
    # 等效于 ulimit -c unlimited（对子进程生效）
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
    except Exception:
        # 某些环境可能不允许，忽略不致命
        pass


def try_fix_core_pattern_or_bypass(env: Dict[str, str]) -> None:
    """
    WSL 常见：/proc/sys/kernel/core_pattern 以 '|' 开头会导致 AFL++ abort。
    能 sudo 就改成 core；不能 sudo 就设置 AFL_I_DONT_CARE... 绕过。
    """
    p = Path("/proc/sys/kernel/core_pattern")
    try:
        cur = p.read_text().strip()
    except Exception:
        env["AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES"] = "1"
        return

    if not cur.startswith("|"):
        return

    # 尝试 sudo 写入：echo core | sudo tee ...
    try:
        p1 = subprocess.Popen(["echo", "core"], stdout=subprocess.PIPE, text=True)
        subprocess.run(["sudo", "tee", "/proc/sys/kernel/core_pattern"],
                       stdin=p1.stdout, text=True, check=True)
        if p1.stdout:
            p1.stdout.close()
    except Exception:
        env["AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES"] = "1"


def prepare_seeds(seed_location: str, in_dir: Path) -> None:
    in_dir.mkdir(parents=True, exist_ok=True)

    src = Path(seed_location).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"seed_location 不存在：{src}")

    # 清空旧 seeds（仅清 in_dir）
    for f in in_dir.glob("*"):
        if f.is_file():
            f.unlink()

    if src.is_file():
        shutil.copy2(src, in_dir / src.name)
    else:
        # 复制目录下普通文件
        copied = 0
        for f in src.rglob("*"):
            if f.is_file():
                shutil.copy2(f, in_dir / f.name)
                copied += 1
        if copied == 0:
            raise RuntimeError("seed_location 目录下没有可用文件。")


def build_afl_command(
    afl_dir: Path,
    in_dir: Path,
    out_base: Path,
    instance_id: str,
    max_test_cases: int,
    time_budget: int,
    target_cmd: str,
    extra_args: Optional[List[str]] = None
) -> List[str]:
    afl_fuzz = afl_dir / "afl-fuzz"
    if not afl_fuzz.exists():
        raise FileNotFoundError(f"找不到 afl-fuzz：{afl_fuzz}")

    cmd = [str(afl_fuzz), "-i", str(in_dir), "-o", str(out_base), "-S", instance_id]

    # time_budget -> -V (seconds)
    if time_budget > 0:
        cmd += ["-V", str(time_budget)]

    # 注意：max_test_cases 暂不映射到 afl-fuzz 选项（不同版本不稳定）
    # 如果你要硬限制用例数，建议以后做“达到阈值自动 Stop”。

    if extra_args:
        cmd += extra_args

    cmd += ["--"]
    cmd += target_cmd.strip().split()
    return cmd


def read_fuzzer_stats(task: TaskRecord) -> str:
    stats = Path(task.out_dir) / task.instance_id / "fuzzer_stats"
    if stats.exists():
        return stats.read_text(errors="ignore")
    return "(未找到 fuzzer_stats，可能尚未生成或任务未启动成功)"


def task_report_list(db: Dict[str, Any], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    模拟 fuzz_test_report_query：返回 report_list（这里把 report 对应到 out/<id>/fuzzer_stats 等）
    """
    tasks = db.get("tasks", {})
    res = []
    task_id = (filters.get("task_id") or "").strip()
    task_name = (filters.get("task_name") or "").strip()
    tr = filters.get("time_range") or {}
    start = tr.get("start_time")
    end = tr.get("end_time")

    def in_time_range(created_at: str) -> bool:
        if not start and not end:
            return True
        try:
            t = datetime.fromisoformat(created_at)
            if start:
                if t < datetime.fromisoformat(start):
                    return False
            if end:
                if t > datetime.fromisoformat(end):
                    return False
            return True
        except Exception:
            return True

    for tid, rec in tasks.items():
        try:
            t = TaskRecord(**rec)
        except Exception:
            continue

        if task_id and t.task_id != task_id:
            continue
        if task_name and (task_name not in t.task_name):
            continue
        if not in_time_range(t.created_at):
            continue

        out_dir = Path(t.out_dir) / t.instance_id
        report_name = f"{t.task_name}_{t.task_id[:8]}_afl_report"
        download_url = str(out_dir / "fuzzer_stats")
        res.append({
            "task_id": t.task_id,
            "task_name": t.task_name,
            "report_name": report_name,
            "generate_time": t.updated_at,
            "download_url": download_url
        })
    return res


# =========================
# GUI
# =========================

class FuzzGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fuzz 测试工具（对应 3.1.2.2.5 参数定义）")
        self.geometry("980x720")

        self.db = load_db()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_submit_tab()
        self._build_query_tab()
        self._build_stop_tab()
        self._build_report_tab()

    # ---------- Submit ----------
    def _build_submit_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="任务下发（Submit）")

        frm = ttk.Frame(tab)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        self.var_afl_dir = tk.StringVar(value=str(Path.cwd()))
        self.var_work_dir = tk.StringVar(value=str(Path.cwd()))
        self.var_target_cmd = tk.StringVar(value="./test_afl")  # 可改成 harness @@

        self.var_task_name = tk.StringVar(value=f"fuzz_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.var_target_type = tk.StringVar(value="http_api")
        self.var_target_endpoint = tk.StringVar(value="http://127.0.0.1:8080/api")
        self.var_seed_source = tk.StringVar(value="seed_file")
        self.var_seed_location = tk.StringVar(value=str(Path.cwd() / "in"))
        self.var_max_test_cases = tk.IntVar(value=200000)
        self.var_time_budget = tk.IntVar(value=60)

        self.var_scope_field = tk.BooleanVar(value=True)
        self.var_scope_boundary = tk.BooleanVar(value=True)
        self.var_scope_structure = tk.BooleanVar(value=False)

        row = 0
        def add_row(label, widget):
            nonlocal row
            ttk.Label(frm, text=label, width=22, anchor="w").grid(row=row, column=0, sticky="w", pady=4)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            row += 1

        frm.columnconfigure(1, weight=1)

        add_row("AFL++ 目录（afl-fuzz）", ttk.Entry(frm, textvariable=self.var_afl_dir))
        add_row("工作目录（in/out）", ttk.Entry(frm, textvariable=self.var_work_dir))
        add_row("目标命令（支持@@）", ttk.Entry(frm, textvariable=self.var_target_cmd))

        ttk.Separator(frm).grid(row=row, column=0, columnspan=2, sticky="ew", pady=10)
        row += 1

        add_row("task_name", ttk.Entry(frm, textvariable=self.var_task_name))

        cb1 = ttk.Combobox(frm, textvariable=self.var_target_type,
                           values=["http_api", "file_upload", "protocol_message"], state="readonly")
        add_row("target_type", cb1)

        add_row("target_endpoint", ttk.Entry(frm, textvariable=self.var_target_endpoint))

        cb2 = ttk.Combobox(frm, textvariable=self.var_seed_source,
                           values=["captured_traffic", "seed_file", "manual"], state="readonly")
        add_row("seed_source", cb2)

        seed_row = ttk.Frame(frm)
        ent_seed = ttk.Entry(seed_row, textvariable=self.var_seed_location)
        ent_seed.pack(side="left", fill="x", expand=True)
        ttk.Button(seed_row, text="选择文件/目录", command=self._browse_seed_location).pack(side="left", padx=6)
        add_row("seed_location", seed_row)

        scope_row = ttk.Frame(frm)
        ttk.Checkbutton(scope_row, text="field_value", variable=self.var_scope_field).pack(side="left", padx=6)
        ttk.Checkbutton(scope_row, text="boundary", variable=self.var_scope_boundary).pack(side="left", padx=6)
        ttk.Checkbutton(scope_row, text="structure", variable=self.var_scope_structure).pack(side="left", padx=6)
        add_row("mutation_scope", scope_row)

        add_row("max_test_cases", ttk.Spinbox(frm, from_=1, to=10**12, textvariable=self.var_max_test_cases))
        add_row("time_budget(秒)", ttk.Spinbox(frm, from_=1, to=10**9, textvariable=self.var_time_budget))

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=12)
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        btn_row.columnconfigure(2, weight=1)
        btn_row.columnconfigure(3, weight=1)

        ttk.Button(btn_row, text="生成输入JSON", command=self._show_submit_json).grid(row=0, column=0, sticky="ew", padx=6)
        ttk.Button(btn_row, text="一键运行（下发并启动）", command=self._submit_and_run).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(btn_row, text="打开输出目录", command=self._open_out_dir).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(btn_row, text="刷新任务列表", command=self._refresh_db).grid(row=0, column=3, sticky="ew", padx=6)

        self.txt_submit_log = tk.Text(frm, height=14)
        self.txt_submit_log.grid(row=row+1, column=0, columnspan=2, sticky="nsew")
        frm.rowconfigure(row+1, weight=1)

    def _browse_seed_location(self):
        f = filedialog.askopenfilename(title="选择种子文件（可选）")
        if f:
            self.var_seed_location.set(f)
            return
        d = filedialog.askdirectory(title="选择种子目录（可选）")
        if d:
            self.var_seed_location.set(d)

    def _log_submit(self, s: str):
        self.txt_submit_log.insert("end", f"[{now_iso()}] {s}\n")
        self.txt_submit_log.see("end")

    def _collect_mutation_scope(self) -> List[str]:
        scope = []
        if self.var_scope_field.get():
            scope.append("field_value")
        if self.var_scope_boundary.get():
            scope.append("boundary")
        if self.var_scope_structure.get():
            scope.append("structure")
        return scope

    def _build_submit_payload(self) -> Dict[str, Any]:
        payload = {
            "task_name": self.var_task_name.get().strip(),
            "target_type": self.var_target_type.get().strip(),
            "target_endpoint": self.var_target_endpoint.get().strip(),
            "seed_source": self.var_seed_source.get().strip(),
            "seed_location": self.var_seed_location.get().strip(),
            "mutation_scope": self._collect_mutation_scope(),
            "max_test_cases": int(self.var_max_test_cases.get()),
            "time_budget": int(self.var_time_budget.get())
        }
        miss = [k for k in SUBMIT_INPUT_SCHEMA["required"] if not payload.get(k)]
        if miss:
            raise ValueError(f"缺少必填字段：{miss}")
        if payload["max_test_cases"] < 1 or payload["time_budget"] < 1:
            raise ValueError("max_test_cases/time_budget 必须 >= 1")
        if len(payload["mutation_scope"]) == 0:
            raise ValueError("mutation_scope 至少选择一项")
        return payload

    def _show_submit_json(self):
        try:
            payload = self._build_submit_payload()
        except Exception as e:
            messagebox.showerror("参数错误", str(e))
            return
        win = tk.Toplevel(self)
        win.title("fuzz_test_submit 输入JSON（input_schema）")
        win.geometry("780x520")
        txt = tk.Text(win)
        txt.pack(fill="both", expand=True)
        txt.insert("end", json.dumps(payload, ensure_ascii=False, indent=2))

    def _submit_and_run(self):
        """
        模拟 fuzz_test_submit：返回 {process_result, task_id}
        并在本机启动 afl-fuzz 进程。
        """
        try:
            payload = self._build_submit_payload()
        except Exception as e:
            messagebox.showerror("参数错误", str(e))
            return

        afl_dir = Path(self.var_afl_dir.get()).expanduser()
        work_dir = Path(self.var_work_dir.get()).expanduser()
        target_cmd = self.var_target_cmd.get().strip()

        if not (afl_dir / "afl-fuzz").exists():
            messagebox.showerror("AFL++ 目录错误", f"找不到：{afl_dir / 'afl-fuzz'}")
            return

        if not work_dir.exists():
            messagebox.showerror("工作目录错误", f"不存在：{work_dir}")
            return

        task_id = str(uuid.uuid4())
        instance_id = task_id.split("-")[0]

        in_dir = work_dir / "in_gui" / instance_id
        out_base = work_dir / "out_gui"

        try:
            prepare_seeds(payload["seed_location"], in_dir)
        except Exception as e:
            messagebox.showerror("种子准备失败", str(e))
            return

        env = os.environ.copy()
        set_core_ulimit_unlimited()
        try_fix_core_pattern_or_bypass(env)

        env["FUZZ_TASK_NAME"] = payload["task_name"]
        env["FUZZ_TARGET_TYPE"] = payload["target_type"]
        env["FUZZ_TARGET_ENDPOINT"] = payload["target_endpoint"]
        env["FUZZ_SEED_SOURCE"] = payload["seed_source"]
        env["FUZZ_SEED_LOCATION"] = payload["seed_location"]
        env["FUZZ_MUTATION_SCOPE"] = ",".join(payload["mutation_scope"])

        try:
            afl_cmd = build_afl_command(
                afl_dir=afl_dir,
                in_dir=in_dir,
                out_base=out_base,
                instance_id=instance_id,
                max_test_cases=payload["max_test_cases"],
                time_budget=payload["time_budget"],
                target_cmd=target_cmd,
                extra_args=None
            )
        except Exception as e:
            messagebox.showerror("命令生成失败", str(e))
            return

        self._log_submit(f"提交任务：task_id={task_id} instance_id={instance_id}")
        self._log_submit("AFL 命令： " + " ".join(afl_cmd))

        # 先落库：starting
        rec = TaskRecord(
            task_id=task_id,
            task_name=payload["task_name"],
            created_at=now_iso(),
            updated_at=now_iso(),
            status="starting",
            pid=None,
            work_dir=str(work_dir),
            afl_dir=str(afl_dir),
            in_dir=str(in_dir),
            out_dir=str(out_base),
            instance_id=instance_id,
            target_cmd=target_cmd,
            submit_params=payload,
            afl_cmd=afl_cmd,
            last_error=None
        )

        self.db = load_db()
        self.db.setdefault("tasks", {})
        self.db["tasks"][task_id] = asdict(rec)
        save_db(self.db)

        if env.get("AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES") == "1":
            self._log_submit("提示：无法 sudo 修改 core_pattern，已设置 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1（可能漏 crash）")

        # 启动：优先 xterm 弹窗显示 AFL++ curses UI；否则后台运行写日志
        log_dir = APP_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{instance_id}.log"

        # 2.5 相关环境变量：建议这里统一设置（多实例不冲突）
        env["AFL_FUZZER_STATS_UPDATE_INTERVAL"] = env.get("AFL_FUZZER_STATS_UPDATE_INTERVAL", "1")
        env["NV_STATUS_PATH"] = str(out_base / instance_id / "nv_status.json")

        afl_cmd_str = " ".join(shlex.quote(x) for x in afl_cmd)

        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(f"\n[{now_iso()}] START AFL\n")
            lf.write("CMD: " + afl_cmd_str + "\n")

        p = None
        try:
            if shutil.which("xterm"):
                subprocess.Popen(
                    ["xterm", "-T", f"AFL++ {instance_id}", "-e", "bash", "-lc", afl_cmd_str],
                    cwd=str(work_dir),
                    env=env
                )
                self._log_submit("已使用 xterm 启动 AFL++（可见原生 UI 界面）")
                p = None  # xterm 方式无法拿到 afl-fuzz pid（拿到的是 xterm pid）
            else:
                lf = open(log_file, "a", encoding="utf-8")
                p = subprocess.Popen(
                    afl_cmd,
                    cwd=str(work_dir),
                    env=env,
                    stdout=lf,
                    stderr=lf,
                    preexec_fn=os.setsid
                )
                self._log_submit(f"已后台启动 AFL++，pid={p.pid}（无 UI）")

        except Exception as e:
            self._log_submit(f"启动失败：{e}")
            messagebox.showerror("启动失败", str(e))
            return

        rec = TaskRecord(
            task_id=task_id,
            task_name=payload["task_name"],
            created_at=now_iso(),
            updated_at=now_iso(),
            status="running",
            pid=(p.pid if p else None),
            work_dir=str(work_dir),
            afl_dir=str(afl_dir),
            in_dir=str(in_dir),
            out_dir=str(out_base),
            instance_id=instance_id,
            target_cmd=target_cmd,
            submit_params=payload,
            afl_cmd=afl_cmd,
            last_error=None
        )

        self.db.setdefault("tasks", {})
        self.db["tasks"][task_id] = asdict(rec)
        save_db(self.db)

        output = {"process_result": 1, "task_id": task_id}
        self._log_submit("下发结果（output_schema）：\n" + json.dumps(output, ensure_ascii=False, indent=2))
        self._log_submit(f"日志文件：{log_file}")
        messagebox.showinfo("提交成功", f"任务已启动。\n task_id = {task_id}\n实例 = {instance_id}\n日志：{log_file}")

    def _open_out_dir(self):
        work_dir = Path(self.var_work_dir.get()).expanduser()
        out_dir = work_dir / "out_gui"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(out_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            messagebox.showinfo("输出目录", str(out_dir))

    def _refresh_db(self):
        self.db = load_db()
        messagebox.showinfo("刷新完成", f"已刷新。本地任务数：{len(self.db.get('tasks', {}))}")

    # ---------- Query ----------
    def _build_query_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="任务查询（Query）")

        frm = ttk.Frame(tab)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        self.var_query_task_id = tk.StringVar()

        ttk.Label(frm, text="task_id").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_query_task_id).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(frm, text="查询", command=self._do_query).grid(row=0, column=2, padx=6)

        self.txt_query = tk.Text(frm)
        self.txt_query.grid(row=1, column=0, columnspan=3, sticky="nsew")
        frm.rowconfigure(1, weight=1)

    def _do_query(self):
        tid = self.var_query_task_id.get().strip()
        db = load_db()
        rec = db.get("tasks", {}).get(tid)
        if not rec:
            messagebox.showerror("未找到任务", f"task_id 不存在：{tid}")
            return

        task = TaskRecord(**rec)

        if task.pid and is_pid_running(task.pid):
            status = "running"
        else:
            status = task.status if task.status in ("stopped", "failed") else "finished"

        task.status = status
        task.updated_at = now_iso()

        stats_text = read_fuzzer_stats(task)

        db["tasks"][tid] = asdict(task)
        save_db(db)

        out = {
            "process_result": 1,
            "query_description": f"status={task.status}, pid={task.pid}, instance={task.instance_id}\n"
                                 f"out={Path(task.out_dir)/task.instance_id}\n\n"
                                 f"=== fuzzer_stats ===\n{stats_text[:8000]}"
        }

        self.txt_query.delete("1.0", "end")
        self.txt_query.insert("end", json.dumps(out, ensure_ascii=False, indent=2))

    # ---------- Stop ----------
    def _build_stop_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="任务停止（Stop）")

        frm = ttk.Frame(tab)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        self.var_stop_task_id = tk.StringVar()

        ttk.Label(frm, text="task_id").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_stop_task_id).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(frm, text="停止任务", command=self._do_stop).grid(row=0, column=2, padx=6)

        self.txt_stop = tk.Text(frm)
        self.txt_stop.grid(row=1, column=0, columnspan=3, sticky="nsew")
        frm.rowconfigure(1, weight=1)

    def _do_stop(self):
        tid = self.var_stop_task_id.get().strip()
        db = load_db()
        rec = db.get("tasks", {}).get(tid)
        if not rec:
            messagebox.showerror("未找到任务", f"task_id 不存在：{tid}")
            return

        task = TaskRecord(**rec)
        ok = False
        err = None

        try:
            # 1) 优先用 pid -> 进程组 SIGINT（等同 Ctrl+C）
            if task.pid and is_pid_running(task.pid):
                try:
                    os.killpg(task.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
            else:
                # 2) fallback：按 instance_id 匹配发送 SIGINT（xterm 模式也靠这个）
                subprocess.run(
                    ["bash", "-lc", f"pkill -2 -f \"afl-fuzz.*-S {task.instance_id}\""],
                    check=False
                )

            time.sleep(1.0)

            still = False
            if task.pid and is_pid_running(task.pid):
                still = True

            check = subprocess.run(
                ["bash", "-lc",
                 "for p in $(pgrep -x afl-fuzz 2>/dev/null); do "
                 "  tr '\\0' ' ' < /proc/$p/cmdline | grep -F -- \"-S %s\" && echo $p; "
                 "done | head -n 1" % task.instance_id],
                capture_output=True, text=True
            )
            if check.stdout.strip():
                still = True

            if still:
                ok = False
                err = f"仍检测到 afl-fuzz 未退出（instance={task.instance_id}, pid={task.pid})"
            else:
                ok = True
                err = None

        except Exception as e:
            ok = False
            err = str(e)

        if ok:
            task.status = "stopped"
            task.updated_at = now_iso()
            db["tasks"][tid] = asdict(task)
            save_db(db)
            out = {"process_result": 1}
            self.txt_stop.delete("1.0", "end")
            self.txt_stop.insert("end", json.dumps(out, ensure_ascii=False, indent=2))
            messagebox.showinfo("停止成功", f"已发送停止信号：task_id={tid}")
        else:
            task.updated_at = now_iso()
            task.last_error = err
            db["tasks"][tid] = asdict(task)
            save_db(db)
            out = {"process_result": 0}
            self.txt_stop.delete("1.0", "end")
            self.txt_stop.insert("end", json.dumps(out, ensure_ascii=False, indent=2) + f"\n原因：{err}")
            messagebox.showerror("停止失败", err or "未知错误")

    # ---------- Report Query ----------
    def _build_report_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="报告查询（Report Query）")

        frm = ttk.Frame(tab)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        self.var_rq_task_id = tk.StringVar()
        self.var_rq_task_name = tk.StringVar()
        self.var_rq_start = tk.StringVar(value="")
        self.var_rq_end = tk.StringVar(value="")

        r = 0
        ttk.Label(frm, text="task_id").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_rq_task_id).grid(row=r, column=1, sticky="ew", pady=4); r += 1

        ttk.Label(frm, text="task_name(模糊匹配)").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_rq_task_name).grid(row=r, column=1, sticky="ew", pady=4); r += 1

        ttk.Label(frm, text="start_time(ISO)").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_rq_start).grid(row=r, column=1, sticky="ew", pady=4); r += 1

        ttk.Label(frm, text="end_time(ISO)").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_rq_end).grid(row=r, column=1, sticky="ew", pady=4); r += 1

        ttk.Button(frm, text="查询报告列表", command=self._do_report_query).grid(row=0, column=2, rowspan=2, padx=8, sticky="ns")
        ttk.Button(frm, text="打开选中 download_url", command=self._open_selected_download).grid(row=2, column=2, rowspan=2, padx=8, sticky="ns")

        self.txt_report = tk.Text(frm)
        self.txt_report.grid(row=r, column=0, columnspan=3, sticky="nsew")
        frm.rowconfigure(r, weight=1)

        self._last_report_list: List[Dict[str, Any]] = []

    def _do_report_query(self):
        db = load_db()
        payload = {
            "task_id": self.var_rq_task_id.get().strip() or None,
            "task_name": self.var_rq_task_name.get().strip() or None,
            "time_range": None
        }
        start = self.var_rq_start.get().strip()
        end = self.var_rq_end.get().strip()
        if start or end:
            payload["time_range"] = {
                "start_time": start or None,
                "end_time": end or None
            }

        if not payload["task_id"] and not payload["task_name"] and not payload["time_range"]:
            messagebox.showerror("参数错误", "至少提供 task_id、task_name 或 time_range 中的一项")
            return

        reports = task_report_list(db, payload)
        self._last_report_list = reports

        out = {
            "process_result": 1 if reports is not None else 0,
            "total_count": len(reports),
            "report_list": reports
        }

        self.txt_report.delete("1.0", "end")
        self.txt_report.insert("end", json.dumps(out, ensure_ascii=False, indent=2))

    def _open_selected_download(self):
        if not self._last_report_list:
            messagebox.showinfo("提示", "没有报告列表。请先查询。")
            return
        url = self._last_report_list[0].get("download_url")
        if not url:
            messagebox.showerror("错误", "download_url 为空")
            return
        p = Path(url)
        if not p.exists():
            messagebox.showerror("错误", f"本地路径不存在：{p}")
            return
        try:
            subprocess.Popen(["xdg-open", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            messagebox.showinfo("download_url", str(p))


def main():
    app = FuzzGUI()
    app.mainloop()


if __name__ == "__main__":
    main()