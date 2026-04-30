#!/usr/bin/env python3
import json, os, sys, time, subprocess

def load(p):
    with open(p,"r",encoding="utf-8") as f:
        return json.load(f)

def snap(d):
    return (int(d["exec"]["valid_exec"]),
            int(d["err"]["err_exec"]),
            int(d["rec"]["rec_total"]),
            int(d["rec"]["rec_success"]))

def write_status(p, exc, code, rec, ms):
    with open(p,"w",encoding="utf-8") as f:
        f.write(f'{{"is_exception":{str(exc).lower()},"http_code":{code},"recovered":{str(rec).lower()},"recover_ms":{ms}}}')

def main():
    out_dir = sys.argv[1] if len(sys.argv)>1 else "out/default"
    rp = os.path.join(out_dir, "eval_report.json")
    sp = os.path.join(out_dir, "nv_status.json")

    if not os.path.isfile(rp):
        print("[FAIL] missing", rp); sys.exit(1)

    # 0) ensure fuzzer is making progress
    a = snap(load(rp))
    time.sleep(5)
    b = snap(load(rp))
    print("progress check a:", a)
    print("progress check b:", b)
    if b[0] <= a[0]:
        print("[FAIL] valid_exec did not increase in 5s. Your afl-fuzz may not be running or stats not updating.")
        print("       Fix: make sure afl-fuzz is running; check out/default/fuzzer_stats timestamp changes.")
        sys.exit(2)
    print("[OK] afl-fuzz is progressing")

    # 1) force env path match (important)
    os.environ["NV_STATUS_PATH"] = sp
    print("[INFO] set NV_STATUS_PATH =", sp)

    # 2) force business error
    before = snap(load(rp))
    print("before force:", before)
    write_status(sp, True, 500, True, 1234)
    print("[INFO] wrote", sp)

    # 3) wait up to 10 seconds for counters to increase
    deadline = time.time() + 10
    changed = False
    while time.time() < deadline:
        time.sleep(1)
        cur = snap(load(rp))
        # require increase in err_exec or rec_total
        if cur[1] > before[1] or cur[2] > before[2] or cur[3] > before[3]:
            print("[OK] counters increased:", cur)
            changed = True
            break

    if not changed:
        print("[FAIL] counters did NOT increase after forcing nv_status.json within 10s.")
        print("Possible causes:")
        print("  1) nv_read_status_json not called (code path not executed)")
        print("  2) NV_STATUS_PATH not used / different path")
        print("  3) parsing failed / file unreadable")
        print("\nNext debugging commands:")
        print("  ls -l", sp)
        print("  cat", sp)
        print("  rg -n \"NV_STATUS_PATH|nv_status\\.json|nv_read_status_json\" -S src/afl-fuzz-run.c")
        sys.exit(3)

    print("[PASS] 2.5 strict business err/rec verification OK")

if __name__ == "__main__":
    main()