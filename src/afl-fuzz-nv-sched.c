/*
   american fuzzy lop++ - SS seed-scheduling weight
   ------------------------------------------------

   The coverage-weighted roulette used by select_next_queue_entry() scores a
   queue entry from the number of security states it reached and how often it
   has already been selected.  It lives in its own translation unit so the
   weight can be asserted directly by a unit test.  Behaviour is identical to
   the previous static definition in afl-fuzz-queue.c.

 */

#include "afl-fuzz.h"

#include <math.h>

double ss_calc_prob(struct queue_entry *q) {

  const double eps = 0.01;     /* minimum probability floor */
  const double alpha = 0.7;    /* suppress over-selected seeds */

  /* (cov+1) / (sel+1)^alpha */
  double num = (double)(q->ss_cov_cnt + 1ULL);
  double den = pow((double)(q->ss_selected_cnt + 1ULL), alpha);
  double score = num / den;

  return (score < eps) ? eps : score;

}
