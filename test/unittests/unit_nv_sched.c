/*
   Deterministic unit tests for the SS seed-scheduling weight.

   These pin down the property the security-state feedback loop depends on:
   a seed that reached new security states must out-weigh one that did not.
   Built and executed by tests/test_nv_mab_unit.py.
 */

#include "afl-fuzz.h"

#include <stdarg.h>
#include <stdio.h>
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

static struct queue_entry mk(u64 cov, u64 sel) {

  struct queue_entry q;
  memset(&q, 0, sizeof(q));
  q.ss_cov_cnt = cov;
  q.ss_selected_cnt = sel;
  return q;

}

/* The case named in the P0 brief. */
static void test_security_state_credit_raises_weight(void) {

  struct queue_entry a = mk(5, 1); /* reached 5 new security states */
  struct queue_entry b = mk(0, 1); /* reached none                  */

  double wa = ss_calc_prob(&a);
  double wb = ss_calc_prob(&b);

  printf("WEIGHT security_state_credit_raises_weight cov5=%.6f cov0=%.6f "
         "ratio=%.6f\n", wa, wb, wb > 0 ? wa / wb : 0.0);

  expect(wa > wb, "security_state_credit_raises_weight",
         "expected weight(cov=5,sel=1)=%.6f > weight(cov=0,sel=1)=%.6f", wa,
         wb);

}

/* (cov+1)/(sel+1)^0.7 -- with equal selection counts the ratio is exactly
   (5+1)/(0+1) = 6. */
static void test_weight_scales_with_security_state_count(void) {

  struct queue_entry a = mk(5, 1);
  struct queue_entry b = mk(0, 1);

  double ratio = ss_calc_prob(&a) / ss_calc_prob(&b);

  expect(ratio > 5.999 && ratio < 6.001,
         "weight_scales_with_security_state_count",
         "expected ratio 6.0 for cov 5 vs 0 at equal selection, got %.6f",
         ratio);

}

static void test_over_selection_suppresses_weight(void) {

  struct queue_entry fresh = mk(2, 1);
  struct queue_entry tired = mk(2, 50);

  expect(ss_calc_prob(&fresh) > ss_calc_prob(&tired),
         "over_selection_suppresses_weight",
         "expected an over-selected seed to weigh less: %.6f vs %.6f",
         ss_calc_prob(&fresh), ss_calc_prob(&tired));

}

static void test_weight_has_a_floor(void) {

  struct queue_entry starved = mk(0, 1000000);

  expect(ss_calc_prob(&starved) >= 0.01, "weight_has_a_floor",
         "expected the 0.01 floor, got %.9f", ss_calc_prob(&starved));

}

int main(void) {

  test_security_state_credit_raises_weight();
  test_weight_scales_with_security_state_count();
  test_over_selection_suppresses_weight();
  test_weight_has_a_floor();

  printf("FAILURES %d\n", g_failures);
  return g_failures ? 1 : 0;

}
