/*
   Deterministic unit tests for the NV multi-armed bandit (NC_MAB) core.

   Built and executed by tests/test_nv_mab_unit.py.  Links only
   src/afl-fuzz-nv-mab.c, so no fuzzer runtime is required.

   Output is line oriented so the Python wrapper can assert on individual
   cases:  "PASS <name>" / "FAIL <name>: <detail>" plus "SEQ"/"PULLS"
   diagnostic lines that double as P0 evidence.
 */

#include "afl-fuzz.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_failures = 0;

static void expect(int cond, const char *name, const char *fmt, ...) {

  if (cond) {

    printf("PASS %s\n", name);

  } else {

    va_list ap;
    printf("FAIL %s: ", name);
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    printf("\n");
    ++g_failures;

  }

}

/* Drive the bandit for `n` decisions, always feeding back `reward`.
   Records the chosen arm of every decision into `seq`. */
static void drive(nv_mab_t *mab, u32 scope, u32 n, double reward, char *seq) {

  for (u32 i = 0; i < n; ++i) {

    nv_arm_id_t a = nv_mab_pick(mab, scope);
    if (seq) seq[i] = (char)('0' + (int)a);
    nv_mab_update(mab, a, reward);

  }

  if (seq) seq[n] = 0;

}

static u64 least_pulls(nv_mab_t *mab) {

  u64 lo = mab->arms[0].pulls;
  for (int a = 1; a < NV_ARM_MAX; ++a)
    if (mab->arms[a].pulls < lo) lo = mab->arms[a].pulls;
  return lo;

}

/* ---- P0-B: cold start must sample every enabled arm fairly ---- */
static void test_cold_start_is_fair(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  nv_mab_init_defaults(&mab);

  char seq[64];
  drive(&mab, 0x7, 30, 0.0, seq);

  printf("SEQ cold_start_is_fair %s\n", seq);
  printf("PULLS cold_start_is_fair %llu %llu %llu\n",
         (unsigned long long)mab.arms[0].pulls,
         (unsigned long long)mab.arms[1].pulls,
         (unsigned long long)mab.arms[2].pulls);

  /* With 30 decisions over 3 arms a fair cold start gives every arm a
     meaningful share.  A sequential drain gives arm0 everything. */
  expect(least_pulls(&mab) >= 8, "cold_start_is_fair",
         "least-pulled arm has %llu pulls after 30 decisions "
         "(arm0=%llu arm1=%llu arm2=%llu); expected >= 8",
         (unsigned long long)least_pulls(&mab),
         (unsigned long long)mab.arms[0].pulls,
         (unsigned long long)mab.arms[1].pulls,
         (unsigned long long)mab.arms[2].pulls);

}

/* ---- scope mask must be honoured (regression guard for the TU move) ---- */
static void test_scope_mask_respected(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  nv_mab_init_defaults(&mab);

  drive(&mab, 0x2, 20, 0.0, NULL); /* boundary only */

  expect(mab.arms[0].pulls == 0 && mab.arms[2].pulls == 0 &&
             mab.arms[1].pulls == 20,
         "scope_mask_respected",
         "expected all 20 pulls on arm1, got %llu/%llu/%llu",
         (unsigned long long)mab.arms[0].pulls,
         (unsigned long long)mab.arms[1].pulls,
         (unsigned long long)mab.arms[2].pulls);

}

/* ---- P0-A: exploration coefficient must not depend on task.json ---- */
static void test_defaults_give_positive_c(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  unsetenv("NV_MAB_C");
  nv_mab_init_defaults(&mab);

  expect(mab.c == NV_MAB_DEFAULT_C && mab.c > 0.0,
         "defaults_give_positive_c",
         "expected c == NV_MAB_DEFAULT_C (%g) and > 0, got %g",
         (double)NV_MAB_DEFAULT_C, mab.c);

}

/* A calloc'd afl_state_t that never loaded task.json must still explore. */
static void test_uninitialised_mab_is_never_silently_greedy(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab)); /* exactly what calloc() in afl-fuzz.c yields */
  unsetenv("NV_MAB_C");

  /* no nv_mab_init_defaults() call here on purpose */
  drive(&mab, 0x7, 5, 0.0, NULL);

  expect(mab.c > 0.0, "uninitialised_mab_is_never_silently_greedy",
         "zero-initialised bandit still has c=%g after use; UCB would be "
         "pure greedy", mab.c);

}

static void test_env_c_override_applies(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  setenv("NV_MAB_C", "0.7", 1);
  nv_mab_init_defaults(&mab);
  unsetenv("NV_MAB_C");

  expect(mab.c > 0.6999 && mab.c < 0.7001, "env_c_override_applies",
         "expected c=0.7 from NV_MAB_C, got %g", mab.c);

}

static void test_env_c_negative_falls_back(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  setenv("NV_MAB_C", "-1.5", 1);
  nv_mab_init_defaults(&mab);
  unsetenv("NV_MAB_C");

  expect(mab.c == NV_MAB_DEFAULT_C, "env_c_negative_falls_back",
         "negative NV_MAB_C must fall back to %g, got %g",
         (double)NV_MAB_DEFAULT_C, mab.c);

}

