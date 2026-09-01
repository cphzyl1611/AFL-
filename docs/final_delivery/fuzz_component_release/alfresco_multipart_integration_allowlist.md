# Alfresco Multipart Fuzzing Integration Allowlist

## Integration target

```text
/home/dministrator/AFLplusplus
branch = public-release
HEAD = c6817ce46b0120da95ba55869b6b298e18e4cf8b
```

Integration means working-tree content only. It does not mean commit, merge, push, or ref movement.

## Allowlist

The following paths are in scope for this closure and may be selectively applied after final regression:

```text
nv_json_mutator.py
nv_http_harness.py
scripts/run_alfresco_bounded_feedback.py
scripts/run_alfresco_levelc_metadata.py
runner/fuzz_test_runner.py
include/afl-fuzz.h
src/afl-fuzz-init.c
src/afl-fuzz-nv-mab.c
src/afl-fuzz-one.c
src/afl-fuzz-queue.c
src/afl-fuzz-run.c
src/afl-fuzz-stats.c
src/afl-fuzz.c
targets/alfresco_multipart_upload.json
in/alfresco_multipart_upload_bounded/manifest.txt
in/alfresco_multipart_upload_bounded/seed_0.http
in/alfresco_multipart_upload_bounded/seed_1.http
in/alfresco_multipart_upload_bounded/seed_2.http
in/alfresco_multipart_upload_bounded/negative_boundary_mismatch.http
in/alfresco_multipart_upload_bounded/negative_missing_filedata.http
scripts/reproduce_alfresco_multipart_bounded.py
tests/test_alfresco_bounded_feedback.py
tests/test_alfresco_multipart_reproduction.py
docs/project_docs/alfresco_multipart_bounded_repro.md
docs/final_delivery/fuzz_component_release/alfresco_multipart_bounded_final.md
```

Existing fuzzing files already present in the public-release working tree must be compared before copying; unrelated dirty content must never be overwritten blindly.

## Denylist

Never integrate:

```text
/tmp/**
run-roots and AFL output directories
credentials, tokens, Authorization headers
*.env and runtime secret files
__pycache__/**
*.pyc, object files, static libraries, generated binaries
/tmp_multipart_negative_check.py
multipart_closure_inspect.py
multipart_closure_inspect_final.py
run_multipart_closure_once.sh
tmp_inspect_multipart_nodes.py
tmp_make_unique_multipart_seeds.py
unrelated Flowable/model-stage changes
unrelated O2OA historical experiment outputs
```

## Review rules

Before applying any allowlisted path:

1. Compare bounded and baseline hashes.
2. If baseline is dirty, do not overwrite silently; apply only an audited patch or copy a missing file.
3. Verify no secret literal or run-root enters the path.
4. Run `git diff --check` after integration.
5. Rebuild AFL++ in the baseline worktree and run the fuzzing regression there.
6. Confirm baseline HEAD and `public-release` ref remain unchanged.

## Known repository state

Both worktrees contain pre-existing dirty files outside this closure. Those files are classified as unrelated or prior fuzzing work and are not automatically part of this allowlist application.

```text
PUBLIC_RELEASE_COMMITTED = NOT_DONE
PUBLIC_RELEASE_PUSHED = NOT_DONE
```
