/*
   american fuzzy lop++ - stats related routines
   ---------------------------------------------

   Originally written by Michal Zalewski

   Now maintained by Marc Heuse <mh@mh-sec.de>,
                     Dominik Meier <mail@dmnk.co>,
                     Andrea Fioraldi <andreafioraldi@gmail.com>, and
                     Heiko Eissfeldt <heiko.eissfeldt@hexco.de>

   Copyright 2016, 2017 Google Inc. All rights reserved.
   Copyright 2019-2024 AFLplusplus Project. All rights reserved.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at:

     https://www.apache.org/licenses/LICENSE-2.0

   This is the real deal: the program takes an instrumented binary and
   attempts a variety of basic fuzzing tricks, paying close attention to
   how they affect the execution path.

 */

#include "afl-fuzz.h"
#include "envs.h"
#include <limits.h>
extern u64 ss_new_bits_any;
extern u64 ss_new_bits_kept;
//  7 is the number of characters in a color control code
// 11 is the number of characters in the fuzzing state itself
//  5 is the number of characters in `cRST`
//  1 is for the null character
static char fuzzing_state[4][7 + 11 + 5 + 1] = {

    "started :-)", "in progress", "final phase", cRED "finished..." cRST};

char *get_fuzzing_state(afl_state_t *afl) {

  u64 cur_ms = get_cur_time();
  u64 last_find = cur_ms - afl->last_find_time;
  u64 cur_run_time = cur_ms - afl->start_time;
  u64 cur_total_run_time = afl->prev_run_time + cur_run_time;

  if (unlikely(afl->non_instrumented_mode)) {

    return fuzzing_state[1];

  } else if (unlikely(cur_run_time < 60 * 3 * 1000 ||

                      cur_total_run_time < 60 * 5 * 1000)) {

    return fuzzing_state[0];

  } else {

    u64 last_find_100 = 100 * last_find;
    u64 percent_cur = last_find_100 / cur_run_time;
    u64 percent_total = last_find_100 / cur_total_run_time;

    if (unlikely(percent_cur >= 75 && percent_total >= 75)) {

      if (unlikely(afl->afl_env.afl_exit_when_done)) { afl->stop_soon = 2; }

      return fuzzing_state[3];

    } else if (unlikely(percent_cur >= 50 && percent_total >= 50)) {

      return fuzzing_state[2];

    } else {

      return fuzzing_state[1];

    }

  }

}

/* Write fuzzer setup file */

