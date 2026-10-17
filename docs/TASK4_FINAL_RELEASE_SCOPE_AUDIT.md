# Task 4 Final Git Release Scope Audit

Project: 河南重大专项 / Task 4 模糊测试组件

- Acceptance base: `d1a2c5db454b78cb4034f4f8da4778e12c514871`
- Audited branch: `main`
- Release remote: `origin`
- Release branch: `main`
- Release tag: `task4-fuzzing-final-20261017`
- Initial dirty file count: 16
- Release-generated provenance/audit file count: 2
- Release whitespace-policy file count: 1
- Total explicit release paths: 19
- Review-required count: 0
- `.gitignore` change required: no

The initial dirty path set exactly matches the accepted dirty-worktree set in
the frozen delivery package's `REPOSITORY_PROVENANCE.txt`. The final technical
document and two experiment entrypoints are exact-byte matches of their frozen
copies. Existing ignored runtime outputs and Python/test caches remain outside
the release scope; the external frozen evidence package is not stored in Git.

| Path | Git status | Classification | Reason |
|---|---:|---|---|
| `.gitattributes` | A | INCLUDE_RELEASE | Path-scoped policy preserves the frozen guide's intentional Markdown hard-break and EOF bytes while keeping the release whitespace gate meaningful for every other path. |
| `nv_body_valid.py` | M | INCLUDE_RELEASE | Accepted validity implementation for formal O2OA body and URL-query contracts. |
| `nv_http_harness.py` | M | INCLUDE_RELEASE | Accepted HTTP harness, runtime binding, observation, and O2OA state-chain implementation. |
| `nv_json_mutator.py` | M | INCLUDE_RELEASE | Accepted endpoint-aware O2OA mutation implementation. |
| `nv_url_query.py` | M | INCLUDE_RELEASE | Accepted URL-query seed serialization correction. |
| `targets/o2oa_query.json` | M | INCLUDE_RELEASE | Accepted O2OA endpoint and runtime-binding configuration. |
| `validity/o2oa_query_rules.json` | M | INCLUDE_RELEASE | Accepted O2OA validity rules. |
| `docs/TASK4_FINAL_TECHNICAL_AUDIT_AND_EXPERIMENT_GUIDE.md` | A | INCLUDE_RELEASE | Authoritative final technical document; exact-byte frozen-copy match. |
| `in/o2oa_document_create/seed_create_draft_0.json` | A | INCLUDE_RELEASE | Sanitized formal O2OA create seed with runtime markers only. |
| `in/o2oa_document_data_update/seed_update_data_0.json` | A | INCLUDE_RELEASE | Sanitized formal O2OA data-update seed. |
| `in/o2oa_url_query/seed_cms_attachment_download_query_0.json` | A | INCLUDE_RELEASE | Sanitized formal O2OA attachment-query seed. |
| `in/o2oa_url_query/seed_file_share_list_my_query_0.json` | A | INCLUDE_RELEASE | Sanitized formal O2OA share-list query seed. |
| `scripts/run_task4_alfresco_final_experiment.sh` | A (0755) | INCLUDE_RELEASE | Authoritative Alfresco reproducibility entrypoint; exact-byte frozen-copy match. |
| `scripts/run_task4_o2oa_final_experiment.sh` | A (0755) | INCLUDE_RELEASE | Authoritative O2OA reproducibility entrypoint; exact-byte frozen-copy match. |
| `tests/test_o2oa_create_update_e2e.py` | A | INCLUDE_RELEASE | Accepted formal O2OA create/update contract and state-chain tests. |
| `tests/test_o2oa_share_list_query_e2e.py` | A | INCLUDE_RELEASE | Accepted formal O2OA share-list query tests. |
| `tests/test_o2oa_url_query_e2e.py` | A | INCLUDE_RELEASE | Accepted formal O2OA URL-query tests. |
| `docs/TASK4_FINAL_RELEASE_PROVENANCE.md` | A | INCLUDE_RELEASE | Required durable mapping between the acceptance base, final tag, and frozen package. |
| `docs/TASK4_FINAL_RELEASE_SCOPE_AUDIT.md` | A | INCLUDE_RELEASE | Durable release-scope classification and audit record. |

Classification totals across the explicit release path set:

```text
INCLUDE_RELEASE = 19
EXCLUDE_RUNTIME = 0
EXCLUDE_EVIDENCE = 0
EXCLUDE_SECRET count is 0
EXCLUDE_TEMP = 0
EXCLUDE_UNRELATED = 0
REVIEW_REQUIRED = 0
```

The zero excluded counts apply to modified, added, or untracked Git paths.
Ignored runtime artifacts and the external evidence/delivery roots were
inspected as boundary conditions but were never candidates for staging.
