# Provenance correction (P0.1 M-8)

## Classification

```
artifact_class  = behavioral_regression_probe
NOT             = raw pre-P0 runtime artifact
baseline_commit = (none — this is not a 6924b2d run)
```

**No number in this directory has been changed.** Only this description is
added. `fuzzer_stats`, `eval_report.json`, `summary.csv`,
`security_states.jsonl` and `task.json` are byte-for-byte as the P0 round
committed them.

## Why the original label was wrong

The P0 commit message described this directory as *"the pre-fix baseline kept
for comparison"*. It cannot be one. Its `fuzzer_stats` contains:

```
nv_mab_c                : 5.0000000000e-02
nv_mab_min_explore      : 8
nv_mab_cold_start_picks : 24
nv_mab_ucb_picks        : 178
```

None of those fields exist in `6924b2d`'s `src/afl-fuzz-stats.c` — a grep for
`cold_start_picks` there returns zero hits — and `min_explore: 8` is the P0
default `NV_MAB_DEFAULT_MIN_EXPLORE`, not the old hardcoded `200`. The run was
therefore produced by an **intermediate build**: the MAB fix already applied,
the security-state feedback not yet added. Consistent with that, its
`security_state_*` columns are empty and `eval_report.json` has no
`security_state_cov` block.

It was also run **without** `-s`, so it does not share the pinned AFL seed
(`20260816`) with the runs it was being compared against.

## What it is actually useful for

A probe of the intermediate state in which the bandit tunables existed but the
security-state feedback loop did not. In that role its numbers are meaningful:
`ss_cov_sum = 0` and `ss_prob_max = 0.615572` (= `1 / 2^0.7`, the weight of a
seed with `ss_cov_cnt = 0`) show the seed scheduler receiving no
security-state signal at all.

## Where the real baseline is

`out/p01_red_baseline_6924b2d/` — a genuine run of the `6924b2d` fuzzer core
from a clean clone, with the same pinned seed. It has no `security_state_*`
fields whatsoever, which is what makes it verifiably pre-P0.
