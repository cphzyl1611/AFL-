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
#include <fcntl.h>
#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

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

int nv_mab_terminal_ledger_suppresses_cleanup(const char *outcome) {

  return outcome && strcmp(outcome, "arm_mismatch") == 0;

}

void nv_mab_begin_pending(afl_state_t *afl, nv_arm_id_t selected_arm,
                          nv_arm_id_t actual_used_arm, u64 iteration_id,
                          u8 update_source) {

  if (!afl) return;
  afl->nv_mab.pending_arm = actual_used_arm;
  afl->nv_mab.pending_selected_arm = selected_arm;
  afl->nv_mab.pending_selected_valid = 1;
  afl->nv_mab.pending_iteration = iteration_id;
  afl->nv_mab.pending_update = 1;
  afl->nv_mab.pending_ledger_terminal_recorded = 0;
  afl->nv_mab.update_source = update_source;

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

static nv_mab_journal_write_hook_t nv_mab_journal_write_hook;

void nv_mab_journal_set_write_hook(nv_mab_journal_write_hook_t hook) {

  nv_mab_journal_write_hook = hook;

}

static int nv_mab_journal_write(afl_state_t *afl, const char *line,
                                 size_t len) {

  const char *path = getenv("NV_MAB_JOURNAL_PATH");
  if (!path || !*path) return 1;
  afl->nv_mab_journal_enabled = 1;

  int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0644);
  if (fd < 0) goto failed;

  size_t written = 0;
  while (written < len) {
    ssize_t n = nv_mab_journal_write_hook
                    ? nv_mab_journal_write_hook(fd, line + written,
                                                len - written)
                    : write(fd, line + written, len - written);
    if (n <= 0) {
      close(fd);
      goto failed;
    }
    written += (size_t)n;
  }

  if (fsync(fd) < 0) {
    close(fd);
    goto failed;
  }
  if (close(fd) < 0) goto failed;
  afl->nv_mab_journal_record_count++;
  return 1;

failed:
  afl->nv_mab_journal_error_count++;
  afl->nv_mab_journal_audit_invalid = 1;
  afl->stop_soon = 1;
  fprintf(stderr, "NV_MAB_JOURNAL_ERROR path=%s errno=%d\n", path, errno);
  return 0;

}

int nv_mab_journal_commit_update(afl_state_t *afl,
                                 const nv_mab_journal_update_t *update) {

  if (!afl || !update || update->selected_arm < 0 ||
      update->selected_arm >= NV_ARM_MAX || update->actual_used_arm < 0 ||
      update->actual_used_arm >= NV_ARM_MAX || !update->arm_match ||
      update->exec_seq == 0) return 0;

  nv_arm_t *arm = &afl->nv_mab.arms[update->actual_used_arm];
  u64 pulls_before = arm->pulls;
  double sum_before = arm->sum_reward;

  /* The aggregate is authoritative and is intentionally committed before the
     append.  A failed append invalidates the audit but never rolls back MAB. */
  nv_mab_update(&afl->nv_mab, update->actual_used_arm, update->reward);
  arm = &afl->nv_mab.arms[update->actual_used_arm];

  char line[2048];
  int n = snprintf(
      line, sizeof(line),
      "{\"schema_version\":1,\"event\":\"mab_update\","
      "\"exec_seq\":%llu,\"selected_arm\":%d,\"actual_used_arm\":%d,"
      "\"arm_match\":%s,\"reward\":%.17g,\"reward_components\":{"
      "\"harness_native_coverage\":%.17g,\"security_state\":%.17g,"
      "\"exception\":%.17g,\"recovery\":%.17g,"
      "\"http_4xx_penalty\":%.17g},\"security_state_new\":%u,"
      "\"pulls_before\":%llu,\"pulls_after\":%llu,"
      "\"sum_before\":%.17g,\"sum_after\":%.17g,\"mean_after\":%.17g,"
      "\"positive_after\":%llu,\"update_source\":%u}\n",
      (unsigned long long)update->exec_seq, (int)update->selected_arm,
      (int)update->actual_used_arm, update->arm_match ? "true" : "false",
      update->reward, update->harness_native_coverage, update->security_state,
      update->exception, update->recovery, update->http_4xx_penalty,
      (unsigned)update->security_state_new,
      (unsigned long long)pulls_before, (unsigned long long)arm->pulls,
      sum_before, arm->sum_reward, arm->mean_reward,
      (unsigned long long)arm->pos_cnt, (unsigned)update->update_source);
  if (n < 0 || (size_t)n >= sizeof(line)) {
    afl->nv_mab_journal_error_count++;
    afl->nv_mab_journal_audit_invalid = 1;
    afl->stop_soon = 1;
    fprintf(stderr, "NV_MAB_JOURNAL_ERROR record_too_large\n");
    return 0;
  }
  return nv_mab_journal_write(afl, line, (size_t)n);

}

