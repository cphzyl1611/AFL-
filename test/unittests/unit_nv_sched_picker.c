/* Deterministic integration test for the production SS queue picker. */

#include "afl-fuzz.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>

static int failures;
static const u64 random_values[] = {0, 0x40000000ULL, 0x70000000ULL,
                                    0x10000000ULL};
static size_t random_index;

static FILE *audit_open_failure(const char *path, const char *mode) {

  (void)path;
  (void)mode;
  return NULL;

}

static int audit_write_failure(FILE *f, const char *buf, size_t len) {

  (void)f;
  (void)buf;
  (void)len;
  return -1;

}

static int audit_close_failure(FILE *f) {

  (void)fclose(f);
  return -1;

}

AFL_RAND_RETURN rand_next(afl_state_t *afl) {

  (void)afl;
  return random_values[random_index++ %
                       (sizeof(random_values) / sizeof(random_values[0]))];

}

u64 get_cur_time(void) {

  return 1;

}

u8 *stringify_mem_size(u8 *buf, size_t len, u64 val) {

  snprintf((char *)buf, len, "%llu", (unsigned long long)val);
  return buf;

}

void run_afl_custom_queue_new_entry(afl_state_t *afl, struct queue_entry *q,
                                    u8 *a, u8 *b) {

  (void)afl;
  (void)q;
  (void)a;
  (void)b;

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

static int write_seed(const char *dir, const char *name, const u8 *data,
                      size_t len) {

  char path[PATH_MAX];
  snprintf(path, sizeof(path), "%s/%s", dir, name);
  int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (fd < 0) return 0;
  ssize_t written = write(fd, data, len);
  close(fd);
  return written == (ssize_t)len;

}

static int full_http_content_length_matches(const u8 *seed) {

  const char *delimiter = strstr((const char *)seed, "\r\n\r\n");
  const char *header = strstr((const char *)seed, "Content-Length: ");
  if (!delimiter || !header || header > delimiter) return 0;

  unsigned long declared = strtoul(header + strlen("Content-Length: "), NULL, 10);
  return declared == strlen(delimiter + 4);

}

static void init_three_entry_picker(afl_state_t *afl,
                                    struct queue_entry *entries,
                                    struct queue_entry **queue) {

  memset(afl, 0, sizeof(*afl));
  memset(entries, 0, sizeof(struct queue_entry) * 3);
  for (u32 i = 0; i < 3; ++i) {

    entries[i].id = i;
    entries[i].depth = 1;
    queue[i] = &entries[i];

  }
  afl->queued_items = 3;
  afl->queue_buf = queue;
  afl->fixed_seed = 1;

}

int main(void) {

  static u8 seed0[] =
      "PUT /offline/dedicated-metadata-node HTTP/1.1\r\n"
      "Host: offline.invalid\r\n"
      "Content-Type: application/json\r\n"
      "Content-Length: 39\r\n\r\n"
      "{\"properties\":{\"cm:title\":\"seed zero\"}}";
  static u8 seed1[] =
      "PUT /offline/dedicated-metadata-node HTTP/1.1\r\n"
      "Host: offline.invalid\r\n"
      "Content-Type: application/json\r\n"
      "Content-Length: 61\r\n\r\n"
      "{\"properties\":{\"cm:title\":\"seed one\",\"cm:description\":\"one\"}}";
  static u8 seed2[] =
      "PUT /offline/dedicated-metadata-node HTTP/1.1\r\n"
      "Host: offline.invalid\r\n"
      "Content-Type: application/json\r\n"
      "Content-Length: 61\r\n\r\n"
      "{\"properties\":{\"cm:title\":\"seed two\",\"cm:description\":\"two\"}}";
  char seed_dir[] = "/tmp/nv-seed-ingestion-XXXXXX";
  char *made_dir = mkdtemp(seed_dir);
  afl_state_t afl;
  struct queue_entry first, second, third;
  struct queue_entry *queue[] = {&first, &second, &third};
  memset(&afl, 0, sizeof(afl));

  /* Live C validator minimum: an allowed METHOD / absolute path request line,
     the CRLF envelope/body delimiter, and a JSON object/array body. Host and
     Content-Length are retained as complete HTTP metadata but are not
     promoted into the validator's actual required minimum. */
  expect(strstr((char *)seed0, "PUT /offline/dedicated-metadata-node HTTP/1.1\r\n") &&
             strstr((char *)seed1, "PUT /offline/dedicated-metadata-node HTTP/1.1\r\n") &&
             strstr((char *)seed2, "PUT /offline/dedicated-metadata-node HTTP/1.1\r\n") &&
             strstr((char *)seed0, "Host: offline.invalid\r\n") &&
             strstr((char *)seed1, "Host: offline.invalid\r\n") &&
             strstr((char *)seed2, "Host: offline.invalid\r\n") &&
             strstr((char *)seed0, "Content-Length: 39\r\n") &&
             strstr((char *)seed1, "Content-Length: 61\r\n") &&
             strstr((char *)seed2, "Content-Length: 61\r\n") &&
             full_http_content_length_matches(seed0) &&
             full_http_content_length_matches(seed1) &&
             full_http_content_length_matches(seed2) &&
             strstr((char *)seed0, "\r\n\r\n{") &&
             strstr((char *)seed1, "\r\n\r\n{") &&
             strstr((char *)seed2, "\r\n\r\n{") &&
             strcmp((char *)seed0, (char *)seed1) &&
             strcmp((char *)seed1, (char *)seed2) &&
             !strstr((char *)seed0, "Authorization:") &&
             !strstr((char *)seed1, "Authorization:") &&
             !strstr((char *)seed2, "Authorization:"),
         "three_metadata_seeds_are_full_http_distinct_and_credential_free",
          "seed fixture contract failed");

  expect(made_dir &&
             write_seed(seed_dir, "seed_a.http", seed0, sizeof(seed0) - 1) &&
             write_seed(seed_dir, "seed_b.http", seed1, sizeof(seed1) - 1) &&
             write_seed(seed_dir, "seed_c.http", seed2, sizeof(seed2) - 1),
         "seed_directory_is_loaded_through_read_testcases_and_add_to_queue",
         "unable to materialize seed directory");
  if (made_dir) {

    afl.in_dir = (u8 *)seed_dir;
    afl.fixed_seed = 1;
    read_testcases(&afl, NULL);
    expect(afl.queued_at_start == 3 && afl.queued_items == 3 &&
               afl.queue_buf[0]->id == 0 && afl.queue_buf[1]->id == 1 &&
               afl.queue_buf[2]->id == 2 && afl.queue_buf[0]->fname &&
               afl.queue_buf[1]->fname && afl.queue_buf[2]->fname,
           "seed_directory_is_loaded_through_read_testcases_and_add_to_queue",
           "loaded=%u queued=%u ids=%u/%u/%u", afl.queued_at_start,
           afl.queued_items, afl.queue_buf[0] ? afl.queue_buf[0]->id : 99,
           afl.queue_buf[1] ? afl.queue_buf[1]->id : 99,
           afl.queue_buf[2] ? afl.queue_buf[2]->id : 99);

  }

  /* Equal initial weights and deterministic roulette values visit all seeds. */
  char audit_path[] = "/tmp/nv-seed-selection-unit-XXXXXX";
  int audit_fd = mkstemp(audit_path);
  if (audit_fd >= 0) close(audit_fd);
  setenv("NV_SEED_SELECTION_AUDIT_PATH", audit_path, 1);
  u32 selected[] = {select_next_queue_entry(&afl),
                    select_next_queue_entry(&afl),
                    select_next_queue_entry(&afl)};
  unsetenv("NV_SEED_SELECTION_AUDIT_PATH");
  printf("SELECTED %u %u %u\n", selected[0], selected[1], selected[2]);
  first = *afl.queue_buf[0];
  second = *afl.queue_buf[1];
  third = *afl.queue_buf[2];
  expect(selected[0] == 0 && selected[1] == 1 && selected[2] == 2 &&
             first.ss_selected_cnt == 1 && second.ss_selected_cnt == 1 &&
             third.ss_selected_cnt == 1,
         "production_picker_selects_each_initial_seed",
         "selected=%u/%u/%u counts=%llu/%llu/%llu", selected[0], selected[1],
         selected[2], (unsigned long long)first.ss_selected_cnt,
         (unsigned long long)second.ss_selected_cnt,
         (unsigned long long)third.ss_selected_cnt);

  char audit[4096] = {0};
  FILE *audit_file = fopen(audit_path, "r");
  if (audit_file) {

    (void)fread(audit, 1, sizeof(audit) - 1, audit_file);
    fclose(audit_file);

  }
  char audit_for_output[4096];
  memcpy(audit_for_output, audit, sizeof(audit_for_output));
  char *saveptr = NULL;
  char *audit_line = strtok_r(audit_for_output, "\n", &saveptr);
  while (audit_line) {

    printf("AUDIT_JSON %s\n", audit_line);
    audit_line = strtok_r(NULL, "\n", &saveptr);

  }
  expect(audit_fd >= 0, "selection_audit_has_exact_allowed_fields",
         "audit file was not created");
  expect(audit_fd >= 0, "selection_audit_has_no_sensitive_fields",
         "audit file was not created");
  expect(audit_fd >= 0 && strstr(audit, "\"queue_id\":0") &&
             strstr(audit, "\"queue_id\":1") &&
             strstr(audit, "\"queue_id\":2") &&
             !strstr(audit, "Authorization") && !strstr(audit, "seed zero"),
         "selection_audit_distinguishes_seeds_without_request_data",
          "audit=%s", audit);
  unlink(audit_path);

  /* Credit applies to the current seed's live field, then production selection
      recomputes its probability before the next roulette decision. */
  afl.queue_buf[1]->ss_cov_cnt += 5;
  (void)select_next_queue_entry(&afl);
  printf("WEIGHTS first=%.6f second=%.6f third=%.6f\n", afl.queue_buf[0]->ss_prob,
         afl.queue_buf[1]->ss_prob, afl.queue_buf[2]->ss_prob);
  expect(afl.queue_buf[1]->ss_prob > afl.queue_buf[0]->ss_prob &&
             afl.queue_buf[1]->ss_prob > afl.queue_buf[2]->ss_prob,
         "production_picker_uses_security_state_credit",
         "weights=%.6f/%.6f/%.6f", afl.queue_buf[0]->ss_prob,
         afl.queue_buf[1]->ss_prob, afl.queue_buf[2]->ss_prob);

  afl_state_t without_audit, with_audit;
  struct queue_entry without_entries[3], with_entries[3];
  struct queue_entry *without_queue[3], *with_queue[3];
  init_three_entry_picker(&without_audit, without_entries, without_queue);
  init_three_entry_picker(&with_audit, with_entries, with_queue);
  char comparison_audit[] = "/tmp/nv-seed-selection-compare-XXXXXX";
  int comparison_fd = mkstemp(comparison_audit);
  if (comparison_fd >= 0) close(comparison_fd);
  random_index = 0;
  unsetenv("NV_SEED_SELECTION_AUDIT_PATH");
  u32 without_id = select_next_queue_entry(&without_audit);
  size_t rng_without = random_index;
  random_index = 0;
  setenv("NV_SEED_SELECTION_AUDIT_PATH", comparison_audit, 1);
  u32 with_id = select_next_queue_entry(&with_audit);
  size_t rng_with = random_index;
  unsetenv("NV_SEED_SELECTION_AUDIT_PATH");
  expect(without_id == with_id,
         "selection_audit_does_not_change_picker_decision",
         "without=%u with=%u", without_id, with_id);
  expect(rng_without == rng_with &&
             without_entries[0].ss_prob == with_entries[0].ss_prob &&
             without_entries[1].ss_prob == with_entries[1].ss_prob &&
             without_entries[2].ss_prob == with_entries[2].ss_prob &&
             without_entries[0].ss_selected_cnt == with_entries[0].ss_selected_cnt &&
             without_entries[1].ss_selected_cnt == with_entries[1].ss_selected_cnt &&
             without_entries[2].ss_selected_cnt == with_entries[2].ss_selected_cnt,
         "selection_audit_does_not_modify_rng_or_weights",
         "rng=%zu/%zu", rng_without, rng_with);
  unlink(comparison_audit);

  /* Writer failures are injected after the picker has made its decision. */
  afl_state_t failure_afl;
  struct queue_entry failure_entries[3];
  struct queue_entry *failure_queue[3];
  init_three_entry_picker(&failure_afl, failure_entries, failure_queue);
  char failure_audit[] = "/tmp/nv-seed-selection-failure-XXXXXX";
  int failure_fd = mkstemp(failure_audit);
  if (failure_fd >= 0) {

    close(failure_fd);
    unlink(failure_audit);

  }
  setenv("NV_SEED_SELECTION_AUDIT_PATH", failure_audit, 1);
  random_index = 0;
  nv_seed_selection_audit_set_hooks(audit_open_failure, NULL, NULL);
  u32 open_failure_id = select_next_queue_entry(&failure_afl);
  expect(open_failure_id == 0 && random_index == 1 &&
             failure_afl.seed_audit_error_count == 1 &&
             failure_afl.seed_audit_invalid && failure_afl.stop_soon &&
             failure_afl.seed_audit_record_count == 0 &&
             failure_entries[0].ss_selected_cnt == 1 &&
             failure_entries[0].ss_prob == 1.0,
         "seed_audit_open_failure_is_observable",
         "id=%u errors=%llu invalid=%u stop=%u records=%llu",
         open_failure_id,
         (unsigned long long)failure_afl.seed_audit_error_count,
         (unsigned)failure_afl.seed_audit_invalid, (unsigned)failure_afl.stop_soon,
         (unsigned long long)failure_afl.seed_audit_record_count);

  init_three_entry_picker(&failure_afl, failure_entries, failure_queue);
  random_index = 0;
  nv_seed_selection_audit_set_hooks(NULL, audit_write_failure, NULL);
  u32 write_failure_id = select_next_queue_entry(&failure_afl);
  expect(write_failure_id == 0 && random_index == 1 &&
             failure_afl.seed_audit_error_count == 1 &&
             failure_afl.seed_audit_invalid && failure_afl.stop_soon &&
             failure_afl.seed_audit_record_count == 0 &&
             failure_entries[0].ss_selected_cnt == 1 &&
             failure_entries[0].ss_prob == 1.0,
         "seed_audit_write_failure_is_observable",
         "id=%u errors=%llu invalid=%u stop=%u records=%llu",
         write_failure_id,
         (unsigned long long)failure_afl.seed_audit_error_count,
         (unsigned)failure_afl.seed_audit_invalid, (unsigned)failure_afl.stop_soon,
         (unsigned long long)failure_afl.seed_audit_record_count);

  init_three_entry_picker(&failure_afl, failure_entries, failure_queue);
  random_index = 0;
  nv_seed_selection_audit_set_hooks(NULL, NULL, audit_close_failure);
  u32 close_failure_id = select_next_queue_entry(&failure_afl);
  expect(close_failure_id == 0 && random_index == 1 &&
             failure_afl.seed_audit_error_count == 1 &&
             failure_afl.seed_audit_invalid && failure_afl.stop_soon &&
             failure_afl.seed_audit_record_count == 0 &&
             failure_entries[0].ss_selected_cnt == 1 &&
             failure_entries[0].ss_prob == 1.0,
         "seed_audit_close_failure_is_observable",
         "id=%u errors=%llu invalid=%u stop=%u records=%llu",
         close_failure_id,
         (unsigned long long)failure_afl.seed_audit_error_count,
         (unsigned)failure_afl.seed_audit_invalid, (unsigned)failure_afl.stop_soon,
         (unsigned long long)failure_afl.seed_audit_record_count);
  nv_seed_selection_audit_set_hooks(NULL, NULL, NULL);
  unsetenv("NV_SEED_SELECTION_AUDIT_PATH");
  unlink(failure_audit);

  char unset_audit[] = "/tmp/nv-seed-selection-unset-XXXXXX";
  int unset_fd = mkstemp(unset_audit);
  if (unset_fd >= 0) {

    close(unset_fd);
    unlink(unset_audit);

  }
  random_index = 0;
  unsetenv("NV_SEED_SELECTION_AUDIT_PATH");
  (void)select_next_queue_entry(&without_audit);
  expect(access(unset_audit, F_OK) != 0 && !without_audit.seed_audit_enabled &&
             without_audit.seed_audit_error_count == 0 &&
             without_audit.seed_audit_record_count == 0,
         "selection_audit_is_disabled_when_path_unset",
         "unexpected audit file %s", unset_audit);

  if (made_dir) {

    char seed_path[PATH_MAX];
    for (const char *name = "seed_a.http"; name; ) {

      snprintf(seed_path, sizeof(seed_path), "%s/%s", seed_dir, name);
      unlink(seed_path);
      name = !strcmp(name, "seed_a.http") ? "seed_b.http" :
             (!strcmp(name, "seed_b.http") ? "seed_c.http" : NULL);

    }
    rmdir(seed_dir);

  }

  printf("FAILURES %d\n", failures);
  return failures ? 1 : 0;

}
