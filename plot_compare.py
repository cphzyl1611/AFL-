#!/usr/bin/env python3
"""
plot_compare.py

Compare two experiment roots produced by run_ablation_v2.sh (each containing summary.csv)
and generate:
  - C_final_compare.png
  - ErrRate_compare.png
  - summary_compare.csv

Usage:
  python3 plot_compare.py --root120 out_http_ablation_120 --root300 out_http_ablation_300 --out compare_out

Notes:
  - Each root must contain summary.csv with columns:
      run,ncov_total,nall,C_final,err_cnt,rec_cnt,err_rate,rec_rate,score
  - "run" is expected to include: mab_all, only_field, only_boundary, only_structure
"""
import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ORDER = ["mab_all", "only_field", "only_boundary", "only_structure"]

def load_summary(root: Path) -> pd.DataFrame:
    csv_path = root / "summary.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"summary.csv not found under: {root}")
    df = pd.read_csv(csv_path)
    need = {"run","C_final","err_rate","score"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} missing columns: {sorted(missing)}")
    return df

def lineplot(df: pd.DataFrame, x_col: str, y_col: str, out_png: Path, title: str):
    plt.figure()
    for budget, grp in df.groupby("budget"):
        grp = grp.sort_values("run")
        plt.plot(grp[x_col].astype(str), grp[y_col], marker="o", label=budget)
    plt.xlabel(x_col)
    plt.ylabel(y_col)
    plt.title(title)
    plt.legend()
    plt.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root120", required=True, help="Experiment root for 120s (contains summary.csv)")
    ap.add_argument("--root300", required=True, help="Experiment root for 300s (contains summary.csv)")
    ap.add_argument("--out", default="compare_out", help="Output directory for plots/csv")
    args = ap.parse_args()

    r120 = Path(args.root120)
    r300 = Path(args.root300)
    out_dir = Path(args.out)

    df120 = load_summary(r120)
    df300 = load_summary(r300)

    df120 = df120.copy()
    df300 = df300.copy()
    df120["budget"] = "120s"
    df300["budget"] = "300s"

    combined = pd.concat([df120, df300], ignore_index=True)

    combined["run"] = pd.Categorical(combined["run"], categories=ORDER, ordered=True)
    combined = combined.sort_values(["run","budget"])

    out_dir.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out_dir / "summary_compare.csv", index=False)

    lineplot(combined, "run", "C_final", out_dir / "C_final_compare.png",
             "Coverage (C_final) by strategy (120s vs 300s)")
    lineplot(combined, "run", "err_rate", out_dir / "ErrRate_compare.png",
             "Error rate (err_rate) by strategy (120s vs 300s)")
    lineplot(combined, "run", "score", out_dir / "Score_compare.png",
             "Score by strategy (120s vs 300s)")

    print("[OK] Wrote:")
    print(" -", out_dir / "summary_compare.csv")
    print(" -", out_dir / "C_final_compare.png")
    print(" -", out_dir / "ErrRate_compare.png")
    print(" -", out_dir / "Score_compare.png")

if __name__ == "__main__":
    main()
