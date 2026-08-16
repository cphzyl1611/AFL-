# AFL native edge-coverage integration smoke

## What this proves

AFL++ instrumentation and bitmap feedback work in this build:

- target: `test/p0/edge_cov_target.c`, compiled with `afl-clang-fast -O1`
- `edges_found: 11`, `total_edges: 22`, `bitmap_cvg: 50.00%`
- `corpus_count: 7` (5 new items discovered from 2 seeds)
- `ss_cov_sum: 10` — the SS seed scheduler also consumes AFL edge novelty

Before this round every archived AFL run in this repository reported
`edges_found: 0` / `bitmap_cvg: 0.00%`, because all of them used `-n`.

## What this does NOT prove

This is **not** the project's security-state coverage metric and must not be
reported as Deep2Fuzz-ES security-state coverage.  Note that this run shows
`security_state_total: 0` and `nv_mab_ucb_picks: 0` precisely because the
target writes no status document and no NV custom mutator is loaded — the two
coverage notions are independent by construction.

The project's Cov signal is the security-state coverage demonstrated in
`out/p0_mab_feedback_*`.
