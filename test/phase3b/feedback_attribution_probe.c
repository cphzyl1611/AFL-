/*
   TEST PROBE ONLY.
   NO NETWORK. NOT ALFRESCO. NOT FLOWABLE. NOT REAL-SERVICE VERIFICATION.

   Includes afl-fuzz-run.c so the tests call its actual static feedback
   functions.  This file supplies only bounded infrastructure dependencies;
   it contains no security-state, reward, MAB, scheduler, or coverage logic.
 */

#include "afl-fuzz.h"

#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static u32 write_calls;
static u32 target_calls;
static u32 status_producer_calls;
static u32 network_calls;
static u8  continuous_mode;
static u8  pending_at_common;
static u32 pending_arm_at_common;
static u32 mutator_calls;
static s32 mutator_reported = -1;
static u8  continuous_scenario;
static fsrv_run_result_t forced_fault = FSRV_RUN_OK;
static const char *target_input_path;
static const char *fake_target_path;
static const char *python_path;

/* TEST FIXTURE ONLY: deny and count every C-side network socket attempt. */
int socket(int domain, int type, int protocol) {

  (void)domain;
  (void)type;
  (void)protocol;
  network_calls++;
  errno = EPERM;
  return -1;

}

void afl_fsrv_write_to_testcase(afl_forkserver_t *fsrv, u8 *buf, size_t len) {

  (void)fsrv;
  write_calls++;

  if (continuous_mode) {

    FILE *fp = fopen(target_input_path, "wb");
    if (!fp) return;
    size_t written = fwrite(buf, 1, len, fp);
    int    close_rc = fclose(fp);
    if (written != len || close_rc) {

      return;

    }

  }

}

fsrv_run_result_t afl_fsrv_run_target(afl_forkserver_t *fsrv, u32 timeout,
                                      volatile u8 *stop_soon_p) {

  (void)fsrv;
  (void)timeout;
  target_calls++;
  status_producer_calls++;

  if (continuous_mode) {

    static const char audited_runner[] =
        "import os,runpy,sys\n"
        "fixture=sys.argv[1]\n"
        "def deny_network(event,_args):\n"
        "  if event.startswith('socket.'):\n"
        "    os.write(2,('NETWORK_AUDIT_EVENT='+event+'\\n').encode())\n"
        "    raise RuntimeError('network activity is forbidden')\n"
        "sys.addaudithook(deny_network)\n"
        "sys.argv=[fixture]\n"
        "runpy.run_path(fixture,run_name='__main__')\n";

    pid_t child = fork();
    if (child == 0) {

      int input_fd = open(target_input_path, O_RDONLY);
      if (input_fd < 0 || dup2(input_fd, STDIN_FILENO) < 0) _exit(126);
      close(input_fd);
      execl(python_path, python_path, "-c", audited_runner, fake_target_path,
            (char *)NULL);
      _exit(127);

    }

    int status = 0;
    if (child < 0 || waitpid(child, &status, 0) != child ||
        !WIFEXITED(status) || WEXITSTATUS(status) != 0) {

      return FSRV_RUN_CRASH;

    }

  }

  return forced_fault;

}

u8 save_if_interesting(afl_state_t *afl, void *mem, u32 len, u8 fault) {

  (void)afl;
  (void)mem;
  (void)len;
  (void)fault;
  return 0;

}

void show_stats(afl_state_t *afl) { (void)afl; }

void ijon_update_max_dynamic(ijon_min_state *self,
                             dynamic_shared_access_t *shared, uint8_t *data,
                             size_t len) {

  (void)self;
  (void)shared;
  (void)data;
  (void)len;

}

int nv_is_allowed_pair(afl_state_t *afl, const char *method,
                       const char *path) {

  (void)afl;
  (void)method;
  (void)path;
  return 1;

}

#define common_fuzz_stuff phase3b_actual_common_fuzz_stuff
#define calibrate_case phase3b_unused_calibrate_case
#define trim_case phase3b_unused_trim_case
#include "../../src/afl-fuzz-run.c"
#undef trim_case
#undef calibrate_case
#undef common_fuzz_stuff

u8 common_fuzz_stuff(afl_state_t *afl, u8 *out_buf, u32 len) {

  if (continuous_mode) {

    pending_at_common = afl->nv_mab.pending_update;
    pending_arm_at_common = (u32)afl->nv_mab.pending_arm;

  }

  return phase3b_actual_common_fuzz_stuff(afl, out_buf, len);

}

u32 calculate_score(afl_state_t *afl, struct queue_entry *queue) {

  (void)afl;
  return queue->perf_score;

}

u8 calibrate_case(afl_state_t *afl, struct queue_entry *queue, u8 *mem,
                  u32 handicap, u8 from_queue) {

  (void)afl;
  (void)queue;
  (void)mem;
  (void)handicap;
  (void)from_queue;
  return FSRV_RUN_OK;

}

u8 trim_case(afl_state_t *afl, struct queue_entry *queue, u8 *mem) {

  (void)afl;
  (void)queue;
  (void)mem;
  return FSRV_RUN_OK;

}

