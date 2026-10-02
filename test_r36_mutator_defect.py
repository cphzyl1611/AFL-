#!/usr/bin/env python3
"""R36 Step 2: Reproduce the current mutator defect with content_update."""

import sys
import os

sys.path.insert(0, '.')
import nv_json_mutator

# content_update contract: raw UTF-8 text body with text/plain
raw_text_body = '关于系统联调测试的通知\n请各部门按照计划完成接口联调、日志归档和问题闭环。'.encode('utf-8')
full_http = (
    b'PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/abc123/content HTTP/1.1\r\n'
    b'Host: 127.0.0.1\r\n'
    b'Content-Type: text/plain; charset=utf-8\r\n'
    b'Content-Length: ' + str(len(raw_text_body)).encode() + b'\r\n'
    b'\r\n' + raw_text_body
)

# Simulate AFL++ environment
os.environ['NV_CUR_ARM'] = '0'
os.environ['NV_BODY_ONLY_MODE'] = '0'
os.environ['NV_MULTIPART_MODE'] = '0'

print("=" * 70)
print("R36 STEP 2: PRE-REPAIR MUTATOR DEFECT REPRODUCTION")
print("=" * 70)
print()

print("INPUT:")
print(f"  Full HTTP testcase length: {len(full_http)} bytes")
print(f"  Body length: {len(raw_text_body)} bytes")
print(f"  Body content: {raw_text_body[:80]}")
print(f"  Content-Type: text/plain; charset=utf-8")
print()

result = nv_json_mutator.afl_custom_fuzz(None, full_http, None, 10000)

print("OUTPUT:")
print(f"  Mutated testcase length: {len(result)} bytes")
print()

# Parse output
lines = result.decode('utf-8', errors='ignore').splitlines()
body_start = 0
for i, line in enumerate(lines):
    if line.strip() == '':
        body_start = i + 1
        break

if body_start < len(lines):
    output_body = '\n'.join(lines[body_start:])
    print(f"  Output body (first 200 chars): {output_body[:200]}")
    print()

    # Check for JSON wrapping defect
    is_json_wrapped = output_body.strip().startswith('{') and '"raw"' in output_body
    print(f"  Body starts with '{{': {output_body.strip().startswith('{')}")
    print(f"  Body contains '\"raw\"': {'\"raw\"' in output_body}")
    print(f"  JSON-wrapped defect detected: {is_json_wrapped}")
    print()

    # Check Content-Type preservation
    ct_line = [l for l in lines[:body_start] if l.lower().startswith('content-type:')]
    if ct_line:
        print(f"  Output Content-Type: {ct_line[0]}")
        ct_preserved = 'text/plain' in ct_line[0].lower()
        print(f"  Content-Type preserved as text/plain: {ct_preserved}")
    else:
        print("  Content-Type header: MISSING")
        ct_preserved = False
    print()

    print("VERDICT:")
    print(f"  PRE_REPAIR_MUTATOR_INPUT_IS_FULL_HTTP = YES")
    print(f"  PRE_REPAIR_MUTATOR_OUTPUT_IS_FULL_HTTP = YES")
    print(f"  PRE_REPAIR_BODY_BEFORE = RAW_TEXT")
    print(f"  PRE_REPAIR_BODY_AFTER_CLASS = {'JSON_WRAPPED' if is_json_wrapped else 'RAW_TEXT'}")
    print(f"  PRE_REPAIR_BODY_AFTER_IS_RAW_TEXT = {not is_json_wrapped}")
    print(f"  PRE_REPAIR_BODY_AFTER_IS_JSON_WRAPPED = {is_json_wrapped}")
    print(f"  PRE_REPAIR_CONTENT_TYPE_PRESERVED = {ct_preserved}")
    print()

    if is_json_wrapped:
        print("RED TEST CONFIRMED: Current mutator wraps raw text in JSON")
        print("This violates content_update semantic contract.")
        sys.exit(1)
    else:
        print("UNEXPECTED: No defect detected (should see JSON wrapping)")
        sys.exit(2)
