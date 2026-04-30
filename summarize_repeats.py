#!/usr/bin/env python3
import argparse, csv, math
from pathlib import Path

RUNS = ["mab_all","only_field","only_boundary","only_structure"]
BUDGETS = [120, 300]

def read_summary(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def mean_std(xs):
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    m = sum(xs) / n
    if n == 1:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r", type=int, default=3, help="repeat count")
    ap.add_argument("--out", default="repeat_summary.csv")
    args = ap.parse_args()

    rows_out = []
    for budget in BUDGETS:
        for run in RUNS:
            C_list, err_list, score_list = [], [], []
            ncov_list, errcnt_list = [], []

            for i in range(1, args.r + 1):
                root = Path(f"out_http_ablation_{budget}_r{i}")
                summ = root / "summary.csv"
                if not summ.exists():
                    raise FileNotFoundError(f"missing {summ}")
                data = read_summary(summ)
                m = {d["run"]: d for d in data}
                d = m.get(run)
                if not d:
                    raise ValueError(f"{summ} missing run={run}")

                C_list.append(float(d["C_final"]))
                err_list.append(float(d["err_rate"]))
                score_list.append(float(d["score"]))
                ncov_list.append(int(d["ncov_total"]))
                errcnt_list.append(int(d["err_cnt"]))

            C_m, C_s = mean_std(C_list)
            E_m, E_s = mean_std(err_list)
            S_m, S_s = mean_std(score_list)
            nc_m, nc_s = mean_std([float(x) for x in ncov_list])
            ec_m, ec_s = mean_std([float(x) for x in errcnt_list])

            rows_out.append({
                "budget_s": budget,
                "run": run,
                "C_mean": f"{C_m:.6f}", "C_std": f"{C_s:.6f}",
                "err_rate_mean": f"{E_m:.6f}", "err_rate_std": f"{E_s:.6f}",
                "score_mean": f"{S_m:.6f}", "score_std": f"{S_s:.6f}",
                "ncov_mean": f"{nc_m:.3f}", "ncov_std": f"{nc_s:.3f}",
                "err_cnt_mean": f"{ec_m:.3f}", "err_cnt_std": f"{ec_s:.3f}",
            })

    outp = Path(args.out)
    fields = ["budget_s","run",
              "C_mean","C_std",
              "err_rate_mean","err_rate_std",
              "score_mean","score_std",
              "ncov_mean","ncov_std",
              "err_cnt_mean","err_cnt_std"]
    with outp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    print("[OK] Wrote", outp)

if __name__ == "__main__":
    main()
