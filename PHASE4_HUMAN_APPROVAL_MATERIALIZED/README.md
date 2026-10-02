# Phase 4 — Human Approval Materialized

**Package Name:** PHASE4_HUMAN_APPROVAL_MATERIALIZED

**Approval Date:** 2026-09-21

**Approval Statement:** 批准按最终 approval template 的推荐值执行 D1–D15

---

## Package Contents

- `00_APPROVAL_STATUS.json` — Approval metadata and provenance
- `01_APPROVED_D1_D15.json` — All 15 approved design decisions
- `02_APPROVAL_PROVENANCE.json` — Provenance chain
- `03_APPROVED_DESIGN_SUMMARY.md` — Human-readable summary
- `FORMAL_SEED_LIST.json` — 30 formal seeds (master seed: 3485535768)
- `FORMAL_PAIRED_ORDER_SCHEDULE.json` — Counterbalanced order schedule

---

## Approval Scope

All recommended values from PHASE4_FINAL_APPROVAL_BLOCKER_RECONCILIATION/07_FINAL_HUMAN_APPROVAL_TEMPLATE.md approved.

No alternative values specified.

---

## Key Decisions

- **Primary estimand:** Mean paired difference for security_state_new_total
- **Sample size:** N=30 (pragmatic, not power-justified)
- **Execution order:** Counterbalanced alternating
- **Budget:** MAX_TEST_CASES=5, TIME=60s
- **Master seed:** 3485535768