u32 count_non_255_bytes(afl_state_t *afl, u8 *mem) {

  (void)afl;
  (void)mem;
  return 0;

}

char *get_fuzzing_state(afl_state_t *afl) {

  (void)afl;
  return (char *)"phase3b5b";

}

u8 *queue_testcase_get(afl_state_t *afl, struct queue_entry *queue) {

  (void)afl;
  return queue->testcase_buf;

}

u8 input_to_state_stage(afl_state_t *afl, u8 *orig_buf, u8 *buf, u32 len) {

  (void)afl;
  (void)orig_buf;
  (void)buf;
  (void)len;
  return 0;

}

u8 skip_deterministic_stage(afl_state_t *afl, u8 *orig_buf, u8 *out_buf,
                            u32 len, u64 before_det_time) {

  (void)afl;
  (void)orig_buf;
  (void)out_buf;
  (void)len;
  (void)before_det_time;
  return 1;

}

u8 is_det_timeout(u64 before_det_time, u8 is_flip) {

  (void)before_det_time;
  (void)is_flip;
  return 0;

}

void mark_as_det_done(afl_state_t *afl, struct queue_entry *queue) {

  (void)afl;
  (void)queue;

}

void maybe_add_auto(afl_state_t *afl, u8 *mem, u32 len) {

  (void)afl;
  (void)mem;
  (void)len;

}

u8 *u_simplestring_time_diff(u8 *buf, u64 cur_ms, u64 event_ms) {

  (void)cur_ms;
  (void)event_ms;
  buf[0] = 0;
  return buf;

}

ijon_input_info *ijon_get_input(ijon_min_state *self) {

  (void)self;
  return NULL;

}

u8 ijon_should_schedule(ijon_min_state *self) {

  (void)self;
  return 0;

}

u64 get_cur_time(void) {

  static u64 now = 1000;
  return now++;

}

u64 get_cur_time_us(void) {

  return get_cur_time() * 1000;

}

AFL_RAND_RETURN rand_next(afl_state_t *afl) {

  return ++afl->rand_seed[0];

}

u64 hash64(u8 *key, u32 len, u64 seed) {

  (void)key;
  (void)len;
  return seed;

}

/* TEST FIXTURE ONLY: keep production reporting intact while supplying the
   normal filesystem helper against a caller-owned temporary directory. */
FILE *create_ffile(u8 *fn, mode_t mode) {

  (void)mode;
  return fopen((char *)fn, "w");

}

u64 ss_new_bits_any;
u64 ss_new_bits_kept;

char *phase3c_actual_get_fuzzing_state(afl_state_t *afl);
void  phase3c_actual_show_stats(afl_state_t *afl);

#define get_fuzzing_state phase3c_actual_get_fuzzing_state
#define show_stats phase3c_actual_show_stats
#include "../../src/afl-fuzz-stats.c"
#undef show_stats
#undef get_fuzzing_state

#include "../../src/afl-fuzz-nv-sched.c"

extern struct custom_mutator *load_custom_mutator_py(afl_state_t *afl,
                                                      char *module_name);

struct audited_mutator {

  void *actual_data;
  size_t (*actual_fuzz)(void *, u8 *, size_t, u8 **, u8 *, size_t, size_t);

};

static u32 one_custom_fuzz(void *data, const u8 *buf, size_t len) {

  (void)data;
  (void)buf;
  (void)len;
  return 1;

}

static size_t audited_custom_fuzz(void *data, u8 *buf, size_t buf_size,
                                  u8 **out_buf, u8 *add_buf,
                                  size_t add_buf_size, size_t max_size) {

  struct audited_mutator *audited = data;
  mutator_calls++;
  size_t size = audited->actual_fuzz(audited->actual_data, buf, buf_size,
                                     out_buf, add_buf, add_buf_size, max_size);
  const char *reported = getenv("NV_JSON_ARM_USED");
  mutator_reported = reported && reported[0] && !reported[1]
                         ? (s32)(reported[0] - '0')
                         : -1;
  if (continuous_scenario == 1) {

    unsetenv("NV_JSON_ARM_USED");

  } else if (continuous_scenario == 2) {

    setenv("NV_JSON_ARM_USED", "1", 1);

  }
  return size;

}

static void init_feedback_state(afl_state_t *afl, struct queue_entry *queue) {

  memset(afl, 0, sizeof(*afl));
  memset(queue, 0, sizeof(*queue));
  afl->queue_cur = queue;

}

static void print_observation(const char *label, const afl_state_t *afl,
                              const struct queue_entry *queue,
                              const nv_state_obs_t *obs) {

  printf("%s has=%u new=%llu exec_seq=%llu used=%u ss_cov=%llu "
         "seed_credit=%llu\n",
         label, (unsigned)obs->has, (unsigned long long)obs->new_states,
         (unsigned long long)obs->exec_seq, afl->nv_cov_used,
         (unsigned long long)queue->ss_cov_cnt,
         (unsigned long long)afl->nv_sec_state_seed_credit);

}

