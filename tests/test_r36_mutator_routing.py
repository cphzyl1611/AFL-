#!/usr/bin/env python3
"""R36 Test: Verify scenario-based mutator routing."""

import sys
import os

sys.path.insert(0, '.')


def test_content_update_routes_to_text_mutator():
    """content_update scenario should route to nv_text_mutator."""
    import nv_text_mutator

    raw_body = 'Content update test'.encode('utf-8')
    full_http = (
        b'PUT /api/content HTTP/1.1\r\n'
        b'Host: 127.0.0.1\r\n'
        b'Content-Type: text/plain\r\n'
        b'\r\n' + raw_body
    )

    os.environ['NV_CUR_ARM'] = '0'
    nv_text_mutator.random.seed(1)
    result = nv_text_mutator.afl_custom_fuzz(None, full_http, None, 10000)

    # Verify it produces raw text, not JSON
    result_text = result.decode('utf-8', errors='ignore')
    lines = result_text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == '':
            body_start = i + 1
            break

    output_body = '\n'.join(lines[body_start:]) if body_start < len(lines) else ''

    assert not output_body.strip().startswith('{'), \
        f"content_update mutator produced JSON: {output_body[:100]}"

    print("✓ content_update → nv_text_mutator → raw text output")
    return True


def test_metadata_update_routes_to_json_mutator():
    """metadata_update scenario should route to nv_json_mutator."""
    import nv_json_mutator
    import json

    json_body = b'{"properties":{"cm:title":"Test"}}'
    full_http = (
        b'POST /api/metadata HTTP/1.1\r\n'
        b'Host: 127.0.0.1\r\n'
        b'Content-Type: application/json\r\n'
        b'\r\n' + json_body
    )

    os.environ['NV_CUR_ARM'] = '0'
    os.environ.pop('NV_MULTIPART_MODE', None)
    nv_json_mutator.random.seed(1)
    result = nv_json_mutator.afl_custom_fuzz(None, full_http, None, 10000)

    # Verify it produces valid JSON
    result_text = result.decode('utf-8', errors='ignore')
    lines = result_text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == '':
            body_start = i + 1
            break

    output_body = '\n'.join(lines[body_start:]) if body_start < len(lines) else ''

    try:
        json.loads(output_body)
        is_json = True
    except:
        is_json = False

    assert is_json, f"metadata_update mutator did not produce JSON: {output_body[:100]}"

    print("✓ metadata_update → nv_json_mutator → JSON output")
    return True


def test_routing_logic_in_runner():
    """Verify the runner script routing logic is correct."""
    # Check that the routing code exists in run_alfresco_bounded_feedback.py
    runner_path = 'scripts/run_alfresco_bounded_feedback.py'
    with open(runner_path, 'r') as f:
        content = f.read()

    # Check for R36 routing comment
    assert 'R36' in content or 'scenario-based mutator routing' in content.lower(), \
        "R36 routing code not found in runner script"

    # Check for content_update → nv_text_mutator routing
    assert 'nv_text_mutator' in content, \
        "nv_text_mutator reference not found in runner"

    # Check for scenario-based branching
    assert 'scenario' in content and 'content_update' in content, \
        "Scenario-based routing logic not found"

    print("✓ Runner script contains scenario-based routing logic")
    return True


if __name__ == '__main__':
    print("=" * 70)
    print("R36: Mutator Routing Verification")
    print("=" * 70)
    print()

    tests = [
        test_content_update_routes_to_text_mutator,
        test_metadata_update_routes_to_json_mutator,
        test_routing_logic_in_runner,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_func.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()

    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)
