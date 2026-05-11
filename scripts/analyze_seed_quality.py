#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


DEFAULT_OUT_JSON = "docs/review/evidence/seed_quality_summary.json"
DEFAULT_OUT_CSV = "docs/review/evidence/seed_quality_summary.csv"
BUSINESS_FIELDS = {
    "docTitle",
    "docContent",
    "cm:title",
    "cm:description",
    "processDefinitionKey",
    "variables",
    "businessKey",
    "name",
    "properties",
}
CSV_FIELDS = [
    "seed_dir",
    "seed_count",
    "json_seed_count",
    "valid_json_count",
    "invalid_json_count",
    "ok_seed_count",
    "border_seed_count",
    "bad_seed_count",
    "avg_size_bytes",
    "max_size_bytes",
    "min_size_bytes",
    "top_level_fields",
    "nested_field_paths",
    "has_expected_negative",
    "business_fields_detected",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze local seed directories and emit seed quality evidence."
    )
    parser.add_argument("--root", default="in", help="Root seed directory to scan.")
    parser.add_argument("--out-json", default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-csv", default=DEFAULT_OUT_CSV)
    return parser.parse_args()


def iter_seed_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []

    dirs: Set[Path] = set()
    for path in root.rglob("*"):
        if path.is_file() and not any(part.startswith(".") for part in path.parts):
            dirs.add(path.parent)
    return sorted(dirs)


def collect_paths(value: Any, prefix: str = "", depth: int = 0, max_depth: int = 4) -> Set[str]:
    if depth >= max_depth:
        return set()

    paths: Set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            paths.add(path)
            paths.update(collect_paths(child, path, depth + 1, max_depth))
    elif isinstance(value, list):
        for child in value:
            path = f"{prefix}[]" if prefix else "[]"
            paths.add(path)
            paths.update(collect_paths(child, path, depth + 1, max_depth))
    return paths


def top_level_fields(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        return [str(key) for key in obj.keys()]
    if isinstance(obj, list):
        fields = set()
        for item in obj:
            if isinstance(item, dict):
                fields.update(str(key) for key in item.keys())
        return sorted(fields)
    return []


def detect_business_fields(paths: Set[str]) -> List[str]:
    found = set()
    for path in paths:
        parts = path.replace("[]", "").split(".")
        for part in parts:
            if part in BUSINESS_FIELDS:
                found.add(part)
    return sorted(found)


def analyze_dir(seed_dir: Path) -> Dict[str, Any]:
    files = sorted(path for path in seed_dir.iterdir() if path.is_file())
    sizes = [path.stat().st_size for path in files]
    json_files = [path for path in files if path.suffix.lower() == ".json"]

    valid_json_count = 0
    invalid_json_count = 0
    top_fields: Set[str] = set()
    nested_paths: Set[str] = set()

    for path in json_files:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            invalid_json_count += 1
            continue

        valid_json_count += 1
        top_fields.update(top_level_fields(obj))
        nested_paths.update(collect_paths(obj))

    lower_names = [path.name.lower() for path in files]
    ok_count = sum(1 for name in lower_names if "ok" in name)
    border_count = sum(1 for name in lower_names if "border" in name)
    bad_count = sum(1 for name in lower_names if "bad" in name)
    business_fields = detect_business_fields(nested_paths | top_fields)

    notes = []
    if ok_count:
        notes.append("has_ok_seed")
    if border_count:
        notes.append("has_border_seed")
    if bad_count:
        notes.append("has_expected_negative_seed")
    if business_fields:
        notes.append("has_business_fields")
    if invalid_json_count:
        notes.append("has_invalid_json")
    if not json_files:
        notes.append("non_json_seed_dir")

    return {
        "seed_dir": str(seed_dir),
        "seed_count": len(files),
        "json_seed_count": len(json_files),
        "valid_json_count": valid_json_count,
        "invalid_json_count": invalid_json_count,
        "ok_seed_count": ok_count,
        "border_seed_count": border_count,
        "bad_seed_count": bad_count,
        "avg_size_bytes": round(sum(sizes) / len(sizes), 2) if sizes else 0,
        "max_size_bytes": max(sizes) if sizes else 0,
        "min_size_bytes": min(sizes) if sizes else 0,
        "top_level_fields": sorted(top_fields),
        "nested_field_paths": sorted(nested_paths),
        "has_expected_negative": bad_count > 0,
        "business_fields_detected": business_fields,
        "notes": notes,
    }


def csv_row(record: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(record)
    for key in ["top_level_fields", "nested_field_paths", "business_fields_detected", "notes"]:
        row[key] = ";".join(str(item) for item in row.get(key, []))
    row["has_expected_negative"] = str(bool(row.get("has_expected_negative"))).lower()
    return row


def write_outputs(records: List[Dict[str, Any]], warnings: List[str], out_json: Path, out_csv: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "seed_quality_summary_v1",
        "description": (
            "Local seed quality statistics for stage acceptance. The method is "
            "engineering heuristic based, not a fully automated semantic seed generator."
        ),
        "records": records,
        "warnings": warnings,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for rec in records:
            writer.writerow(csv_row(rec))


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    warnings: List[str] = []

    if not root.exists():
        warnings.append(f"unavailable seed root: {root}")
        records: List[Dict[str, Any]] = []
    else:
        records = [analyze_dir(seed_dir) for seed_dir in iter_seed_dirs(root)]

    write_outputs(records, warnings, Path(args.out_json), Path(args.out_csv))
    print(f"[OK] seed_dirs={len(records)} json={args.out_json} csv={args.out_csv}")
    for warning in warnings:
        print(f"[WARN] {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
