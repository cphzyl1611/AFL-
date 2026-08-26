# README_START_HERE

## AFL++ / 河南重大专项 — New AI Handoff, 2026-08-25

**Do not begin by changing code or running a real fuzz campaign.**

Start with a READ-ONLY revalidation of the repository and use this authority
order:

```text
CURRENT WORKING-TREE SOURCE
> exact committed source snapshot
> independent audit
> historical handoff/report
```

The package intentionally contains both the exact `53cb267...` source archives
and a small set of later/current files, because the current bounded-feedback
work includes uncommitted or post-snapshot delta.

### Read in this order

1. `01_context/CURRENT_STATE.md`
2. `01_context/FILE_INDEX.md`
3. `03_current_delta/MISSING_CURRENT_WORKTREE_FILES.md`
4. `02_source/` exact source archives
5. `03_current_delta/` supplied current files and patches
6. `04_audits/latest_reviews/`
7. `04_audits/levelc/` and `04_audits/gate2/`
8. `06_background/AFL++源代码修改总纲.md`
9. `07_prompts/NEW_AI_CONTINUATION_PROMPT.md`

### Immediate task

Revalidate two blockers before real execution:

```text
CB-1 representation bridge
CB-2 bounded runner orchestration
```

The supplied current harness already contains the representation bridge
implementation, but this package does not claim a fresh test pass. The latest
runner review still described `main()` as a stub, but the receiving AI must
inspect the actual repo copy before acting.

### Hard safety / integrity rules

- Never paste or print `ALFRESCO_USER` or `ALFRESCO_PASS`.
- No Authorization header / old password / reset token is included here.
- Do not infer current source from old reports.
- Do not run real Alfresco fuzz until offline gates pass.
- Do not commit/push/merge/tag/reset/rebase during the first revalidation pass.
- Prefer the existing audited Level-C preflight for real-service identity.
