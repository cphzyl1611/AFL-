#!/usr/bin/env python3
"""R36 STEP 6: RED tests for text mutator contract (pre-repair expected failures)."""

import sys
import os
import json

# RED tests must fail with current nv_json_mutator, pass with nv_text_mutator

sys.path.insert(0, '.')


def test_red_a_raw_text_preservation():
    """RED A: Raw text must remain raw text (not JSON-wrapped)."""
    import nv_text_mutator

    raw_body = 'System integration test notification\nPlease complete API integration.'.encode('utf-8')
    full_http = (
        b'PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/abc/content HTTP/1.1\r\n'
        b'Host: 127.0.0.1\r\n'
        b'Content-Type: text/plain; charset=utf-8\r\n'
        b'Content-Length: ' + str(len(raw_body)).encode() + b'\r\n'
        b'\r\n' + raw_body
    )

    os.environ['NV_CUR_ARM'] = '0'
    nv_text_mutator.random.seed(42)
    result = nv_text_mutator.afl_custom_fuzz(None, full_http, None, 10000)

    # Parse output
    result_text = result.decode('utf-8', errors='ignore')
    lines = result_text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == '':
            body_start = i + 1
            break

    output_body = '\n'.join(lines[body_start:]) if body_start < len(lines) else ''

    # Check NOT JSON
    is_json_wrapped = output_body.strip().startswith('{')
    is_valid_utf8 = True
    try:
        output_body.encode('utf-8')
    except:
        is_valid_utf8 = False

    assert not is_json_wrapped, f"RED A FAIL: Body is JSON-wrapped: {output_body[:100]}"
    assert is_valid_utf8, "RED A FAIL: Output is not valid UTF-8"

    print("✓ RED A PASS: Raw text remains raw text (not JSON-wrapped)")
    return True


def test_red_b_http_envelope_preservation():
    """RED B: HTTP envelope must be preserved."""
    import nv_text_mutator

    raw_body = 'Test content for envelope check'.encode('utf-8')
    full_http = (
        b'PUT /api/nodes/xyz/content HTTP/1.1\r\n'
        b'Host: 127.0.0.1\r\n'
        b'Authorization: Bearer token123\r\n'
        b'Content-Type: text/plain; charset=utf-8\r\n'
        b'\r\n' + raw_body
    )

    os.environ['NV_CUR_ARM'] = '1'
    nv_text_mutator.random.seed(123)
    result = nv_text_mutator.afl_custom_fuzz(None, full_http, None, 10000)

    result_text = result.decode('utf-8', errors='ignore')
    lines = result_text.splitlines()

    # Check request line unchanged
    request_line = lines[0] if lines else ''
    assert 'PUT' in request_line, f"RED B FAIL: Request method changed: {request_line}"
    assert '/api/nodes/xyz/content' in request_line, f"RED B FAIL: Path changed: {request_line}"

    # Check Content-Type preserved
    ct_found = False
    for line in lines:
        if line.lower().startswith('content-type:'):
            ct_found = True
            assert 'text/plain' in line.lower(), f"RED B FAIL: Content-Type not text/plain: {line}"
            break
    assert ct_found, "RED B FAIL: Content-Type header missing"

    # Check separator exists
    assert '' in lines, "RED B FAIL: HTTP envelope separator missing"

    print("✓ RED B PASS: HTTP envelope preserved (request line, headers, separator)")
    return True


