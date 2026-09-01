/* Offline unit coverage for the per-update NV MAB JSONL audit trail. */

#include "afl-fuzz.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>

static int failures;

static int scripted_write_calls;
static ssize_t scripted_partial_then_failure(int fd, const void *buf,
                                             size_t len) {

  ++scripted_write_calls;
  if (scripted_write_calls == 1) {
    size_t partial = len > 1 ? len / 2 : 0;
    return partial ? write(fd, buf, partial) : -1;
  }
  errno = EIO;
  return -1;

}

static void expect(int condition, const char *name, const char *fmt, ...) {

  if (condition) {

    printf("PASS %s\n", name);

  } else {

    va_list ap;
    printf("FAIL %s: ", name);
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    printf("\n");
    ++failures;

  }

}

static void read_file(const char *path, char *out, size_t size) {

  FILE *f = fopen(path, "rb");
  size_t n = f ? fread(out, 1, size - 1, f) : 0;
  if (f) fclose(f);
  out[n] = 0;

}

static void test_update_record_and_zero_reward(void) {

  char path[] = "/tmp/nv-mab-journal-unit-XXXXXX";
  int fd = mkstemp(path);
  afl_state_t afl;
  nv_mab_journal_update_t update;
  char content[8192];

  memset(&afl, 0, sizeof(afl));
  memset(&update, 0, sizeof(update));
  if (fd >= 0) close(fd);
  setenv("NV_MAB_JOURNAL_PATH", path, 1);

  update.exec_seq = 4;
  update.selected_arm = NV_ARM_FIELD_VALUE;
  update.actual_used_arm = NV_ARM_FIELD_VALUE;
  update.arm_match = 1;
  update.reward = 10.0;
  update.harness_native_coverage = 0.0;
  update.security_state = 10.0;
  update.security_state_new = 1;
  update.update_source = 1;
  expect(nv_mab_journal_commit_update(&afl, &update), "journal_positive_update",
         "commit failed");

  update.exec_seq = 5;
  update.reward = 0.0;
  update.security_state = 0.0;
  update.security_state_new = 0;
  expect(nv_mab_journal_commit_update(&afl, &update), "journal_zero_reward_update",
         "zero-reward commit failed");

  read_file(path, content, sizeof(content));
  expect(strstr(content, "\"schema_version\":1") &&
             strstr(content, "\"event\":\"mab_update\"") &&
             strstr(content, "\"exec_seq\":4") &&
             strstr(content, "\"actual_used_arm\":0") &&
             strstr(content, "\"security_state\":10") &&
             strstr(content, "\"pulls_before\":0") &&
             strstr(content, "\"pulls_after\":1") &&
             strstr(content, "\"reward\":0"),
         "journal_schema_contains_required_update_fields",
         "record did not contain expected schema: %s", content);
  expect(afl.nv_mab.total_pulls == 2 && afl.nv_mab.arms[0].pulls == 2 &&
             afl.nv_mab.arms[0].pos_cnt == 1 &&
             afl.nv_mab_journal_record_count == 2,
         "journal_update_aggregate_ordering",
         "pulls=%llu arm=%llu pos=%llu records=%llu",
         (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab.arms[0].pulls,
         (unsigned long long)afl.nv_mab.arms[0].pos_cnt,
         (unsigned long long)afl.nv_mab_journal_record_count);

  unsetenv("NV_MAB_JOURNAL_PATH");
  unlink(path);

}

static void test_open_failure_is_fail_closed_after_aggregate(void) {

  afl_state_t afl;
  nv_mab_journal_update_t update;

  memset(&afl, 0, sizeof(afl));
  memset(&update, 0, sizeof(update));
  setenv("NV_MAB_JOURNAL_PATH", "/proc/nv-mab-journal-forbidden", 1);
  update.exec_seq = 9;
  update.selected_arm = NV_ARM_BOUNDARY;
  update.actual_used_arm = NV_ARM_BOUNDARY;
  update.arm_match = 1;
  update.update_source = 1;

  expect(!nv_mab_journal_commit_update(&afl, &update),
         "journal_open_failure_returns_failure", "open failure was accepted");
  expect(afl.nv_mab.total_pulls == 1 && afl.nv_mab.arms[1].pulls == 1 &&
             afl.nv_mab_journal_error_count == 1 &&
             afl.nv_mab_journal_audit_invalid && afl.stop_soon,
         "journal_open_failure_marks_audit_invalid_without_rollback",
         "pulls=%llu errors=%llu invalid=%u stop=%u",
         (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab_journal_error_count,
         (unsigned)afl.nv_mab_journal_audit_invalid, (unsigned)afl.stop_soon);
  unsetenv("NV_MAB_JOURNAL_PATH");

}

static void test_write_and_flush_failures_are_not_counted(void) {

  const char *paths[] = {"/dev/full", "/dev/null"};
  const char *names[] = {"journal_write_failure_is_fail_closed",
                         "journal_flush_failure_is_fail_closed"};
  for (size_t i = 0; i < 2; ++i) {
    afl_state_t afl;
    nv_mab_journal_update_t update;
    memset(&afl, 0, sizeof(afl));
    memset(&update, 0, sizeof(update));
    setenv("NV_MAB_JOURNAL_PATH", paths[i], 1);
    update.exec_seq = 20 + i;
    update.selected_arm = NV_ARM_STRUCTURE;
    update.actual_used_arm = NV_ARM_STRUCTURE;
    update.arm_match = 1;
    update.update_source = 1;
    expect(!nv_mab_journal_commit_update(&afl, &update) &&
               afl.nv_mab.total_pulls == 1 &&
               afl.nv_mab_journal_record_count == 0 &&
               afl.nv_mab_journal_error_count == 1 &&
               afl.nv_mab_journal_audit_invalid && afl.stop_soon,
           names[i], "path=%s pulls=%llu records=%llu errors=%llu", paths[i],
           (unsigned long long)afl.nv_mab.total_pulls,
           (unsigned long long)afl.nv_mab_journal_record_count,
           (unsigned long long)afl.nv_mab_journal_error_count);
  }
  unsetenv("NV_MAB_JOURNAL_PATH");

}

static void test_non_update_events_are_distinct(void) {

  char path[] = "/tmp/nv-mab-events-unit-XXXXXX";
  int fd = mkstemp(path);
  afl_state_t afl;
  char content[2048];
  memset(&afl, 0, sizeof(afl));
  if (fd >= 0) close(fd);
  setenv("NV_MAB_JOURNAL_PATH", path, 1);

  int pending_ok = nv_mab_journal_append_event(
      &afl, "mab_pending_cleared", "budget_boundary", NV_ARM_FIELD_VALUE,
      NV_ARM_FIELD_VALUE);
  int mismatch_ok = nv_mab_journal_append_event(
      &afl, "mab_update_mismatch", "", NV_ARM_BOUNDARY, NV_ARM_STRUCTURE);
  read_file(path, content, sizeof(content));
  expect(pending_ok && mismatch_ok &&
             strstr(content, "\"event\":\"mab_pending_cleared\"") &&
             strstr(content, "\"reason\":\"budget_boundary\"") &&
             strstr(content, "\"event\":\"mab_update_mismatch\"") &&
             strstr(content, "\"selected_arm\":1") &&
             strstr(content, "\"actual_used_arm\":2") &&
             afl.nv_mab.total_pulls == 0 &&
             afl.nv_mab_journal_pending_cleared_count == 1 &&
             afl.nv_mab_journal_mismatch_count == 1,
         "journal_non_update_events_do_not_increment_pulls", "%s", content);
  unsetenv("NV_MAB_JOURNAL_PATH");
  unlink(path);

}

static void test_terminal_marker_only_suppresses_duplicate_mismatch_cleanup(void) {

  afl_state_t afl;
  memset(&afl, 0, sizeof(afl));

  expect(nv_mab_terminal_ledger_suppresses_cleanup("arm_mismatch"),
         "terminal_marker_for_mismatch",
         "mismatch terminal marker was not recognized");
  expect(!nv_mab_terminal_ledger_suppresses_cleanup("invalid_exec_identity"),
         "invalid_identity_does_not_suppress_cleanup",
         "invalid identity incorrectly suppressed cleanup");

}

static void test_begin_pending_resets_terminal_marker(void) {

  afl_state_t afl;
  memset(&afl, 0, sizeof(afl));
  afl.nv_mab.pending_ledger_terminal_recorded = 1;

  nv_mab_begin_pending(&afl, NV_ARM_BOUNDARY, NV_ARM_BOUNDARY, 7, 1);

  expect(afl.nv_mab.pending_update &&
             afl.nv_mab.pending_arm == NV_ARM_BOUNDARY &&
             afl.nv_mab.pending_selected_arm == NV_ARM_BOUNDARY &&
             afl.nv_mab.pending_selected_valid &&
             afl.nv_mab.pending_iteration == 7 &&
             afl.nv_mab.update_source == 1 &&
             !afl.nv_mab.pending_ledger_terminal_recorded,
         "begin_pending_resets_terminal_marker",
         "pending=%u terminal=%u iteration=%llu",
         (unsigned)afl.nv_mab.pending_update,
         (unsigned)afl.nv_mab.pending_ledger_terminal_recorded,
         (unsigned long long)afl.nv_mab.pending_iteration);

}

static void test_execution_ledger_record_and_invalid_identity(void) {

  char path[] = "/tmp/nv-execution-ledger-unit-XXXXXX";
  int fd = mkstemp(path);
  afl_state_t afl;
  char content[4096];
  memset(&afl, 0, sizeof(afl));
  if (fd >= 0) close(fd);
  setenv("NV_EXECUTION_LEDGER_PATH", path, 1);
  expect(nv_execution_ledger_append(
             &afl, 1, NV_ARM_FIELD_VALUE, NV_ARM_FIELD_VALUE, 1, 1, 1, 1,
             1, 4, 200, "committed_update", NULL),
         "execution_ledger_record", "append failed");
  expect(nv_execution_ledger_append(
             &afl, 2, NV_ARM_BOUNDARY, NV_ARM_BOUNDARY, 1, 1, 1, 1, 0, 0,
             0, "invalid_exec_identity", NULL),
         "execution_ledger_null_identity", "append failed");
  read_file(path, content, sizeof(content));
  expect(strstr(content, "\"iteration_id\":1") &&
             strstr(content, "\"exec_seq\":4") &&
             strstr(content, "\"exec_seq\":null") &&
             strstr(content, "\"mab_outcome\":\"invalid_exec_identity\""),
         "execution_ledger_schema", "unexpected ledger: %s", content);
  expect(afl.nv_execution_ledger_record_count == 2 &&
             !afl.nv_execution_ledger_audit_invalid,
         "execution_ledger_aggregate", "records=%llu invalid=%u",
         (unsigned long long)afl.nv_execution_ledger_record_count,
         (unsigned)afl.nv_execution_ledger_audit_invalid);
  unsetenv("NV_EXECUTION_LEDGER_PATH");
  unlink(path);

}

static void test_non_update_event_failure_is_fail_closed(void) {

  afl_state_t afl;
  memset(&afl, 0, sizeof(afl));
  setenv("NV_MAB_JOURNAL_PATH", "/dev/full", 1);
  expect(!nv_mab_journal_append_event(
             &afl, "mab_update_mismatch", "", NV_ARM_FIELD_VALUE,
             NV_ARM_BOUNDARY) &&
             afl.nv_mab.total_pulls == 0 &&
             afl.nv_mab_journal_record_count == 0 &&
             afl.nv_mab_journal_error_count == 1 &&
             afl.nv_mab_journal_audit_invalid && afl.stop_soon,
         "journal_non_update_failure_is_fail_closed",
         "records=%llu errors=%llu invalid=%u stop=%u",
         (unsigned long long)afl.nv_mab_journal_record_count,
         (unsigned long long)afl.nv_mab_journal_error_count,
         (unsigned)afl.nv_mab_journal_audit_invalid, (unsigned)afl.stop_soon);
  unsetenv("NV_MAB_JOURNAL_PATH");

}

static void test_partial_write_then_failure_marks_audit_invalid(void) {

  char path[] = "/tmp/nv-mab-partial-unit-XXXXXX";
  int fd = mkstemp(path);
  afl_state_t afl;
  nv_mab_journal_update_t update;
  char content[4096];

  memset(&afl, 0, sizeof(afl));
  memset(&update, 0, sizeof(update));
  if (fd >= 0) close(fd);
  update.exec_seq = 31;
  update.selected_arm = NV_ARM_FIELD_VALUE;
  update.actual_used_arm = NV_ARM_FIELD_VALUE;
  update.arm_match = 1;
  update.update_source = 1;
  setenv("NV_MAB_JOURNAL_PATH", path, 1);
  scripted_write_calls = 0;
  nv_mab_journal_set_write_hook(scripted_partial_then_failure);

  int ok = nv_mab_journal_commit_update(&afl, &update);
  nv_mab_journal_set_write_hook(NULL);
  read_file(path, content, sizeof(content));
  expect(!ok && scripted_write_calls == 2 && afl.nv_mab.total_pulls == 1 &&
             afl.nv_mab.arms[0].pulls == 1 &&
             afl.nv_mab_journal_record_count == 0 &&
             afl.nv_mab_journal_error_count == 1 &&
             afl.nv_mab_journal_audit_invalid && afl.stop_soon &&
             content[0] != 0 && content[strlen(content) - 1] != '\n',
         "partial_write_then_failure_marks_audit_invalid",
         "ok=%d calls=%d pulls=%llu records=%llu errors=%llu content_len=%zu",
         ok, scripted_write_calls, (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab_journal_record_count,
         (unsigned long long)afl.nv_mab_journal_error_count, strlen(content));
  unsetenv("NV_MAB_JOURNAL_PATH");
  unlink(path);

}

static void test_commit_rejects_zero_exec_seq(void) {

  char path[] = "/tmp/nv-mab-zero-seq-unit-XXXXXX";
  int fd = mkstemp(path);
  afl_state_t afl;
  nv_mab_journal_update_t update;

  memset(&afl, 0, sizeof(afl));
  memset(&update, 0, sizeof(update));
  if (fd >= 0) close(fd);
  setenv("NV_MAB_JOURNAL_PATH", path, 1);

  update.exec_seq = 0;
  update.selected_arm = NV_ARM_BOUNDARY;
  update.actual_used_arm = NV_ARM_BOUNDARY;
  update.arm_match = 1;
  update.reward = 0.0;
  update.update_source = 1;
  afl.nv_mab.pending_update = 1;
  afl.nv_mab.pending_arm = NV_ARM_BOUNDARY;
  expect(!nv_mab_journal_commit_update(&afl, &update),
         "journal_rejects_zero_exec_seq_commit",
         "committed mab_update with exec_seq=0");

  expect(nv_mab_journal_clear_pending(&afl, "invalid_exec_identity") &&
             !afl.nv_mab.pending_update &&
             afl.nv_mab_journal_pending_cleared_count == 1,
         "journal_zero_exec_seq_pending_is_cleared",
         "zero-seq pending arm was not cleared");

  expect(afl.nv_mab.total_pulls == 0 &&
             afl.nv_mab.arms[1].pulls == 0 &&
             afl.nv_mab_journal_record_count == 1,
         "journal_zero_exec_seq_does_not_increment_aggregate",
         "pulls=%llu arm=%llu records=%llu",
         (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab.arms[1].pulls,
          (unsigned long long)afl.nv_mab_journal_record_count);

  unsetenv("NV_MAB_JOURNAL_PATH");
  unlink(path);

}

static void test_commit_rejects_arm_identity_mismatch(void) {

  char path[] = "/tmp/nv-mab-mismatch-unit-XXXXXX";
  int fd = mkstemp(path);
  afl_state_t afl;
  nv_mab_journal_update_t update;

  memset(&afl, 0, sizeof(afl));
  memset(&update, 0, sizeof(update));
  if (fd >= 0) close(fd);
  setenv("NV_MAB_JOURNAL_PATH", path, 1);
  update.exec_seq = 7;
  update.selected_arm = NV_ARM_FIELD_VALUE;
  update.actual_used_arm = NV_ARM_BOUNDARY;
  update.arm_match = 0;
  update.reward = 100.0;
  expect(!nv_mab_journal_commit_update(&afl, &update) &&
             afl.nv_mab.total_pulls == 0 &&
             afl.nv_mab_journal_record_count == 0,
         "journal_arm_mismatch_is_rejected",
         "mismatched arms changed aggregate");
  unsetenv("NV_MAB_JOURNAL_PATH");
  unlink(path);

}

static void test_commit_rejects_missing_actual_arm(void) {

  char path[] = "/tmp/nv-mab-missing-arm-unit-XXXXXX";
  int fd = mkstemp(path);
  afl_state_t afl;
  nv_mab_journal_update_t update;

  memset(&afl, 0, sizeof(afl));
  memset(&update, 0, sizeof(update));
  if (fd >= 0) close(fd);
  setenv("NV_MAB_JOURNAL_PATH", path, 1);
  update.exec_seq = 8;
  update.selected_arm = NV_ARM_BOUNDARY;
  update.actual_used_arm = NV_ARM_MAX;
  update.arm_match = 1;
  update.reward = 100.0;
  expect(!nv_mab_journal_commit_update(&afl, &update) &&
             afl.nv_mab.total_pulls == 0 &&
             afl.nv_mab_journal_record_count == 0,
         "journal_missing_actual_arm_is_rejected",
         "missing actual arm changed aggregate");
  unsetenv("NV_MAB_JOURNAL_PATH");
  unlink(path);

}

static void test_pending_without_valid_exec_id_is_cleared_not_committed(void) {

  char path[] = "/tmp/nv-mab-novid-unit-XXXXXX";
  int fd = mkstemp(path);
  afl_state_t afl;
  nv_mab_journal_update_t update;
  char content[4096];

  memset(&afl, 0, sizeof(afl));
  memset(&update, 0, sizeof(update));
  if (fd >= 0) close(fd);
  setenv("NV_MAB_JOURNAL_PATH", path, 1);

  afl.nv_mab.pending_update = 1;
  afl.nv_mab.pending_arm = NV_ARM_BOUNDARY;
  afl.nv_mab.update_source = 1;

  int cleared = nv_mab_journal_clear_pending(&afl, "pending_no_exec_id");
  read_file(path, content, sizeof(content));

  expect(cleared && !afl.nv_mab.pending_update,
         "journal_clears_pending_without_exec_id",
         "pending not cleared");
  expect(afl.nv_mab.total_pulls == 0 &&
             afl.nv_mab.arms[1].pulls == 0 &&
             afl.nv_mab_journal_record_count == 1 &&
             afl.nv_mab_journal_pending_cleared_count == 1,
         "journal_no_exec_id_clear_does_not_count_as_update",
         "pulls=%llu arm=%llu records=%llu cleared=%llu",
         (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab.arms[1].pulls,
         (unsigned long long)afl.nv_mab_journal_record_count,
         (unsigned long long)afl.nv_mab_journal_pending_cleared_count);
  expect(strstr(content, "\"event\":\"mab_pending_cleared\"") &&
             strstr(content, "\"reason\":\"pending_no_exec_id\"") &&
             strstr(content, "\"selected_arm\":1") &&
             strstr(content, "\"actual_used_arm\":1") &&
             !strstr(content, "\"event\":\"mab_update\""),
         "journal_no_exec_id_line_is_clear_event_not_update",
         "content=%s", content);

  unsetenv("NV_MAB_JOURNAL_PATH");
  unlink(path);

}

static void test_each_pending_clear_reason_is_a_non_update_event(void) {

  const char *reasons[] = {"budget_boundary", "stop_soon", "timeout",
                           "invalid_input", "skip"};
  for (size_t i = 0; i < sizeof(reasons) / sizeof(reasons[0]); ++i) {
    char path[] = "/tmp/nv-mab-reason-unit-XXXXXX";
    int fd = mkstemp(path);
    afl_state_t afl;
    char content[1024];
    memset(&afl, 0, sizeof(afl));
    if (fd >= 0) close(fd);
    afl.nv_mab.pending_update = 1;
    afl.nv_mab.pending_arm = NV_ARM_BOUNDARY;
    setenv("NV_MAB_JOURNAL_PATH", path, 1);
    expect(nv_mab_journal_clear_pending(&afl, reasons[i]) &&
               !afl.nv_mab.pending_update && afl.nv_mab.total_pulls == 0 &&
               afl.nv_mab.arms[1].pulls == 0 &&
               afl.nv_mab_journal_record_count == 1,
           reasons[i], "cleanup did not preserve aggregate");
    read_file(path, content, sizeof(content));
    expect(strstr(content, "\"event\":\"mab_pending_cleared\"") &&
               strstr(content, reasons[i]) && !strstr(content, "mab_update\""),
           "pending_clear_jsonl_is_not_update", "reason=%s content=%s",
           reasons[i], content);
    unsetenv("NV_MAB_JOURNAL_PATH");
    unlink(path);
  }

}

int main(void) {

  test_update_record_and_zero_reward();
  test_open_failure_is_fail_closed_after_aggregate();
  test_write_and_flush_failures_are_not_counted();
  test_non_update_events_are_distinct();
  test_begin_pending_resets_terminal_marker();
  test_execution_ledger_record_and_invalid_identity();
  test_non_update_event_failure_is_fail_closed();
  test_partial_write_then_failure_marks_audit_invalid();
  test_each_pending_clear_reason_is_a_non_update_event();
  test_commit_rejects_zero_exec_seq();
  test_pending_without_valid_exec_id_is_cleared_not_committed();
  test_commit_rejects_arm_identity_mismatch();
  test_commit_rejects_missing_actual_arm();
  printf("FAILURES %d\n", failures);
  return failures ? 1 : 0;

}
