# Genuine pre-P0 baseline (RED) evidence

## What this is

A real `afl-fuzz` run produced by the **historical** fuzzer core, built from a
clean clone of the delivery baseline:

```
baseline_commit = 6924b2d5d6af01dd80f57ef7f58b92e80fcc227d
tag             = v0.6.3-final-docs-polish
```

It exists because the P0 round shipped `out/p0_red_probe/` described as "the
pre-fix baseline", which it is not: that directory contains
`nv_mab_cold_start_picks`, `nv_mab_ucb_picks` and `nv_mab_min_explore`, fields
that do not exist in `6924b2d`'s `src/afl-fuzz-stats.c` at all. See
`out/p0_red_probe/PROVENANCE.md`.

## How it was produced

The fuzzer core is untouched `6924b2d`. Only *test fixtures* were copied into
the historical tree, because they were introduced later and are harness, not
subject:

- `targets/nv_p0_deterministic_target.py`
- `in/p0_o2oa_cms_doc_list/`

Command (AFL seed pinned, identical to the P0/P0.1 runs):

```
afl-fuzz -n -m none -s 20260816 \
  -i in/p0_o2oa_cms_doc_list -o out/base_red \
  -- python3 targets/nv_p0_deterministic_target.py @@
```

## What it shows

Both defects the P0 round set out to fix, in the original code:

| | 6924b2d (this evidence) | P0.1 |
|---|---|---|
| `nv_mab_c` | **field absent** | `5.0e-02` |
| `nv_mab_min_explore` | **field absent** | `8` |
| `nv_mab_cold_start_picks` | **field absent** | `24` |
| `nv_mab_ucb_picks` | **field absent** | `> 0` |
| arm0 / arm1 / arm2 pulls | **194 / 1 / 1** | balanced |
| `security_state_*` | **all fields absent** | reported |

`arm0_pulls = 194` out of `total_pulls = 196` is the cold-start drain: the old
loop returned the first arm below a hardcoded 200-pull threshold, so arm0
absorbed effectively the whole budget and UCB was never reached. The complete
absence of every `security_state_*` field is what makes this document
verifiably pre-P0 — no post-P0 build can produce a `fuzzer_stats` without them.

## Boundary

Local network-free deterministic target. Not a platform experiment, and not a
real O2OA / Alfresco / Flowable service.
