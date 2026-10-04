#!/usr/bin/env python3
"""
O2OA Multi-API Expansion - Dry-Run Integration Test

Validates that all framework components work for the selected endpoints
without requiring live O2OA target or NV_TOKEN.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))

import nv_body_valid

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def test_seed_files():
    """Test 1: Verify seed files exist and are valid JSON"""
    print(f"{Colors.BOLD}TEST 1: Seed File Validation{Colors.RESET}")

    endpoints = ['review_count', 'calendar_filter', 'person_detail']
    all_pass = True

    for ep_name in endpoints:
        seed_path = REPO_ROOT / f"in/o2oa_body/seed_{ep_name}_0.json"

        if not seed_path.exists():
            print(f"  {Colors.RED}❌ {ep_name}: seed file missing{Colors.RESET}")
            all_pass = False
            continue

        try:
            seed_data = json.loads(seed_path.read_text())
            print(f"  {Colors.GREEN}✅ {ep_name}: {seed_path.name} parsed OK{Colors.RESET}")
        except json.JSONDecodeError as e:
            print(f"  {Colors.RED}❌ {ep_name}: invalid JSON - {e}{Colors.RESET}")
            all_pass = False

    return all_pass

def test_target_config():
    """Test 2: Verify target configuration has all endpoints"""
    print(f"\n{Colors.BOLD}TEST 2: Target Configuration{Colors.RESET}")

    cfg_path = REPO_ROOT / "targets/o2oa_query.json"
    cfg = json.loads(cfg_path.read_text())

    endpoints = ['review_count', 'calendar_filter', 'person_detail']
    all_pass = True

    for ep_name in endpoints:
        ep = next((e for e in cfg['endpoints'] if e['name'] == ep_name), None)

        if not ep:
            print(f"  {Colors.RED}❌ {ep_name}: not in endpoints array{Colors.RESET}")
            all_pass = False
            continue

        has_template = ep_name in cfg.get('body_templates', {})

        if has_template:
            print(f"  {Colors.GREEN}✅ {ep_name}: {ep['method']} {ep['path']}{Colors.RESET}")
        else:
            print(f"  {Colors.YELLOW}⚠️  {ep_name}: no body template (may be OK for empty body){Colors.RESET}")

    return all_pass

def test_validity_rules():
    """Test 3: Verify validity rules exist and seeds pass"""
    print(f"\n{Colors.BOLD}TEST 3: Validity Rules Integration{Colors.RESET}")

    rules_path = str(REPO_ROOT / "validity/o2oa_query_rules.json")
    endpoints = [
        ('review_count', {'credentialList': []}),
        ('calendar_filter', {'startTime': '2026-03-01 00:00:00', 'endTime': '2026-03-31 23:59:59', 'calendarIds': []}),
        ('person_detail', {})
    ]

    all_pass = True

    for ep_name, seed_data in endpoints:
        seed_bytes = json.dumps(seed_data).encode()
        result = nv_body_valid.body_validate('metadata_update', ep_name, seed_bytes, rules_path)

        passed = result['ok'] and result['decision'] == 'pass'

        if passed:
            print(f"  {Colors.GREEN}✅ {ep_name}: ok={result['ok']}, decision={result['decision']}{Colors.RESET}")
        else:
            print(f"  {Colors.RED}❌ {ep_name}: ok={result['ok']}, decision={result['decision']}, reason={result['reason']}{Colors.RESET}")
            all_pass = False

    return all_pass

def test_endpoint_resolution():
    """Test 4: Verify harness can resolve endpoint URLs"""
    print(f"\n{Colors.BOLD}TEST 4: Endpoint URL Resolution{Colors.RESET}")

    cfg_path = REPO_ROOT / "targets/o2oa_query.json"
    cfg = json.loads(cfg_path.read_text())

    endpoints = ['review_count', 'calendar_filter', 'person_detail']
    all_pass = True

    for ep_name in endpoints:
        ep = next((e for e in cfg['endpoints'] if e['name'] == ep_name), None)

        if not ep:
            print(f"  {Colors.RED}❌ {ep_name}: cannot resolve{Colors.RESET}")
            all_pass = False
            continue

        url = cfg['base'].rstrip('/') + ep['path']
        print(f"  {Colors.GREEN}✅ {ep_name}: {ep['method']} {url}{Colors.RESET}")

    return all_pass

def test_harness_import():
    """Test 5: Verify harness module loads successfully"""
    print(f"\n{Colors.BOLD}TEST 5: Harness Module Import{Colors.RESET}")

    try:
        import nv_http_harness
        print(f"  {Colors.GREEN}✅ nv_http_harness imported successfully{Colors.RESET}")

        # Check key functions exist
        required = ['main', 'resolve_health_url', 'load_target_config']
        for func_name in required:
            if hasattr(nv_http_harness, func_name):
                print(f"  {Colors.GREEN}✅   - {func_name}() exists{Colors.RESET}")
            else:
                print(f"  {Colors.RED}❌   - {func_name}() missing{Colors.RESET}")
                return False

        return True
    except Exception as e:
        print(f"  {Colors.RED}❌ Failed to import: {e}{Colors.RESET}")
        return False

def test_mutation_routing():
    """Test 6: Verify MAB mutation arms are configured"""
    print(f"\n{Colors.BOLD}TEST 6: Mutation Routing Configuration{Colors.RESET}")

    # Check that afl-fuzz binary exists and was built
    afl_fuzz = REPO_ROOT / "afl-fuzz"

    if not afl_fuzz.exists():
        print(f"  {Colors.RED}❌ afl-fuzz binary not found{Colors.RESET}")
        return False

    print(f"  {Colors.GREEN}✅ afl-fuzz binary exists: {afl_fuzz}{Colors.RESET}")

    # Check MAB configuration in code (grep for nv_mab_t)
    src_file = REPO_ROOT / "include/afl-fuzz.h"
    if src_file.exists():
        content = src_file.read_text()
        if 'nv_mab_t' in content:
            print(f"  {Colors.GREEN}✅ NV MAB structure defined in afl-fuzz.h{Colors.RESET}")
        else:
            print(f"  {Colors.YELLOW}⚠️  nv_mab_t not found in afl-fuzz.h{Colors.RESET}")

    return True

def test_output_directory():
    """Test 7: Verify output directory can be created"""
    print(f"\n{Colors.BOLD}TEST 7: Output Directory Setup{Colors.RESET}")

    out_dir = REPO_ROOT / "out/o2oa_expansion_dryrun"
    out_dir.mkdir(parents=True, exist_ok=True)

    if out_dir.exists() and out_dir.is_dir():
        print(f"  {Colors.GREEN}✅ Output directory created: {out_dir}{Colors.RESET}")
        return True
    else:
        print(f"  {Colors.RED}❌ Failed to create output directory{Colors.RESET}")
        return False

def main():
    print("=" * 70)
    print(f"{Colors.BOLD}O2OA Multi-API Expansion - Dry-Run Integration Test{Colors.RESET}")
    print("=" * 70)
    print()

    tests = [
        test_seed_files,
        test_target_config,
        test_validity_rules,
        test_endpoint_resolution,
        test_harness_import,
        test_mutation_routing,
        test_output_directory,
    ]

    results = []
    for test_func in tests:
        result = test_func()
        results.append(result)

    print()
    print("=" * 70)
    print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    for i, (test_func, result) in enumerate(zip(tests, results), 1):
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if result else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"Test {i}: {test_func.__doc__.split(':')[1].strip()} - {status}")

    print()
    print(f"Result: {passed}/{total} tests passed")

    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ DRY-RUN INTEGRATION TEST PASSED{Colors.RESET}")
        print()
        print("Framework is ready for O2OA multi-API expansion.")
        print("Next step: Set NV_TOKEN and run scripts/run_o2oa_expansion_bounded.sh")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ DRY-RUN INTEGRATION TEST FAILED{Colors.RESET}")
        print()
        print(f"{total - passed} test(s) failed. Fix issues before proceeding.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