int nv_mab_journal_append_event(afl_state_t *afl, const char *event,
                                const char *reason,
                                nv_arm_id_t selected_arm,
                                nv_arm_id_t actual_used_arm) {

  if (!afl || !event || !*event) return 0;
  char line[512];
  int n = snprintf(line, sizeof(line),
                   "{\"schema_version\":1,\"event\":\"%s\","
                   "\"reason\":\"%s\",\"selected_arm\":%d,"
                   "\"actual_used_arm\":%d}\n",
                   event, reason ? reason : "", (int)selected_arm,
                   (int)actual_used_arm);
  if (n < 0 || (size_t)n >= sizeof(line)) return 0;
  int ok = nv_mab_journal_write(afl, line, (size_t)n);
  if (ok && strcmp(event, "mab_pending_cleared") == 0)
    afl->nv_mab_journal_pending_cleared_count++;
  if (ok && strcmp(event, "mab_update_mismatch") == 0)
    afl->nv_mab_journal_mismatch_count++;
  return ok;

}

int nv_mab_journal_clear_pending(afl_state_t *afl, const char *reason) {

  if (!afl || !afl->nv_mab.pending_update) return 1;
  nv_arm_id_t arm = afl->nv_mab.pending_arm;
  nv_arm_id_t selected_arm = afl->nv_mab.pending_selected_valid
                               ? afl->nv_mab.pending_selected_arm : arm;
  u64 iteration = afl->nv_mab.pending_iteration;
  int ok = nv_mab_journal_append_event(afl, "mab_pending_cleared", reason,
                                       selected_arm, arm);
  /* The MAB journal schema remains unchanged.  The execution ledger carries
     the pending lifecycle's iteration/arm correlation. */
  if (ok && iteration && !afl->nv_mab.pending_ledger_terminal_recorded &&
      getenv("NV_EXECUTION_LEDGER_PATH")) {
    if (!nv_execution_ledger_append(afl, iteration, selected_arm, arm, 0, 1,
                                    0, 0, 0, 0, 0, "pending_cleanup",
                                    reason))
      ok = 0;
  }
  afl->nv_mab.pending_update = 0;
  afl->nv_mab.pending_iteration = 0;
  afl->nv_mab.pending_selected_arm = NV_ARM_FIELD_VALUE;
  afl->nv_mab.pending_selected_valid = 0;
  afl->nv_mab.pending_ledger_terminal_recorded = 0;
  afl->nv_mab.update_source = 0;
  return ok;

}