static void test_env_c_garbage_falls_back(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  setenv("NV_MAB_C", "not-a-number", 1);
  nv_mab_init_defaults(&mab);
  unsetenv("NV_MAB_C");

  expect(mab.c == NV_MAB_DEFAULT_C, "env_c_garbage_falls_back",
         "unparseable NV_MAB_C must fall back to %g, got %g",
         (double)NV_MAB_DEFAULT_C, mab.c);

}

/* P0.1 M-6.  The header requires c > 0, so a zero coefficient is invalid
   input, not an opt-out: UCB with c = 0 is pure greedy selection, which is not
   a supported mode of this project.  It falls back to the default like any
   other invalid value.  (This replaces the P0-era
   test_env_c_explicit_zero_is_honoured, whose contract M-6 reverses.) */
static void test_env_c_zero_falls_back(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  setenv("NV_MAB_C", "0", 1);
  nv_mab_init_defaults(&mab);
  unsetenv("NV_MAB_C");

  expect(mab.c == NV_MAB_DEFAULT_C, "env_c_zero_falls_back",
         "NV_MAB_C=0 disables exploration and must fall back to %g, got %g",
         (double)NV_MAB_DEFAULT_C, mab.c);

}

/* P0.1 M-5.  "Valid" is the qualifier that matters: a variable that merely
   exists must never suppress a valid task.json value. */
static void test_env_c_validity_is_reported(void) {

  double v = -1.0;
  int    ok_absent, ok_empty, ok_space, ok_garbage, ok_zero, ok_neg, ok_valid;

  unsetenv("NV_MAB_C");
  ok_absent = nv_mab_env_c(&v);

  setenv("NV_MAB_C", "", 1);          ok_empty   = nv_mab_env_c(&v);
  setenv("NV_MAB_C", "   ", 1);       ok_space   = nv_mab_env_c(&v);
  setenv("NV_MAB_C", "not-a-num", 1); ok_garbage = nv_mab_env_c(&v);
  setenv("NV_MAB_C", "0", 1);         ok_zero    = nv_mab_env_c(&v);
  setenv("NV_MAB_C", "-2", 1);        ok_neg     = nv_mab_env_c(&v);

  v = -1.0;
  setenv("NV_MAB_C", "0.25", 1);      ok_valid   = nv_mab_env_c(&v);
  unsetenv("NV_MAB_C");

  expect(!ok_absent && !ok_empty && !ok_space && !ok_garbage && !ok_zero &&
             !ok_neg && ok_valid && v > 0.2499 && v < 0.2501,
         "env_c_validity_is_reported",
         "absent=%d empty=%d space=%d garbage=%d zero=%d neg=%d valid=%d "
         "value=%g", ok_absent, ok_empty, ok_space, ok_garbage, ok_zero,
         ok_neg, ok_valid, v);

}

/* P0.1 M-7.  strtod/strtol overflow was unchecked: NV_MAB_C=1e400 produced
   c = inf (every arm's UCB infinite, first enabled arm always wins) and a huge
   NV_MAB_MIN_EXPLORE produced LONG_MAX, so UCB was never reached at all. */
static void test_env_overflow_falls_back(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  setenv("NV_MAB_C", "1e400", 1);
  setenv("NV_MAB_MIN_EXPLORE", "99999999999999999999", 1);
  nv_mab_init_defaults(&mab);
  unsetenv("NV_MAB_C");
  unsetenv("NV_MAB_MIN_EXPLORE");

  expect(mab.c == NV_MAB_DEFAULT_C &&
             mab.min_explore == NV_MAB_DEFAULT_MIN_EXPLORE,
         "env_overflow_falls_back",
         "overflowing overrides must fall back to %g/%llu, got %g/%llu",
         (double)NV_MAB_DEFAULT_C,
         (unsigned long long)NV_MAB_DEFAULT_MIN_EXPLORE, mab.c,
         (unsigned long long)mab.min_explore);

}

static void test_env_min_explore_validity_is_reported(void) {

  u64 v = 0;
  int ok_absent, ok_empty, ok_zero, ok_neg, ok_garbage, ok_huge, ok_valid;

  unsetenv("NV_MAB_MIN_EXPLORE");
  ok_absent = nv_mab_env_min_explore(&v);

  setenv("NV_MAB_MIN_EXPLORE", "", 1);      ok_empty   = nv_mab_env_min_explore(&v);
  setenv("NV_MAB_MIN_EXPLORE", "0", 1);     ok_zero    = nv_mab_env_min_explore(&v);
  setenv("NV_MAB_MIN_EXPLORE", "-3", 1);    ok_neg     = nv_mab_env_min_explore(&v);
  setenv("NV_MAB_MIN_EXPLORE", "abc", 1);   ok_garbage = nv_mab_env_min_explore(&v);
  setenv("NV_MAB_MIN_EXPLORE", "99999999999999999999", 1);
  ok_huge = nv_mab_env_min_explore(&v);

  v = 0;
  setenv("NV_MAB_MIN_EXPLORE", "12", 1);    ok_valid   = nv_mab_env_min_explore(&v);
  unsetenv("NV_MAB_MIN_EXPLORE");

  expect(!ok_absent && !ok_empty && !ok_zero && !ok_neg && !ok_garbage &&
             !ok_huge && ok_valid && v == 12,
         "env_min_explore_validity_is_reported",
         "absent=%d empty=%d zero=%d neg=%d garbage=%d huge=%d valid=%d "
         "value=%llu", ok_absent, ok_empty, ok_zero, ok_neg, ok_garbage,
         ok_huge, ok_valid, (unsigned long long)v);

}

