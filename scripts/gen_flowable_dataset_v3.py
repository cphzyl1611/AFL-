#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path.home() / "AFLplusplus"
OUT = ROOT / "in" / "flowable_process_start_dataset_v3"
MANIFEST = ROOT / "model_stage" / "manifests" / "flowable_manifest_130.txt"

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
# 1) normal = 80
# -------------------------
normal_names = [
    "John Doe","Alice","Bob","Carol","David","Eve","Frank","Grace","Heidi","Ivan",
    "Judy","Mallory","Niaj","Olivia","Peggy","Rupert","Sybil","Trent","Victor","Walter",
    "Zhang San","Li Si","Wang Wu","Zhao Liu","Sun Qi","Zhou Ba","Wu Jiu","Zheng Shi","Qian Yi","Liu Er",
    "Employee A","Employee B","Employee C","Employee D","Employee E","Employee F","Employee G","Employee H","Employee I","Employee J",
    "HR Demo","Flow User","Test User","Normal User","Demo Starter","Requester One","Requester Two","Requester Three","Requester Four","Requester Five",
    "Alpha User","Beta User","Gamma User","Delta User","Omega User","审批测试","流程用户","测试人员甲","测试人员乙","测试人员丙",
    "Starter_01","Starter_02","Starter_03","Starter_04","Starter_05","Starter_06","Starter_07","Starter_08","Starter_09","Starter_10",
    "DeptA_User1","DeptA_User2","DeptB_User1","DeptB_User2","DeptC_User1","DeptC_User2","NorthRegionUser","SouthRegionUser","EastRegionUser","WestRegionUser"
]

normal_days = [
    1,2,3,4,5,6,7,8,9,10,
    3,5,7,2,4,6,8,1,9,12,
    14,15,11,13,5,6,7,8,9,10,
    2,3,4,5,6,7,8,9,10,11,
    12,13,14,15,1,2,3,4,5,6,
    7,8,9,10,11,12,13,14,15,1,
    2,3,4,5,6,7,8,9,10,11,
    12,13,14,15,1,2,3,4,5,6
]

for i, (n, d) in enumerate(zip(normal_names, normal_days)):
    dump(f"seed_ok_{i}.json", mk_normal(n, d))

# -------------------------
# 2) border = 20
# 只放轻边界，不放极端异常
# -------------------------
border_cases = [
    mk_normal("", 7),
    mk_normal("A", 7),
    mk_normal(" ", 5),
    mk_normal("张三", 1),
    mk_normal("BoundaryUser1", 0),
    mk_normal("BoundaryUser2", 16),
    mk_normal("BoundaryUser3", 18),
    mk_normal("BoundaryUser4", 20),
    mk_normal("BoundaryUser5", 25),
    mk_normal("BoundaryUser6", 30),

    mk_normal("User-01_Test", 15),
    mk_normal("User_02", 14),
    mk_normal("LongButReasonableEmployeeName_2026", 7),
    mk_normal("LongButStillAcceptable_Requester_Name", 8),
    mk_normal("汉字EnglishMixUser", 6),
    mk_normal("Boundary-Case-Name", 12),
    mk_normal("Boundary.Space User", 10),
    mk_normal("BoundaryUser7", 1),
    mk_normal("BoundaryUser8", 2),
    mk_normal("BoundaryUser9", 15),
]

for i, obj in enumerate(border_cases):
    dump(f"seed_border_{i}.json", obj)

# -------------------------
# 3) abnormal = 30
# 明显错误 / 极端异常
# -------------------------
abnormal_cases = [
    {},
    {"processDefinitionKey": ""},
    {"processDefinitionKey": "not_exist"},
    {"processDefinitionKey": "holidayRequest", "variables": []},
    {"processDefinitionKey": "holidayRequest", "variables": {}},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": "John Doe"}, {"name": "nrOfHolidays", "value": "abc"}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee"}, {"name": "nrOfHolidays", "value": 7}]},
    {"variables": [{"name": "employee", "value": "John Doe"}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": None}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": 123, "variables": "bad"},

    mk_normal("VeryLongEmployeeName_" * 20, 7),
    mk_normal("ExtremeDays", 999),
    mk_normal("NegativeDays", -1),
    mk_normal("HugeDays", 9999),
    mk_normal("OverflowDays", 2147483647),

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

    # 更多结构异常
    {"processDefinitionKey": "holidayRequest", "variables": None},
    {"processDefinitionKey": ["holidayRequest"], "variables": [{"name": "employee", "value": "John Doe"}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": {"k": "holidayRequest"}, "variables": [{"name": "employee", "value": "John Doe"}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": True}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": "John Doe"}, {"name": "nrOfHolidays", "value": False}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": ""}, {"name": "nrOfHolidays", "value": -999}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": " " * 200}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": "X" * 500}, {"name": "nrOfHolidays", "value": 7}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name": "employee", "value": "John Doe"}]},
]

for i, obj in enumerate(abnormal_cases):
    dump(f"seed_bad_{i}.json", obj)

# -------------------------
# 4) manifest
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
print(f"[OK] wrote manifest: {MANIFEST}")
print("normal=80 border=20 abnormal=30 total=130")
