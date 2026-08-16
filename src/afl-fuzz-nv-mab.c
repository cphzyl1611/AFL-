/*
   american fuzzy lop++ - NV multi-armed bandit (NC_MAB) core
   ----------------------------------------------------------

   The NV mutation-arm bandit lives in its own translation unit so that the
   selection and reward-update logic can be exercised by a standalone unit
   test without linking the whole fuzzer.  Behaviour is identical to the
   previous in-place implementation in afl-fuzz-run.c.

 */

#include "afl-fuzz.h"

#include <math.h>
#include <stdlib.h>

static inline int nv_arm_enabled(u32 scope_mask, nv_arm_id_t arm) {
  switch (arm) {
    case NV_ARM_FIELD_VALUE: return (scope_mask & 0x1) != 0;
    case NV_ARM_BOUNDARY:    return (scope_mask & 0x2) != 0;
    case NV_ARM_STRUCTURE:   return (scope_mask & 0x4) != 0;
    default: return 0;
  }
}

/* Establish the bandit's tunables.  Defaults apply unconditionally so that a
   run without task.json still explores; NV_MAB_C / NV_MAB_MIN_EXPLORE may
   override them.  An unparseable or negative coefficient is rejected in
   favour of the default -- only an explicit "0" disables exploration, and
   the effective value is reported in fuzzer_stats either way. */
void nv_mab_init_defaults(nv_mab_t *mab) {

  if (!mab) return;

  mab->c           = NV_MAB_DEFAULT_C;
  mab->min_explore = NV_MAB_DEFAULT_MIN_EXPLORE;

  const char *env_c = getenv("NV_MAB_C");
  if (env_c && *env_c) {

    char  *end = NULL;
    double v   = strtod(env_c, &end);
    if (end && *end == 0 && v >= 0.0) { mab->c = v; }

  }

  const char *env_me = getenv("NV_MAB_MIN_EXPLORE");
  if (env_me && *env_me) {

    char *end = NULL;
    long  v   = strtol(env_me, &end, 10);
    if (end && *end == 0 && v >= 1) { mab->min_explore = (u64)v; }

  }

  mab->initialized = 1;

}

nv_arm_id_t nv_mab_pick(nv_mab_t *mab, u32 scope_mask) {

  /* A calloc'd afl_state_t leaves c=0, which turns UCB into pure greedy
     selection.  Initialise lazily so that can never happen silently. */
  if (!mab->initialized) nv_mab_init_defaults(mab);

  /* respect task scope; fallback: if mask==0 enable all */
  if (!scope_mask) scope_mask = 0x7;

  /* Warm-up: hand the next sample to the least-pulled enabled arm until each
     has min_explore of them.  Ties resolve to the lowest arm id, which keeps
     the sequence deterministic and testable. */
  {

    nv_arm_id_t least       = NV_ARM_MAX;
    u64         least_seen  = 0;

    for (nv_arm_id_t a = 0; a < NV_ARM_MAX; ++a) {

      if (!nv_arm_enabled(scope_mask, a)) continue;
      if (least == NV_ARM_MAX || mab->arms[a].pulls < least_seen) {

        least      = a;
        least_seen = mab->arms[a].pulls;

      }

    }

    if (least == NV_ARM_MAX) return NV_ARM_FIELD_VALUE; /* nothing enabled */

    if (least_seen < mab->min_explore) {

      mab->cold_start_picks++;
      return least;

    }

  }

  /* UCB */
  double best_ucb = -1e100;
  nv_arm_id_t best = NV_ARM_FIELD_VALUE;

  /* avoid ln(0) */
  double ln_total = log((double)mab->total_pulls + 1.0);

  for (nv_arm_id_t a = 0; a < NV_ARM_MAX; ++a) {

    if (!nv_arm_enabled(scope_mask, a)) continue;

    u64 pulls = mab->arms[a].pulls;
    if (pulls == 0) return a;

    double mean = mab->arms[a].mean_reward;
    double ucb = mean + mab->c * sqrt(ln_total / (double)pulls);

    if (ucb > best_ucb) { best_ucb = ucb; best = a; }

  }

  mab->ucb_picks++;
  return best;

}

void nv_mab_update(nv_mab_t *mab, nv_arm_id_t arm, double reward) {

  if (arm < 0 || arm >= NV_ARM_MAX) return;

  mab->total_pulls++;
  mab->arms[arm].pulls++;
  mab->arms[arm].sum_reward += reward;
  if (reward > 0) mab->arms[arm].pos_cnt++;
  /* incremental mean update */
  double mean = mab->arms[arm].mean_reward;
  double n = (double)mab->arms[arm].pulls;
  mab->arms[arm].mean_reward = mean + (reward - mean) / n;

}
