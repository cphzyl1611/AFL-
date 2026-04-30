#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

def tail_last_line(p: Path) -> str:
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    for i in range(len(lines)-1, -1, -1):
        if lines[i].strip() and not lines[i].startswith("#"):
            return lines[i]
    raise RuntimeError("No data line found in plot_data")

def parse_plot_last(plot_path: Path):
    lines = plot_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    header = None
    last = None
    for ln in lines:
        if ln.startswith("#"):
            header = [x.strip() for x in ln.lstrip("#").split(",")]
        elif ln.strip():
            last = [x.strip() for x in ln.split(",")]
    if not header or not last:
        raise RuntimeError("plot_data missing header or data")

    idx = {name: i for i, name in enumerate(header)}

    def get(name, default=0.0):
        i = idx.get(name, None)
        if i is None or i >= len(last):
            return default
        try:
            return float(last[i])
        except Exception:
            return default

    return {
        "nv_http_ok": int(get("nv_http_ok", 0)),
        "nv_http_fail": int(get("nv_http_fail", 0)),
        "nv_ncov_hit": int(get("nv_ncov_hit", 0)),
        "nv_err_cnt": int(get("nv_err_cnt", 0)),
        "nv_rec_cnt": int(get("nv_rec_cnt", 0)),
        "nv_rec_ms_sum": int(get("nv_rec_ms_sum", 0)),
        "nv_status_cnt": int(get("nv_status_cnt", 0)),
        "mab": {
            "a0_pulls": int(get("nv_mab_a0_pulls", 0)),
            "a1_pulls": int(get("nv_mab_a1_pulls", 0)),
            "a2_pulls": int(get("nv_mab_a2_pulls", 0)),
            "a0_mean": float(get("nv_mab_a0_mean", 0.0)),
            "a1_mean": float(get("nv_mab_a1_mean", 0.0)),
            "a2_mean": float(get("nv_mab_a2_mean", 0.0)),
        }
    }

def load_probe(probe_path: Path):
    if not probe_path.exists():
        return {"ncov_total": 0, "ncov_delta": 0, "nall": 0, "ts_ms": 0}
    return json.loads(probe_path.read_text(encoding="utf-8", errors="ignore"))

def score(C, err_rate, rec_rate, avg_rec_ms):
    # 默认权重（可配置）
    wC = float(os.getenv("NV_W_C", "100"))
    wE = float(os.getenv("NV_W_E", "50"))
    wR = float(os.getenv("NV_W_R", "50"))
    wT = float(os.getenv("NV_W_T", "0.1"))
    return wC*C + wR*rec_rate - wE*err_rate - wT*avg_rec_ms

def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out_http")
    plot = out_dir / "plot_data"
    if not plot.exists():
        raise SystemExit(f"plot_data not found: {plot}")

    probe_path = Path(os.getenv("NV_PROBE_PATH", "/tmp/nv_probe.json"))
    probe = load_probe(probe_path)

    stats = parse_plot_last(plot)

    ncov_total = int(probe.get("ncov_total", 0))
    nall = int(probe.get("nall", 0))
    C_final = (ncov_total / nall) if nall > 0 else 0.0

    # Err/Rec 指标
    denom = max(stats.get("nv_status_cnt", 0), 1)
    err_rate = stats["nv_err_cnt"] / denom
    rec_rate = (stats["nv_rec_cnt"] / stats["nv_err_cnt"]) if stats["nv_err_cnt"] > 0 else 1.0
    avg_rec_ms = (stats["nv_rec_ms_sum"] / stats["nv_rec_cnt"]) if stats["nv_rec_cnt"] > 0 else 0.0

    total_score = score(C_final, err_rate, rec_rate, avg_rec_ms)

    report = {
        "out_dir": str(out_dir),
        "probe_path": str(probe_path),
        "Cov": {
            "ncov_total": ncov_total,
            "nall": nall,
            "C_final": C_final,
            "ncov_last_delta": int(probe.get("ncov_delta", 0)),
        },
        "ErrRec": {
            "err_cnt": stats["nv_err_cnt"],
            "rec_cnt": stats["nv_rec_cnt"],
            "err_rate": err_rate,
            "rec_rate": rec_rate,
            "avg_recover_ms": avg_rec_ms,
        },
        "MAB": stats["mab"],
        "Raw": stats,
        "Score": {
            "total": total_score,
            "weights": {
                "NV_W_C": os.getenv("NV_W_C", "100"),
                "NV_W_E": os.getenv("NV_W_E", "50"),
                "NV_W_R": os.getenv("NV_W_R", "50"),
                "NV_W_T": os.getenv("NV_W_T", "0.1"),
            }
        }
    }

    out_path = out_dir / "report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {out_path}")
    print(json.dumps(report["Cov"], ensure_ascii=False))
    print(json.dumps(report["ErrRec"], ensure_ascii=False))
    print(json.dumps(report["Score"], ensure_ascii=False))

if __name__ == "__main__":
    main()
