#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path.home() / "AFLplusplus"
OUT = ROOT / "in" / "flowable_process_start_dataset"
OUT.mkdir(parents=True, exist_ok=True)

def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# 1) normal: 30
names = [
    "John Doe","Alice","Bob","Carol","David","Eve","Frank","Grace","Heidi","Ivan",
    "Judy","Mallory","Niaj","Olivia","Peggy","Rupert","Sybil","Trent","Victor","Walter",
    "Zhang San","Li Si","Wang Wu","Zhao Liu","Test User","Normal User","Employee A","Employee B","HR Demo","Flow User"
]
days = [1,2,3,4,5,6,7,8,9,10,3,5,7,2,4,6,8,1,9,12,14,15,11,13,5,6,7,8,9,10]

for i, (n, d) in enumerate(zip(names, days)):
    dump(f"seed_ok_{i}.json", {
        "processDefinitionKey": "holidayRequest",
        "variables": [
            {"name": "employee", "value": n},
            {"name": "nrOfHolidays", "value": d}
        ]
    })

# 2) border: 10
border_cases = [
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":""},{"name":"nrOfHolidays","value":7}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":"A"},{"name":"nrOfHolidays","value":7}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":"VeryLongEmployeeName_" * 8},{"name":"nrOfHolidays","value":7}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":"John Doe"},{"name":"nrOfHolidays","value":0}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":"John Doe"},{"name":"nrOfHolidays","value":30}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":"张三"},{"name":"nrOfHolidays","value":1}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":"John-Doe_Test"},{"name":"nrOfHolidays","value":15}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":" "},{"name":"nrOfHolidays","value":5}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":"EdgeUser"},{"name":"nrOfHolidays","value":999}]},
    {"processDefinitionKey":"holidayRequest","variables":[{"name":"employee","value":"EdgeUser2"},{"name":"nrOfHolidays","value":-1}]}
]
for i, obj in enumerate(border_cases):
    dump(f"seed_border_{i}.json", obj)

# 3) abnormal: 10
abnormal_cases = [
    {},
    {"processDefinitionKey": ""},
    {"processDefinitionKey": "not_exist"},
    {"processDefinitionKey": "holidayRequest", "variables": []},
    {"processDefinitionKey": "holidayRequest", "variables": {}},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name":"employee","value":"John Doe"},{"name":"nrOfHolidays","value":"abc"}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name":"employee"},{"name":"nrOfHolidays","value":7}]},
    {"variables": [{"name":"employee","value":"John Doe"},{"name":"nrOfHolidays","value":7}]},
    {"processDefinitionKey": "holidayRequest", "variables": [{"name":"employee","value":None},{"name":"nrOfHolidays","value":7}]},
    {"processDefinitionKey": 123, "variables": "bad"}
]
for i, obj in enumerate(abnormal_cases):
    dump(f"seed_bad_{i}.json", obj)

print(f"[OK] generated dataset in {OUT}")
print(f"normal=30 border=10 abnormal=10 total=50")
