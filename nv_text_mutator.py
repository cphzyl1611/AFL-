# AFL++ Python custom mutator for raw text content (content_update scenario)
# Preserves full HTTP envelope while mutating plain text body.

import os
import random
import ctypes

try:
    _LIBC = ctypes.CDLL(None)
    _LIBC.getenv.restype = ctypes.c_char_p
except Exception:
    _LIBC = None


def _live_getenv(name, default=""):
    """Read environment variable via libc to get fuzzer-side updates."""
    if _LIBC is not None:
        raw = _LIBC.getenv(name.encode("utf-8"))
        if raw is not None:
            return raw.decode("utf-8", errors="ignore")
    return os.getenv(name, default)


def _get_arm():
    """Read selected mutation arm from fuzzer (0=field_value, 1=boundary, 2=structure)."""
    s = _live_getenv("NV_CUR_ARM", "0")
    try:
        a = int(s)
    except:
        a = 0
    return 0 if a < 0 or a > 2 else a


def _parse_http(seed_bytes: bytes):
    """Parse full HTTP testcase into (request_line, headers_lines, body)."""
    text = seed_bytes.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if not lines:
        return "PUT /content HTTP/1.1", [], ""

    # Find first non-empty line as request line
    i0 = 0
    while i0 < len(lines) and lines[i0].strip() == "":
        i0 += 1
    first = lines[i0].strip() if i0 < len(lines) and lines[i0].strip() else "PUT /content HTTP/1.1"

    # Collect headers until blank line
    headers_lines = []
    i = i0 + 1
    while i < len(lines) and lines[i].strip() != "":
        headers_lines.append(lines[i])
        i += 1

    # Skip blank separator lines
    while i < len(lines) and lines[i].strip() == "":
        i += 1

    # Everything else is body
    body = "\n".join(lines[i:]) if i < len(lines) else ""
    return first, headers_lines, body


def _emit_http(first, headers_lines, body):
    """Reconstruct full HTTP testcase from components."""
    out = [first]
    out.extend(headers_lines)
    out.append("")  # blank separator
    out.append(body)
    return ("\n".join(out)).encode("utf-8", errors="ignore")


def _mutate_text_field_value(text: str) -> str:
    """ARM 0: Character/token-level substitution and insertion."""
    if not text:
        return "mutated"

    lines = text.split("\n")
    if not lines:
        return text + "X"

    # Pick a random line
    line_idx = random.randint(0, len(lines) - 1)
    line = lines[line_idx]

    if not line:
        lines[line_idx] = "X"
        return "\n".join(lines)

    # Pick mutation type
    mutation = random.choice(["substitute", "insert", "append"])

    if mutation == "substitute" and len(line) > 0:
        pos = random.randint(0, len(line) - 1)
        replacement = random.choice(["A", "!", "X", "0", " ", "中"])
        line = line[:pos] + replacement + line[pos+1:]
    elif mutation == "insert" and len(line) > 0:
        pos = random.randint(0, len(line))
        insertion = random.choice(["!", "test", " ", "中文"])
        line = line[:pos] + insertion + line[pos:]
    else:  # append
        line += random.choice(["!", "X", " extra", "中"])

    lines[line_idx] = line
    return "\n".join(lines)


def _mutate_text_boundary(text: str) -> str:
    """ARM 1: Length and character boundary testing."""
    if not text:
        # Empty boundary case
        return ""

    lines = text.split("\n")
    if not lines:
        return text

    boundary_type = random.choice(["empty_line", "long_line", "special_chars", "truncate", "extend"])

    if boundary_type == "empty_line":
        # Insert or replace with empty line
        idx = random.randint(0, len(lines))
        lines.insert(idx, "")
    elif boundary_type == "long_line":
        # Create very long line
        idx = random.randint(0, len(lines) - 1) if lines else 0
        if idx < len(lines):
            lines[idx] = lines[idx] + ("A" * random.choice([100, 1000, 4096]))
    elif boundary_type == "special_chars":
        # Insert special/control characters
        idx = random.randint(0, len(lines) - 1) if lines else 0
        if idx < len(lines):
            special = random.choice(["\t", "\r", "\x00", "￿", "\\u0000"])
            lines[idx] = lines[idx] + special
    elif boundary_type == "truncate":
        # Truncate to boundary length
        length = random.choice([0, 1, 10])
        return text[:length]
    else:  # extend
        # Extend with repetition
        return text + text[:random.randint(1, min(100, len(text)))]

    return "\n".join(lines)


def _mutate_text_structure(text: str) -> str:
    """ARM 2: Line-level structural mutations."""
    if not text:
        return "new line"

    lines = text.split("\n")
    if len(lines) <= 1:
        # Add a new line
        return text + "\nnew line"

    mutation = random.choice(["delete_line", "duplicate_line", "reorder", "insert_line"])

    if mutation == "delete_line":
        idx = random.randint(0, len(lines) - 1)
        del lines[idx]
    elif mutation == "duplicate_line":
        idx = random.randint(0, len(lines) - 1)
        lines.insert(idx + 1, lines[idx])
    elif mutation == "reorder" and len(lines) >= 2:
        # Swap two lines
        idx1 = random.randint(0, len(lines) - 1)
        idx2 = random.randint(0, len(lines) - 1)
        lines[idx1], lines[idx2] = lines[idx2], lines[idx1]
    else:  # insert_line
        idx = random.randint(0, len(lines))
        lines.insert(idx, "inserted line")

    return "\n".join(lines)


def afl_custom_fuzz(my_state, buf, add_buf, max_size):
    """Main AFL++ custom mutator entry point."""
    # Parse full HTTP envelope
    first, headers_lines, body = _parse_http(buf)

    # Get selected arm from fuzzer
    arm = _get_arm()

    # Confirm actual arm used (for MAB feedback)
    os.environ["NV_JSON_ARM_USED"] = str(arm)

    # Apply text mutation based on arm
    if arm == 0:
        mutated_body = _mutate_text_field_value(body)
    elif arm == 1:
        mutated_body = _mutate_text_boundary(body)
    else:  # arm == 2
        mutated_body = _mutate_text_structure(body)

    # Ensure Content-Type: text/plain is present
    has_ct = any(line.lower().startswith("content-type:") for line in headers_lines)
    if not has_ct:
        headers_lines = headers_lines + ["Content-Type: text/plain; charset=utf-8"]

    # Reconstruct full HTTP testcase
    out = _emit_http(first, headers_lines, mutated_body)

    # Respect max_size constraint
    if not out:
        out = buf
    return out[:max_size] if max_size and len(out) > max_size else out


# AFL++ standard interface
def init(seed):
    random.seed(seed)


def fuzz(buf, add_buf, max_size):
    return bytearray(afl_custom_fuzz(None, buf, add_buf, max_size))


def deinit():
    return None


def afl_custom_init(seed):
    random.seed(seed)
    return {}