static int run_wait_for_fresh(const char *status_path,
                               const char *new_status_path) {

  afl_state_t afl;
  struct queue_entry queue;
  nv_state_obs_t obs;
  init_feedback_state(&afl, &queue);
  if (setenv("NV_STATUS_PATH", status_path, 1) != 0) return 2;

  nv_observe_security_state(&afl, status_path, &obs);
  if (!obs.has) return 3;

  pid_t child = fork();
  if (child < 0) return 4;
  if (child == 0) {
    usleep(20000);
    if (rename(new_status_path, status_path) != 0) _exit(5);
    _exit(0);
  }

  nv_observe_security_state_after_execution(&afl, status_path, &obs);
  int child_status = 0;
  if (waitpid(child, &child_status, 0) != child ||
      !WIFEXITED(child_status) || WEXITSTATUS(child_status) != 0) return 6;
  printf("WAIT has=%u exec_seq=%llu replays=%llu\n",
         (unsigned)obs.has,
         (unsigned long long)obs.exec_seq,
         (unsigned long long)afl.nv_sec_state_replays);
  return obs.has && obs.exec_seq > 1 ? 0 : 1;

}

static int run_credit(const char *first_path, const char *second_path) {

  afl_state_t        afl;
  struct queue_entry queue;
  nv_state_obs_t     obs;
  init_feedback_state(&afl, &queue);

  nv_observe_security_state(&afl, first_path, &obs);
  print_observation("FIRST", &afl, &queue, &obs);

  nv_observe_security_state(&afl, second_path, &obs);
  print_observation("SECOND", &afl, &queue, &obs);
  return 0;

}

static int run_saturation(const char *status_path) {

  afl_state_t        scratch;
  struct queue_entry scratch_queue;
  nv_state_obs_t     scratch_obs;
  init_feedback_state(&scratch, &scratch_queue);
  nv_observe_security_state(&scratch, status_path, &scratch_obs);

  u64 occupied = scratch_obs.state_id ^ 1ULL;
  if (!occupied) occupied = 2;

  afl_state_t        afl;
  struct queue_entry queue;
  nv_state_obs_t     obs;
  init_feedback_state(&afl, &queue);
  afl.nv_covset = &occupied;
  afl.nv_cov_cap = 1;
  afl.nv_cov_used = 1;

  nv_observe_security_state(&afl, status_path, &obs);
  printf("SATURATED has=%u new=%llu exec_seq=%llu used=%u ss_cov=%llu "
         "seed_credit=%llu saturated=%u dropped=%llu\n",
         (unsigned)obs.has, (unsigned long long)obs.new_states,
         (unsigned long long)obs.exec_seq, afl.nv_cov_used,
         (unsigned long long)queue.ss_cov_cnt,
         (unsigned long long)afl.nv_sec_state_seed_credit,
         (unsigned)afl.nv_sec_state_saturated,
         (unsigned long long)afl.nv_sec_state_dropped);
  return 0;

}

