#!/usr/bin/env python3
import json
import argparse
from pathlib import Path

ROOT = Path.home() / "AFLplusplus"
IN_DIR = ROOT / "in" / "o2oa_body_cms_score"
OUT_DIR = ROOT / "model_stage" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "sefanogan_dataset.jsonl"

SAMPLES = [
    ("seed_ok_0.json", "normal"),
    ("seed_ok_1.json", "normal"),
    ("seed_ok_2.json", "normal"),
    ("seed_ok_3.json", "normal"),
    ("seed_ok_4.json", "normal"),
    ("seed_ok_5.json", "normal"),
    ("seed_ok_6.json", "normal"),
    ("seed_ok_7.json", "normal"),
    ("seed_ok_8.json", "normal"),
    ("seed_ok_9.json", "normal"),
    ("seed_ok_10.json", "normal"),
    ("seed_ok_11.json", "normal"),
    ("seed_ok_12.json", "normal"),
    ("seed_ok_13.json", "normal"),
    ("seed_ok_14.json", "normal"),
    ("seed_ok_15.json", "normal"),
    ("seed_ok_16.json", "normal"),
    ("seed_ok_17.json", "normal"),
    ("seed_ok_18.json", "normal"),
    ("seed_ok_19.json", "normal"),
    ("seed_ok_20.json", "normal"),
    ("seed_ok_21.json", "normal"),
    ("seed_ok_22.json", "normal"),
    ("seed_ok_23.json", "normal"),
    ("seed_ok_24.json", "normal"),
    ("seed_ok_25.json", "normal"),
    ("seed_ok_26.json", "normal"),
    ("seed_ok_27.json", "normal"),
    ("seed_ok_28.json", "normal"),
    ("seed_ok_29.json", "normal"),
    ("seed_ok_30.json", "normal"),
    ("seed_ok_31.json", "normal"),
    ("seed_ok_32.json", "normal"),
    ("seed_ok_33.json", "normal"),
    ("seed_ok_34.json", "normal"),
    ("seed_ok_35.json", "normal"),
    ("seed_ok_36.json", "normal"),
    ("seed_ok_37.json", "normal"),
    ("seed_ok_38.json", "normal"),
    ("seed_ok_39.json", "normal"),
    ("seed_ok_40.json", "normal"),
    ("seed_ok_41.json", "normal"),
    ("seed_ok_42.json", "normal"),
    ("seed_ok_43.json", "normal"),
    ("seed_ok_44.json", "normal"),
    ("seed_ok_45.json", "normal"),
    ("seed_ok_46.json", "normal"),
    ("seed_ok_47.json", "normal"),
    ("seed_ok_48.json", "normal"),
    ("seed_ok_49.json", "normal"),
    ("seed_ok_50.json", "normal"),
    ("seed_ok_51.json", "normal"),
    ("seed_ok_52.json", "normal"),
    ("seed_ok_53.json", "normal"),
    ("seed_ok_54.json", "normal"),
    ("seed_ok_55.json", "normal"),
    ("seed_ok_56.json", "normal"),
    ("seed_ok_57.json", "normal"),
    ("seed_ok_58.json", "normal"),
    ("seed_ok_59.json", "normal"),
    ("seed_ok_60.json", "normal"),
    ("seed_ok_61.json", "normal"),
    ("seed_ok_62.json", "normal"),
    ("seed_ok_63.json", "normal"),
    ("seed_ok_64.json", "normal"),
    ("seed_ok_65.json", "normal"),
    ("seed_ok_66.json", "normal"),
    ("seed_ok_67.json", "normal"),
    ("seed_ok_68.json", "normal"),
    ("seed_ok_69.json", "normal"),
    ("seed_ok_70.json", "normal"),
    ("seed_ok_71.json", "normal"),
    ("seed_ok_72.json", "normal"),
    ("seed_ok_73.json", "normal"),
    ("seed_ok_74.json", "normal"),
    ("seed_ok_75.json", "normal"),
    ("seed_ok_76.json", "normal"),
    ("seed_ok_77.json", "normal"),
    ("seed_ok_78.json", "normal"),
    ("seed_ok_79.json", "normal"),
    ("seed_ok_80.json", "normal"),
    ("seed_ok_81.json", "normal"),
    ("seed_ok_82.json", "normal"),
    ("seed_ok_83.json", "normal"),
    ("seed_ok_84.json", "normal"),
    ("seed_ok_85.json", "normal"),
    ("seed_ok_86.json", "normal"),
    ("seed_ok_87.json", "normal"),
    ("seed_ok_88.json", "normal"),
    ("seed_ok_89.json", "normal"),
    ("seed_ok_90.json", "normal"),
    ("seed_ok_91.json", "normal"),
    ("seed_ok_92.json", "normal"),
    ("seed_ok_93.json", "normal"),
    ("seed_ok_94.json", "normal"),
    ("seed_ok_95.json", "normal"),
    ("seed_ok_96.json", "normal"),
    ("seed_ok_97.json", "normal"),
    ("seed_ok_98.json", "normal"),
    ("seed_ok_99.json", "normal"),
    ("seed_ok_100.json", "normal"),
    ("seed_ok_101.json", "normal"),
    ("seed_ok_102.json", "normal"),
    ("seed_ok_103.json", "normal"),
    ("seed_ok_104.json", "normal"),
    ("seed_ok_105.json", "normal"),
    ("seed_ok_106.json", "normal"),
    ("seed_ok_107.json", "normal"),
    ("seed_ok_108.json", "normal"),
    ("seed_ok_109.json", "normal"),
    ("seed_ok_110.json", "normal"),
    ("seed_ok_111.json", "normal"),
    ("seed_ok_112.json", "normal"),

    ("seed_border_2.json", "border"),
    ("seed_border_3.json", "border"),
    ("seed_border_4.json", "border"),
    ("seed_border_5.json", "border"),
    ("seed_border_6.json", "border"),
    ("seed_border_7.json", "border"),
    ("fuzz_border_1.json", "border"),
    ("fuzz_border_2.json", "border"),
    ("fuzz_border_3.json", "border"),
    ("fuzz_border_4.json", "border"),
    ("seed_border_8.json", "border"),
    ("seed_border_9.json", "border"),
    ("seed_border_10.json", "border"),
    ("seed_border_11.json", "border"),
    ("seed_border_12.json", "border"),
    ("seed_border_13.json", "border"),
    ("fuzz_border_5.json", "border"),
    ("fuzz_border_6.json", "border"),
    ("fuzz_border_7.json", "border"),
    ("fuzz_border_8.json", "border"),
    ("fuzz_border_9.json", "border"),
    ("fuzz_border_10.json", "border"),
    ("fuzz_border_11.json", "border"),
    ("fuzz_border_12.json", "border"),
    ("fuzz_border_13.json", "border"),
    ("fuzz_border_14.json", "border"),
    ("fuzz_border_15.json", "border"),
    ("fuzz_border_16.json", "border"),
    ("fuzz_border_17.json", "border"),
    ("fuzz_border_18.json", "border"),
    ("fuzz_border_19.json", "border"),
    ("fuzz_border_20.json", "border"),

    ("seed_badscore_3.json", "abnormal"),
    ("seed_badscore_4.json", "abnormal"),
    ("seed_badscore_5.json", "abnormal"),
    ("seed_badscore_6.json", "abnormal"),
    ("seed_badscore_7.json", "abnormal"),
    ("seed_badscore_8.json", "abnormal"),
    ("seed_badscore_9.json", "abnormal"),
    ("seed_badscore_10.json", "abnormal"),
    ("seed_badscore_11.json", "abnormal"),
    ("fuzz_bad_1.json", "abnormal"),
    ("fuzz_bad_2.json", "abnormal"),
    ("fuzz_bad_3.json", "abnormal"),
    ("fuzz_bad_4.json", "abnormal"),
    ("seed_badscore_12.json", "abnormal"),
    ("seed_badscore_13.json", "abnormal"),
    ("seed_badscore_14.json", "abnormal"),
    ("seed_badscore_15.json", "abnormal"),
    ("seed_badscore_16.json", "abnormal"),
    ("seed_badscore_17.json", "abnormal"),
    ("fuzz_bad_5.json", "abnormal"),
    ("fuzz_bad_6.json", "abnormal"),
    ("fuzz_bad_7.json", "abnormal"),
    ("fuzz_bad_8.json", "abnormal"),
    ("fuzz_bad_9.json", "abnormal"),
    ("fuzz_bad_10.json", "abnormal"),
    ("fuzz_bad_11.json", "abnormal"),
    ("fuzz_bad_12.json", "abnormal"),
    ("fuzz_bad_13.json", "abnormal"),
    ("fuzz_bad_14.json", "abnormal"),
    ("fuzz_bad_15.json", "abnormal"),
    ("fuzz_bad_16.json", "abnormal"),
    ("fuzz_bad_17.json", "abnormal"),
    ("fuzz_bad_18.json", "abnormal"),
    ("fuzz_bad_19.json", "abnormal"),
    ("fuzz_bad_20.json", "abnormal"),
    ("fuzz_bad_21.json", "abnormal"),
    ("fuzz_bad_22.json", "abnormal"),
]

def load_manifest_pairs(manifest_path: str):
    pairs = []
    p = Path(manifest_path)
    with p.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [x.strip() for x in line.split(",")]
            if len(parts) != 2:
                raise ValueError(f"Invalid manifest line: {line}")
            fname, tag = parts
            pairs.append((fname, tag))
    return pairs

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Optional manifest file: each line 'filename,tag'"
    )
    args = parser.parse_args()

    dataset_pairs = SAMPLES
    if args.manifest:
        dataset_pairs = load_manifest_pairs(args.manifest)

    rows = []
    for fname, tag in dataset_pairs:
        path = IN_DIR / fname
        if not path.exists():
            raise FileNotFoundError(f"Sample file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            body_obj = json.load(f)

        row = {
            "endpoint": "cms_doc_list",
            "source_file": fname,
            "tag": tag,
            "body": body_obj,
        }
        rows.append(row)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.manifest:
        print(f"[OK] wrote {OUT_FILE} ({len(rows)} rows) from manifest {args.manifest}")
    else:
        print(f"[OK] wrote {OUT_FILE} ({len(rows)} rows)")

if __name__ == "__main__":
    main()