import json, os, time, hashlib

RESP_CLASS_COUNT = 6

# 业务桶全集（必须与你 bucket_biz_code 返回集合一致）
BIZ_BUCKETS = [
    "auth_fail",
    "perm_denied",
    "validation_err",
    "duplicate",
    "not_found",
    "server_error",
    "none",
    "other",
]

def calc_nall() -> int:
    # 允许手工覆盖（验收/论文需要固定口径时有用）
    v = os.getenv("NV_NALL", "").strip()
    if v.isdigit() and int(v) > 0:
        return int(v)

    # 由 harness 传入的 endpoint 数（推荐）
    ep = os.getenv("NV_ENDPOINTS", "").strip()
    n_ep = int(ep) if ep.isdigit() and int(ep) > 0 else 1

    return max(1, n_ep * RESP_CLASS_COUNT * len(BIZ_BUCKETS))

PROBE_PATH = os.getenv("NV_PROBE_PATH", "/tmp/nv_probe.json")
STATE_DB_PATH = os.getenv("NV_STATE_DB", "/tmp/nv_state_db.json")

def _load_db():
    try:
        return set(json.load(open(STATE_DB_PATH, "r", encoding="utf-8")))
    except Exception:
        return set()

def _save_db(s):
    tmp = STATE_DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(list(s)), f, ensure_ascii=False)
    os.replace(tmp, STATE_DB_PATH)

def bucket_biz_code(biz_code) -> str:
    s = str(biz_code or "").lower()
    if "auth" in s or "login" in s: return "auth_fail"
    if "perm" in s or "forbidden" in s: return "perm_denied"
    if "valid" in s or "param" in s: return "validation_err"
    if "dup" in s or "exist" in s: return "duplicate"
    if s.strip() == "": return "none"
    return "other"

def update_state(method, path, resp_class, biz_code="", extra_tag=""):
    biz_bucket = bucket_biz_code(biz_code)
    key = f"{method} {path}|{resp_class}|{biz_bucket}|{extra_tag}"
    keyh = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()

    db = _load_db()
    before = len(db)
    db.add(keyh)
    after = len(db)
    delta = 1 if after > before else 0

    _save_db(db)

    data = {
        "ts_ms": int(time.time()*1000),
        "ncov_total": after,
        "ncov_delta": delta,
        "nall": calc_nall()
    }

    tmp = PROBE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, PROBE_PATH)
    return data
