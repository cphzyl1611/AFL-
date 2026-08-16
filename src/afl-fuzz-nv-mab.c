/*
   american fuzzy lop++ - NV multi-armed bandit (NC_MAB) core
   ----------------------------------------------------------

   The NV mutation-arm bandit lives in its own translation unit so that the
   selection and reward-update logic can be exercised by a standalone unit
   test without linking the whole fuzzer.  Behaviour is identical to the
   previous in-place implementation in afl-fuzz-run.c.

 */

#include "afl-fuzz.h"

#include <ctype.h>
#include <errno.h>
#include <limits.h>
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

/* Trimmed view of an environment variable, or NULL when it carries no value.
   An empty or all-whitespace variable is treated exactly like an absent one:
   under the P0.1 precedence rule it is the *validity* of an override that
   decides, never its mere presence. */
static const char *nv_env_value(const char *name) {

  const char *v = getenv(name);
  if (!v) return NULL;

  while (*v && isspace((unsigned char)*v)) ++v;
  return *v ? v : NULL;

}

static int nv_str_is_terminated(const char *end) {

  if (!end) return 0;
  while (*end && isspace((unsigned char)*end)) ++end;
  return *end == 0;

}

/* ---- P0.1 M-5/M-6/M-7: what counts as a *valid* override ----
   c must be finite and strictly positive.  Zero is not an opt-out: UCB with
   c = 0 collapses into pure greedy selection, which this project does not
   support as a mode (see NV_MAB_DEFAULT_C).  Overflow to infinity is rejected
   too -- it makes every arm's UCB infinite and hands every decision to the
   first enabled arm. */
int nv_mab_env_c(double *out) {

  const char *raw = nv_env_value("NV_MAB_C");
  if (!raw) return 0;

  errno = 0;
  char  *end = NULL;
  double v   = strtod(raw, &end);

  if (!nv_str_is_terminated(end) || end == raw) return 0;
  if (errno == ERANGE || !isfinite(v) || v <= 0.0) return 0;

  if (out) *out = v;
  return 1;

}

/* min_explore must be at least one sample per arm and small enough that UCB is
   actually reachable inside a campaign; an overflowed LONG_MAX warm-up means
   the bandit never adapts at all. */
int nv_mab_env_min_explore(u64 *out) {

  const char *raw = nv_env_value("NV_MAB_MIN_EXPLORE");
  if (!raw) return 0;

  errno = 0;
  char *end = NULL;
  long  v   = strtol(raw, &end, 10);

  if (!nv_str_is_terminated(end) || end == raw) return 0;
  if (errno == ERANGE || v < 1 || v > NV_MAB_MAX_MIN_EXPLORE) return 0;

  if (out) *out = (u64)v;
  return 1;

}

/* Establish the bandit's tunables.  Defaults apply unconditionally so that a
   run without task.json still explores, then a *valid* environment override
   wins.  task.json is layered in between by nv_load_task_json(); see
   NV_MAB_DEFAULT_C for the full precedence rule. */
void nv_mab_init_defaults(nv_mab_t *mab) {

  if (!mab) return;

  mab->c           = NV_MAB_DEFAULT_C;
  mab->min_explore = NV_MAB_DEFAULT_MIN_EXPLORE;

  nv_mab_env_c(&mab->c);
  nv_mab_env_min_explore(&mab->min_explore);

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
