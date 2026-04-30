#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path.home() / "AFLplusplus"
OUT = ROOT / "in" / "flowable_process_start_dataset_v2"
MANIFEST = ROOT / "model_stage" / "manifests" / "flowable_manifest_90.txt"

OUT.mkdir(parents=True, exist_ok=True)
MANIFEST.parent.mkdir(parents=True, exist_ok=True)

def dump(name, obj):
    (OUT / name).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def mk_normal(employee, days):
    return {
        "processDefinitionKey": "holidayRequest",
        "variables": [
            {"name": "employee", "value": employee},
            {"name": "nrOfHolidays", "value": days}
        ]
    }

# -------------------------
# 1) normal = 50
# -------------------------
normal_names = [
    "John Doe","Alice","Bob","Carol","David","Eve","Frank","Grace","Heidi","Ivan",
    "Judy","Mallory","Niaj","Olivia","Peggy","Rupert","Sybil","Trent","Victor","Walter",
    "Zhang San","Li Si","Wang Wu","Zhao Liu","Sun Qi","Zhou Ba","Wu Jiu","Zheng Shi","Qian Yi","Liu Er",
    "Employee A","Employee B","Employee C","Employee D","HR Demo","Flow User","Test User","Normal User","Demo Starter","Requester One",
    "Requester Two","Requester Three","Requester Four","Alpha User","Beta User","Gamma User","Delta User","Omega User","审批测试","流程用户"
]
normal_days = [
    1,2,3,4,5,6,7,8,9,10,
    3,5,7,2,4,6,8,1,9,12,
    14,15,11,13,5,6,7,8,9,10,
    2,3,4,5,6,7,8,9,10,11,
    12,13,14,15,1,2,3,4,5,6
]

for i, (n, d) in enumerate(zip(normal_names, normal_days)):
    dump(f"seed_ok_{i}.json", mk_normal(n, d))

# -------------------------
# 2) border = 10
# 轻边界：仍然是合法 JSON，且大概率还能被系统接受或至少接近正常
# -------------------------
border_cases = [
    mk_normal("", 7),                       # 空姓名
    mk_normal("A", 7),                      # 极短姓名
    mk_normal(" ", 5),                      # 空格姓名
    mk_normal("张三", 1),                    # 非英文短姓名
    mk_normal("EdgeUser", 0),               # 0 天
    mk_normal("EdgeUser2", 16),             # 稍高于常规范围
    mk_normal("EdgeUser3", 20),             # 更高一点，但不极端
    mk_normal("User-01_Test", 15),          # 带符号
    mk_normal("LongButReasonableEmployeeName_2026", 7),  # 较长但不夸张
    mk_normal("BoundaryCase", 30),          # 上界附近
]

for i, obj in enumerate(border_cases):
    dump(f"seed_border_{i}.json", obj)

# -------------------------
# 3) abnormal = 20
# 明显异常 / 极端异常
# -------------------------
abnormal_cases = [
    {},  # 空对象
    {"processDefinitionKey": ""},
    {"processDefinitionKey": "not_exist"},
    {"processDefinitionKey": "holidayRequest", "variables": []},
    {"processDefinitionKey": "holidayRequest", "variables": {}},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": "John Doe"}, {"name": "nrOfHolidays", "value": "abc"}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee"}, {"name": "nrOfHolidays", "value": 7}]},
    {"variables": [{"name": "employee", "value": "John Doe"}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": None}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": 123, "variables": "bad"},

    # 以下是从旧 border 中迁过来的极端样本
    mk_normal("VeryLongEmployeeName_" * 20, 7),  # 超长字符串
    mk_normal("ExtremeDays", 999),               # 极大值
    mk_normal("NegativeDays", -1),               # 负值
    mk_normal("HugeDays", 9999),                 # 更极端的大值

    # 结构异常
    {
        "processDefinitionKey": "holidayRequest",
        "variables": [
            {"name": "employee", "value": "John Doe"},
            {"name": "nrOfHolidays", "value": {"nested": "bad"}}
        ]
    },
    {
        "processDefinitionKey": "holidayRequest",
        "variables": [
            {"name": "employee", "value": ["bad", "list"]},
            {"name": "nrOfHolidays", "value": 7}
        ]
    },
    {
        "processDefinitionKey": "holidayRequest",
        "variables": [
            {"name": "", "value": "John Doe"},
            {"name": "nrOfHolidays", "value": 7}
        ]
    },
    {
        "processDefinitionKey": None,
        "variables": [
            {"name": "employee", "value": "John Doe"},
            {"name": "nrOfHolidays", "value": 7}
        ]
    },
    {
        "processDefinitionKey": "holidayRequest",
        "variables": [
            {"name": "employee", "value": "John Doe"},
            {"name": "nrOfHolidays", "value": None}
        ]
    },
    {
        "processDefinitionKey": "holidayRequest",
        "variables": "totally_wrong_type"
    },
]

for i, obj in enumerate(abnormal_cases):
    dump(f"seed_bad_{i}.json", obj)

# -------------------------
# 4) 写 manifest
# -------------------------
rows = []
for p in sorted(OUT.glob("seed_ok_*.json")):
    rows.append(f"{p.name},normal")
for p in sorted(OUT.glob("seed_border_*.json")):
    rows.append(f"{p.name},border")
for p in sorted(OUT.glob("seed_bad_*.json")):
    rows.append(f"{p.name},abnormal")

MANIFEST.write_text("\n".join(rows) + "\n", encoding="utf-8")

print(f"[OK] generated dataset in {OUT}")
print("[OK] wrote manifest:", MANIFEST)
print("normal=50 border=10 abnormal=20 total=80")