static int run_reward(const char *status_path, const char *pending_text,
                      const char *arm_text, const char *journal_path,
                      const char *zero_reward_text) {

  int pending = atoi(pending_text);
  int arm = atoi(arm_text);
  if ((pending != 0 && pending != 1) || arm < 0 || arm >= NV_ARM_MAX) return 2;

  afl_state_t        afl;
  struct queue_entry queue;
  u8                 input[] = "x";
  init_feedback_state(&afl, &queue);
  afl.max_length = 1024;
  afl.stage_name = (u8 *)"phase3b";
  afl.stage_cur = 1;
  afl.stage_max = 10;
  afl.stats_update_freq = 100;
  nv_mab_init_defaults(&afl.nv_mab);
  afl.nv_mab.last_arm = (nv_arm_id_t)arm;
  afl.nv_mab.pending_arm = (nv_arm_id_t)arm;
  afl.nv_mab.pending_update = (u8)pending;
  afl.nv_mab.update_source = pending ? 1 : 0;
  setenv("NV_STATUS_PATH", status_path, 1);
  if (journal_path && *journal_path) setenv("NV_MAB_JOURNAL_PATH", journal_path, 1);

  if (zero_reward_text && !strcmp(zero_reward_text, "zero")) {

    nv_state_obs_t prior;
    nv_observe_security_state(&afl, status_path, &prior);
    /* The fixture reuses one status document for the next execution.  Keep
       the consumed state set, but model the next execution identity. */
    if (prior.exec_seq > 0) afl.nv_last_exec_seq = prior.exec_seq - 1;

  }

  int rc = common_fuzz_stuff(&afl, input, 1);
  printf("REWARD rc=%d selected=%u observed_seq=%llu reward_src_seq=%llu "
         "total_pulls=%llu arm0=%llu arm1=%llu arm2=%llu pending=%u "
         "update_source=%u target_calls=%u\n",
         rc, (unsigned)afl.nv_mab.last_arm,
         (unsigned long long)afl.nv_last_exec_seq,
         (unsigned long long)afl.nv_sec_state_reward_src_seq,
         (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab.arms[0].pulls,
         (unsigned long long)afl.nv_mab.arms[1].pulls,
         (unsigned long long)afl.nv_mab.arms[2].pulls,
         (unsigned)afl.nv_mab.pending_update,
         (unsigned)afl.nv_mab.update_source, target_calls);
  unsetenv("NV_MAB_JOURNAL_PATH");
  return rc;

}

static int run_no_status_target(const char *status_path,
                                 const char *ledger_path) {

  afl_state_t afl;
  struct queue_entry queue;
  u8 input[] = "x";
  init_feedback_state(&afl, &queue);
  afl.max_length = 1024;
  afl.stage_name = (u8 *)"phase3b";
  afl.stage_cur = 1;
  afl.stage_max = 10;
  afl.stats_update_freq = 100;
  afl.nv_mab.pending_update = 0;
  forced_fault = FSRV_RUN_OK;
  continuous_mode = 0;
  target_calls = 0;
  setenv("NV_STATUS_PATH", status_path, 1);
  setenv("NV_EXECUTION_LEDGER_PATH", ledger_path, 1);

  int rc = common_fuzz_stuff(&afl, input, 1);
  FILE *fp = fopen(ledger_path, "rb");
  char line[2048] = {0};
  if (!fp || !fgets(line, sizeof(line), fp)) {
    if (fp) fclose(fp);
    return 3;
  }
  fclose(fp);
  printf("NO_STATUS rc=%d target_calls=%u ledger=%s", rc, target_calls, line);
  unsetenv("NV_EXECUTION_LEDGER_PATH");
  return 0;

}

static int run_pending(const char *reason, const char *status_path,
                       const char *journal_path) {

  afl_state_t afl;
  struct queue_entry queue;
  u8 input[] = "x";
  init_feedback_state(&afl, &queue);
  afl.max_length = 1024;
  afl.stage_name = (u8 *)"phase3b";
  afl.stage_cur = 1;
  afl.stage_max = 10;
  afl.stats_update_freq = 100;
  afl.nv_mab.pending_arm = NV_ARM_BOUNDARY;
  afl.nv_mab.pending_update = 1;
  afl.nv_mab.update_source = 1;
  forced_fault = FSRV_RUN_OK;

  if (!strcmp(reason, "budget_boundary")) {
    afl.nv_task.max_test_cases = 1;
  } else if (!strcmp(reason, "stop_soon")) {
    afl.stop_soon = 1;
  } else if (!strcmp(reason, "timeout")) {
    forced_fault = FSRV_RUN_TMOUT;
    afl.subseq_tmouts = TMOUT_LIMIT + 1;
  } else if (!strcmp(reason, "invalid_input")) {
    input[0] = 0;
  } else if (!strcmp(reason, "skip")) {
    afl.skip_requested = 1;
  } else {
    return 2;
  }

  setenv("NV_STATUS_PATH", status_path, 1);
  setenv("NV_MAB_JOURNAL_PATH", journal_path, 1);
  u32 input_len = strcmp(reason, "invalid_input") ? 1 : 0;
  int rc = common_fuzz_stuff(&afl, input, input_len);
  printf("PENDING rc=%d pulls=%llu arm_pulls=%llu records=%llu pending=%u "
         "update_source=%u\n",
         rc, (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab.arms[NV_ARM_BOUNDARY].pulls,
         (unsigned long long)afl.nv_mab_journal_record_count,
         (unsigned)afl.nv_mab.pending_update, (unsigned)afl.nv_mab.update_source);
  unsetenv("NV_MAB_JOURNAL_PATH");
  forced_fault = FSRV_RUN_OK;
  return rc;

}

static int run_reject(const char *status_path, const char *testcase) {

  afl_state_t        afl;
  struct queue_entry queue;
  init_feedback_state(&afl, &queue);
  afl.max_length = 1024;
  afl.nv_task.enable_validity = 1;
  nv_mab_init_defaults(&afl.nv_mab);
  afl.nv_mab.pending_arm = NV_ARM_BOUNDARY;
  afl.nv_mab.pending_update = 1;
  afl.nv_mab.update_source = 1;
  afl.nv_sec_state_reward_src_seq = 77;
  setenv("NV_STATUS_PATH", status_path, 1);

  nv_mab_t mab_before = afl.nv_mab;
  u64 invalid_before = afl.nv_invalid_cnt;
  u64 invalid_parse_before = afl.nv_invalid_parse_cnt;
  u64 invalid_rule_before = afl.nv_invalid_rule_cnt;
  u64 status_count_before = afl.nv_status_cnt;
  u64 observations_before = afl.nv_sec_state_obs;
  u64 last_exec_seq_before = afl.nv_last_exec_seq;
  u64 reward_src_seq_before = afl.nv_sec_state_reward_src_seq;
  u32 write_before = write_calls;
  u32 target_before = target_calls;
  u32 status_producer_before = status_producer_calls;
  u32 network_before = network_calls;

  int rc = common_fuzz_stuff(&afl, (u8 *)testcase, (u32)strlen(testcase));
  u8 sum_rewards_unchanged = 1;
  u8 mean_rewards_unchanged = 1;
  for (u32 arm = 0; arm < NV_ARM_MAX; ++arm) {

    if (mab_before.arms[arm].sum_reward != afl.nv_mab.arms[arm].sum_reward)
      sum_rewards_unchanged = 0;
    if (mab_before.arms[arm].mean_reward != afl.nv_mab.arms[arm].mean_reward)
      mean_rewards_unchanged = 0;

  }

  printf(
      "REJECT rc=%d enable_validity=%u "
      "invalid_before=%llu invalid_after=%llu invalid_delta=%llu "
      "invalid_parse_before=%llu invalid_parse_after=%llu "
      "invalid_parse_delta=%llu invalid_rule_before=%llu "
      "invalid_rule_after=%llu invalid_rule_delta=%llu "
      "write_before=%u write_after=%u write_delta=%u "
      "target_before=%u target_after=%u target_delta=%u "
      "status_producer_before=%u status_producer_after=%u "
      "status_producer_delta=%u pending_before=%u pending_arm_before=%u "
      "update_source_before=%u pending_after=%u update_source_after=%u "
      "status_count_before=%llu status_count_after=%llu "
      "status_count_delta=%llu observations_before=%llu "
      "observations_after=%llu observations_delta=%llu "
      "last_exec_seq_before=%llu last_exec_seq_after=%llu "
      "last_exec_seq_delta=%llu reward_src_seq_before=%llu "
      "reward_src_seq_after=%llu total_pulls_before=%llu "
      "total_pulls_after=%llu arm0_before=%llu arm0_after=%llu "
      "arm1_before=%llu arm1_after=%llu arm2_before=%llu arm2_after=%llu "
      "sum_rewards_unchanged=%u mean_rewards_unchanged=%u "
      "network_before=%u network_after=%u network_delta=%u\n",
      rc, (unsigned)afl.nv_task.enable_validity,
      (unsigned long long)invalid_before,
      (unsigned long long)afl.nv_invalid_cnt,
      (unsigned long long)(afl.nv_invalid_cnt - invalid_before),
      (unsigned long long)invalid_parse_before,
      (unsigned long long)afl.nv_invalid_parse_cnt,
      (unsigned long long)(afl.nv_invalid_parse_cnt - invalid_parse_before),
      (unsigned long long)invalid_rule_before,
      (unsigned long long)afl.nv_invalid_rule_cnt,
      (unsigned long long)(afl.nv_invalid_rule_cnt - invalid_rule_before),
      write_before, write_calls, write_calls - write_before, target_before,
      target_calls, target_calls - target_before, status_producer_before,
      status_producer_calls, status_producer_calls - status_producer_before,
      (unsigned)mab_before.pending_update,
      (unsigned)mab_before.pending_arm, (unsigned)mab_before.update_source,
      (unsigned)afl.nv_mab.pending_update,
      (unsigned)afl.nv_mab.update_source,
      (unsigned long long)status_count_before,
      (unsigned long long)afl.nv_status_cnt,
      (unsigned long long)(afl.nv_status_cnt - status_count_before),
      (unsigned long long)observations_before,
      (unsigned long long)afl.nv_sec_state_obs,
      (unsigned long long)(afl.nv_sec_state_obs - observations_before),
      (unsigned long long)last_exec_seq_before,
      (unsigned long long)afl.nv_last_exec_seq,
      (unsigned long long)(afl.nv_last_exec_seq - last_exec_seq_before),
      (unsigned long long)reward_src_seq_before,
      (unsigned long long)afl.nv_sec_state_reward_src_seq,
      (unsigned long long)mab_before.total_pulls,
      (unsigned long long)afl.nv_mab.total_pulls,
      (unsigned long long)mab_before.arms[0].pulls,
      (unsigned long long)afl.nv_mab.arms[0].pulls,
      (unsigned long long)mab_before.arms[1].pulls,
      (unsigned long long)afl.nv_mab.arms[1].pulls,
      (unsigned long long)mab_before.arms[2].pulls,
      (unsigned long long)afl.nv_mab.arms[2].pulls,
      (unsigned)sum_rewards_unchanged, (unsigned)mean_rewards_unchanged,
      network_before, network_calls, network_calls - network_before);
  return rc;

}

static int run_continuous(const char *scenario, const char *status_path,
                          const char *fixture_path, const char *rules_path,
                          const char *python_executable,
                          const char *input_path,
                          const char *report_out_dir) {

  if (!strcmp(scenario, "positive")) {

    continuous_scenario = 0;

  } else if (!strcmp(scenario, "unconfirmed")) {

    continuous_scenario = 1;

  } else if (!strcmp(scenario, "mismatch")) {

    continuous_scenario = 2;

  } else {

    return 2;

  }

  static u8 testcase[] =
      "PUT /offline/node HTTP/1.1\r\n"
      "Content-Type: application/json\r\n"
      "\r\n"
      "{\"name\":\"offline-node\",\"properties\":"
      "{\"cm:title\":\"local\"}}";

  afl_state_t         afl;
  struct queue_entry  queue;
  struct queue_entry *fixed_queue[1] = {&queue};
  struct skipdet_entry skipdet;
  init_feedback_state(&afl, &queue);
  memset(&skipdet, 0, sizeof(skipdet));

  u64    queue_cov_before = queue.ss_cov_cnt;
  u64    selected_before = queue.ss_selected_cnt;
  double weight_before_credit = ss_calc_prob(&queue);

  queue.testcase_buf = testcase;
  queue.len = sizeof(testcase) - 1;
  queue.depth = 1;
  queue.perf_score = 100;
  queue.weight = 1.0;
  queue.trim_done = 1;
  queue.was_fuzzed = 1;
  queue.favored = 1;
  queue.skipdet_e = &skipdet;

  afl.queued_items = 1;
  afl.active_items = 1;
  afl.non_instrumented_mode = 1;
  afl.skip_deterministic = 1;
  afl.custom_only = 1;
  afl.havoc_div = 1;
  afl.max_length = MAX_FILE;
  afl.stats_update_freq = 100;
  afl.fixed_seed = 1;
  afl.fsrv.real_map_size = 1;
  afl.rand_seed[0] = 1;
  nv_mab_init_defaults(&afl.nv_mab);

  if (report_out_dir) {

    afl.queue_buf = fixed_queue;
    afl.out_dir = (u8 *)report_out_dir;
    afl.perm = 0600;
    afl.start_time = 1;
    afl.use_banner = (u8 *)"phase3c-offline";
    afl.orig_cmdline = (u8 *)"phase3c-offline";

  }

  setenv("NV_STATUS_PATH", status_path, 1);
  setenv("NV_BODY_RULES", rules_path, 1);
  setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
  unsetenv("NV_CUR_ARM");
  unsetenv("NV_JSON_ARM_USED");

  target_input_path = input_path;
  fake_target_path = fixture_path;
  python_path = python_executable;
  continuous_mode = 1;

  struct custom_mutator *mutator =
      load_custom_mutator_py(&afl, (char *)"nv_json_mutator");
  struct audited_mutator audited = {
      .actual_data = mutator->data,
      .actual_fuzz = mutator->afl_custom_fuzz,
  };
  mutator->data = &audited;
  mutator->afl_custom_fuzz = audited_custom_fuzz;
  mutator->afl_custom_fuzz_count = one_custom_fuzz;
  afl.custom_mutators_count = 1;
  list_append(&afl.custom_mutator_list, mutator);

  int fuzz_rc = fuzz_one_original(&afl);

  if (report_out_dir) {

    double weight_after_credit = ss_calc_prob(&queue);

    u32 state_total_before_replay = afl.nv_cov_used;
    u64 new_total_before_replay = afl.nv_sec_state_new_total;
    u64 observations_before_replay = afl.nv_sec_state_obs;
    u64 seed_credit_before_replay = afl.nv_sec_state_seed_credit;
    u64 total_pulls_before_replay = afl.nv_mab.total_pulls;
    u64 reward_src_before_replay = afl.nv_sec_state_reward_src_seq;
    u64 replays_before = afl.nv_sec_state_replays;

    nv_state_obs_t replay_obs;
    nv_observe_security_state(&afl, status_path, &replay_obs);

    u32 selected_index = select_next_queue_entry(&afl);
    double weight_after_selection = ss_calc_prob(&queue);
    queue.ss_prob = weight_after_selection;

    afl.fsrv.total_execs = target_calls;
    write_stats_file(&afl, 0, 0.0, 0.0, 0.0);

    printf(
        "REPORTING fuzz_rc=%d fixed_queue=%u same_queue=%u queue_count=%u "
        "selected_index=%u "
        "queue_cov_before=%llu queue_cov_after=%llu selected_before=%llu "
        "selected_after=%llu weight_before=%.17g weight_after_credit=%.17g "
        "weight_after_selection=%.17g state_total=%u state_new=%llu "
        "observations=%llu seed_credit=%llu replays=%llu reward_src_seq=%llu "
        "last_exec_seq=%llu total_pulls=%llu cold_start_picks=%llu "
        "ucb_picks=%llu arm_count=%u arm0_pulls=%llu arm0_mean=%.17g "
        "arm0_sum=%.17g arm0_pos=%llu arm1_pulls=%llu arm1_mean=%.17g "
        "arm1_sum=%.17g arm1_pos=%llu arm2_pulls=%llu arm2_mean=%.17g "
        "arm2_sum=%.17g arm2_pos=%llu queue_cov_sum=%llu "
        "replay_delta=%llu replay_state_total_delta=%lld "
        "replay_new_delta=%lld replay_observations_delta=%lld "
        "replay_seed_delta=%lld replay_pulls_delta=%lld "
        "replay_reward_src_unchanged=%u err_exec=%llu rec_total=%llu "
        "rec_success=%llu target_calls=%u network_calls=%u\n",
        fuzz_rc, 1U,
        (unsigned)(afl.queue_cur == &queue && afl.queue_buf == fixed_queue &&
                   afl.queue_buf[0] == &queue),
        afl.queued_items, selected_index, (unsigned long long)queue_cov_before,
        (unsigned long long)queue.ss_cov_cnt,
        (unsigned long long)selected_before,
        (unsigned long long)queue.ss_selected_cnt, weight_before_credit,
        weight_after_credit, weight_after_selection, afl.nv_cov_used,
        (unsigned long long)afl.nv_sec_state_new_total,
        (unsigned long long)afl.nv_sec_state_obs,
        (unsigned long long)afl.nv_sec_state_seed_credit,
        (unsigned long long)afl.nv_sec_state_replays,
        (unsigned long long)afl.nv_sec_state_reward_src_seq,
        (unsigned long long)afl.nv_last_exec_seq,
        (unsigned long long)afl.nv_mab.total_pulls,
        (unsigned long long)afl.nv_mab.cold_start_picks,
        (unsigned long long)afl.nv_mab.ucb_picks, (unsigned)NV_ARM_MAX,
        (unsigned long long)afl.nv_mab.arms[0].pulls,
        afl.nv_mab.arms[0].mean_reward, afl.nv_mab.arms[0].sum_reward,
        (unsigned long long)afl.nv_mab.arms[0].pos_cnt,
        (unsigned long long)afl.nv_mab.arms[1].pulls,
        afl.nv_mab.arms[1].mean_reward, afl.nv_mab.arms[1].sum_reward,
        (unsigned long long)afl.nv_mab.arms[1].pos_cnt,
        (unsigned long long)afl.nv_mab.arms[2].pulls,
        afl.nv_mab.arms[2].mean_reward, afl.nv_mab.arms[2].sum_reward,
        (unsigned long long)afl.nv_mab.arms[2].pos_cnt,
        (unsigned long long)queue.ss_cov_cnt,
        (unsigned long long)(afl.nv_sec_state_replays - replays_before),
        (long long)afl.nv_cov_used - (long long)state_total_before_replay,
        (long long)afl.nv_sec_state_new_total -
            (long long)new_total_before_replay,
        (long long)afl.nv_sec_state_obs -
            (long long)observations_before_replay,
        (long long)afl.nv_sec_state_seed_credit -
            (long long)seed_credit_before_replay,
        (long long)afl.nv_mab.total_pulls -
            (long long)total_pulls_before_replay,
        (unsigned)(afl.nv_sec_state_reward_src_seq ==
                   reward_src_before_replay),
        (unsigned long long)afl.nv_err_exec,
        (unsigned long long)afl.nv_rec_total,
        (unsigned long long)afl.nv_rec_success, target_calls, network_calls);

  }

  const char *nv_cur = getenv("NV_CUR_ARM");
  const char *nv_used = getenv("NV_JSON_ARM_USED");
  printf("CONTINUOUS scenario=%u fuzz_rc=%d selected=%u nv_cur=%d nv_used=%d "
         "mutator_calls=%u pending_at_common=%u pending_arm_at_common=%u "
         "target_calls=%u observed_seq=%llu reward_src_seq=%llu "
         "total_pulls=%llu arm0=%llu arm1=%llu arm2=%llu pending_after=%u "
         "update_source_after=%u arm0_sum=%.17g arm1_sum=%.17g "
         "arm2_sum=%.17g arm0_pos=%llu arm1_pos=%llu arm2_pos=%llu "
         "mutator_reported=%d\n",
         (unsigned)continuous_scenario, fuzz_rc, (unsigned)afl.nv_mab.last_arm,
         nv_cur && nv_cur[0] && !nv_cur[1] ? nv_cur[0] - '0' : -1,
         nv_used && nv_used[0] && !nv_used[1] ? nv_used[0] - '0' : -1,
         mutator_calls, (unsigned)pending_at_common, pending_arm_at_common,
         target_calls, (unsigned long long)afl.nv_last_exec_seq,
         (unsigned long long)afl.nv_sec_state_reward_src_seq,
         (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab.arms[0].pulls,
         (unsigned long long)afl.nv_mab.arms[1].pulls,
         (unsigned long long)afl.nv_mab.arms[2].pulls,
         (unsigned)afl.nv_mab.pending_update,
          (unsigned)afl.nv_mab.update_source,
          afl.nv_mab.arms[0].sum_reward, afl.nv_mab.arms[1].sum_reward,
          afl.nv_mab.arms[2].sum_reward,
          (unsigned long long)afl.nv_mab.arms[0].pos_cnt,
          (unsigned long long)afl.nv_mab.arms[1].pos_cnt,
          (unsigned long long)afl.nv_mab.arms[2].pos_cnt, mutator_reported);
  return fuzz_rc;

}

static int run_multi_arm(const char *status_path, const char *fixture_path,
                         const char *rules_path, const char *python_executable,
                         const char *input_path, const char *journal_path) {

  static u8 testcase[] =
      "PUT /offline/node HTTP/1.1\r\n"
      "Content-Type: application/json\r\n"
      "\r\n"
      "{\"name\":\"offline-node\",\"properties\":"
      "{\"cm:title\":\"local\"}}";
  afl_state_t         afl;
  struct queue_entry  queue;
  struct skipdet_entry skipdet;
  init_feedback_state(&afl, &queue);
  memset(&skipdet, 0, sizeof(skipdet));

  queue.testcase_buf = testcase;
  queue.len = sizeof(testcase) - 1;
  queue.depth = 1;
  queue.perf_score = 100;
  queue.weight = 1.0;
  queue.trim_done = 1;
  queue.was_fuzzed = 1;
  queue.favored = 1;
  queue.skipdet_e = &skipdet;
  afl.queued_items = 1;
  afl.active_items = 1;
  afl.non_instrumented_mode = 1;
  afl.skip_deterministic = 1;
  afl.custom_only = 1;
  afl.havoc_div = 1;
  afl.max_length = MAX_FILE;
  afl.stats_update_freq = 100;
  afl.fixed_seed = 1;
  afl.fsrv.real_map_size = 1;
  afl.rand_seed[0] = 1;
  nv_mab_init_defaults(&afl.nv_mab);
  afl.nv_mab.min_explore = 1;
  afl.nv_task.mutation_scope = 0x7;

  setenv("NV_STATUS_PATH", status_path, 1);
  setenv("NV_BODY_RULES", rules_path, 1);
  setenv("NV_MAB_JOURNAL_PATH", journal_path, 1);
  setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
  unsetenv("NV_CUR_ARM");
  unsetenv("NV_JSON_ARM_USED");
  target_input_path = input_path;
  fake_target_path = fixture_path;
  python_path = python_executable;
  continuous_mode = 1;
  continuous_scenario = 0;
  mutator_calls = 0;
  mutator_reported = -1;

  struct custom_mutator *mutator =
      load_custom_mutator_py(&afl, (char *)"nv_json_mutator");
  struct audited_mutator audited = {
      .actual_data = mutator->data,
      .actual_fuzz = mutator->afl_custom_fuzz,
  };
  mutator->data = &audited;
  mutator->afl_custom_fuzz = audited_custom_fuzz;
  mutator->afl_custom_fuzz_count = one_custom_fuzz;
  afl.custom_mutators_count = 1;
  list_append(&afl.custom_mutator_list, mutator);

  int rc0 = fuzz_one_original(&afl);
  int rc1 = fuzz_one_original(&afl);
  int rc2 = fuzz_one_original(&afl);
  printf("MULTI_ARM rc0=%d rc1=%d rc2=%d calls=%u total_pulls=%llu arm0=%llu arm1=%llu "
         "arm2=%llu records=%llu last_exec_seq=%llu last_arm=%u\n",
         rc0, rc1, rc2, mutator_calls,
         (unsigned long long)afl.nv_mab.total_pulls,
         (unsigned long long)afl.nv_mab.arms[0].pulls,
         (unsigned long long)afl.nv_mab.arms[1].pulls,
         (unsigned long long)afl.nv_mab.arms[2].pulls,
         (unsigned long long)afl.nv_mab_journal_record_count,
         (unsigned long long)afl.nv_last_exec_seq, (unsigned)afl.nv_mab.last_arm);
  unsetenv("NV_MAB_JOURNAL_PATH");
  return rc0 || rc1 || rc2;

}

int main(int argc, char **argv) {

  if (argc == 4 && !strcmp(argv[1], "wait-for-fresh")) {

    return run_wait_for_fresh(argv[2], argv[3]);

  }

  if (argc == 4 && !strcmp(argv[1], "no-status-target")) {

    return run_no_status_target(argv[2], argv[3]);

  }

  if (argc == 4 && !strcmp(argv[1], "credit")) {

    return run_credit(argv[2], argv[3]);

  }

  if (argc == 3 && !strcmp(argv[1], "saturation")) {

    return run_saturation(argv[2]);

  }

  if (argc == 4 && !strcmp(argv[1], "reject")) {

    return run_reject(argv[2], argv[3]);

  }

  if (argc == 5 && !strcmp(argv[1], "reward")) {

    return run_reward(argv[2], argv[3], argv[4], NULL, NULL);

  }

  if (argc == 6 && !strcmp(argv[1], "reward")) {

    return run_reward(argv[2], argv[3], argv[4], argv[5], NULL);

  }

  if (argc == 7 && !strcmp(argv[1], "reward")) {

    return run_reward(argv[2], argv[3], argv[4], argv[5], argv[6]);

  }

  if (argc == 5 && !strcmp(argv[1], "pending")) {

    return run_pending(argv[2], argv[3], argv[4]);

  }

  if (argc == 8 && !strcmp(argv[1], "continuous")) {

    return run_continuous(argv[2], argv[3], argv[4], argv[5], argv[6],
                          argv[7], NULL);

  }

  if (argc == 8 && !strcmp(argv[1], "reporting")) {

    return run_continuous("positive", argv[2], argv[3], argv[4], argv[5],
                          argv[6], argv[7]);

  }

  if (argc == 8 && !strcmp(argv[1], "multi-arm")) {

    return run_multi_arm(argv[2], argv[3], argv[4], argv[5], argv[6], argv[7]);

  }

  fprintf(stderr,
          "usage: %s credit <first-status> <second-status> | "
          "saturation <status> | reject <status> <testcase> | "
           "reward <status> <pending:0|1> <arm> | continuous <scenario> "
           "<status> <fixture> <rules> <python> <input> | pending <reason> "
           "<status> <journal> | reporting "
           "<status> <fixture> <rules> <python> <input> | multi-arm "
           "<status> <fixture> <rules> <python> <input> <journal> | reporting "
          "<status> <fixture> <rules> <python> <input> <out-dir>\n",
          argv[0]);
  return 2;

}