int nv_execution_ledger_append(afl_state_t *afl, u64 iteration_id,
                               nv_arm_id_t selected_arm,
                               nv_arm_id_t actual_used_arm,
                               u8 counted_execution, u8 harness_invoked,
                               u8 target_invoked, u8 body_validated,
                               u8 status_observed, u64 exec_seq,
                               int http_status, const char *outcome,
                               const char *cleanup_reason) {

  const char *path = getenv("NV_EXECUTION_LEDGER_PATH");
  if (!path || !*path) return 1;
  if (!outcome || !*outcome || iteration_id == 0 ||
      selected_arm < 0 || selected_arm >= NV_ARM_MAX ||
      ((actual_used_arm < 0 || actual_used_arm >= NV_ARM_MAX) &&
       actual_used_arm != NV_ARM_MAX) ||
      (!status_observed && exec_seq != 0)) {
    afl->nv_execution_ledger_audit_invalid = 1;
    afl->nv_execution_ledger_error_count++;
    return 0;
  }

  /* A status document without a positive execution identity is never a
     terminal target observation.  Preserve the explicit invalid outcome, but
     force the serialized identity into the unavailable domain. */
  if (status_observed && exec_seq == 0) {
    status_observed = 0;
    if (strcmp(outcome, "invalid_exec_identity") != 0) {
      afl->nv_execution_ledger_audit_invalid = 1;
      afl->nv_execution_ledger_error_count++;
      return 0;
    }
  }

  afl->nv_execution_ledger_enabled = 1;
  char line[1024];
  char seq[32];
  const char *reason = cleanup_reason ? cleanup_reason : "";
  if (status_observed && exec_seq > 0)
    snprintf(seq, sizeof(seq), "%llu", (unsigned long long)exec_seq);
  else
    snprintf(seq, sizeof(seq), "null");
  int n = snprintf(line, sizeof(line),
      "{\"schema_version\":1,\"event\":\"execution\","
      "\"iteration_id\":%llu,\"input_id\":\"unavailable\","
      "\"stage\":\"fuzz\",\"selected_arm\":%d,"
      "\"actual_used_arm\":%d,\"arm_match\":%s,"
      "\"counted_execution\":%s,\"harness_invoked\":%s,"
      "\"target_invoked\":%s,\"body_validated\":%s,"
      "\"status_observed\":%s,\"exec_seq\":%s,"
      "\"http_status\":%d,\"mab_outcome\":\"%s\","
      "\"pending_cleanup_reason\":%s}\n",
      (unsigned long long)iteration_id, (int)selected_arm,
      (int)actual_used_arm,
      (actual_used_arm == selected_arm) ? "true" : "false",
      counted_execution ? "true" : "false", harness_invoked ? "true" : "false",
      target_invoked ? "true" : "false", body_validated ? "true" : "false",
      status_observed ? "true" : "false", seq,
       http_status, outcome,
       cleanup_reason ? (strcmp(reason, "budget_boundary") == 0 ?
                         "\"budget_boundary\"" :
                         strcmp(reason, "invalid_input") == 0 ?
                         "\"invalid_input\"" :
                         strcmp(reason, "invalid_exec_identity") == 0 ?
                         "\"invalid_exec_identity\"" :
                         strcmp(reason, "pending_no_exec_id") == 0 ?
                         "\"pending_no_exec_id\"" :
                         strcmp(reason, "arm_mismatch") == 0 ?
                         "\"arm_mismatch\"" :
                         strcmp(reason, "timeout") == 0 ? "\"timeout\"" :
                         strcmp(reason, "skip") == 0 ? "\"skip\"" :
                         "\"stop_soon\"") : "null");
  if (n < 0 || (size_t)n >= sizeof(line)) goto failed;
  int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0644);
  if (fd < 0) goto failed;
  size_t off = 0;
  while (off < (size_t)n) {
    ssize_t written = write(fd, line + off, (size_t)n - off);
    if (written <= 0) { close(fd); goto failed; }
    off += (size_t)written;
  }
  if (fsync(fd) < 0 || close(fd) < 0) goto failed;
  afl->nv_execution_ledger_record_count++;
  return 1;

failed:
  afl->nv_execution_ledger_audit_invalid = 1;
  afl->nv_execution_ledger_error_count++;
  afl->stop_soon = 1;
  return 0;
}
