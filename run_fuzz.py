#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import resource
from pathlib import Path

AFL_DIR = Path.cwd()  # 建议在 ~/AFLplusplus 目录下运行
IN_DIR = AFL_DIR / "in"
OUT_DIR = AFL_DIR / "out"
TEST_C = AFL_DIR / "test.c"
TEST_BIN = AFL_DIR / "test_afl"

def run(cmd, check=True, **kwargs):
    print(f"[cmd] {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, text=True, **kwargs)

def ensure_tools():
    afl_fuzz = AFL_DIR / "afl-fuzz"
    afl_cc = AFL_DIR / "afl-clang-fast"
    if not afl_fuzz.exists():
        print("[!] 找不到 ./afl-fuzz，请确认你在 AFLplusplus 源码目录里运行。")
        sys.exit(1)
    if not afl_cc.exists():
        print("[!] 找不到 ./afl-clang-fast，说明插桩编译器未生成。请先 make distrib -j。")
        sys.exit(1)

def write_test_c():
    code = r'''#include <unistd.h>
int main() {
  char b[4];
  int n = read(0, b, 4);
  if (n > 2 && b[0] == 'B' && b[1] == 'U' && b[2] == 'G') {
    *(volatile int*)0 = 0; // SIGSEGV
  }
  return 0;
}
'''
    TEST_C.write_text(code, encoding="utf-8")

def compile_target():
    # -O0 -g 便于复现与调试
    run([str(AFL_DIR / "afl-clang-fast"), "-O0", "-g", str(TEST_C), "-o", str(TEST_BIN)])

def prep_dirs_and_seed():
    IN_DIR.mkdir(parents=True, exist_ok=True)
    # 至少一个不崩的 seed（避免 dry run 直接 abort）
    (IN_DIR / "seed_ok").write_bytes(b"AAAA")
    # 清理旧 out
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def try_fix_core_pattern():
    """
    AFL++ 在 core_pattern 以 '|' 开头时会 abort。
    在 WSL 里常见 '|/wsl-capture-crash ...'。
    能 sudo 就把它改成 'core'；不能 sudo 就设置绕过变量。
    """
    core_pattern = Path("/proc/sys/kernel/core_pattern")
    try:
        cur = core_pattern.read_text().strip()
    except Exception as e:
        print(f"[!] 读取 core_pattern 失败：{e}")
        return {"AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1"}

    if not cur.startswith("|"):
        print(f"[+] core_pattern OK: {cur}")
        return {}

    print(f"[!] core_pattern 是管道模式：{cur}")
    # 尝试 sudo 写入：echo core | sudo tee /proc/sys/kernel/core_pattern
    try:
        p1 = subprocess.Popen(["echo", "core"], stdout=subprocess.PIPE, text=True)
        p2 = subprocess.run(["sudo", "tee", "/proc/sys/kernel/core_pattern"],
                            stdin=p1.stdout, text=True, check=True)
        p1.stdout.close()
        print("[+] 已通过 sudo 将 core_pattern 临时改为 'core'")
        return {}
    except Exception as e:
        print(f"[!] sudo 修改 core_pattern 失败（将采用绕过变量）：{e}")
        return {"AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1"}

def set_core_ulimit_unlimited():
    # 等价于 ulimit -c unlimited，但在 Python 里对当前进程及其子进程生效
    resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
    print("[+] core dump ulimit 已设置为 unlimited")

def start_fuzz(extra_env):
    env = os.environ.copy()
    env.update(extra_env)

    # 启动 afl-fuzz（Ctrl+C 停止）
    cmd = [str(AFL_DIR / "afl-fuzz"), "-i", str(IN_DIR), "-o", str(OUT_DIR), "--", str(TEST_BIN)]
    print("\n[+] 即将启动 fuzz（按 Ctrl+C 停止）...\n")
    # 让 afl-fuzz 接管终端（交互 UI）
    os.execve(str(AFL_DIR / "afl-fuzz"), cmd, env)

def main():
    ensure_tools()
    write_test_c()
    compile_target()
    prep_dirs_and_seed()
    set_core_ulimit_unlimited()
    extra_env = try_fix_core_pattern()
    start_fuzz(extra_env)

if __name__ == "__main__":
    main()