def test_red_c_actual_body_changes():
    """RED C: Mutation must actually change body (not no-op)."""
    import nv_text_mutator

    raw_body = 'Original test content'.encode('utf-8')
    full_http = (
        b'PUT /api/content HTTP/1.1\r\n'
        b'Host: 127.0.0.1\r\n'
        b'Content-Type: text/plain\r\n'
        b'\r\n' + raw_body
    )

    changes_detected = 0
    for seed in [1, 2, 3, 4, 5]:
        for arm in [0, 1, 2]:
            os.environ['NV_CUR_ARM'] = str(arm)
            nv_text_mutator.random.seed(seed)
            result = nv_text_mutator.afl_custom_fuzz(None, full_http, None, 10000)

            # Extract body
            result_text = result.decode('utf-8', errors='ignore')
            lines = result_text.splitlines()
            body_start = 0
            for i, line in enumerate(lines):
                if line.strip() == '':
                    body_start = i + 1
                    break
            output_body = '\n'.join(lines[body_start:]) if body_start < len(lines) else ''

            if output_body != raw_body.decode('utf-8'):
                changes_detected += 1

    assert changes_detected > 0, f"RED C FAIL: No mutations detected in {5*3} attempts (all no-ops)"
    assert changes_detected >= 10, f"RED C FAIL: Too few mutations: {changes_detected}/15 (likely mostly no-ops)"

    print(f"✓ RED C PASS: Actual mutations detected ({changes_detected}/15 changed)")
    return True


def test_red_d_arm_attribution():
    """RED D: Actual arm usage must be reported via NV_JSON_ARM_USED."""
    import nv_text_mutator

    raw_body = 'Arm attribution test'.encode('utf-8')
    full_http = (
        b'PUT /api/content HTTP/1.1\r\n'
        b'Host: 127.0.0.1\r\n'
        b'Content-Type: text/plain\r\n'
        b'\r\n' + raw_body
    )

    for arm in [0, 1, 2]:
        os.environ.pop('NV_JSON_ARM_USED', None)
        os.environ['NV_CUR_ARM'] = str(arm)
        nv_text_mutator.random.seed(1)

        _ = nv_text_mutator.afl_custom_fuzz(None, full_http, None, 10000)

        reported_arm = os.environ.get('NV_JSON_ARM_USED')
        assert reported_arm is not None, f"RED D FAIL: NV_JSON_ARM_USED not set for arm {arm}"
        assert reported_arm == str(arm), f"RED D FAIL: Arm mismatch, selected={arm} reported={reported_arm}"

    print("✓ RED D PASS: Arm attribution correctly reported via NV_JSON_ARM_USED")
    return True


def test_red_e_metadata_regression_guard():
    """RED E: metadata_update must still use JSON mutation (regression guard)."""
    import nv_json_mutator

    # This is a metadata_update JSON body
    json_body = b'{"properties":{"cm:title":"Test","cm:description":"Desc"}}'
    full_http = (
        b'POST /api/nodes/xyz/metadata HTTP/1.1\r\n'
        b'Host: 127.0.0.1\r\n'
        b'Content-Type: application/json\r\n'
        b'\r\n' + json_body
    )

    os.environ['NV_CUR_ARM'] = '0'
    os.environ.pop('NV_MULTIPART_MODE', None)
    nv_json_mutator.random.seed(42)

    result = nv_json_mutator.afl_custom_fuzz(None, full_http, None, 10000)

    # Extract body
    result_text = result.decode('utf-8', errors='ignore')
    lines = result_text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == '':
            body_start = i + 1
            break
    output_body = '\n'.join(lines[body_start:]) if body_start < len(lines) else ''

    # Should remain valid JSON
    try:
        parsed = json.loads(output_body)
        is_json = True
    except:
        is_json = False

    assert is_json, f"RED E FAIL: metadata_update output is not JSON: {output_body[:100]}"

    # Check Content-Type
    ct_line = [l for l in lines if l.lower().startswith('content-type:')]
    if ct_line:
        assert 'application/json' in ct_line[0].lower(), \
            f"RED E FAIL: metadata_update Content-Type should be application/json: {ct_line[0]}"

    print("✓ RED E PASS: metadata_update still produces JSON (no regression)")
    return True


if __name__ == '__main__':
    print("=" * 70)
    print("R36 STEP 6: RED TESTS (Pre-Repair)")
    print("=" * 70)
    print()

    tests = [
        ("RED A: Raw text preservation", test_red_a_raw_text_preservation),
        ("RED B: HTTP envelope preservation", test_red_b_http_envelope_preservation),
        ("RED C: Actual body changes", test_red_c_actual_body_changes),
        ("RED D: Arm attribution", test_red_d_arm_attribution),
        ("RED E: metadata_update regression guard", test_red_e_metadata_regression_guard),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ {name} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {name} ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()

    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)
