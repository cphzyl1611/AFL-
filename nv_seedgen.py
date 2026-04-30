#!/usr/bin/env python3
import os, json, argparse, re
from pathlib import Path
from urllib.parse import quote_plus

def _qs_keep_placeholders(q: dict) -> str:
    parts = []
    for k, v in q.items():
        ks = quote_plus(str(k), safe="")
        vs = str(v)
        # 关键：保留 {{xxx}}，其余正常编码
        if "{{" in vs and "}}" in vs:
            vs_enc = quote_plus(vs, safe="{}")  # 保留花括号
        else:
            vs_enc = quote_plus(vs, safe="")
        parts.append(f"{ks}={vs_enc}")
    return "&".join(parts)


def safe_name(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[^a-zA-Z0-9_./-]+", "_", s)
    s = s.replace("/", "_").replace(":", "_")
    return s.strip("_")[:120] or "seed"

def dump_http(method, path, headers, body_bytes):
    lines = [f"{method} {path}"]
    for k, v in headers.items():
        lines.append(f"{k}: {v}")
    lines.append("")  # blank line
    if body_bytes:
        try:
            lines.append(body_bytes.decode("utf-8", errors="ignore"))
        except Exception:
            lines.append("")
    return "\n".join(lines) + "\n"

def mk_variants(body_json):
    # 变体1：缺字段/空对象
    v1 = {}
    # 变体2：类型错配/边界
    v2 = {}
    if isinstance(body_json, dict):
        for k, v in body_json.items():
            if isinstance(v, int):
                v2[k] = 2**31-1
            elif isinstance(v, list):
                v2[k] = ["", 0, None]
            elif isinstance(v, str):
                v2[k] = "A"*512
            else:
                v2[k] = None
    return [v1, v2]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default=os.getenv("NV_TARGET_CONFIG","nv_target.json"))
    ap.add_argument("--out", default="in_http")
    args = ap.parse_args()

    cfg = json.load(open(args.cfg, "r", encoding="utf-8"))
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    defaults = cfg.get("seed_defaults", {})
    def_headers = defaults.get("headers", {}) if isinstance(defaults.get("headers", {}), dict) else {}
    templates = cfg.get("seed_templates", {}) if isinstance(cfg.get("seed_templates", {}), dict) else {}

    endpoints = cfg.get("endpoints", [])
    if not isinstance(endpoints, list) or not endpoints:
        raise SystemExit("endpoints empty in cfg")

    wrote = 0
    for ep in endpoints:
        if not isinstance(ep, dict): 
            continue
        method = str(ep.get("method","GET")).upper().strip()
        path = str(ep.get("path","/")).strip()
        if not path.startswith("/"):
            path = "/" + path

        tag = str(ep.get("tag","")).strip() or safe_name(f"{method}_{path}")
        key = f"{method} {path}"

        # base template:
        # prefer by tag (matches nv_target.json), fallback by "METHOD PATH" for compatibility
        t = templates.get(tag, None)
        if t is None:
            t = templates.get(key, {})
        if not isinstance(t, dict):
            t = {}

        # body_json (POST/PUT/PATCH)
        body_json = t.get("body_json", {})
        if not isinstance(body_json, dict):
            body_json = {}

        # query (GET): will append ?k=v
        query = t.get("query", {})
        if not isinstance(query, dict):
            query = {}

        # headers = defaults + template.headers
        headers = dict(def_headers)
        th = t.get("headers", {})
        if isinstance(th, dict):
            headers.update(th)

        # build full path with query if present
        full_path = path
        if query:
            from urllib.parse import urlencode
            qs = _qs_keep_placeholders(query)
            full_path = f"{path}?{qs}"

        # GET default no body; POST/PUT/PATCH default JSON
        body_bytes = b""
        if method in ("POST","PUT","PATCH"):
            headers.setdefault("Content-Type", "application/json")
            body_bytes = json.dumps(body_json, ensure_ascii=False).encode("utf-8") if body_json else b"{}"

        # seed0: standard
        fn0 = outdir / f"seed_{tag}_0.http"
        fn0.write_bytes(dump_http(method, full_path, headers, body_bytes).encode("utf-8"))
        wrote += 1

        # seed1/2... variants (only for requests with body)
        if method in ("POST","PUT","PATCH"):
            for vi, vj in enumerate(mk_variants(body_json), start=1):
                fn = outdir / f"seed_{tag}_{vi}.http"
                vb = json.dumps(vj, ensure_ascii=False).encode("utf-8")
                fn.write_bytes(dump_http(method, full_path, headers, vb).encode("utf-8"))
                wrote += 1

    print(f"[OK] wrote {wrote} seeds to {outdir}")

if __name__ == "__main__":
    main()