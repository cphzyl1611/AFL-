#!/usr/bin/env python3
"""
R29 STEP 6: Local deterministic reproduction of validity_endpoint bug.

This script proves:
1. Current code writes task.json WITHOUT validity_endpoint
2. AFL reads task.json and sets validity_endpoint = NULL
3. AFL skips all scorer invocations when validity_endpoint is NULL

The reproduction does NOT run a full AFL campaign (respecting R29 boundaries).
Instead, it:
- Creates a minimal run directory structure
- Calls build_task_payload() with validity_backend set
- Writes task.json
- Verifies validity_endpoint field is missing
- Simulates scorer startup
- Shows what the fixed task.json should contain

NO real campaign is authorized. This is diagnostic code only.
"""

import json
import sys
import tempfile
from pathlib import Path

# Add repo root to path for imports
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_alfresco_bounded_feedback import build_task_payload


def reproduce_bug():
    """Reproduce the validity_endpoint missing bug."""

    print("=" * 70)
    print("R29 STEP 6: VALIDITY_ENDPOINT BUG REPRODUCTION")
    print("=" * 70)
    print()

    # Create minimal directory structure
    with tempfile.TemporaryDirectory(prefix="r29_repro_") as tmpdir:
        run_root = Path(tmpdir)
        seed_dir = run_root / "seed_input"
        seed_dir.mkdir()

        # Create minimal seed file
        seed_file = seed_dir / "seed.http"
        seed_file.write_text('{"test": "data"}')

        print(f"Created test directory: {run_root}")
        print()

        # STEP 1: Call build_task_payload with validity_backend
        print("STEP 1: Call build_task_payload with validity_backend")
        print("-" * 70)

        task = build_task_payload(
            seed_dir,
            max_test_cases=3,
            time_budget=30,
            scenario="content_update",
            validity_backend="sefanogan_es_reference",  # Model comparison mode!
        )

        print(f"validity_backend argument: 'sefanogan_es_reference'")
        print(f"Returned task dict keys: {sorted(task.keys())}")
        print()

        # STEP 2: Check if validity_endpoint is in the payload
        print("STEP 2: Check for validity_endpoint field")
        print("-" * 70)

        if "validity_endpoint" in task:
            print("✓ validity_endpoint PRESENT in task dict")
            print(f"  Value: {task['validity_endpoint']}")
        else:
            print("✗ validity_endpoint MISSING from task dict")
            print("  BUG CONFIRMED: build_task_payload() does not populate validity_endpoint")
        print()

        # STEP 3: Write task.json as the runner does
        print("STEP 3: Write task.json (as runner does)")
        print("-" * 70)

        task_json_path = run_root / "task.json"
        task_json_path.write_text(
            json.dumps(task, ensure_ascii=False, sort_keys=True),
            encoding="utf-8"
        )

        print(f"Wrote: {task_json_path}")
        print()

        # STEP 4: Read back and display
        print("STEP 4: Read task.json and verify")
        print("-" * 70)

        written_task = json.loads(task_json_path.read_text(encoding="utf-8"))
        print("task.json contents:")
        print(json.dumps(written_task, indent=2, sort_keys=True))
        print()

        # STEP 5: Simulate scorer startup
        print("STEP 5: Simulate scorer startup (post-task.json)")
        print("-" * 70)

        scorer_socket = run_root / "scorer.sock"
        scorer_endpoint = f"unix://{scorer_socket}"

        print(f"Scorer socket would be created at: {scorer_socket}")
        print(f"Scorer endpoint string: {scorer_endpoint}")
        print()

        # STEP 6: Show what AFL expects
        print("STEP 6: What AFL expects to read from task.json")
        print("-" * 70)

        print("AFL code (src/afl-fuzz.c:378):")
        print('  const char *vep = json_get_string(j, "validity_endpoint");')
        print()
        print("AFL code (src/afl-fuzz.c:449-450):")
        print("  if (vep && *vep) {")
        print("    afl->nv_task.validity_endpoint = ck_strdup(vep);")
        print("  }")
        print()
        print("AFL code (src/afl-fuzz-run.c:783-784):")
        print("  const char *ep = afl->nv_task.validity_endpoint;")
        print("  if (!ep || !*ep) return 0.0;  // Skip scorer!")
        print()

        if "validity_endpoint" in written_task:
            print(f"✓ AFL will read: validity_endpoint = '{written_task['validity_endpoint']}'")
            print("✓ AFL will invoke scorer for each execution")
        else:
            print("✗ AFL will read: validity_endpoint = NULL (field missing)")
            print("✗ AFL will skip scorer for ALL executions")
            print("✗ Result: ZERO_SCORER_INVOCATIONS")
        print()

        # STEP 7: Show the fix
        print("STEP 7: Demonstrate the required fix")
        print("-" * 70)

        print("After scorer_manager.start(), runner must add:")
        print()
        print("  # Re-read task.json")
        print("  task = json.loads(layout['task'].read_text(encoding='utf-8'))")
        print()
        print("  # Add scorer endpoint")
        print(f"  task['validity_endpoint'] = 'unix://{scorer_socket}'")
        print()
        print("  # Write updated task.json")
        print("  layout['task'].write_text(")
        print("    json.dumps(task, ensure_ascii=False, sort_keys=True),")
        print("    encoding='utf-8'")
        print("  )")
        print()

        # STEP 8: Show fixed task.json
        print("STEP 8: Fixed task.json (with validity_endpoint)")
        print("-" * 70)

        fixed_task = dict(written_task)
        fixed_task["validity_endpoint"] = scorer_endpoint

        print(json.dumps(fixed_task, indent=2, sort_keys=True))
        print()

        # STEP 9: Summary
        print("=" * 70)
        print("REPRODUCTION SUMMARY")
        print("=" * 70)

        if "validity_endpoint" not in written_task:
            print("✗ BUG CONFIRMED:")
            print("  - build_task_payload() receives validity_backend")
            print("  - But does NOT populate validity_endpoint in returned dict")
            print("  - task.json written without validity_endpoint field")
            print("  - AFL reads NULL and skips all scorer invocations")
            print()
            print("✓ FIX IDENTIFIED:")
            print("  - After scorer starts, update task.json with validity_endpoint")
            print("  - Location: scripts/run_alfresco_bounded_feedback.py after line 3179")
            print("  - Estimated fix: 7 lines of code")
            return 1  # Exit code 1 = bug confirmed
        else:
            print("✓ NO BUG DETECTED:")
            print("  - validity_endpoint present in task.json")
            print("  - AFL will be able to contact scorer")
            return 0  # Exit code 0 = bug not present


if __name__ == "__main__":
    sys.exit(reproduce_bug())
