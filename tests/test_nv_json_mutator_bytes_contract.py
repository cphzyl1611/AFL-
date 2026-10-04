#!/usr/bin/env python3
"""
RED TEST — nv_json_mutator.py bytes contract violation

Reproduces the exact failure from Smoke B exec_seq=619:
  AttributeError: 'bytes' object has no attribute 'encode'

When json.dumps() fails in body_only mode, the exception handler
assigns bytes to new_body, then line 247 tries to call .encode().

This test exercises the production mutator function and asserts:
1. No AttributeError when json.dumps fails
2. Returns valid bytes representation
3. Happy path (json.dumps success) still works
"""

import os
import sys
import json

# Add repo root to path to import nv_json_mutator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nv_json_mutator import afl_custom_fuzz


def test_body_only_mode_json_dumps_exception():
    """RED TEST: Reproduce bytes.encode() failure when json.dumps fails."""

    # Set body_only mode
    os.environ["NV_BODY_ONLY_MODE"] = "1"
    os.environ["NV_CUR_ARM"] = "0"

    # Craft input that will cause json.dumps to fail:
    # Create a dict with circular reference or non-serializable object
    # Simpler: provide malformed JSON bytes that parse but contain non-serializable
    # Even simpler: provide bytes that trigger the except clause directly

    # The mutator will:
    # 1. Parse body as JSON (line 228)
    # 2. Mutate obj (line 235-239)
    # 3. Try json.dumps(obj) (line 242)
    # 4. If that fails, assign body (bytes) to new_body (line 244)
    # 5. Try new_body.encode() (line 247) ← FAILS HERE

    # To trigger the except clause, we need obj that json.dumps rejects
    # After mutation, the mutator may create invalid structures

    # Start with valid JSON that will be mutated into non-serializable form
    seed = b'{"value": "test"}'

    # The mutator will randomly mutate this
    # In the worst case, _mutate_field_value may create structures that
    # json.dumps cannot serialize (though rare with basic types)

    # More direct: provide input that's already unparseable
    # When json.loads fails, obj becomes {"raw": body[:128]}
    # That should serialize fine, so not the trigger

    # The real trigger: after mutation, obj may contain types json.dumps rejects
    # But _mutate_field_value only creates str/int/float/bool

    # The actual failure in Smoke B was at exec_seq=619, suggesting
    # it happens after many mutations accumulate

    # For this RED test, we'll directly test the contract:
    # If new_body is bytes, calling .encode() fails

    # Patch json.dumps to force exception:
    import nv_json_mutator
    original_dumps = json.dumps

    def failing_dumps(obj, **kwargs):
        raise ValueError("forced failure")

    # Monkey patch to force exception path
    json.dumps = failing_dumps

    try:
        result = afl_custom_fuzz(None, seed, b"", 4096)

        # RED TEST EXPECTATION: This should FAIL with AttributeError
        # After fix: should return bytes without exception

        assert isinstance(result, (bytes, bytearray)), \
            f"Expected bytes/bytearray, got {type(result)}"

        assert len(result) > 0, "Result should not be empty"

        print("✅ PASS: body_only mode json.dumps exception handled correctly")

    except AttributeError as e:
        if "'bytes' object has no attribute 'encode'" in str(e):
            print("❌ FAIL (EXPECTED): Reproduced bytes.encode() contract violation")
            print(f"   Error: {e}")
            raise AssertionError(f"RED TEST CONFIRMED: {e}")
        else:
            raise
    finally:
        # Restore original json.dumps
        json.dumps = original_dumps
        # Clean up env
        os.environ.pop("NV_BODY_ONLY_MODE", None)
        os.environ.pop("NV_CUR_ARM", None)


def test_body_only_mode_happy_path():
    """GREEN BASELINE: Normal json.dumps success should work."""

    os.environ["NV_BODY_ONLY_MODE"] = "1"
    os.environ["NV_CUR_ARM"] = "0"

    seed = b'{"value": "test", "count": 42}'

    try:
        result = afl_custom_fuzz(None, seed, b"", 4096)

        assert isinstance(result, (bytes, bytearray)), \
            f"Expected bytes/bytearray, got {type(result)}"

        assert len(result) > 0, "Result should not be empty"

        # Should be valid JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict), "Result should be valid JSON dict"

        print("✅ PASS: body_only mode happy path works correctly")

    finally:
        os.environ.pop("NV_BODY_ONLY_MODE", None)
        os.environ.pop("NV_CUR_ARM", None)


def test_http_mode_not_affected():
    """Ensure HTTP mode (body_only=0) is not affected by the fix."""

    os.environ["NV_BODY_ONLY_MODE"] = "0"
    os.environ["NV_CUR_ARM"] = "0"

    seed = b'POST /api/test HTTP/1.1\nContent-Type: application/json\n\n{"value": "test"}'

    try:
        result = afl_custom_fuzz(None, seed, b"", 4096)

        assert isinstance(result, (bytes, bytearray)), \
            f"Expected bytes/bytearray, got {type(result)}"

        assert len(result) > 0, "Result should not be empty"
        assert b"POST" in bytes(result), "HTTP request line should be preserved"

        print("✅ PASS: HTTP mode not affected by bytes contract fix")

    finally:
        os.environ.pop("NV_BODY_ONLY_MODE", None)
        os.environ.pop("NV_CUR_ARM", None)


if __name__ == "__main__":
    print("═" * 60)
    print("RED TEST — nv_json_mutator.py bytes contract")
    print("═" * 60)

    try:
        test_body_only_mode_happy_path()
    except Exception as e:
        print(f"❌ Happy path failed: {e}")
        sys.exit(1)

    try:
        test_http_mode_not_affected()
    except Exception as e:
        print(f"❌ HTTP mode test failed: {e}")
        sys.exit(1)

    try:
        test_body_only_mode_json_dumps_exception()
        print("\n⚠️  RED TEST DID NOT FAIL — Bug may already be fixed")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✅ RED TEST CONFIRMED: {e}")
        print("   This is EXPECTED behavior before fix.")
        sys.exit(0)