void write_setup_file(afl_state_t *afl, u32 argc, char **argv) {

  u8 fn[PATH_MAX], fn2[PATH_MAX];

  snprintf(fn2, PATH_MAX, "%s/target_hash", afl->out_dir);
  FILE *f2 = create_ffile(fn2, afl->perm);

  if (afl->chown_needed) {

    if (chown(fn2, -1, afl->fsrv.gid) == -1) { PFATAL("chown() failed"); }

  }

#ifdef __linux__
  if (afl->fsrv.nyx_mode) {

    nyx_load_target_hash(&afl->fsrv);
    fprintf(f2, "%llx\n", afl->fsrv.nyx_target_hash64);

  } else {

    fprintf(f2, "%p\n", (void *)get_binary_hash(afl->fsrv.target_path));

  }

#else
  fprintf(f2, "%p\n", (void *)get_binary_hash(afl->fsrv.target_path));
#endif
  fclose(f2);

  snprintf(fn, PATH_MAX, "%s/fuzzer_setup", afl->out_dir);
  FILE *f = create_ffile(fn, afl->perm);
  u32   i;

  if (afl->chown_needed) {

    if (chown(fn, -1, afl->fsrv.gid) == -1) { PFATAL("chown() failed"); }

  }

  fprintf(f, "# environment variables:\n");
  u32 s_afl_env = (u32)sizeof(afl_environment_variables) /
                      sizeof(afl_environment_variables[0]) -
                  1U;

  for (i = 0; i < s_afl_env; ++i) {

    char *val;
    if ((val = getenv(afl_environment_variables[i])) != NULL) {

      fprintf(f, "%s=%s\n", afl_environment_variables[i], val);

    }

  }

  fprintf(f, "# command line:\n");

  size_t j;
  for (i = 0; i < argc; ++i) {

    if (i) fprintf(f, " ");
#ifdef __ANDROID__
    if (memchr(argv[i], '\'', strlen(argv[i]))) {

#else
    if (strchr(argv[i], '\'')) {

#endif

      fprintf(f, "'");
      for (j = 0; j < strlen(argv[i]); j++)
        if (argv[i][j] == '\'')
          fprintf(f, "'\"'\"'");
        else
          fprintf(f, "%c", argv[i][j]);
      fprintf(f, "'");

    } else {

      fprintf(f, "'%s'", argv[i]);

    }

  }

  fprintf(f, "\n");

  fclose(f);
  (void)(afl_environment_deprecated);

}

static bool starts_with(char *key, char *line) {

  return strncmp(key, line, strlen(key)) == 0;

}

/* load some of the existing stats file when resuming.*/
void load_stats_file(afl_state_t *afl) {

  FILE *f;
  u8    buf[MAX_LINE];
  u8   *lptr;
  u8    fn[PATH_MAX];
  u32   lineno = 0;
  snprintf(fn, PATH_MAX, "%s/fuzzer_stats", afl->out_dir);
  f = fopen(fn, "r");
  if (!f) {

    WARNF("Unable to load stats file '%s'", fn);
    return;

  }

  while ((lptr = fgets(buf, MAX_LINE, f))) {

    lineno++;
    u8 *lstartptr = lptr;
    u8 *rptr = lptr + strlen(lptr) - 1;
    u8  keystring[MAX_LINE];
    while (*lptr != ':' && lptr < rptr) {

      lptr++;

    }

    if (*lptr == '\n' || !*lptr) {

      WARNF("Unable to read line %d of stats file", lineno);
      continue;

    }

    if (*lptr == ':') {

      *lptr = 0;
      strcpy(keystring, lstartptr);
      lptr++;
      char *nptr;
      if (starts_with("run_time", keystring)) {

        afl->prev_run_time = 1000 * strtoull(lptr, &nptr, 10);

      }

      if (starts_with("cycles_done", keystring)) {

        afl->queue_cycle =
            strtoull(lptr, &nptr, 10) ? strtoull(lptr, &nptr, 10) + 1 : 0;

      }

      if (starts_with("calibration_time", keystring)) {

        afl->calibration_time_us = strtoull(lptr, &nptr, 10) * 1000000;

      }

      if (starts_with("sync_time", keystring)) {

        afl->sync_time_us = strtoull(lptr, &nptr, 10) * 1000000;

      }

      if (starts_with("cmplog_time", keystring)) {

        afl->cmplog_time_us = strtoull(lptr, &nptr, 10) * 1000000;

      }

      if (starts_with("trim_time", keystring)) {

        afl->trim_time_us = strtoull(lptr, &nptr, 10) * 1000000;

      }

      if (starts_with("execs_done", keystring)) {

        afl->fsrv.total_execs = strtoull(lptr, &nptr, 10);

      }

      if (starts_with("corpus_count", keystring)) {

        u32 corpus_count = strtoul(lptr, &nptr, 10);
        if (corpus_count != afl->queued_items) {

          WARNF(
              "queue/ has been modified -- things might not work, you're "
              "on your own!");
          sleep(3);

        }

      }

      if (starts_with("corpus_found", keystring)) {

        afl->queued_discovered = strtoul(lptr, &nptr, 10);

      }

      if (starts_with("corpus_imported", keystring)) {

        afl->queued_imported = strtoul(lptr, &nptr, 10);

      }

      if (starts_with("max_depth", keystring)) {

        afl->max_depth = strtoul(lptr, &nptr, 10);

      }

      if (starts_with("saved_crashes", keystring)) {

        afl->saved_crashes = strtoull(lptr, &nptr, 10);

      }

      if (starts_with("saved_hangs", keystring)) {

        afl->saved_hangs = strtoull(lptr, &nptr, 10);

      }

    }

  }

  if (afl->saved_crashes) { write_crash_readme(afl); }

  return;

}
/* --- NV 2.5: minimal JSON string escape --- */
static void nv_json_puts_escaped(FILE *f, const char *s) {

  if (!s) { fputs("(null)", f); return; }

  for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {

    unsigned char c = *p;
    switch (c) {
      case '\\': fputs("\\\\", f); break;
      case '\"': fputs("\\\"", f); break;
      case '\b': fputs("\\b", f); break;
      case '\f': fputs("\\f", f); break;
      case '\n': fputs("\\n", f); break;
      case '\r': fputs("\\r", f); break;
      case '\t': fputs("\\t", f); break;
      default:
        if (c < 0x20) fprintf(f, "\\u%04x", c);
        else fputc(c, f);
    }

  }

}
/* --- NV 2.5: write eval_report.json --- */
static void nv_write_eval_report_json(afl_state_t *afl, double bitmap_cvg,
                                      u32 edges_found) {

  char fn_tmp[PATH_MAX], fn_final[PATH_MAX];
  snprintf(fn_tmp,   PATH_MAX, "%s/.eval_report_tmp.json", afl->out_dir);
  snprintf(fn_final, PATH_MAX, "%s/eval_report.json", afl->out_dir);

  FILE *j = fopen(fn_tmp, "w");
  if (!j) return;

  u64 valid_exec = afl->nv_total_valid_exec;
  u64 err_exec   = afl->nv_err_exec;
  u64 rec_total  = afl->nv_rec_total;
  u64 rec_succ   = afl->nv_rec_success;

  double err_rate = valid_exec ? (double)err_exec / (double)valid_exec : 0.0;
  double rec_rate = rec_total  ? (double)rec_succ / (double)rec_total  : 0.0;
  double rec_avg  = rec_succ   ? (double)afl->nv_rec_time_sum_ms / (double)rec_succ : 0.0;

  u64 tot_v = afl->nv_valid_cnt + afl->nv_invalid_cnt;
  double invalid_rate = tot_v ? (double)afl->nv_invalid_cnt / (double)tot_v : 0.0;
  u8 has_nv_task = afl->nv_task_path && afl->nv_task_path[0];
  const char *task_source = has_nv_task ? "nv_task_path" : "harness_only";
  const char *target_type_name = "unknown";
  if (afl->nv_task.target_type == NV_TARGET_HTTP_API) target_type_name = "http_api";
  else if (afl->nv_task.target_type == NV_TARGET_BINARY) target_type_name = "binary";

  /* JSON */
  fputs("{\n", j);

  /* task (你现在 nv_task 里没有 task_id/task_name 字段，就先输出现有字段；后续若你补充字段再扩展) */
  fputs("  \"task\": {\n", j);
  fprintf(j, "    \"source\": \"%s\",\n", task_source);
  fputs("    \"source_note\": \"", j);
  nv_json_puts_escaped(
      j,
      has_nv_task
          ? "Loaded from NV_TASK_PATH; AFL++ task metadata is authoritative."
          : "NV_TASK_PATH was not set; AFL++ task metadata is inactive and harness/report artifacts are the source of task context.");
  fputs("\",\n", j);
  fputs("    \"nv_task_path\": \"", j);
  nv_json_puts_escaped(j, has_nv_task ? (const char *)afl->nv_task_path : "");
  fputs("\",\n", j);
  fprintf(j, "    \"target_type_name\": \"%s\",\n", target_type_name);
  fprintf(j, "    \"target_type\": %d,\n", (int)afl->nv_task.target_type);

  fputs("    \"target_endpoint\": \"", j);
  nv_json_puts_escaped(
      j,
      has_nv_task && afl->nv_task.target_endpoint
          ? (const char *)afl->nv_task.target_endpoint
          : "");
  fputs("\",\n", j);

  fputs("    \"seed_source\": \"", j);
  nv_json_puts_escaped(
      j,
      has_nv_task && afl->nv_task.seed_source
          ? (const char *)afl->nv_task.seed_source
          : "");
  fputs("\",\n", j);

  fputs("    \"seed_location\": \"", j);
  nv_json_puts_escaped(
      j,
      has_nv_task && afl->nv_task.seed_location
          ? (const char *)afl->nv_task.seed_location
          : "");
  fputs("\",\n", j);

  fprintf(j, "    \"mutation_scope\": %u,\n", (unsigned)afl->nv_task.mutation_scope);
  fprintf(j, "    \"max_test_cases\": %llu,\n", (unsigned long long)afl->nv_task.max_test_cases);
  fprintf(j, "    \"time_budget_sec\": %llu,\n", (unsigned long long)afl->nv_task.time_budget_sec);
  fprintf(j, "    \"enable_validity\": %u\n", (unsigned)afl->nv_task.enable_validity);
  fputs("  },\n", j);

  /* cov */
  fprintf(j, "  \"cov\": {\"bitmap_cvg\": %.6f, \"edges_found\": %u},\n",
          bitmap_cvg, edges_found);

  /* security-state coverage: the project's Cov signal.  Deliberately
     reported next to, and separately from, the AFL edge bitmap above. */
  fprintf(j,
          "  \"security_state_cov\": {\"security_state_total\": %u, "
          "\"security_state_new_total\": %llu, "
          "\"security_state_delta_last\": %llu, "
          "\"security_state_observations\": %llu, "
          "\"security_state_seed_credit\": %llu, "
          "\"security_state_capacity\": %u, "
          "\"security_state_saturated\": %u, "
          "\"security_state_dropped\": %llu, "
          "\"security_state_replays\": %llu, "
          "\"security_state_reward_src_seq\": %llu, "
          "\"state_id\": \"fnv1a64(METHOD SPACE PATH | RESPONSE_CLASS)\", "
          "\"note\": \"project security-state coverage; not AFL native edge "
          "coverage\"},\n",
          afl->nv_cov_used,
          (unsigned long long)afl->nv_sec_state_new_total,
          (unsigned long long)afl->nv_sec_state_delta_last,
          (unsigned long long)afl->nv_sec_state_obs,
          (unsigned long long)afl->nv_sec_state_seed_credit,
          afl->nv_cov_cap,
          (unsigned)afl->nv_sec_state_saturated,
          (unsigned long long)afl->nv_sec_state_dropped,
          (unsigned long long)afl->nv_sec_state_replays,
          (unsigned long long)afl->nv_sec_state_reward_src_seq);

  /* mab: enough to prove whether UCB actually ran */
  fprintf(j,
          "  \"mab\": {\"c\": %.6f, \"min_explore\": %llu, "
          "\"total_pulls\": %llu, \"cold_start_picks\": %llu, "
          "\"ucb_picks\": %llu, \"arms\": [",
          afl->nv_mab.c,
          (unsigned long long)afl->nv_mab.min_explore,
          (unsigned long long)afl->nv_mab.total_pulls,
          (unsigned long long)afl->nv_mab.cold_start_picks,
          (unsigned long long)afl->nv_mab.ucb_picks);

  for (int a = 0; a < NV_ARM_MAX; ++a) {

    fprintf(j,
            "%s{\"arm\": %d, \"pulls\": %llu, \"mean_reward\": %.6f, "
            "\"sum_reward\": %.6f, \"pos_cnt\": %llu}",
            a ? ", " : "", a,
            (unsigned long long)afl->nv_mab.arms[a].pulls,
            afl->nv_mab.arms[a].mean_reward,
            afl->nv_mab.arms[a].sum_reward,
            (unsigned long long)afl->nv_mab.arms[a].pos_cnt);

  }

  fputs("]},\n", j);
  fprintf(j,
          "  \"mab_journal\": {\"enabled\": %u, \"record_count\": %llu, "
          "\"error_count\": %llu, \"audit_invalid\": %u},\n",
          (unsigned)(afl->nv_mab_journal_enabled ||
                     (getenv("NV_MAB_JOURNAL_PATH") &&
                      *getenv("NV_MAB_JOURNAL_PATH"))),
          (unsigned long long)afl->nv_mab_journal_record_count,
          (unsigned long long)afl->nv_mab_journal_error_count,
          (unsigned)afl->nv_mab_journal_audit_invalid);

  /* validity */
  fprintf(j,
          "  \"validity\": {\"valid_cnt\": %llu, \"invalid_cnt\": %llu, "
          "\"invalid_rate\": %.6f, \"invalid_parse_cnt\": %llu, "
          "\"invalid_rule_cnt\": %llu, \"invalid_rpc_fail_cnt\": %llu},\n",
          (unsigned long long)afl->nv_valid_cnt,
          (unsigned long long)afl->nv_invalid_cnt,
          invalid_rate,
          (unsigned long long)afl->nv_invalid_parse_cnt,
          (unsigned long long)afl->nv_invalid_rule_cnt,
          (unsigned long long)afl->nv_invalid_rpc_fail_cnt);

  /* err */
  fprintf(j, "  \"err\": {\"err_exec\": %llu, \"err_rate\": %.6f},\n",
          (unsigned long long)err_exec, err_rate);

  /* rec */
  fprintf(j,
          "  \"rec\": {\"rec_total\": %llu, \"rec_success\": %llu, "
          "\"rec_rate\": %.6f, \"rec_avg_ms\": %.3f},\n",
          (unsigned long long)rec_total,
          (unsigned long long)rec_succ,
          rec_rate, rec_avg);

  /* exec summary */
  fprintf(j,
          "  \"exec\": {\"valid_exec\": %llu, \"total_execs\": %llu}\n",
          (unsigned long long)valid_exec,
          (unsigned long long)afl->fsrv.total_execs);

  fputs("}\n", j);

  fclose(j);
  rename(fn_tmp, fn_final);

}
/* Update stats file for unattended monitoring. */

void write_stats_file(afl_state_t *afl, u32 t_bytes, double bitmap_cvg,
                      double stability, double eps) {

#ifndef __HAIKU__
  struct rusage rus;
#endif

  u64   cur_time = get_cur_time();
  u8    fn_tmp[PATH_MAX];
  u8    fn_final[PATH_MAX];
  FILE *f;

  snprintf(fn_tmp, PATH_MAX, "%s/.fuzzer_stats_tmp", afl->out_dir);
  snprintf(fn_final, PATH_MAX, "%s/fuzzer_stats", afl->out_dir);
  f = create_ffile(fn_tmp, afl->perm);

  if (afl->chown_needed) {

    if (chown(fn_tmp, -1, afl->fsrv.gid) == -1) { PFATAL("fchown() failed"); }

  }

  /* Keep last values in case we're called from another context
     where exec/sec stats and such are not readily available. */

  if (!bitmap_cvg && !stability && !eps) {

    bitmap_cvg = afl->last_bitmap_cvg;
    stability = afl->last_stability;

  } else {

    afl->last_bitmap_cvg = bitmap_cvg;
    afl->last_stability = stability;
    afl->last_eps = eps;

  }

  if ((unlikely(!afl->last_avg_exec_update ||
                cur_time - afl->last_avg_exec_update >= 60000))) {

    afl->last_avg_execs_saved =
        (double)(1000 * (afl->fsrv.total_execs - afl->last_avg_total_execs)) /
        (double)(cur_time - afl->last_avg_exec_update);
    afl->last_avg_total_execs = afl->fsrv.total_execs;
    afl->last_avg_exec_update = cur_time;

  }

#ifndef __HAIKU__
  if (getrusage(RUSAGE_CHILDREN, &rus)) { rus.ru_maxrss = 0; }
#endif
  u64 runtime_ms = afl->prev_run_time + cur_time - afl->start_time;
  u64 overhead_ms = (afl->calibration_time_us + afl->sync_time_us +
                     afl->trim_time_us + afl->cmplog_time_us) /
                    1000;
  if (!runtime_ms) { runtime_ms = 1; }

  fprintf(f,
          "start_time        : %llu\n"
          "last_update       : %llu\n"
          "run_time          : %llu\n"
          "fuzzer_pid        : %u\n"
          "cycles_done       : %llu\n"
          "cycles_wo_finds   : %llu\n"
          "time_wo_finds     : %llu\n"
          "fuzz_time         : %llu\n"
          "calibration_time  : %llu\n"
          "cmplog_time       : %llu\n"
          "sync_time         : %llu\n"
          "trim_time         : %llu\n"
          "execs_done        : %llu\n"
          "execs_per_sec     : %0.02f\n"
          "execs_ps_last_min : %0.02f\n"
          "corpus_count      : %u\n"
          "corpus_favored    : %u\n"
          "corpus_found      : %u\n"
          "corpus_imported   : %u\n"
          "corpus_variable   : %u\n"
          "max_depth         : %u\n"
          "cur_item          : %u\n"
          "pending_favs      : %u\n"
          "pending_total     : %u\n"
          "stability         : %0.02f%%\n"
          "bitmap_cvg        : %0.02f%%\n"
          "saved_crashes     : %llu\n"
          "saved_hangs       : %llu\n"
          "total_tmout       : %llu\n"
          "last_find         : %llu\n"
          "last_crash        : %llu\n"
          "last_hang         : %llu\n"
          "execs_since_crash : %llu\n"
          "exec_timeout      : %u\n"
          "slowest_exec_ms   : %u\n"
          "peak_rss_mb       : %lu\n"
          "cpu_affinity      : %d\n"
          "edges_found       : %u\n"
          "total_edges       : %u\n"
          "var_byte_count    : %u\n"
          "havoc_expansion   : %u\n"
          "auto_dict_entries : %u\n"
          "testcache_size    : %llu\n"
          "testcache_count   : %u\n"
          "testcache_evict   : %u\n"
          "afl_banner        : %s\n"
          "afl_version       : " VERSION
          "\n"
          "target_mode       : %s%s%s%s%s%s%s%s%s%s\n"
          "command_line      : %s\n",
          (afl->start_time /*- afl->prev_run_time*/) / 1000, cur_time / 1000,
          runtime_ms / 1000, (u32)getpid(),
          afl->queue_cycle ? (afl->queue_cycle - 1) : 0, afl->cycles_wo_finds,
          afl->longest_find_time > cur_time - afl->last_find_time
              ? afl->longest_find_time / 1000
              : ((afl->start_time == 0 || afl->last_find_time == 0)
                     ? 0
                     : (cur_time - afl->last_find_time) / 1000),
          (runtime_ms - MIN(runtime_ms, overhead_ms)) / 1000,
          afl->calibration_time_us / 1000000, afl->cmplog_time_us / 1000000,
          afl->sync_time_us / 1000000, afl->trim_time_us / 1000000,
          afl->fsrv.total_execs,
          afl->fsrv.total_execs / ((double)(runtime_ms) / 1000),
          afl->last_avg_execs_saved, afl->queued_items, afl->queued_favored,
          afl->queued_discovered, afl->queued_imported, afl->queued_variable,
          afl->max_depth, afl->current_entry, afl->pending_favored,
          afl->pending_not_fuzzed, stability, bitmap_cvg, afl->saved_crashes,
          afl->saved_hangs, afl->total_tmouts, afl->last_find_time / 1000,
          afl->last_crash_time / 1000, afl->last_hang_time / 1000,
          afl->fsrv.total_execs - afl->last_crash_execs, afl->fsrv.exec_tmout,
          afl->slowest_exec_ms,
#ifndef __HAIKU__
  #ifdef __APPLE__
          (unsigned long int)(rus.ru_maxrss >> 20),
  #else
          (unsigned long int)(rus.ru_maxrss >> 10),
  #endif
#else
          -1UL,
#endif
#ifdef HAVE_AFFINITY
          afl->cpu_aff,
#else
          -1,
#endif
          t_bytes, afl->fsrv.real_map_size, afl->var_byte_count,
          afl->expand_havoc, afl->a_extras_cnt, afl->q_testcase_cache_size,
          afl->q_testcase_cache_count, afl->q_testcase_evictions,
          afl->use_banner, afl->unicorn_mode ? "unicorn" : "",
          afl->fsrv.qemu_mode ? "qemu " : "",
          afl->fsrv.cs_mode ? "coresight" : "",
          afl->non_instrumented_mode ? " non_instrumented " : "",
          afl->no_forkserver ? "no_fsrv " : "", afl->crash_mode ? "crash " : "",
          afl->persistent_mode ? "persistent " : "",
          afl->shmem_testcase_mode ? "shmem_testcase " : "",
          afl->deferred_mode ? "deferred " : "",
          (afl->unicorn_mode || afl->fsrv.qemu_mode || afl->fsrv.cs_mode ||
           afl->non_instrumented_mode || afl->no_forkserver ||
           afl->crash_mode || afl->persistent_mode || afl->deferred_mode)
              ? ""
              : "default",
          afl->orig_cmdline);
  fprintf(f, "nv_task_path       : %s\n",
              afl->nv_task_path ? (char *)afl->nv_task_path : "(null)");
  fprintf(f, "nv_target_type     : %d\n", (int)afl->nv_task.target_type);
  fprintf(f, "nv_target_endpoint : %s\n",
              afl->nv_task.target_endpoint ? (char *)afl->nv_task.target_endpoint : "(null)");
  fprintf(f, "nv_seed_source     : %s\n",
              afl->nv_task.seed_source ? (char *)afl->nv_task.seed_source : "(null)");
  fprintf(f, "nv_seed_location   : %s\n",
              afl->nv_task.seed_location ? (char *)afl->nv_task.seed_location : "(null)");
  fprintf(f, "nv_mutation_scope  : 0x%x\n", afl->nv_task.mutation_scope);
  fprintf(f, "nv_max_test_cases  : %llu\n",
              (unsigned long long)afl->nv_task.max_test_cases);
  fprintf(f, "nv_time_budget_sec : %llu\n",
              (unsigned long long)afl->nv_task.time_budget_sec);          
  if (afl->queue_cur) {
  fprintf(f, "ss_cov_cnt : %llu\n",
          (unsigned long long)afl->queue_cur->ss_cov_cnt);
  fprintf(f, "ss_selected_cnt : %llu\n",
          (unsigned long long)afl->queue_cur->ss_selected_cnt);
  fprintf(f, "ss_prob : %.6f\n", afl->queue_cur->ss_prob);
}
  /* ---- NV MAB stats (global, always print) ---- */
  fprintf(f, "nv_mab_total_pulls : %llu\n",
          (unsigned long long)afl->nv_mab.total_pulls);
  fprintf(f, "nv_mab_last_arm    : %u\n", (unsigned)afl->nv_mab.last_arm);
  fprintf(f, "nv_mab_pending_arm : %u\n", (unsigned)afl->nv_mab.pending_arm);
  fprintf(f, "nv_mab_pending     : %u\n", (unsigned)afl->nv_mab.pending_update);
  fprintf(f, "nv_mab_update_src  : %u\n", (unsigned)afl->nv_mab.update_source);
  fprintf(f, "nv_mab_journal_enabled : %u\n",
          (unsigned)(afl->nv_mab_journal_enabled ||
                     (getenv("NV_MAB_JOURNAL_PATH") &&
                      *getenv("NV_MAB_JOURNAL_PATH"))));
  fprintf(f, "nv_mab_journal_record_count : %llu\n",
          (unsigned long long)afl->nv_mab_journal_record_count);
  fprintf(f, "nv_mab_journal_error_count : %llu\n",
          (unsigned long long)afl->nv_mab_journal_error_count);
  fprintf(f, "nv_mab_journal_audit_invalid : %u\n",
          (unsigned)afl->nv_mab_journal_audit_invalid);
  fprintf(f, "nv_mab_journal_pending_cleared_count : %llu\n",
          (unsigned long long)afl->nv_mab_journal_pending_cleared_count);
  fprintf(f, "nv_mab_journal_mismatch_count : %llu\n",
           (unsigned long long)afl->nv_mab_journal_mismatch_count);
  fprintf(f, "nv_execution_ledger_enabled : %u\n",
          (unsigned)(afl->nv_execution_ledger_enabled ||
                     (getenv("NV_EXECUTION_LEDGER_PATH") &&
                      *getenv("NV_EXECUTION_LEDGER_PATH"))));
  fprintf(f, "nv_execution_ledger_record_count : %llu\n",
          (unsigned long long)afl->nv_execution_ledger_record_count);
  fprintf(f, "nv_execution_ledger_error_count : %llu\n",
          (unsigned long long)afl->nv_execution_ledger_error_count);
  fprintf(f, "nv_execution_ledger_audit_invalid : %u\n",
           (unsigned)afl->nv_execution_ledger_audit_invalid);
  fprintf(f, "nv_execution_iteration : %llu\n",
          (unsigned long long)afl->nv_execution_iteration);
  fprintf(f, "nv_mab_c           : %.10e\n", afl->nv_mab.c);
  fprintf(f, "nv_mab_min_explore : %llu\n",
          (unsigned long long)afl->nv_mab.min_explore);
  fprintf(f, "nv_mab_cold_start_picks : %llu\n",
          (unsigned long long)afl->nv_mab.cold_start_picks);
  fprintf(f, "nv_mab_ucb_picks   : %llu\n",
          (unsigned long long)afl->nv_mab.ucb_picks);

  /* ---- security-state coverage (project Cov, not AFL edge coverage) ---- */
  fprintf(f, "security_state_total : %u\n", afl->nv_cov_used);
  fprintf(f, "security_state_new_total : %llu\n",
          (unsigned long long)afl->nv_sec_state_new_total);
  fprintf(f, "security_state_delta_last : %llu\n",
          (unsigned long long)afl->nv_sec_state_delta_last);
  fprintf(f, "security_state_observations : %llu\n",
          (unsigned long long)afl->nv_sec_state_obs);
  fprintf(f, "security_state_seed_credit : %llu\n",
          (unsigned long long)afl->nv_sec_state_seed_credit);
  fprintf(f, "security_state_capacity : %u\n", afl->nv_cov_cap);
  fprintf(f, "security_state_saturated : %u\n",
          (unsigned)afl->nv_sec_state_saturated);
  fprintf(f, "security_state_dropped : %llu\n",
          (unsigned long long)afl->nv_sec_state_dropped);
  fprintf(f, "security_state_replays : %llu\n",
          (unsigned long long)afl->nv_sec_state_replays);
  fprintf(f, "security_state_reward_src_seq : %llu\n",
          (unsigned long long)afl->nv_sec_state_reward_src_seq);

  fprintf(f, "nv_mab_arm0_pulls  : %llu\n",
          (unsigned long long)afl->nv_mab.arms[0].pulls);
  fprintf(f, "nv_mab_arm0_mean   : %.10e\n", afl->nv_mab.arms[0].mean_reward);
  fprintf(f, "nv_mab_arm0_pos    : %llu\n",
          (unsigned long long)afl->nv_mab.arms[0].pos_cnt);
  fprintf(f, "nv_mab_arm0_sum    : %.10e\n",
          afl->nv_mab.arms[0].sum_reward);

  fprintf(f, "nv_mab_arm1_pulls  : %llu\n",
          (unsigned long long)afl->nv_mab.arms[1].pulls);
  fprintf(f, "nv_mab_arm1_mean   : %.10e\n", afl->nv_mab.arms[1].mean_reward);
  fprintf(f, "nv_mab_arm1_pos    : %llu\n",
          (unsigned long long)afl->nv_mab.arms[1].pos_cnt);
  fprintf(f, "nv_mab_arm1_sum    : %.10e\n",
          afl->nv_mab.arms[1].sum_reward);

  fprintf(f, "nv_mab_arm2_pulls  : %llu\n",
          (unsigned long long)afl->nv_mab.arms[2].pulls);
  fprintf(f, "nv_mab_arm2_mean   : %.10e\n", afl->nv_mab.arms[2].mean_reward);
  fprintf(f, "nv_mab_arm2_pos    : %llu\n",
          (unsigned long long)afl->nv_mab.arms[2].pos_cnt);
  fprintf(f, "nv_mab_arm2_sum    : %.10e\n",
          afl->nv_mab.arms[2].sum_reward);
  fprintf(f, "nv_enable_validity : %u\n", (unsigned)afl->nv_task.enable_validity);
  fprintf(f, "nv_valid_cnt       : %llu\n", (unsigned long long)afl->nv_valid_cnt);
  fprintf(f, "nv_invalid_cnt     : %llu\n", (unsigned long long)afl->nv_invalid_cnt);
  u64 tot = afl->nv_valid_cnt + afl->nv_invalid_cnt;
  double rate = tot ? (double)afl->nv_invalid_cnt / (double)tot : 0.0;
  fprintf(f, "nv_invalid_rate    : %.6f\n", rate);
    /* --- NV 2.5 metrics --- */
  fprintf(f, "nv_total_valid_exec : %llu\n",
          (unsigned long long)afl->nv_total_valid_exec);

  fprintf(f, "nv_err_exec         : %llu\n",
          (unsigned long long)afl->nv_err_exec);

  double err_rate2 = afl->nv_total_valid_exec
                       ? (double)afl->nv_err_exec / (double)afl->nv_total_valid_exec
                       : 0.0;
  fprintf(f, "nv_err_rate         : %.6f\n", err_rate2);

  fprintf(f, "nv_rec_total        : %llu\n",
          (unsigned long long)afl->nv_rec_total);

  fprintf(f, "nv_rec_success      : %llu\n",
          (unsigned long long)afl->nv_rec_success);

  double rec_rate2 = afl->nv_rec_total
                       ? (double)afl->nv_rec_success / (double)afl->nv_rec_total
                       : 0.0;
  fprintf(f, "nv_rec_rate         : %.6f\n", rec_rate2);

  double rec_avg_ms2 = afl->nv_rec_success
                         ? (double)afl->nv_rec_time_sum_ms / (double)afl->nv_rec_success
                         : 0.0;
  fprintf(f, "nv_rec_avg_ms       : %.3f\n", rec_avg_ms2);
  fprintf(f, "nv_invalid_parse_cnt    : %llu\n",
          (unsigned long long)afl->nv_invalid_parse_cnt);
  fprintf(f, "nv_invalid_rule_cnt     : %llu\n",
          (unsigned long long)afl->nv_invalid_rule_cnt);
  fprintf(f, "nv_invalid_rpc_fail_cnt : %llu\n",
          (unsigned long long)afl->nv_invalid_rpc_fail_cnt);
  fprintf(f, "nv_invalid_allow_cnt   : %llu\n",
          (unsigned long long)afl->nv_invalid_allow_cnt);
  fprintf(f, "nv_invalid_docid_cnt   : %llu\n",
          (unsigned long long)afl->nv_invalid_docid_cnt);
  fprintf(f, "nv_invalid_body_cnt    : %llu\n",
          (unsigned long long)afl->nv_invalid_body_cnt);
  fprintf(f, "nv_invalid_score_cnt   : %llu\n",
          (unsigned long long)afl->nv_invalid_score_cnt);
  u64 ss_cov_max = 0;
  for (u32 i = 0; i < afl->queued_items; ++i) {
    struct queue_entry *q = afl->queue_buf[i];
    if (q && q->ss_cov_cnt > ss_cov_max) ss_cov_max = q->ss_cov_cnt;
  }
  fprintf(f, "ss_cov_max       : %llu\n", (unsigned long long)ss_cov_max);
  fprintf(f, "ss_new_bits_any  : %llu\n", (unsigned long long)ss_new_bits_any);
  fprintf(f, "ss_new_bits_kept : %llu\n", (unsigned long long)ss_new_bits_kept);
    /* ===== SS scheduling stats (global view) ===== */
  u64    ss_cov_sum = 0, ss_sel_sum = 0;
  u64    ss_cov_max2 = 0, ss_sel_max = 0;
  double ss_prob_max = 0.0;

  for (u32 i = 0; i < afl->queued_items; ++i) {

    struct queue_entry *q = afl->queue_buf[i];
    if (!q) continue;

    ss_cov_sum += q->ss_cov_cnt;
    ss_sel_sum += q->ss_selected_cnt;

    if (q->ss_cov_cnt > ss_cov_max2) ss_cov_max2 = q->ss_cov_cnt;
    if (q->ss_selected_cnt > ss_sel_max) ss_sel_max = q->ss_selected_cnt;
    if (q->ss_prob > ss_prob_max) ss_prob_max = q->ss_prob;

  }

  /* 你原来的 ss_cov_max 也可以保留，这里给一个更全面的集合 */
  fprintf(f, "ss_cov_sum       : %llu\n", (unsigned long long)ss_cov_sum);
  fprintf(f, "ss_selected_sum  : %llu\n", (unsigned long long)ss_sel_sum);
  fprintf(f, "ss_cov_max2      : %llu\n", (unsigned long long)ss_cov_max2);
  fprintf(f, "ss_selected_max  : %llu\n", (unsigned long long)ss_sel_max);
  fprintf(f, "ss_prob_max      : %.6f\n", ss_prob_max);

  fprintf(f, "seed_audit_enabled : %u\n",
          (unsigned)(afl->seed_audit_enabled ||
                     (getenv("NV_SEED_SELECTION_AUDIT_PATH") &&
                      *getenv("NV_SEED_SELECTION_AUDIT_PATH"))));
  fprintf(f, "seed_audit_error_count : %llu\n",
          (unsigned long long)afl->seed_audit_error_count);
  fprintf(f, "seed_audit_invalid : %u\n", (unsigned)afl->seed_audit_invalid);
  fprintf(f, "seed_audit_record_count : %llu\n",
          (unsigned long long)afl->seed_audit_record_count);
  fprintf(f, "seed_audit_expected_selection_count : %llu\n",
          (unsigned long long)afl->seed_audit_expected_selection_count);
  if (afl->seed_audit_enabled ||
      (getenv("NV_SEED_SELECTION_AUDIT_PATH") &&
       *getenv("NV_SEED_SELECTION_AUDIT_PATH"))) {

    for (u32 i = 0; i < afl->queued_items; ++i) {

      struct queue_entry *q = afl->queue_buf[i];
      if (!q) continue;
      fprintf(f, "ss_selected_queue_%u : %llu\n", q->id,
              (unsigned long long)q->ss_selected_cnt);

    }

  }
  
  if (afl->san_binary_length) {

    for (u8 i = 0; i < afl->san_binary_length; i++) {

      fprintf(f,
              "extra_binary      : %s\n"
              "total_execs       : %llu\n",
              afl->san_binary[i], afl->san_fsrvs[i].total_execs);

    }

  }

  /* ignore errors */

  if (afl->debug) {

    u32 i = 0;
    fprintf(f, "virgin_bytes     :");
    for (i = 0; i < afl->fsrv.real_map_size; i++) {

      if (afl->virgin_bits[i] != 0xff) {

        fprintf(f, " %u[%02x]", i, afl->virgin_bits[i]);

      }

    }

    fprintf(f, "\n");
    fprintf(f, "var_bytes        :");
    for (i = 0; i < afl->fsrv.real_map_size; i++) {

      if (afl->var_bytes[i]) { fprintf(f, " %u", i); }

    }

    fprintf(f, "\n");

  }
  u32 edges_found = 0;
  if (afl->virgin_bits) edges_found = count_non_255_bytes(afl, afl->virgin_bits);
  nv_write_eval_report_json(afl, bitmap_cvg, edges_found);

  fclose(f);
  rename(fn_tmp, fn_final);

}

#ifdef INTROSPECTION
void write_queue_stats(afl_state_t *afl) {

  FILE *f;
  u8   *fn = alloc_printf("%s/queue_data", afl->out_dir);
  if ((f = fopen(fn, "w")) != NULL) {

    u32 id;
    fprintf(f,
            "# filename, length, exec_us, selected, skipped, mutations, finds, "
            "crashes, timeouts, bitmap_size, perf_score, weight, colorized, "
            "favored, disabled\n");
    for (id = 0; id < afl->queued_items; ++id) {

      struct queue_entry *q = afl->queue_buf[id];
      fprintf(f, "\"%s\",%u,%llu,%u,%u,%llu,%u,%u,%u,%u,%.3f,%.3f,%u,%u,%u\n",
              q->fname, q->len, q->exec_us, q->stats_selected, q->stats_skipped,
              q->stats_mutated, q->stats_finds, q->stats_crashes,
              q->stats_tmouts, q->bitmap_size, q->perf_score, q->weight,
              q->colorized, q->favored, q->disabled);

    }

    fclose(f);

  }

  ck_free(fn);

}

#endif

/* Update the plot file if there is a reason to. */

void maybe_update_plot_file(afl_state_t *afl, u32 t_bytes, double bitmap_cvg,
                            double eps) {

  if (unlikely(!afl->force_ui_update &&
               (afl->stop_soon ||
                (afl->plot_prev_qp == afl->queued_items &&
                 afl->plot_prev_pf == afl->pending_favored &&
                 afl->plot_prev_pnf == afl->pending_not_fuzzed &&
                 afl->plot_prev_ce == afl->current_entry &&
                 afl->plot_prev_qc == afl->queue_cycle &&
                 afl->plot_prev_uc == afl->saved_crashes &&
                 afl->plot_prev_uh == afl->saved_hangs &&
                 afl->plot_prev_md == afl->max_depth &&
                 afl->plot_prev_ed == afl->fsrv.total_execs) ||
                !afl->queue_cycle ||
                get_cur_time() - afl->start_time <= 60000))) {

    return;

  }

  afl->plot_prev_qp = afl->queued_items;
  afl->plot_prev_pf = afl->pending_favored;
  afl->plot_prev_pnf = afl->pending_not_fuzzed;
  afl->plot_prev_ce = afl->current_entry;
  afl->plot_prev_qc = afl->queue_cycle;
  afl->plot_prev_uc = afl->saved_crashes;
  afl->plot_prev_uh = afl->saved_hangs;
  afl->plot_prev_md = afl->max_depth;
  afl->plot_prev_ed = afl->fsrv.total_execs;

  /* Fields in the file:

     relative_time, afl->cycles_done, cur_item, corpus_count, corpus_not_fuzzed,
     favored_not_fuzzed, saved_crashes, saved_hangs, max_depth,
     execs_per_sec, edges_found */

  fprintf(afl->fsrv.plot_file,
          "%llu, %llu, %u, %u, %u, %u, %0.02f%%, %llu, %llu, %u, %0.02f, %llu, "
          "%u, %llu, %u",
          ((afl->prev_run_time + get_cur_time() - afl->start_time) / 1000),
          afl->queue_cycle - 1, afl->current_entry, afl->queued_items,
          afl->pending_not_fuzzed, afl->pending_favored, bitmap_cvg,
          afl->saved_crashes, afl->saved_hangs, afl->max_depth, eps,
          afl->plot_prev_ed, t_bytes, afl->total_crashes,
          (u32)afl->san_binary_length);                    /* ignore errors */

  for (u32 i = 0; i < afl->san_binary_length; i++) {

    fprintf(afl->fsrv.plot_file, ", %llu", afl->san_fsrvs[i].total_execs);

  }
  fprintf(afl->fsrv.plot_file, ", %llu, %llu, %llu, %.6e, %.6e, %.6e",
        (unsigned long long)afl->nv_mab.arms[0].pos_cnt,
        (unsigned long long)afl->nv_mab.arms[1].pos_cnt,
        (unsigned long long)afl->nv_mab.arms[2].pos_cnt,
        afl->nv_mab.arms[0].mean_reward,
        afl->nv_mab.arms[1].mean_reward,
        afl->nv_mab.arms[2].mean_reward);
  fprintf(afl->fsrv.plot_file, ", %llu, %llu, %llu",
        (unsigned long long)afl->nv_mab.arms[0].pulls,
        (unsigned long long)afl->nv_mab.arms[1].pulls,
        (unsigned long long)afl->nv_mab.arms[2].pulls);
  fprintf(afl->fsrv.plot_file, ", %llu, %llu",
        (unsigned long long)afl->nv_http_status_ok,
        (unsigned long long)afl->nv_http_status_fail);
  fprintf(afl->fsrv.plot_file, ", %llu", (unsigned long long)afl->nv_ncov_hit);
  fprintf(afl->fsrv.plot_file, ", %llu, %llu, %llu, %llu",
        (unsigned long long)afl->nv_err_cnt,
        (unsigned long long)afl->nv_rec_cnt,
        (unsigned long long)afl->nv_rec_ms_sum,
        (unsigned long long)afl->nv_status_cnt);
  double nv_plot_err_rate =
      afl->nv_total_valid_exec
          ? (double)afl->nv_err_exec / (double)afl->nv_total_valid_exec
          : 0.0;
  double nv_plot_rec_rate =
      afl->nv_rec_total
          ? (double)afl->nv_rec_success / (double)afl->nv_rec_total
          : 0.0;
  fprintf(afl->fsrv.plot_file, ", %llu, %llu, %.6f, %.6f",
        (unsigned long long)afl->nv_valid_cnt,
        (unsigned long long)afl->nv_invalid_cnt,
        nv_plot_err_rate,
        nv_plot_rec_rate);

  fprintf(afl->fsrv.plot_file, "\n");

  fflush(afl->fsrv.plot_file);

}

/* Log deterministic stage efficiency */

void plot_profile_data(afl_state_t *afl, struct queue_entry *q) {

  if (afl->skip_deterministic) { return; }

  u64 current_ms = get_cur_time() - afl->start_time;

  u32    current_edges = count_non_255_bytes(afl, afl->virgin_bits);
  double det_finding_rate = (double)afl->havoc_prof->total_det_edge * 100.0 /
                            (double)current_edges,
         det_time_rate = (double)afl->havoc_prof->total_det_time * 100.0 /
                         (double)current_ms;

  u32 ndet_bits = 0;
  for (u32 i = 0; i < afl->fsrv.map_size; i++) {

    if (afl->skipdet_g->virgin_det_bits[i]) ndet_bits += 1;

  }

  double det_fuzzed_rate = (double)ndet_bits * 100.0 / (double)current_edges;

  fprintf(afl->fsrv.det_plot_file,
          "[%02lld:%02lld:%02lld] fuzz %d (%d), find %d/%d among %d(%02.2f) "
          "and spend %lld/%lld(%02.2f), cover %02.2f yet, %d/%d undet bits, "
          "continue %d.\n",
          current_ms / 1000 / 3600, (current_ms / 1000 / 60) % 60,
          (current_ms / 1000) % 60, afl->current_entry, q->fuzz_level,
          afl->havoc_prof->edge_det_stage, afl->havoc_prof->edge_havoc_stage,
          current_edges, det_finding_rate,
          afl->havoc_prof->det_stage_time / 1000,
          afl->havoc_prof->havoc_stage_time / 1000, det_time_rate,
          det_fuzzed_rate, q->skipdet_e->undet_bits,
          afl->skipdet_g->undet_bits_threshold, q->skipdet_e->continue_inf);

  fflush(afl->fsrv.det_plot_file);

}

/* Scroll the terminal so when the stats clear the screen
   we don't delete anything. */

void make_space_for_stats() {

  struct winsize ws;

  if (ioctl(1, TIOCGWINSZ, &ws)) { return; }

  SAYF("\x1b[%dS", ws.ws_row);

}

/* Check terminal dimensions after resize. */

static void check_term_size(afl_state_t *afl) {

  struct winsize ws;

  afl->term_too_small = 0;

  if (ioctl(1, TIOCGWINSZ, &ws)) { return; }

  if (ws.ws_row == 0 || ws.ws_col == 0) { return; }
  if (ws.ws_row < 24 || ws.ws_col < 79) { afl->term_too_small = 1; }

}

/* A spiffy retro stats screen! This is called every afl->stats_update_freq
   execve() calls, plus in several other circumstances. */

void show_stats(afl_state_t *afl) {

  if (afl->pizza_is_served) {

    show_stats_pizza(afl);

  } else {

    show_stats_normal(afl);

  }

}

void show_stats_normal(afl_state_t *afl) {

  double t_byte_ratio, stab_ratio;

  u64 cur_ms;
  u32 t_bytes, t_bits;

  static u8 banner[128];
  u32       banner_len, banner_pad;
  u8        tmp[256];
  u8        time_tmp[64];

  u8 val_buf[8][STRINGIFY_VAL_SIZE_MAX];
#define IB(i) (val_buf[(i)])

  cur_ms = get_cur_time();

  if (afl->most_time_key && afl->queue_cycle) {

    if (afl->most_time * 1000 + afl->sync_time_us / 1000 <
        cur_ms - afl->start_time) {

      afl->most_time_key = 2;
      afl->stop_soon = 2;

    }

  }

  if (afl->most_execs_key == 1 && afl->queue_cycle) {

    if (afl->most_execs <= afl->fsrv.total_execs) {

      afl->most_execs_key = 2;
      afl->stop_soon = 2;

    }

  }

  /* If not enough time has passed since last UI update, bail out. */

  if (cur_ms - afl->stats_last_ms < 1000 / UI_TARGET_HZ &&
      !afl->force_ui_update) {

    return;

  }

  /* Check if we're past the 10 minute mark. */

  if (cur_ms - afl->start_time > 10 * 60 * 1000) { afl->run_over10m = 1; }

  /* Calculate smoothed exec speed stats. */

  if (unlikely(!afl->stats_last_execs)) {

    if (likely(cur_ms != afl->start_time)) {

      afl->stats_avg_exec = ((double)afl->fsrv.total_execs) * 1000 /
                            (afl->prev_run_time + cur_ms - afl->start_time);

    }

  } else {

    if (likely(cur_ms != afl->stats_last_ms)) {

      double cur_avg =
          ((double)(afl->fsrv.total_execs - afl->stats_last_execs)) * 1000 /
          (cur_ms - afl->stats_last_ms);

      /* If there is a dramatic (5x+) jump in speed, reset the indicator
         more quickly. */

      if (cur_avg * 5 < afl->stats_avg_exec ||
          cur_avg / 5 > afl->stats_avg_exec) {

        afl->stats_avg_exec = cur_avg;

      }

      afl->stats_avg_exec = afl->stats_avg_exec * (1.0 - 1.0 / AVG_SMOOTHING) +
                            cur_avg * (1.0 / AVG_SMOOTHING);

    }

  }

  afl->stats_last_ms = cur_ms;
  afl->stats_last_execs = afl->fsrv.total_execs;

  /* Tell the callers when to contact us (as measured in execs). */

  afl->stats_update_freq = afl->stats_avg_exec / (UI_TARGET_HZ * 10);
  if (!afl->stats_update_freq) { afl->stats_update_freq = 1; }

  /* Do some bitmap stats. */

  t_bytes = count_non_255_bytes(afl, afl->virgin_bits);
  t_byte_ratio = ((double)t_bytes * 100) / afl->fsrv.real_map_size;

  if (unlikely(t_bytes > afl->fsrv.real_map_size)) {

    if (unlikely(!afl->afl_env.afl_ignore_problems)) {

      FATAL(
          "Incorrect fuzzing setup detected. Your target seems to have loaded "
          "incorrectly instrumented shared libraries (%u of %u/%u). If you use "
          "LTO mode "
          "please see instrumentation/README.lto.md. To ignore this problem "
          "and continue fuzzing just set 'AFL_IGNORE_PROBLEMS=1'.\n",
          t_bytes, afl->fsrv.real_map_size, afl->fsrv.map_size);

    }

  }

  if (likely(t_bytes) && unlikely(afl->var_byte_count)) {

    stab_ratio = 100 - (((double)afl->var_byte_count * 100) / t_bytes);

  } else {

    stab_ratio = 100;

  }

  /* Roughly every minute, update fuzzer stats and save auto tokens. */

  if (unlikely(
          !afl->non_instrumented_mode &&
          (afl->force_ui_update || cur_ms - afl->stats_last_stats_ms >
                                       afl->stats_file_update_freq_msecs))) {

    afl->stats_last_stats_ms = cur_ms;
    write_stats_file(afl, t_bytes, t_byte_ratio, stab_ratio,
                     afl->stats_avg_exec);
    save_auto(afl);
    write_bitmap(afl);

  }

  if (unlikely(afl->afl_env.afl_statsd)) {

    if (unlikely(afl->force_ui_update || cur_ms - afl->statsd_last_send_ms >
                                             STATSD_UPDATE_SEC * 1000)) {

      /* reset counter, even if send failed. */
      afl->statsd_last_send_ms = cur_ms;
      if (statsd_send_metric(afl)) { WARNF("could not send statsd metric."); }

    }

  }

  /* Every now and then, write plot data. */

  if (unlikely(afl->force_ui_update ||
               cur_ms - afl->stats_last_plot_ms > PLOT_UPDATE_SEC * 1000)) {

    afl->stats_last_plot_ms = cur_ms;
    maybe_update_plot_file(afl, t_bytes, t_byte_ratio, afl->stats_avg_exec);

  }

  /* Every now and then, write queue data. */

  if (unlikely(afl->force_ui_update ||
               cur_ms - afl->stats_last_queue_ms > QUEUE_UPDATE_SEC * 1000)) {

    afl->stats_last_queue_ms = cur_ms;
#ifdef INTROSPECTION
    write_queue_stats(afl);
#endif

  }

  /* AFL_EXIT_ON_TIME. */

  /* If no coverage was found yet, check whether run time is greater than
   * exit_on_time. */

  if (unlikely(!afl->non_instrumented_mode && afl->afl_env.afl_exit_on_time &&
               ((afl->last_find_time &&
                 (cur_ms - afl->last_find_time) > afl->exit_on_time) ||
                (!afl->last_find_time &&
                 (cur_ms - afl->start_time) > afl->exit_on_time)))) {

    afl->stop_soon = 2;

  }

  if (unlikely(afl->total_crashes && afl->afl_env.afl_bench_until_crash)) {

    afl->stop_soon = 2;

  }

  /* If we're not on TTY, bail out. */

  if (afl->not_on_tty) { return; }

  /* If we haven't started doing things, bail out. */

  if (unlikely(!afl->queue_cur)) { return; }

  /* Now, for the visuals... */

  if (afl->clear_screen) {

    SAYF(TERM_CLEAR CURSOR_HIDE);
    afl->clear_screen = 0;

    check_term_size(afl);

  }

  SAYF(TERM_HOME);

  if (unlikely(afl->term_too_small)) {

    SAYF(cBRI
         "Your terminal is too small to display the UI.\n"
         "Please resize terminal window to at least 79x24.\n" cRST);

    return;

  }

  /* Compute some mildly useful bitmap stats. */

  t_bits = (afl->fsrv.map_size << 3) - count_bits(afl, afl->virgin_bits);

  /* Let's start by drawing a centered banner. */
  if (unlikely(!banner[0])) {

    char *si = "";
    char *fuzzer_name;

    if (afl->sync_id) { si = afl->sync_id; }
    memset(banner, 0, sizeof(banner));

    banner_len = strlen(VERSION) + strlen(si) + strlen(afl->power_name) + 4 + 6;

    if (afl->crash_mode) {

      fuzzer_name = "peruvian were-rabbit";

    } else {

      fuzzer_name = "american fuzzy lop";
      if (banner_len + strlen(fuzzer_name) + strlen(afl->use_banner) > 75) {

        fuzzer_name = "AFL";

      }

    }

    banner_len += strlen(fuzzer_name);

    if (strlen(afl->use_banner) + banner_len > 75) {

      afl->use_banner += (strlen(afl->use_banner) + banner_len) - 76;
      memset(afl->use_banner, '.', 3);

    }

    banner_len += strlen(afl->use_banner);
    banner_pad = (79 - banner_len) / 2;
    memset(banner, ' ', banner_pad);

#ifdef __linux__
    if (afl->fsrv.nyx_mode) {

      snprintf(banner + banner_pad, sizeof(banner) - banner_pad,
               "%s%s " cLCY VERSION cLBL " {%s} " cLGN "(%s) " cPIN
               "[%s] - Nyx",
               afl->crash_mode ? cPIN : cYEL, fuzzer_name, si, afl->use_banner,
               afl->power_name);

    } else {

#endif
      snprintf(banner + banner_pad, sizeof(banner) - banner_pad,
               "%s%s " cLCY VERSION cLBL " {%s} " cLGN "(%s) " cPIN "[%s]",
               afl->crash_mode ? cPIN : cYEL, fuzzer_name, si, afl->use_banner,
               afl->power_name);

#ifdef __linux__

    }

#endif

    if (banner_pad)
      for (u32 i = 0; i < banner_pad; ++i)
        strcat(banner, " ");

  }

  SAYF("\n%s\n", banner);

  /* "Handy" shortcuts for drawing boxes... */

#define bSTG bSTART cGRA
#define bH2 bH bH
#define bH5 bH2 bH2 bH
#define bH10 bH5 bH5
#define bH20 bH10 bH10
#define bH30 bH20 bH10
#define SP5 "     "
#define SP10 SP5 SP5
#define SP20 SP10 SP10

  /* Since `total_crashes` does not get reloaded from disk on restart,
    it indicates if we found crashes this round already -> paint red.
    If it's 0, but `saved_crashes` is set from a past run, paint in yellow. */
  char *crash_color = afl->total_crashes   ? cLRD
                      : afl->saved_crashes ? cYEL
                                           : cRST;

  /* Lord, forgive me this. */

  SAYF(SET_G1 bSTG bLT bH                         bSTOP cCYA
       " process timing " bSTG bH30 bH5 bH bHB bH bSTOP cCYA
       " overall results " bSTG bH2               bH2 bRT "\n");

  if (afl->non_instrumented_mode) {

    strcpy(tmp, cRST);

  } else {

    u64 min_wo_finds = (cur_ms - afl->last_find_time) / 1000 / 60;

    /* First queue cycle: don't stop now! */
    if (afl->queue_cycle == 1 || min_wo_finds < 15) {

      strcpy(tmp, cMGN);

    } else

      /* Subsequent cycles, but we're still making finds. */
      if (afl->cycles_wo_finds < 2 || min_wo_finds <= 30) {

        strcpy(tmp, cYEL);

      } else

        /* No finds for a long time and no test cases to try. */
        if (afl->cycles_wo_finds > 1 && !afl->pending_not_fuzzed &&
            min_wo_finds > 120) {

          strcpy(tmp, cLGN);

          /* Default: cautiously OK to stop? */

        } else {

          strcpy(tmp, cLBL);

        }

  }

  u_stringify_time_diff(time_tmp, afl->prev_run_time + cur_ms, afl->start_time);
  SAYF(bV bSTOP "        run time : " cRST "%-33s " bSTG bV bSTOP
                "  cycles done : %s%-5s " bSTG bV "\n",
       time_tmp, tmp, u_stringify_int(IB(0), afl->queue_cycle - 1));

  /* We want to warn people about not seeing new paths after a full cycle,
     except when resuming fuzzing or running in non-instrumented mode. */

  if (!afl->non_instrumented_mode &&
      (afl->last_find_time || afl->resuming_fuzz || afl->queue_cycle == 1 ||
       afl->in_bitmap || afl->crash_mode)) {

    u_stringify_time_diff(time_tmp, cur_ms, afl->last_find_time);
    SAYF(bV bSTOP "   last new find : " cRST "%-33s ", time_tmp);

  } else {

    if (afl->non_instrumented_mode) {

      SAYF(bV bSTOP "   last new find : " cPIN "n/a" cRST
                    " (non-instrumented mode)       ");

    } else {

      SAYF(bV bSTOP "   last new find : " cRST "none yet " cLRD
                    "(odd, check syntax!)     ");

    }

  }

  SAYF(bSTG bV bSTOP " corpus count : " cRST "%-5s " bSTG bV "\n",
       u_stringify_int(IB(0), afl->queued_items));

  /* Highlight crashes in red if found, denote going over the KEEP_UNIQUE_CRASH
     limit with a '+' appended to the count. */

  sprintf(tmp, "%s%s", u_stringify_int(IB(0), afl->saved_crashes),
          (afl->saved_crashes >= KEEP_UNIQUE_CRASH) ? "+" : "");

  u_stringify_time_diff(time_tmp, cur_ms, afl->last_crash_time);
  SAYF(bV bSTOP "last saved crash : " cRST "%-33s " bSTG bV bSTOP
                "saved crashes : %s%-6s" bSTG bV "\n",
       time_tmp, crash_color, tmp);

  sprintf(tmp, "%s%s", u_stringify_int(IB(0), afl->saved_hangs),
          (afl->saved_hangs >= KEEP_UNIQUE_HANG) ? "+" : "");

  u_stringify_time_diff(time_tmp, cur_ms, afl->last_hang_time);
  SAYF(bV bSTOP " last saved hang : " cRST "%-33s " bSTG bV bSTOP
                "  saved hangs : " cRST "%-6s" bSTG bV "\n",
       time_tmp, tmp);

  SAYF(bVR bH                                              bSTOP cCYA
       " cycle progress " bSTG bH10 bH5 bH2 bH2 bH2 bHB bH bSTOP cCYA
       " map coverage" bSTG bHT bH20                       bH2 bVL "\n");

  /* This gets funny because we want to print several variable-length variables
     together, but then cram them into a fixed-width field - so we need to
     put them in a temporary buffer first. */

  sprintf(tmp, "%s%s%u (%0.01f%%)", u_stringify_int(IB(0), afl->current_entry),
          afl->queue_cur->favored ? "." : "*", afl->queue_cur->fuzz_level,
          ((double)afl->current_entry * 100) / afl->queued_items);

  SAYF(bV bSTOP "  now processing : " cRST "%-18s " bSTG bV bSTOP, tmp);

  sprintf(tmp, "%0.02f%% / %0.02f%%",
          ((double)afl->queue_cur->bitmap_size) * 100 / afl->fsrv.real_map_size,
          t_byte_ratio);

  SAYF("    map density : %s%-19s" bSTG bV "\n",
       t_byte_ratio > 70
           ? cLRD
           : ((t_bytes < 200 && !afl->non_instrumented_mode) ? cPIN : cRST),
       tmp);

  sprintf(tmp, "%s (%0.02f%%)", u_stringify_int(IB(0), afl->cur_skipped_items),
          ((double)afl->cur_skipped_items * 100) / afl->queued_items);

  SAYF(bV bSTOP "  runs timed out : " cRST "%-18s " bSTG bV, tmp);

  sprintf(tmp, "%0.02f bits/tuple", t_bytes ? (((double)t_bits) / t_bytes) : 0);

  SAYF(bSTOP " count coverage : " cRST "%-19s" bSTG bV "\n", tmp);

  SAYF(bVR bH                                             bSTOP cCYA
       " stage progress " bSTG bH10 bH5 bH2 bH2 bH2 bX bH bSTOP cCYA
       " findings in depth " bSTG bH10 bH5                bH2 bVL "\n");

  sprintf(tmp, "%s (%0.02f%%)", u_stringify_int(IB(0), afl->queued_favored),
          ((double)afl->queued_favored) * 100 / afl->queued_items);

  /* Yeah... it's still going on... halp? */

  SAYF(bV bSTOP "  now trying : " cRST "%-22s " bSTG bV bSTOP
                " favored items : " cRST "%-20s" bSTG bV "\n",
       afl->stage_name, tmp);

  if (!afl->stage_max) {

    sprintf(tmp, "%s/-", u_stringify_int(IB(0), afl->stage_cur));

  } else {

    sprintf(tmp, "%s/%s (%0.02f%%)", u_stringify_int(IB(0), afl->stage_cur),
            u_stringify_int(IB(1), afl->stage_max),
            ((double)afl->stage_cur) * 100 / afl->stage_max);

  }

  SAYF(bV bSTOP " stage execs : " cRST "%-23s" bSTG bV bSTOP, tmp);

  sprintf(tmp, "%s (%0.02f%%)", u_stringify_int(IB(0), afl->queued_with_cov),
          ((double)afl->queued_with_cov) * 100 / afl->queued_items);

  SAYF("  new edges on : " cRST "%-20s" bSTG bV "\n", tmp);

  sprintf(tmp, "%s (%s%s saved)", u_stringify_int(IB(0), afl->total_crashes),
          u_stringify_int(IB(1), afl->saved_crashes),
          (afl->saved_crashes >= KEEP_UNIQUE_CRASH) ? "+" : "");

  if (afl->crash_mode) {

    SAYF(bV bSTOP " total execs : " cRST "%-22s " bSTG bV bSTOP
                  "   new crashes : %s%-20s" bSTG bV "\n",
         u_stringify_int(IB(0), afl->fsrv.total_execs), crash_color, tmp);

  } else {

    SAYF(bV bSTOP " total execs : " cRST "%-22s " bSTG bV bSTOP
                  " total crashes : %s%-20s" bSTG bV "\n",
         u_stringify_int(IB(0), afl->fsrv.total_execs), crash_color, tmp);

  }

  /* Show a warning about slow execution. */

  if (afl->stats_avg_exec < 100) {

    sprintf(tmp, "%s/sec (%s)", u_stringify_float(IB(0), afl->stats_avg_exec),
            afl->stats_avg_exec < 20 ? "zzzz..." : "slow!");

    SAYF(bV bSTOP "  exec speed : " cLRD "%-22s ", tmp);

  } else {

    sprintf(tmp, "%s/sec", u_stringify_float(IB(0), afl->stats_avg_exec));
    SAYF(bV bSTOP "  exec speed : " cRST "%-22s ", tmp);

  }

  sprintf(tmp, "%s (%s%s saved)", u_stringify_int(IB(0), afl->total_tmouts),
          u_stringify_int(IB(1), afl->saved_tmouts),
          (afl->saved_tmouts >= KEEP_UNIQUE_HANG) ? "+" : "");

  SAYF(bSTG bV bSTOP "  total tmouts : " cRST "%-20s" bSTG bV "\n", tmp);

  /* Aaaalmost there... hold on! */

  SAYF(bVR bH cCYA bSTOP " fuzzing strategy yields " bSTG bH10 bH2 bHT bH10 bH2
           bH bHB bH bSTOP cCYA " item geometry " bSTG bH5 bH2 bVL "\n");

  if (unlikely(afl->custom_only)) {

    strcpy(tmp, "disabled (custom-mutator-only mode)");

  } else if (likely(afl->skip_deterministic)) {

    strcpy(tmp, "disabled (-z switch used)");

  } else {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_FLIP1]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_FLIP1]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_FLIP2]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_FLIP2]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_FLIP4]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_FLIP4]));

  }

  SAYF(bV bSTOP "   bit flips : " cRST "%-36s " bSTG bV bSTOP
                "    levels : " cRST "%-10s" bSTG bV "\n",
       tmp, u_stringify_int(IB(0), afl->max_depth));

  if (unlikely(!afl->skip_deterministic)) {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_FLIP8]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_FLIP8]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_FLIP16]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_FLIP16]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_FLIP32]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_FLIP32]));

  }

  SAYF(bV bSTOP "  byte flips : " cRST "%-36s " bSTG bV bSTOP
                "   pending : " cRST "%-10s" bSTG bV "\n",
       tmp, u_stringify_int(IB(0), afl->pending_not_fuzzed));

  if (unlikely(!afl->skip_deterministic)) {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_ARITH8]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_ARITH8]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_ARITH16]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_ARITH16]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_ARITH32]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_ARITH32]));

  }

  SAYF(bV bSTOP " arithmetics : " cRST "%-36s " bSTG bV bSTOP
                "  pend fav : " cRST "%-10s" bSTG bV "\n",
       tmp, u_stringify_int(IB(0), afl->pending_favored));

  if (unlikely(!afl->skip_deterministic)) {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_INTEREST8]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_INTEREST8]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_INTEREST16]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_INTEREST16]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_INTEREST32]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_INTEREST32]));

  }

  SAYF(bV bSTOP "  known ints : " cRST "%-36s " bSTG bV bSTOP
                " own finds : " cRST "%-10s" bSTG bV "\n",
       tmp, u_stringify_int(IB(0), afl->queued_discovered));

  if (unlikely(!afl->skip_deterministic)) {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_EXTRAS_UO]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_EXTRAS_UO]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_EXTRAS_UI]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_EXTRAS_UI]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_EXTRAS_AO]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_EXTRAS_AO]),
            u_stringify_int(IB(6), afl->stage_finds[STAGE_EXTRAS_AI]),
            u_stringify_int(IB(7), afl->stage_cycles[STAGE_EXTRAS_AI]));

  } else if (unlikely(!afl->extras_cnt || afl->custom_only)) {

    strcpy(tmp, "n/a");

  } else {

    strcpy(tmp, "havoc mode");

  }

  SAYF(bV bSTOP "  dictionary : " cRST "%-36s " bSTG bV bSTOP
                "  imported : " cRST "%-10s" bSTG bV "\n",
       tmp,
       afl->sync_id ? u_stringify_int(IB(0), afl->queued_imported)
                    : (u8 *)"n/a");

  sprintf(tmp, "%s/%s, %s/%s",
          u_stringify_int(IB(0), afl->stage_finds[STAGE_HAVOC]),
          u_stringify_int(IB(2), afl->stage_cycles[STAGE_HAVOC]),
          u_stringify_int(IB(3), afl->stage_finds[STAGE_SPLICE]),
          u_stringify_int(IB(4), afl->stage_cycles[STAGE_SPLICE]));

  SAYF(bV bSTOP "havoc/splice : " cRST "%-36s " bSTG bV bSTOP, tmp);

  if (t_bytes) {

    sprintf(tmp, "%0.02f%%", stab_ratio);

  } else {

    strcpy(tmp, "n/a");

  }

  SAYF(" stability : %s%-10s" bSTG bV "\n",
       (stab_ratio < 85 && afl->var_byte_count > 40)
           ? cLRD
           : ((afl->queued_variable &&
               (!afl->persistent_mode || afl->var_byte_count > 20))
                  ? cMGN
                  : cRST),
       tmp);

  if (unlikely(afl->afl_env.afl_python_module)) {

    sprintf(tmp, "%s/%s,",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_PYTHON]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_PYTHON]));

  } else {

    strcpy(tmp, "unused,");

  }

  if (unlikely(afl->afl_env.afl_custom_mutator_library)) {

    strcat(tmp, " ");
    strcat(tmp, u_stringify_int(IB(2), afl->stage_finds[STAGE_CUSTOM_MUTATOR]));
    strcat(tmp, "/");
    strcat(tmp,
           u_stringify_int(IB(3), afl->stage_cycles[STAGE_CUSTOM_MUTATOR]));
    strcat(tmp, ",");

  } else {

    strcat(tmp, " unused,");

  }

  if (unlikely(afl->shm.cmplog_mode)) {

    strcat(tmp, " ");
    strcat(tmp, u_stringify_int(IB(4), afl->stage_finds[STAGE_COLORIZATION]));
    strcat(tmp, "/");
    strcat(tmp, u_stringify_int(IB(5), afl->stage_cycles[STAGE_COLORIZATION]));
    strcat(tmp, ", ");
    strcat(tmp, u_stringify_int(IB(6), afl->stage_finds[STAGE_ITS]));
    strcat(tmp, "/");
    strcat(tmp, u_stringify_int(IB(7), afl->stage_cycles[STAGE_ITS]));

  } else {

    strcat(tmp, " unused, unused");

  }

  SAYF(bV bSTOP "py/custom/rq : " cRST "%-36s " bSTG bVR bH20 bH2 bH bRB "\n",
       tmp);

  if (likely(afl->disable_trim)) {

    sprintf(tmp, "disabled, ");

  } else if (unlikely(!afl->bytes_trim_out ||

                      afl->bytes_trim_in <= afl->bytes_trim_out)) {

    sprintf(tmp, "n/a, ");

  } else {

    sprintf(tmp, "%0.02f%%/%s, ",
            ((double)(afl->bytes_trim_in - afl->bytes_trim_out)) * 100 /
                afl->bytes_trim_in,
            u_stringify_int(IB(0), afl->trim_execs));

  }

  if (likely(afl->skip_deterministic)) {

    strcat(tmp, "disabled");

  } else if (unlikely(!afl->blocks_eff_total ||

                      afl->blocks_eff_select >= afl->blocks_eff_total)) {

    strcat(tmp, "n/a");

  } else {

    u8 tmp2[128];

    sprintf(tmp2, "%0.02f%%",
            ((double)(afl->blocks_eff_total - afl->blocks_eff_select)) * 100 /
                afl->blocks_eff_total);

    strcat(tmp, tmp2);

  }

  // if (afl->custom_mutators_count) {

  //
  //  sprintf(tmp, "%s/%s",
  //          u_stringify_int(IB(0), afl->stage_finds[STAGE_CUSTOM_MUTATOR]),
  //          u_stringify_int(IB(1), afl->stage_cycles[STAGE_CUSTOM_MUTATOR]));
  //  SAYF(bV bSTOP " custom mut. : " cRST "%-36s " bSTG bV RESET_G1, tmp);
  //
  //} else {

  SAYF(bV bSTOP "    trim/eff : " cRST "%-36s " bSTG bV RESET_G1, tmp);

  //}

  /* Provide some CPU utilization stats. */

  if (afl->cpu_core_count) {

    char *spacing = SP10, snap[24] = " " cLGN "snapshot" cRST " ";

    double cur_runnable = get_runnable_processes();
    u32    cur_utilization = cur_runnable * 100 / afl->cpu_core_count;

    u8 *cpu_color = cCYA;

    /* If we could still run one or more processes, use green. */

    if (afl->cpu_core_count > 1 && cur_runnable + 1 <= afl->cpu_core_count) {

      cpu_color = cLGN;

    }

    /* If we're clearly oversubscribed, use red. */

    if (!afl->no_cpu_meter_red && cur_utilization >= 150) { cpu_color = cLRD; }

    if (afl->fsrv.snapshot) { spacing = snap; }

#ifdef HAVE_AFFINITY

    if (afl->cpu_aff >= 0) {

      SAYF("%s" cGRA "[cpu%03u:%s%3u%%" cGRA "]\r" cRST, spacing,
           MIN(afl->cpu_aff, 999), cpu_color, MIN(cur_utilization, (u32)999));

    } else {

      SAYF("%s" cGRA "   [cpu:%s%3u%%" cGRA "]\r" cRST, spacing, cpu_color,
           MIN(cur_utilization, (u32)999));

    }

#else

    SAYF("%s" cGRA "   [cpu:%s%3u%%" cGRA "]\r" cRST, spacing, cpu_color,
         MIN(cur_utilization, (u32)999));

#endif                                                    /* ^HAVE_AFFINITY */

  } else {

    SAYF("\r");

  }

  /* Last line */

  SAYF(SET_G1 "\n" bSTG bLB bH               cCYA bSTOP " strategy:" cPIN
              " %s " bSTG bH10               cCYA bSTOP " state:" cPIN
              " %s " bSTG bH2 bRB bSTOP cRST RESET_G1,
       afl->fuzz_mode == 0 ? "explore" : "exploit", get_fuzzing_state(afl));