static void test_env_min_explore_override_applies(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  setenv("NV_MAB_MIN_EXPLORE", "3", 1);
  nv_mab_init_defaults(&mab);
  unsetenv("NV_MAB_MIN_EXPLORE");

  drive(&mab, 0x7, 9, 0.0, NULL);

  expect(mab.min_explore == 3 && mab.cold_start_picks == 9 &&
             mab.ucb_picks == 0,
         "env_min_explore_override_applies",
         "expected min_explore=3 and 9 warm-up picks, got min_explore=%llu "
         "cold=%llu ucb=%llu",
         (unsigned long long)mab.min_explore,
         (unsigned long long)mab.cold_start_picks,
         (unsigned long long)mab.ucb_picks);

}

/* ---- the UCB branch must actually run within a short experiment ---- */
static void test_ucb_phase_is_reached(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  nv_mab_init_defaults(&mab);

  u32 warmup = (u32)(mab.min_explore * NV_ARM_MAX);
  drive(&mab, 0x7, warmup + 10, 0.0, NULL);

  printf("PICKS ucb_phase_is_reached cold=%llu ucb=%llu\n",
         (unsigned long long)mab.cold_start_picks,
         (unsigned long long)mab.ucb_picks);

  expect(mab.cold_start_picks == warmup && mab.ucb_picks == 10,
         "ucb_phase_is_reached",
         "expected cold=%u ucb=10, got cold=%llu ucb=%llu", warmup,
         (unsigned long long)mab.cold_start_picks,
         (unsigned long long)mab.ucb_picks);

}

/* ---- the core P0 claim: the next decision reads the updated mean ---- */
static void test_ucb_follows_updated_mean(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  nv_mab_init_defaults(&mab);

  u32 warmup = (u32)(mab.min_explore * NV_ARM_MAX);
  drive(&mab, 0x7, warmup, 0.0, NULL); /* all arms equal, all means 0 */

  nv_arm_id_t before = nv_mab_pick(&mab, 0x7);
  double mean_before = mab.arms[NV_ARM_STRUCTURE].mean_reward;

  /* reward the structure arm only */
  nv_mab_update(&mab, NV_ARM_STRUCTURE, 10.0);
  double mean_after = mab.arms[NV_ARM_STRUCTURE].mean_reward;

  nv_arm_id_t after = nv_mab_pick(&mab, 0x7);

  printf("UCBSHIFT ucb_follows_updated_mean before=%d after=%d "
         "mean_before=%.6f mean_after=%.6f\n",
         (int)before, (int)after, mean_before, mean_after);

  expect(before != NV_ARM_STRUCTURE && after == NV_ARM_STRUCTURE &&
             mean_after > mean_before,
         "ucb_follows_updated_mean",
         "expected pick to shift to arm2 after its mean rose; before=%d "
         "after=%d mean %.6f -> %.6f",
         (int)before, (int)after, mean_before, mean_after);

}

static void test_reward_updates_mean_incrementally(void) {

  nv_mab_t mab;
  memset(&mab, 0, sizeof(mab));
  nv_mab_init_defaults(&mab);

  nv_mab_update(&mab, NV_ARM_FIELD_VALUE, 2.0);
  nv_mab_update(&mab, NV_ARM_FIELD_VALUE, 4.0);

  expect(mab.arms[0].pulls == 2 && mab.arms[0].pos_cnt == 2 &&
             mab.arms[0].sum_reward == 6.0 &&
             mab.arms[0].mean_reward > 2.999 &&
             mab.arms[0].mean_reward < 3.001,
         "reward_updates_mean_incrementally",
         "expected pulls=2 sum=6 mean=3, got pulls=%llu sum=%g mean=%g",
         (unsigned long long)mab.arms[0].pulls, mab.arms[0].sum_reward,
         mab.arms[0].mean_reward);

}

int main(void) {

  test_cold_start_is_fair();
  test_scope_mask_respected();
  test_defaults_give_positive_c();
  test_uninitialised_mab_is_never_silently_greedy();
  test_env_c_override_applies();
  test_env_c_negative_falls_back();
  test_env_c_garbage_falls_back();
  test_env_c_zero_falls_back();
  test_env_c_validity_is_reported();
  test_env_overflow_falls_back();
  test_env_min_explore_validity_is_reported();
  test_env_min_explore_override_applies();
  test_ucb_phase_is_reached();
  test_ucb_follows_updated_mean();
  test_reward_updates_mean_incrementally();

  printf("FAILURES %d\n", g_failures);
  return g_failures ? 1 : 0;

}
