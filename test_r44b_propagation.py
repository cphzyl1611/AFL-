#!/usr/bin/env python3
"""
Test R44B AFL_TARGET_ENV propagation with actual AFL++ binary.
"""
import os
import subprocess
import sys
import tempfile
import json

# Create a minimal test harness that just prints its environment
test_harness = '''#!/usr/bin/env python3
import os
import sys
import json

# Print ALFRESCO_USER and ALFRESCO_PASS if they exist
result = {
    "ALFRESCO_USER": os.getenv("ALFRESCO_USER", "NOT_SET"),
    "ALFRESCO_PASS": os.getenv("ALFRESCO_PASS", "NOT_SET"),
}
print(json.dumps(result), file=sys.stderr)
sys.exit(0)
'''

with tempfile.TemporaryDirectory() as tmpdir:
    # Write test harness
    harness_path = os.path.join(tmpdir, "test_harness.py")
    with open(harness_path, "w") as f:
        f.write(test_harness)
    os.chmod(harness_path, 0o755)

    # Create minimal input
    in_dir = os.path.join(tmpdir, "in")
    os.makedirs(in_dir)
    with open(os.path.join(in_dir, "seed"), "wb") as f:
        f.write(b"test")

    # Create output dir
    out_dir = os.path.join(tmpdir, "out")

    # Test R44B format
    import shlex
    test_user = "test_user_value"
    test_pass = "test_pass_with spaces"

    user_quoted = shlex.quote(test_user)
    pass_quoted = shlex.quote(test_pass)
    afl_target_env = f"ALFRESCO_USER={user_quoted} ALFRESCO_PASS={pass_quoted}"

    print(f"AFL_TARGET_ENV format: {afl_target_env}")

    # Run AFL++ with this format
    env = os.environ.copy()
    env["AFL_TARGET_ENV"] = afl_target_env
    env["AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES"] = "1"
    env["AFL_SKIP_CPUFREQ"] = "1"
    env["AFL_NO_UI"] = "1"

    cmd = [
        "./afl-fuzz",
        "-i", in_dir,
        "-o", out_dir,
        "-V", "1",  # 1 second timeout
        "--",
        sys.executable, harness_path
    ]

    print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd="/home/dministrator/AFLplusplus-phase2-ae-snapshot-recovery",
            capture_output=True,
            timeout=5,
            text=True
        )
    except subprocess.TimeoutExpired as e:
        print("AFL++ timed out (expected), checking stderr output...")
        stderr_output = e.stderr if hasattr(e, 'stderr') else ""

        # Look for the JSON output from our test harness
        if '{"ALFRESCO_USER":' in stderr_output:
            import re
            match = re.search(r'\{"ALFRESCO_USER":.*?\}', stderr_output)
            if match:
                received = json.loads(match.group(0))
                print(f"\nHarness received:")
                print(f"  ALFRESCO_USER: {received['ALFRESCO_USER']}")
                print(f"  ALFRESCO_PASS: {received['ALFRESCO_PASS']}")

                if received['ALFRESCO_USER'] == test_user and received['ALFRESCO_PASS'] == test_pass:
                    print("\n✓ R44B PROPAGATION: PASS")
                    print("✓ Credentials successfully propagated through AFL_TARGET_ENV")
                    sys.exit(0)
                else:
                    print("\n✗ R44B PROPAGATION: FAIL")
                    print(f"✗ Expected user={test_user}, pass={test_pass}")
                    print(f"✗ Got user={received['ALFRESCO_USER']}, pass={received['ALFRESCO_PASS']}")
                    sys.exit(1)

        print("\n✗ Could not find harness output in AFL++ stderr")
        print("AFL++ stderr snippet:")
        print(stderr_output[:500] if stderr_output else "(empty)")
        sys.exit(1)

    print(f"AFL++ exited with code {result.returncode}")
    print("Stderr:", result.stderr[:500])
    sys.exit(1)