#undef IB

  /* Hallelujah! */

  fflush(0);

}

void show_stats_pizza(afl_state_t *afl) {

  double t_byte_ratio, stab_ratio;

  u64 cur_ms;
  u32 t_bytes, t_bits;

  static u8 banner[128];
  u32       banner_len, banner_pad;
  u8        tmp[256];
  u8        time_tmp[64];

  u8 val_buf[8][STRINGIFY_VAL_SIZE_MAX];
#define IB(i) (val_buf[(i)])

  cur_ms = get_cur_time();

  if (afl->most_time_key && afl->queue_cycle) {

    if (afl->most_time * 1000 + afl->sync_time_us / 1000 <
        cur_ms - afl->start_time) {

      afl->most_time_key = 2;
      afl->stop_soon = 2;

    }

  }

  if (afl->most_execs_key == 1 && afl->queue_cycle) {

    if (afl->most_execs <= afl->fsrv.total_execs) {

      afl->most_execs_key = 2;
      afl->stop_soon = 2;

    }

  }

  /* If not enough time has passed since last UI update, bail out. */

  if (cur_ms - afl->stats_last_ms < 1000 / UI_TARGET_HZ &&
      !afl->force_ui_update) {

    return;

  }

  /* Check if we're past the 10 minute mark. */

  if (cur_ms - afl->start_time > 10 * 60 * 1000) { afl->run_over10m = 1; }

  /* Calculate smoothed exec speed stats. */

  if (unlikely(!afl->stats_last_execs)) {

    if (likely(cur_ms != afl->start_time)) {

      afl->stats_avg_exec = ((double)afl->fsrv.total_execs) * 1000 /
                            (afl->prev_run_time + cur_ms - afl->start_time);

    }

  } else {

    if (likely(cur_ms != afl->stats_last_ms)) {

      double cur_avg =
          ((double)(afl->fsrv.total_execs - afl->stats_last_execs)) * 1000 /
          (cur_ms - afl->stats_last_ms);

      /* If there is a dramatic (5x+) jump in speed, reset the indicator
         more quickly. */

      if (cur_avg * 5 < afl->stats_avg_exec ||
          cur_avg / 5 > afl->stats_avg_exec) {

        afl->stats_avg_exec = cur_avg;

      }

      afl->stats_avg_exec = afl->stats_avg_exec * (1.0 - 1.0 / AVG_SMOOTHING) +
                            cur_avg * (1.0 / AVG_SMOOTHING);

    }

  }

  afl->stats_last_ms = cur_ms;
  afl->stats_last_execs = afl->fsrv.total_execs;

  /* Tell the callers when to contact us (as measured in execs). */

  afl->stats_update_freq = afl->stats_avg_exec / (UI_TARGET_HZ * 10);
  if (!afl->stats_update_freq) { afl->stats_update_freq = 1; }

  /* Do some bitmap stats. */

  t_bytes = count_non_255_bytes(afl, afl->virgin_bits);
  t_byte_ratio = ((double)t_bytes * 100) / afl->fsrv.real_map_size;

  if (unlikely(t_bytes > afl->fsrv.real_map_size)) {

    if (unlikely(!afl->afl_env.afl_ignore_problems)) {

      FATAL(
          "This is what happens when you speak italian to the rabbit "
          "Don't speak italian to the rabbit");

    }

  }

  if (likely(t_bytes) && unlikely(afl->var_byte_count)) {

    stab_ratio = 100 - (((double)afl->var_byte_count * 100) / t_bytes);

  } else {

    stab_ratio = 100;

  }

  /* Roughly every minute, update fuzzer stats and save auto tokens. */

  if (unlikely(!afl->non_instrumented_mode &&
               (afl->force_ui_update ||
                cur_ms - afl->stats_last_stats_ms > STATS_UPDATE_SEC * 1000))) {

    afl->stats_last_stats_ms = cur_ms;
    write_stats_file(afl, t_bytes, t_byte_ratio, stab_ratio,
                     afl->stats_avg_exec);
    save_auto(afl);
    write_bitmap(afl);

  }

  if (unlikely(afl->afl_env.afl_statsd)) {

    if (unlikely(afl->force_ui_update || cur_ms - afl->statsd_last_send_ms >
                                             STATSD_UPDATE_SEC * 1000)) {

      /* reset counter, even if send failed. */
      afl->statsd_last_send_ms = cur_ms;
      if (statsd_send_metric(afl)) {

        WARNF("Could not order tomato sauce from statsd.");

      }

    }

  }

  /* Every now and then, write plot data. */

  if (unlikely(afl->force_ui_update ||
               cur_ms - afl->stats_last_plot_ms > PLOT_UPDATE_SEC * 1000)) {

    afl->stats_last_plot_ms = cur_ms;
    maybe_update_plot_file(afl, t_bytes, t_byte_ratio, afl->stats_avg_exec);

  }

  /* Every now and then, write queue data. */

  if (unlikely(afl->force_ui_update ||
               cur_ms - afl->stats_last_queue_ms > QUEUE_UPDATE_SEC * 1000)) {

    afl->stats_last_queue_ms = cur_ms;
#ifdef INTROSPECTION
    write_queue_stats(afl);
#endif

  }

  /* AFL_EXIT_ON_TIME. */

  /* If no coverage was found yet, check whether run time is greater than
   * exit_on_time. */

  if (unlikely(!afl->non_instrumented_mode && afl->afl_env.afl_exit_on_time &&
               ((afl->last_find_time &&
                 (cur_ms - afl->last_find_time) > afl->exit_on_time) ||
                (!afl->last_find_time &&
                 (cur_ms - afl->start_time) > afl->exit_on_time)))) {

    afl->stop_soon = 2;

  }

  if (unlikely(afl->total_crashes && afl->afl_env.afl_bench_until_crash)) {

    afl->stop_soon = 2;

  }

  /* If we're not on TTY, bail out. */

  if (afl->not_on_tty) { return; }

  /* If we haven't started doing things, bail out. */

  if (unlikely(!afl->queue_cur)) { return; }

  /* Now, for the visuals... */

  if (afl->clear_screen) {

    SAYF(TERM_CLEAR CURSOR_HIDE);
    afl->clear_screen = 0;

    check_term_size(afl);

  }

  SAYF(TERM_HOME);

  if (unlikely(afl->term_too_small)) {

    SAYF(cBRI
         "Our pizzeria can't host this many guests.\n"
         "Please call Pizzeria Caravaggio. They have tables of at least "
         "79x24.\n" cRST);

    return;

  }

  /* Compute some mildly useful bitmap stats. */

  t_bits = (afl->fsrv.map_size << 3) - count_bits(afl, afl->virgin_bits);

  /* Let's start by drawing a centered banner. */
  if (unlikely(!banner[0])) {

    char *si = "";
    if (afl->sync_id) { si = afl->sync_id; }
    memset(banner, 0, sizeof(banner));
    banner_len = (afl->crash_mode ? 20 : 18) + strlen(VERSION) + strlen(si) +
                 strlen(afl->power_name) + 4 + 6;

    if (strlen(afl->use_banner) + banner_len > 75) {

      afl->use_banner += (strlen(afl->use_banner) + banner_len) - 76;
      memset(afl->use_banner, '.', 3);

    }

    banner_len += strlen(afl->use_banner);
    banner_pad = (79 - banner_len) / 2;
    memset(banner, ' ', banner_pad);

#ifdef __linux__
    if (afl->fsrv.nyx_mode) {

      snprintf(banner + banner_pad, sizeof(banner) - banner_pad,
               "%s " cLCY VERSION cLBL " {%s} " cLGN "(%s) " cPIN "[%s] - Nyx",
               afl->crash_mode ? cPIN
                   "Mozzarbella Pizzeria table booking system"
                               : cYEL "Mozzarbella Pizzeria management system",
               si, afl->use_banner, afl->power_name);

    } else {

#endif
      snprintf(banner + banner_pad, sizeof(banner) - banner_pad,
               "%s " cLCY VERSION cLBL " {%s} " cLGN "(%s) " cPIN "[%s]",
               afl->crash_mode ? cPIN
                   "Mozzarbella Pizzeria table booking system"
                               : cYEL "Mozzarbella Pizzeria management system",
               si, afl->use_banner, afl->power_name);

#ifdef __linux__

    }

#endif

  }

  SAYF("\n%s\n", banner);

  /* "Handy" shortcuts for drawing boxes... */

#define bSTG bSTART cGRA
#define bH2 bH bH
#define bH5 bH2 bH2 bH
#define bH10 bH5 bH5
#define bH20 bH10 bH10
#define bH30 bH20 bH10
#define SP5 "     "
#define SP10 SP5 SP5
#define SP20 SP10 SP10

  /* Since `total_crashes` does not get reloaded from disk on restart,
    it indicates if we found crashes this round already -> paint red.
    If it's 0, but `saved_crashes` is set from a past run, paint in yellow. */
  char *crash_color = afl->total_crashes   ? cLRD
                      : afl->saved_crashes ? cYEL
                                           : cRST;

  /* Lord, forgive me this. */

  SAYF(SET_G1 bSTG bLT bH bSTOP cCYA
       " Mozzarbella has been proudly serving pizzas since " bSTG bH20 bH bH bH
           bHB bH bSTOP cCYA " In this time, we served " bSTG bH30 bRT "\n");

  if (afl->non_instrumented_mode) {

    strcpy(tmp, cRST);

  } else {

    u64 min_wo_finds = (cur_ms - afl->last_find_time) / 1000 / 60;

    /* First queue cycle: don't stop now! */
    if (afl->queue_cycle == 1 || min_wo_finds < 15) {

      strcpy(tmp, cMGN);

    } else

      /* Subsequent cycles, but we're still making finds. */
      if (afl->cycles_wo_finds < 2 || min_wo_finds <= 30) {

        strcpy(tmp, cYEL);

      } else

        /* No finds for a long time and no test cases to try. */
        if (afl->cycles_wo_finds > 1 && !afl->pending_not_fuzzed &&
            min_wo_finds > 120) {

          strcpy(tmp, cLGN);

          /* Default: cautiously OK to stop? */

        } else {

          strcpy(tmp, cLBL);

        }

  }

  u_stringify_time_diff(time_tmp, afl->prev_run_time + cur_ms, afl->start_time);
  SAYF(bV bSTOP
       "                         open time : " cRST "%-37s " bSTG bV bSTOP
       "                     seasons done : %s%-5s               " bSTG bV "\n",
       time_tmp, tmp, u_stringify_int(IB(0), afl->queue_cycle - 1));

  /* We want to warn people about not seeing new paths after a full cycle,
     except when resuming fuzzing or running in non-instrumented mode. */

  if (!afl->non_instrumented_mode &&
      (afl->last_find_time || afl->resuming_fuzz || afl->queue_cycle == 1 ||
       afl->in_bitmap || afl->crash_mode)) {

    u_stringify_time_diff(time_tmp, cur_ms, afl->last_find_time);
    SAYF(bV bSTOP "                  last pizza baked : " cRST "%-37s ",
         time_tmp);

  } else {

    if (afl->non_instrumented_mode) {

      SAYF(bV bSTOP "                  last pizza baked : " cPIN "n/a" cRST
                    " (non-instrumented mode)           ");

    } else {

      SAYF(bV bSTOP "                  last pizza baked : " cRST
                    "none yet " cLRD
                    "(odd, check Gennarino, he might be slacking!)     ");

    }

  }

  SAYF(bSTG bV bSTOP "               pizzas on the menu : " cRST
                     "%-5s               " bSTG bV "\n",
       u_stringify_int(IB(0), afl->queued_items));

  /* Highlight crashes in red if found, denote going over the KEEP_UNIQUE_CRASH
     limit with a '+' appended to the count. */

  sprintf(tmp, "%s%s", u_stringify_int(IB(0), afl->saved_crashes),
          (afl->saved_crashes >= KEEP_UNIQUE_CRASH) ? "+" : "");

  u_stringify_time_diff(time_tmp, cur_ms, afl->last_crash_time);
  SAYF(bV bSTOP
       "                last ordered pizza : " cRST "%-33s     " bSTG bV bSTOP
       "                         at table : %s%-6s              " bSTG bV "\n",
       time_tmp, crash_color, tmp);

  sprintf(tmp, "%s%s", u_stringify_int(IB(0), afl->saved_hangs),
          (afl->saved_hangs >= KEEP_UNIQUE_HANG) ? "+" : "");

  u_stringify_time_diff(time_tmp, cur_ms, afl->last_hang_time);
  SAYF(bV bSTOP
       "  last conversation with customers : " cRST "%-33s     " bSTG bV bSTOP
       "                 number of Peroni : " cRST "%-6s              " bSTG bV
       "\n",
       time_tmp, tmp);

  SAYF(bVR bH                                           bSTOP cCYA
       " Baking progress  " bSTG bH30 bH20 bH5 bH bX bH bSTOP cCYA
       " Pizzeria busyness" bSTG bH30 bH5 bH            bH bVL "\n");

  /* This gets funny because we want to print several variable-length variables
     together, but then cram them into a fixed-width field - so we need to
     put them in a temporary buffer first. */

  sprintf(tmp, "%s%s%u (%0.01f%%)", u_stringify_int(IB(0), afl->current_entry),
          afl->queue_cur->favored ? "." : "*", afl->queue_cur->fuzz_level,
          ((double)afl->current_entry * 100) / afl->queued_items);

  SAYF(bV bSTOP "                        now baking : " cRST
                "%-18s                    " bSTG bV bSTOP,
       tmp);

  sprintf(tmp, "%0.02f%% / %0.02f%%",
          ((double)afl->queue_cur->bitmap_size) * 100 / afl->fsrv.real_map_size,
          t_byte_ratio);

  SAYF("                       table full : %s%-19s " bSTG bV "\n",
       t_byte_ratio > 70
           ? cLRD
           : ((t_bytes < 200 && !afl->non_instrumented_mode) ? cPIN : cRST),
       tmp);

  sprintf(tmp, "%s (%0.02f%%)", u_stringify_int(IB(0), afl->cur_skipped_items),
          ((double)afl->cur_skipped_items * 100) / afl->queued_items);

  SAYF(bV bSTOP "                     burned pizzas : " cRST
                "%-18s                    " bSTG bV,
       tmp);

  sprintf(tmp, "%0.02f bits/tuple", t_bytes ? (((double)t_bits) / t_bytes) : 0);

  SAYF(bSTOP "                   count coverage : " cRST "%-19s " bSTG bV "\n",
       tmp);

  SAYF(bVR bH                                                 bSTOP cCYA
       " Pizzas almost ready " bSTG bH30 bH20 bH2 bH bX bH    bSTOP cCYA
       " Types of pizzas cooking " bSTG bH10 bH5 bH2 bH10 bH2 bH bVL "\n");

  sprintf(tmp, "%s (%0.02f%%)", u_stringify_int(IB(0), afl->queued_favored),
          ((double)afl->queued_favored) * 100 / afl->queued_items);

  /* Yeah... it's still going on... halp? */

  SAYF(bV bSTOP "                     now preparing : " cRST
                "%-22s                " bSTG bV bSTOP
                "                favourite topping : " cRST "%-20s" bSTG bV
                "\n",
       afl->stage_name, tmp);

  if (!afl->stage_max) {

    sprintf(tmp, "%s/-", u_stringify_int(IB(0), afl->stage_cur));

  } else {

    sprintf(tmp, "%s/%s (%0.02f%%)", u_stringify_int(IB(0), afl->stage_cur),
            u_stringify_int(IB(1), afl->stage_max),
            ((double)afl->stage_cur) * 100 / afl->stage_max);

  }

  SAYF(bV bSTOP "                  number of pizzas : " cRST
                "%-23s               " bSTG bV bSTOP,
       tmp);

  sprintf(tmp, "%s (%0.02f%%)", u_stringify_int(IB(0), afl->queued_with_cov),
          ((double)afl->queued_with_cov) * 100 / afl->queued_items);

  SAYF(" new pizza type seen on Instagram : " cRST "%-20s" bSTG bV "\n", tmp);

  sprintf(tmp, "%s (%s%s saved)", u_stringify_int(IB(0), afl->total_crashes),
          u_stringify_int(IB(1), afl->saved_crashes),
          (afl->saved_crashes >= KEEP_UNIQUE_CRASH) ? "+" : "");

  if (afl->crash_mode) {

    SAYF(bV bSTOP "                      total pizzas : " cRST
                  "%-22s                " bSTG bV bSTOP
                  "      pizzas with pineapple : %s%-20s" bSTG bV "\n",
         u_stringify_int(IB(0), afl->fsrv.total_execs), crash_color, tmp);

  } else {

    SAYF(bV bSTOP "                      total pizzas : " cRST
                  "%-22s                " bSTG bV bSTOP
                  "      total pizzas with pineapple : %s%-20s" bSTG bV "\n",
         u_stringify_int(IB(0), afl->fsrv.total_execs), crash_color, tmp);

  }

  /* Show a warning about slow execution. */

  if (afl->stats_avg_exec < 20) {

    sprintf(tmp, "%s/sec (%s)", u_stringify_float(IB(0), afl->stats_avg_exec),
            "zzzz...");

    SAYF(bV bSTOP "                pizza making speed : " cLRD
                  "%-22s                ",
         tmp);

  } else {

    sprintf(tmp, "%s/sec", u_stringify_float(IB(0), afl->stats_avg_exec));
    SAYF(bV bSTOP "                pizza making speed : " cRST
                  "%-22s                ",
         tmp);

  }

  sprintf(tmp, "%s (%s%s saved)", u_stringify_int(IB(0), afl->total_tmouts),
          u_stringify_int(IB(1), afl->saved_tmouts),
          (afl->saved_tmouts >= KEEP_UNIQUE_HANG) ? "+" : "");

  SAYF(bSTG bV bSTOP "                    burned pizzas : " cRST "%-20s" bSTG bV
                     "\n",
       tmp);

  /* Aaaalmost there... hold on! */

  SAYF(bVR bH cCYA bSTOP " Promotional campaign on TikTok yields " bSTG bH30 bH2
           bH bH2 bX bH                                          bSTOP cCYA
                         " Customer type " bSTG bH5 bH2 bH30 bH2 bH bVL "\n");

  if (unlikely(afl->custom_only)) {

    strcpy(tmp, "oven off (custom-mutator-only mode)");

  } else if (likely(afl->skip_deterministic)) {

    strcpy(tmp, "oven off (default, enable with -D)");

  } else {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_FLIP1]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_FLIP1]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_FLIP2]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_FLIP2]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_FLIP4]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_FLIP4]));

  }

  SAYF(bV bSTOP
       "                pizzas for celiac  : " cRST "%-36s  " bSTG bV bSTOP
       "                           levels : " cRST "%-10s          " bSTG bV
       "\n",
       tmp, u_stringify_int(IB(0), afl->max_depth));

  if (unlikely(!afl->skip_deterministic)) {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_FLIP8]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_FLIP8]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_FLIP16]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_FLIP16]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_FLIP32]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_FLIP32]));

  }

  SAYF(bV bSTOP
       "                   pizzas for kids : " cRST "%-36s  " bSTG bV bSTOP
       "                   pizzas to make : " cRST "%-10s          " bSTG bV
       "\n",
       tmp, u_stringify_int(IB(0), afl->pending_not_fuzzed));

  if (unlikely(!afl->skip_deterministic)) {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_ARITH8]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_ARITH8]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_ARITH16]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_ARITH16]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_ARITH32]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_ARITH32]));

  }

  SAYF(bV bSTOP
       "                      pizza bianca : " cRST "%-36s  " bSTG bV bSTOP
       "                       nice table : " cRST "%-10s          " bSTG bV
       "\n",
       tmp, u_stringify_int(IB(0), afl->pending_favored));

  if (unlikely(!afl->skip_deterministic)) {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_INTEREST8]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_INTEREST8]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_INTEREST16]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_INTEREST16]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_INTEREST32]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_INTEREST32]));

  }

  SAYF(bV bSTOP
       "               recurring customers : " cRST "%-36s  " bSTG bV bSTOP
       "                    new customers : " cRST "%-10s          " bSTG bV
       "\n",
       tmp, u_stringify_int(IB(0), afl->queued_discovered));

  if (unlikely(!afl->skip_deterministic)) {

    sprintf(tmp, "%s/%s, %s/%s, %s/%s, %s/%s",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_EXTRAS_UO]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_EXTRAS_UO]),
            u_stringify_int(IB(2), afl->stage_finds[STAGE_EXTRAS_UI]),
            u_stringify_int(IB(3), afl->stage_cycles[STAGE_EXTRAS_UI]),
            u_stringify_int(IB(4), afl->stage_finds[STAGE_EXTRAS_AO]),
            u_stringify_int(IB(5), afl->stage_cycles[STAGE_EXTRAS_AO]),
            u_stringify_int(IB(6), afl->stage_finds[STAGE_EXTRAS_AI]),
            u_stringify_int(IB(7), afl->stage_cycles[STAGE_EXTRAS_AI]));

  } else if (unlikely(!afl->extras_cnt || afl->custom_only)) {

    strcpy(tmp, "n/a");

  } else {

    strcpy(tmp, "18 year anniversary mode");

  }

  SAYF(bV bSTOP
       "                        dictionary : " cRST "%-36s  " bSTG bV bSTOP
       "      patrons from old restaurant : " cRST "%-10s          " bSTG bV
       "\n",
       tmp,
       afl->sync_id ? u_stringify_int(IB(0), afl->queued_imported)
                    : (u8 *)"n/a");

  sprintf(tmp, "%s/%s, %s/%s",
          u_stringify_int(IB(0), afl->stage_finds[STAGE_HAVOC]),
          u_stringify_int(IB(2), afl->stage_cycles[STAGE_HAVOC]),
          u_stringify_int(IB(3), afl->stage_finds[STAGE_SPLICE]),
          u_stringify_int(IB(4), afl->stage_cycles[STAGE_SPLICE]));

  SAYF(bV bSTOP " 18 year anniversary mode/cleaning : " cRST
                "%-36s  " bSTG bV bSTOP,
       tmp);

  if (t_bytes) {

    sprintf(tmp, "%0.02f%%", stab_ratio);

  } else {

    strcpy(tmp, "n/a");

  }

  SAYF("                    oven flameout : %s%-10s          " bSTG bV "\n",
       (stab_ratio < 85 && afl->var_byte_count > 40)
           ? cLRD
           : ((afl->queued_variable &&
               (!afl->persistent_mode || afl->var_byte_count > 20))
                  ? cMGN
                  : cRST),
       tmp);

  if (unlikely(afl->afl_env.afl_python_module)) {

    sprintf(tmp, "%s/%s,",
            u_stringify_int(IB(0), afl->stage_finds[STAGE_PYTHON]),
            u_stringify_int(IB(1), afl->stage_cycles[STAGE_PYTHON]));

  } else {

    strcpy(tmp, "unused,");

  }

  if (unlikely(afl->afl_env.afl_custom_mutator_library)) {

    strcat(tmp, " ");
    strcat(tmp, u_stringify_int(IB(2), afl->stage_finds[STAGE_CUSTOM_MUTATOR]));
    strcat(tmp, "/");
    strcat(tmp,
           u_stringify_int(IB(3), afl->stage_cycles[STAGE_CUSTOM_MUTATOR]));
    strcat(tmp, ",");

  } else {

    strcat(tmp, " unused,");

  }

  if (unlikely(afl->shm.cmplog_mode)) {

    strcat(tmp, " ");
    strcat(tmp, u_stringify_int(IB(4), afl->stage_finds[STAGE_COLORIZATION]));
    strcat(tmp, "/");
    strcat(tmp, u_stringify_int(IB(5), afl->stage_cycles[STAGE_COLORIZATION]));
    strcat(tmp, ", ");
    strcat(tmp, u_stringify_int(IB(6), afl->stage_finds[STAGE_ITS]));
    strcat(tmp, "/");
    strcat(tmp, u_stringify_int(IB(7), afl->stage_cycles[STAGE_ITS]));

  } else {

    strcat(tmp, " unused, unused");

  }

  SAYF(bV bSTOP "                      py/custom/rq : " cRST
                "%-36s  " bSTG bVR bH20 bH2 bH30 bH2 bH bH bRB "\n",
       tmp);

  if (likely(afl->disable_trim)) {

    sprintf(tmp, "disabled, ");

  } else if (unlikely(!afl->bytes_trim_out)) {

    sprintf(tmp, "n/a, ");

  } else {

    sprintf(tmp, "%0.02f%%/%s, ",
            ((double)(afl->bytes_trim_in - afl->bytes_trim_out)) * 100 /
                afl->bytes_trim_in,
            u_stringify_int(IB(0), afl->trim_execs));

  }

  if (likely(afl->skip_deterministic)) {

    strcat(tmp, "disabled");

  } else if (unlikely(!afl->blocks_eff_total)) {

    strcat(tmp, "n/a");

  } else {

    u8 tmp2[128];

    sprintf(tmp2, "%0.02f%%",
            ((double)(afl->blocks_eff_total - afl->blocks_eff_select)) * 100 /
                afl->blocks_eff_total);

    strcat(tmp, tmp2);

  }

  // if (afl->custom_mutators_count) {

  //
  //  sprintf(tmp, "%s/%s",
  //          u_stringify_int(IB(0), afl->stage_finds[STAGE_CUSTOM_MUTATOR]),
  //          u_stringify_int(IB(1), afl->stage_cycles[STAGE_CUSTOM_MUTATOR]));
  //  SAYF(bV bSTOP " custom mut. : " cRST "%-36s " bSTG bV RESET_G1, tmp);
  //
  //} else {

  SAYF(bV bSTOP "                   toilets clogged : " cRST
                "%-36s  " bSTG bV RESET_G1,
       tmp);

  //}

  /* Provide some CPU utilization stats. */

  if (afl->cpu_core_count) {

    char *spacing = SP10, snap[80] = " " cLGN "Pizzaioli's busyness " cRST " ";

    double cur_runnable = get_runnable_processes();
    u32    cur_utilization = cur_runnable * 100 / afl->cpu_core_count;

    u8 *cpu_color = cCYA;

    /* If we could still run one or more processes, use green. */

    if (afl->cpu_core_count > 1 && cur_runnable + 1 <= afl->cpu_core_count) {

      cpu_color = cLGN;

    }

    /* If we're clearly oversubscribed, use red. */

    if (!afl->no_cpu_meter_red && cur_utilization >= 150) { cpu_color = cLRD; }

    if (afl->fsrv.snapshot) { spacing = snap; }

#ifdef HAVE_AFFINITY

    if (afl->cpu_aff >= 0) {

      SAYF("%s" cGRA "[cpu%03u:%s%3u%%" cGRA "]\r" cRST, spacing,
           MIN(afl->cpu_aff, 999), cpu_color, MIN(cur_utilization, (u32)999));

    } else {

      SAYF("%s" cGRA "   [cpu:%s%3u%%" cGRA "]\r" cRST, spacing, cpu_color,
           MIN(cur_utilization, (u32)999));

    }

#else

    SAYF("%s" cGRA "   [cpu:%s%3u%%" cGRA "]\r" cRST, spacing, cpu_color,
         MIN(cur_utilization, (u32)999));

#endif                                                    /* ^HAVE_AFFINITY */

  } else {

    SAYF("\r");

  }

  /* Last line */
  SAYF(SET_G1 "\n" bSTG bLB bH30 bH20 bH2 bH20 bH2 bH bRB bSTOP cRST RESET_G1);

