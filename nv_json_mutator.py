# AFL++ Python custom mutator: afl_custom_fuzz()
import os, json, random

def _get_arm():
    s = os.getenv("NV_CUR_ARM", "0")
    try:
        a = int(s)
    except:
        a = 0
    return 0 if a < 0 or a > 2 else a

def _mutate_field_value(obj):
    # 找一个 key，轻量替换值
    keys = [k for k in obj.keys()] if isinstance(obj, dict) else []
    if not keys:
        return obj
    k = random.choice(keys)
    v = obj[k]
    if isinstance(v, str):
        obj[k] = v + random.choice(["", "A", "!", "中文", "\\u0000"])
    elif isinstance(v, int):
        obj[k] = v ^ (1 << random.randint(0, 5))
    elif isinstance(v, float):
        obj[k] = v * random.choice([0, -1, 2, 10])
    elif isinstance(v, bool):
        obj[k] = (not v)
    else:
        obj[k] = "mut"
    return obj

def _mutate_boundary(obj):
    keys = [k for k in obj.keys()] if isinstance(obj, dict) else []
    if not keys:
        return obj
    k = random.choice(keys)
    # 边界值集合
    choices = [
        "", "A"*0, "A"*1, "A"*4096,
        -1, 0, 1, 2**31-1, 2**63-1,
        True, False, None
    ]
    obj[k] = random.choice(choices)
    return obj

def _mutate_structure(obj):
    if isinstance(obj, dict):
        # 50% 增字段，50% 删字段
        if obj and random.random() < 0.5:
            del obj[random.choice(list(obj.keys()))]
        else:
            obj[random.choice(["extra","padding","meta","x","y"])] = {"n": random.randint(0,999), "s":"x"*random.randint(0,64)}
    elif isinstance(obj, list):
        if random.random() < 0.5 and obj:
            obj.pop(random.randrange(len(obj)))
        else:
            obj.append({"k":"v","n":random.randint(0,999)})
    return obj

def _parse_http(seed_bytes: bytes):
    text = seed_bytes.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if not lines:
        return "POST /api/doc/create", [], ""

    # 找到第一条非空行作为首行（避免前面空行）
    i0 = 0
    while i0 < len(lines) and lines[i0].strip() == "":
        i0 += 1
    first = lines[i0].strip() if i0 < len(lines) and lines[i0].strip() else "POST /api/doc/create"

    # headers 保留原样（用 list 存）
    headers_lines = []
    i = i0 + 1
    while i < len(lines) and lines[i].strip() != "":
        headers_lines.append(lines[i])
        i += 1

    while i < len(lines) and lines[i].strip() == "":
        i += 1

    body = "\n".join(lines[i:]) if i < len(lines) else ""
    return first, headers_lines, body

def _emit_http(first, headers_lines, body):
    out = [first]
    out.extend(headers_lines)
    out.append("")  # blank line
    out.append(body)
    return ("\n".join(out)).encode("utf-8", errors="ignore")

# AFL++ expects these names
def afl_custom_init(seed):
    random.seed(seed)
    return {}

def afl_custom_fuzz(my_state, buf, add_buf, max_size):
    first, headers_lines, body = _parse_http(buf)

    if not body.strip():
        body = "{}"
    try:
        obj = json.loads(body)
    except:
        obj = {"raw": body[:128]}

    arm = _get_arm()
    if arm == 0:
        obj = _mutate_field_value(obj)
    elif arm == 1:
        obj = _mutate_boundary(obj)
    else:
        obj = _mutate_structure(obj)

    try:
        new_body = json.dumps(obj, ensure_ascii=False)
    except:
        new_body = body

    # 确保 Content-Type 存在（只在 headers_lines 里追加，不改首行）
    has_ct = any(line.lower().startswith("content-type:") for line in headers_lines)
    if not has_ct:
        headers_lines = headers_lines + ["Content-Type: application/json"]

    out = _emit_http(first, headers_lines, new_body)
    if not out:
        out = buf
    return out[:max_size] if max_size and len(out) > max_size else out