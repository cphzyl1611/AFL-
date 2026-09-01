# AFL++ Python custom mutator: afl_custom_fuzz()
import os, json, random, ctypes

try:
    _LIBC = ctypes.CDLL(None)
    _LIBC.getenv.restype = ctypes.c_char_p
except Exception:
    _LIBC = None

def _live_getenv(name, default=""):
    if _LIBC is not None:
        raw = _LIBC.getenv(name.encode("utf-8"))
        if raw is not None:
            return raw.decode("utf-8", errors="ignore")
    return os.getenv(name, default)

def _get_arm():
    s = _live_getenv("NV_CUR_ARM", "0")
    try:
        a = int(s)
    except:
        a = 0
    return 0 if a < 0 or a > 2 else a

def _scalar_refs(value, refs=None):
    if refs is None:
        refs = []
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                _scalar_refs(child, refs)
            else:
                refs.append((value, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                _scalar_refs(child, refs)
            else:
                refs.append((value, index))
    return refs


def _mutate_field_value(obj):
    refs = _scalar_refs(obj)
    if not refs:
        return obj
    container, key = random.choice(refs)
    value = container[key]
    if isinstance(value, bool):
        container[key] = not value
    elif isinstance(value, str):
        container[key] = value + random.choice(["", "A", "!", "中文", "\\u0000"])
    elif isinstance(value, int):
        container[key] = value ^ (1 << random.randint(0, 5))
    elif isinstance(value, float):
        container[key] = value * random.choice([0, -1, 2, 10])
    else:
        container[key] = "mut"
    return obj

def _metadata_properties(obj):
    if isinstance(obj, dict) and isinstance(obj.get("properties"), dict):
        return obj["properties"]
    return None


def _mutate_boundary(obj):
    properties = _metadata_properties(obj)
    if properties is None:
        return obj
    refs = _scalar_refs(properties)
    if not refs:
        return obj
    container, key = random.choice(refs)
    # Keep the metadata envelope intact while exercising scalar boundaries.
    choices = [
        "", "A", "A" * 4096,
        -1, 0, 1, 2**31 - 1, 2**63 - 1,
        True, False, None,
    ]
    container[key] = random.choice(choices)
    return obj


def _mutate_structure(obj):
    properties = _metadata_properties(obj)
    if properties is None:
        return obj
    # Keep required metadata fields intact; only optional fields may be removed.
    required = {"cm:title", "cm:description"}
    removable = [key for key in properties if key not in required]
    if removable and random.random() < 0.5:
        del properties[random.choice(removable)]
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

def _mutate_multipart(seed_bytes: bytes, arm: int, max_size: int) -> bytes:
    """Mutate filedata while preserving the multipart envelope."""
    header_sep = b"\r\n\r\n" if b"\r\n\r\n" in seed_bytes else b"\n\n"
    if header_sep not in seed_bytes:
        return seed_bytes
    header, body = seed_bytes.split(header_sep, 1)
    content_type = next(
        (line for line in header.split(b"\r\n" if b"\r\n" in header else b"\n")
         if line.lower().startswith(b"content-type:")),
        b"",
    )
    marker = b"boundary="
    start = content_type.lower().find(marker)
    if start < 0:
        return seed_bytes
    boundary = content_type[start + len(marker):].strip().strip(b'"')
    if not boundary:
        return seed_bytes
    delimiter = b"--" + boundary
    parts = body.split(delimiter)
    if len(parts) < 3:
        return seed_bytes
    file_index = None
    original = None
    suffix = b""
    for index, part in enumerate(parts[1:-1], start=1):
        separator = b"\r\n\r\n" if b"\r\n\r\n" in part else b"\n\n"
        if separator not in part:
            continue
        part_header, part_body = part.split(separator, 1)
        if b'name="filedata"' not in part_header:
            continue
        if part_body.endswith(b"\r\n"):
            original, suffix = part_body[:-2], b"\r\n"
        elif part_body.endswith(b"\n"):
            original, suffix = part_body[:-1], b"\n"
        else:
            original, suffix = part_body, b""
        file_index = index
        break
    if file_index is None or original is None:
        return seed_bytes
    if arm == 0:
        mutated = original + random.choice([b"A", b"!", b"0"])
        separator = b"\r\n\r\n" if b"\r\n\r\n" in parts[file_index] else b"\n\n"
        part_header = parts[file_index].split(separator, 1)[0]
        parts[file_index] = part_header + separator + mutated + suffix
        out = header + header_sep + delimiter.join(parts)
    elif arm == 1:
        mutated_boundary = boundary + b"-nv"
        mutated_delimiter = b"--" + mutated_boundary
        mutated_header = header.replace(
            b"boundary=" + boundary,
            b"boundary=" + mutated_boundary,
            1,
        )
        out = mutated_header + header_sep + mutated_delimiter.join(parts)
    else:
        line_sep = b"\r\n" if b"\r\n" in body else b"\n"
        optional = (
            line_sep
            + b'Content-Disposition: form-data; name="description"'
            + line_sep + line_sep
            + b"nv-structure"
            + line_sep
        )
        parts.insert(len(parts) - 1, optional)
        out = header + header_sep + delimiter.join(parts)
    return out[:max_size] if max_size and len(out) > max_size else out


# AFL++ expects these names
def init(seed):
    random.seed(seed)

def fuzz(buf, add_buf, max_size):
    return bytearray(afl_custom_fuzz(None, buf, add_buf, max_size))

def deinit():
    return None

def afl_custom_init(seed):
    random.seed(seed)
    return {}

def afl_custom_fuzz(my_state, buf, add_buf, max_size):
    if _live_getenv("NV_MULTIPART_MODE", "0") == "1":
        arm = _get_arm()
        os.environ["NV_JSON_ARM_USED"] = str(arm)
        return _mutate_multipart(bytes(buf), arm, max_size)

    body_only = _live_getenv("NV_BODY_ONLY_MODE", "0") == "1"
    if body_only:
        first, headers_lines, body = "", [], bytes(buf)
    else:
        first, headers_lines, body = _parse_http(buf)

    if not body.strip():
        body = "{}"
    try:
        obj = json.loads(body)
    except:
        obj = {"raw": body[:128]}

    arm = _get_arm()
    os.environ["NV_JSON_ARM_USED"] = str(arm)
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

    if body_only:
        out = new_body.encode("utf-8", errors="ignore")
    else:
        # 确保 Content-Type 存在（只在 headers_lines 里追加，不改首行）
        has_ct = any(line.lower().startswith("content-type:") for line in headers_lines)
        if not has_ct:
            headers_lines = headers_lines + ["Content-Type: application/json"]
        out = _emit_http(first, headers_lines, new_body)
    if not out:
        out = buf
    return out[:max_size] if max_size and len(out) > max_size else out
