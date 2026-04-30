#!/usr/bin/env python3
import argparse, csv
from pathlib import Path

ORDER = ["mab_all","only_field","only_boundary","only_structure"]

def read_summary(p: Path):
    with p.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root120", required=True)
    ap.add_argument("--root300", required=True)
    ap.add_argument("--out", default="compare_out")
    args = ap.parse_args()

    r120 = Path(args.root120) / "summary.csv"
    r300 = Path(args.root300) / "summary.csv"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows120 = read_summary(r120)
    rows300 = read_summary(r300)

    # index by run
    m120 = {x["run"]: x for x in rows120}
    m300 = {x["run"]: x for x in rows300}

    out_csv = out / "summary_compare.csv"
    fields = ["run",
              "C_final_120","err_rate_120","score_120","ncov_120","err_cnt_120",
              "C_final_300","err_rate_300","score_300","ncov_300","err_cnt_300"]
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for run in ORDER:
            a = m120.get(run, {})
            b = m300.get(run, {})
            w.writerow({
                "run": run,
                "C_final_120": a.get("C_final","0"),
                "err_rate_120": a.get("err_rate","0"),
                "score_120": a.get("score","0"),
                "ncov_120": a.get("ncov_total","0"),
                "err_cnt_120": a.get("err_cnt","0"),
                "C_final_300": b.get("C_final","0"),
                "err_rate_300": b.get("err_rate","0"),
                "score_300": b.get("score","0"),
                "ncov_300": b.get("ncov_total","0"),
                "err_cnt_300": b.get("err_cnt","0"),
            })
    print("[OK] Wrote", out_csv)

if __name__ == "__main__":
    main()
