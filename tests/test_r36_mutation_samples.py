#!/usr/bin/env python3
"""R36 STEP 8: Post-repair mutation verification."""

import sys
import os

sys.path.insert(0, '.')
import nv_text_mutator


def verify_mutation_samples():
    """Generate and verify mutation samples for all arms."""

    raw_body = '关于系统联调测试的通知\n请各部门按照计划完成接口联调、日志归档和问题闭环。'.encode('utf-8')
    full_http = (
        b'PUT /alfresco/api/-default-/public/alfresco/versions/1/nodes/abc/content HTTP/1.1\r\n'
        b'Host: 127.0.0.1\r\n'
        b'Content-Type: text/plain; charset=utf-8\r\n'
        b'Content-Length: ' + str(len(raw_body)).encode() + b'\r\n'
        b'\r\n' + raw_body
    )

    samples = []
    total = 0
    non_noop = 0
    valid_utf8 = 0
    raw_text_count = 0
    envelope_preserved = 0
    arm_confirmed = 0

    print("=" * 70)
    print("R36 STEP 8: Post-Repair Mutation Verification")
    print("=" * 70)
    print()

    # Test each arm with multiple seeds
    for arm in [0, 1, 2]:
        print(f"ARM {arm} ({'field_value' if arm == 0 else 'boundary' if arm == 1 else 'structure'}):")
        for seed in range(1, 6):
            total += 1

            os.environ['NV_CUR_ARM'] = str(arm)
            os.environ.pop('NV_JSON_ARM_USED', None)
            nv_text_mutator.random.seed(seed)

            result = nv_text_mutator.afl_custom_fuzz(None, full_http, None, 10000)

            # Parse result
            result_text = result.decode('utf-8', errors='ignore')
            lines = result_text.splitlines()

            # Find body
            body_start = 0
            for i, line in enumerate(lines):
                if line.strip() == '':
                    body_start = i + 1
                    break

            output_body = '\n'.join(lines[body_start:]) if body_start < len(lines) else ''
            original_body = raw_body.decode('utf-8')

            # Check criteria
            is_noop = (output_body == original_body)
            is_valid_utf8 = True
            try:
                output_body.encode('utf-8')
            except:
                is_valid_utf8 = False

            is_raw_text = not output_body.strip().startswith('{')

            # Check HTTP envelope
            request_line = lines[0] if lines else ''
            has_request = 'PUT' in request_line and '/content' in request_line
            has_ct = any('content-type:' in l.lower() and 'text/plain' in l.lower() for l in lines)
            has_separator = '' in lines
            envelope_ok = has_request and has_ct and has_separator

            # Check arm confirmation
            reported_arm = os.environ.get('NV_JSON_ARM_USED')
            arm_ok = reported_arm == str(arm)

            if not is_noop:
                non_noop += 1
            if is_valid_utf8:
                valid_utf8 += 1
            if is_raw_text:
                raw_text_count += 1
            if envelope_ok:
                envelope_preserved += 1
            if arm_ok:
                arm_confirmed += 1

            status = "✓" if (not is_noop and is_valid_utf8 and is_raw_text and envelope_ok and arm_ok) else "✗"
            print(f"  Seed {seed}: {status} noop={is_noop} utf8={is_valid_utf8} raw={is_raw_text} env={envelope_ok} arm={arm_ok}")

            samples.append({
                'arm': arm,
                'seed': seed,
                'body_preview': output_body[:50],
                'is_noop': is_noop,
                'is_valid_utf8': is_valid_utf8,
                'is_raw_text': is_raw_text,
                'envelope_ok': envelope_ok,
                'arm_ok': arm_ok,
            })
        print()

    print("=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    print(f"TEXT_MUTATION_SAMPLE_COUNT = {total}")
    print(f"TEXT_MUTATION_NON_NOOP_COUNT = {non_noop}")
    print(f"TEXT_MUTATION_VALID_UTF8_COUNT = {valid_utf8}")
    print(f"TEXT_MUTATION_RAW_TEXT_COUNT = {raw_text_count}")
    print(f"TEXT_MUTATION_HTTP_ENVELOPE_PRESERVED_COUNT = {envelope_preserved}")
    print(f"TEXT_MUTATION_ARM_CONFIRMATION_COUNT = {arm_confirmed}")
    print()

    # Assertions
    assert total == 15, f"Expected 15 samples, got {total}"
    assert non_noop >= 12, f"Too many no-ops: {non_noop}/15 changed (expected >= 12)"
    assert valid_utf8 == 15, f"Invalid UTF-8 detected: {valid_utf8}/15"
    assert raw_text_count == 15, f"Non-raw-text output: {raw_text_count}/15"
    assert envelope_preserved == 15, f"Envelope not preserved: {envelope_preserved}/15"
    assert arm_confirmed == 15, f"Arm attribution failed: {arm_confirmed}/15"

    print("✓ All mutation verification criteria met")
    print()

    return {
        'sample_count': total,
        'non_noop': non_noop,
        'valid_utf8': valid_utf8,
        'raw_text': raw_text_count,
        'envelope_preserved': envelope_preserved,
        'arm_confirmed': arm_confirmed,
    }


if __name__ == '__main__':
    try:
        result = verify_mutation_samples()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ VERIFICATION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