#undef IB

  /* Hallelujah! */

  fflush(0);

}

/* Display quick statistics at the end of processing the input directory,
   plus a bunch of warnings. Some calibration stuff also ended up here,
   along with several hardcoded constants. Maybe clean up eventually. */

void show_init_stats(afl_state_t *afl) {

  struct queue_entry *q;
  u32                 min_bits = 0, max_bits = 0, max_len = 0, count = 0, i;
  u64                 min_us = 0, max_us = 0;
  u64                 avg_us = 0;

  u8 val_bufs[4][STRINGIFY_VAL_SIZE_MAX];
#define IB(i) val_bufs[(i)], sizeof(val_bufs[(i)])

  if (afl->total_cal_cycles) {

    avg_us = afl->total_cal_us / afl->total_cal_cycles;

  }

  for (i = 0; i < afl->queued_items; i++) {

    q = afl->queue_buf[i];
    if (unlikely(q->disabled)) { continue; }

    if (!min_us || q->exec_us < min_us) { min_us = q->exec_us; }
    if (q->exec_us > max_us) { max_us = q->exec_us; }

    if (!min_bits || q->bitmap_size < min_bits) { min_bits = q->bitmap_size; }
    if (q->bitmap_size > max_bits) { max_bits = q->bitmap_size; }

    if (q->len > max_len) { max_len = q->len; }

    ++count;

  }

  // SAYF("\n");

  if (avg_us > ((afl->fsrv.cs_mode || afl->fsrv.qemu_mode || afl->unicorn_mode)
                    ? 50000
                    : 10000)) {

    WARNF(cLRD
          "The target binary is pretty slow! See "
          "%s/fuzzing_in_depth.md#i-improve-the-speed",
          doc_path);

  }

  /* Let's keep things moving with slow binaries. */

  if (unlikely(afl->fixed_seed)) {

    afl->havoc_div = 1;

  } else if (avg_us > 50000) {

    afl->havoc_div = 10;                                /* 0-19 execs/sec   */

  } else if (avg_us > 20000) {

    afl->havoc_div = 5;                                 /* 20-49 execs/sec  */

  } else if (avg_us > 10000) {

    afl->havoc_div = 2;                                 /* 50-100 execs/sec */

  }

  if (!afl->resuming_fuzz) {

    if (max_len > 50 * 1024) {

      WARNF(cLRD
            "Some test cases are huge (%s) - see "
            "%s/fuzzing_in_depth.md#i-improve-the-speed",
            stringify_mem_size(IB(0), max_len), doc_path);

    } else if (max_len > 10 * 1024) {

      WARNF(
          "Some test cases are big (%s) - see "
          "%s/fuzzing_in_depth.md#i-improve-the-speed",
          stringify_mem_size(IB(0), max_len), doc_path);

    }

    if (afl->useless_at_start && !afl->in_bitmap) {

      WARNF(cLRD "Some test cases look useless. Consider using a smaller set.");

    }

    if (afl->queued_items > 100) {

      WARNF(cLRD
            "You probably have far too many input files! Consider trimming "
            "down.");

    } else if (afl->queued_items > 20) {

      WARNF("You have lots of input files; try starting small.");

    }

  }

  OKF("Here are some useful stats:\n\n"

      cGRA "    Test case count : " cRST
      "%u favored, %u variable, %u ignored, %u total\n" cGRA
      "       Bitmap range : " cRST
      "%u to %u bits (average: %0.02f bits)\n" cGRA
      "        Exec timing : " cRST "%s to %s us (average: %s us)\n",
      afl->queued_favored, afl->queued_variable, afl->queued_items - count,
      afl->queued_items, min_bits, max_bits,
      ((double)afl->total_bitmap_size) /
          (afl->total_bitmap_entries ? afl->total_bitmap_entries : 1),
      stringify_int(IB(0), min_us), stringify_int(IB(1), max_us),
      stringify_int(IB(2), avg_us));

  if (afl->timeout_given == 3) {

    ACTF("Applying timeout settings from resumed session (%u ms).",
         afl->fsrv.exec_tmout);

  } else if (afl->timeout_given != 1) {

    /* Figure out the appropriate timeout. The basic idea is: 5x average or
       1x max, rounded up to EXEC_TM_ROUND ms and capped at 1 second.

       If the program is slow, the multiplier is lowered to 2x or 3x, because
       random scheduler jitter is less likely to have any impact, and because
       our patience is wearing thin =) */

    if (unlikely(afl->fixed_seed)) {

      afl->fsrv.exec_tmout = avg_us * 5 / 1000;

    } else if (avg_us > 50000) {

      afl->fsrv.exec_tmout = avg_us * 2 / 1000;

    } else if (avg_us > 10000) {

      afl->fsrv.exec_tmout = avg_us * 3 / 1000;

    } else {

      afl->fsrv.exec_tmout = avg_us * 5 / 1000;

    }

    afl->fsrv.exec_tmout = MAX(afl->fsrv.exec_tmout, max_us / 1000);
    afl->fsrv.exec_tmout =
        (afl->fsrv.exec_tmout + EXEC_TM_ROUND) / EXEC_TM_ROUND * EXEC_TM_ROUND;

    if (afl->fsrv.exec_tmout > EXEC_TIMEOUT) {

      afl->fsrv.exec_tmout = EXEC_TIMEOUT;

    }

    ACTF("No -t option specified, so I'll use an exec timeout of %u ms.",
         afl->fsrv.exec_tmout);

    afl->timeout_given = 1;

  } else {

    ACTF("-t option specified. We'll use an exec timeout of %u ms.",
         afl->fsrv.exec_tmout);

  }

  /* In non-instrumented mode, re-running every timing out test case with a
     generous time
     limit is very expensive, so let's select a more conservative default. */

  if (afl->non_instrumented_mode && !(afl->afl_env.afl_hang_tmout)) {

    afl->hang_tmout = MIN((u32)EXEC_TIMEOUT, afl->fsrv.exec_tmout * 2 + 100);

  }

  OKF("All set and ready to roll!");
#undef IB

}

inline void update_calibration_time(afl_state_t *afl, u64 *time) {

  u64 cur = get_cur_time_us();
  afl->calibration_time_us += cur - *time;
  *time = cur;

}

inline void update_trim_time(afl_state_t *afl, u64 *time) {

  u64 cur = get_cur_time_us();
  afl->trim_time_us += cur - *time;
  *time = cur;

}

inline void update_sync_time(afl_state_t *afl, u64 *time) {

  u64 cur = get_cur_time_us();
  afl->sync_time_us += cur - *time;
  *time = cur;

}

inline void update_cmplog_time(afl_state_t *afl, u64 *time) {

  u64 cur = get_cur_time_us();
  afl->cmplog_time_us += cur - *time;
  *time = cur;

}
