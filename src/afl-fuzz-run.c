/*
   american fuzzy lop++ - target execution related routines
   --------------------------------------------------------

   Originally written by Michal Zalewski

   Now maintained by Marc Heuse <mh@mh-sec.de>,
                        Heiko Eissfeldt <heiko.eissfeldt@hexco.de> and
                        Andrea Fioraldi <andreafioraldi@gmail.com> and
                        Dominik Maier <mail@dmnk.co>

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
#include "afl-ijon-min.h"
#include <sys/time.h>
#include <sys/stat.h>
#include <signal.h>
#include <limits.h>
#include <glob.h>
#if !defined NAME_MAX
  #define NAME_MAX _XOPEN_NAME_MAX
#endif
#include "third_party/cjson/cJSON.h"  /* 如果本文件没包含，就加上 */
#include "cmplog.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "asanfuzz.h"
#include <stdint.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <errno.h>
#include <ctype.h>


#ifdef PROFILING
u64 time_spent_working = 0;
#endif

/* helper: write all bytes */
static int nv_sendall(int fd, const void *buf, size_t len) {
  const uint8_t *p = (const uint8_t *)buf;
  size_t off = 0;
  while (off < len) {
    ssize_t n = send(fd, p + off, len - off, 0);
    if (n < 0) {
      if (errno == EINTR) continue;
      return 0;
    }
    if (n == 0) return 0;
    off += (size_t)n;
  }
  return 1;
}

/* helper: read exactly len bytes */
static int nv_recvall(int fd, void *buf, size_t len) {
  uint8_t *p = (uint8_t *)buf;
  size_t off = 0;
  while (off < len) {
    ssize_t n = recv(fd, p + off, len - off, 0);
    if (n < 0) {
      if (errno == EINTR) continue;
      return 0;
    }
    if (n == 0) return 0;
    off += (size_t)n;
  }
  return 1;
}

extern int nv_is_allowed_pair(afl_state_t *afl, const char *method, const char *path);
/* Execute target application, monitoring for timeouts. Return status
   information. The called program will update afl->fsrv->trace_bits. */

static inline u64 nv_fnv1a64(const char *s) {
  u64 h = 1469598103934665603ULL;
  for (; *s; ++s) { h ^= (unsigned char)(*s); h *= 1099511628211ULL; }
  return h ? h : 1;
}

static inline void nv_covset_init(afl_state_t *afl) {
  if (afl->nv_covset) return;
  afl->nv_cov_cap = 1u << 16; /* 65536 */
  afl->nv_cov_used = 0;
  afl->nv_covset = ck_alloc(afl->nv_cov_cap * sizeof(u64));
  memset(afl->nv_covset, 0, afl->nv_cov_cap * sizeof(u64));
}

/* Returns NV_COVSET_INSERTED / NV_COVSET_EXISTING / NV_COVSET_SATURATED.
   Probing itself lives in src/afl-fuzz-nv-covset.c so it can be driven to a
   full table by a unit test. */
static inline int nv_covset_insert(afl_state_t *afl, u64 h) {
  nv_covset_init(afl);
  int r = nv_covset_insert_into(afl->nv_covset, afl->nv_cov_cap,
                                &afl->nv_cov_used, h);
  if (unlikely(r == NV_COVSET_SATURATED)) {
    afl->nv_sec_state_saturated = 1;
    afl->nv_sec_state_dropped++;
  }
  return r;
}

/* One observation of the target's security state, derived from the status
   document the harness/target writes after every execution. */
typedef struct {
  u8  has;             /* a fresh (non-replayed) status document was parsed  */
  u8  is_exception;    /* timeout / 5xx / conn_refused                       */
  u8  recovered;
  u8  is_4xx;
  u64 ncov_delta;      /* harness-side coverage proxy, may legitimately be 0 */
  u64 new_states;      /* security states seen for the first time            */
  u64 state_id;        /* fnv1a64("METHOD PATH|CLASS")                       */
  u64 exec_seq;        /* target execution this observation came from, 0=n/a */
} nv_state_obs_t;

/* Reads the status document, folds it into the security-state set, credits
   the current queue entry when a new state shows up, and hands the caller a
   plain observation.  Reward computation is deliberately kept out of here so
   that state accounting happens on every execution, not only on the ones a
   bandit arm produced. */
static void nv_observe_security_state(afl_state_t *afl, const char *path,
                                      nv_state_obs_t *obs) {

  memset(obs, 0, sizeof(*obs));

  FILE *fp = fopen(path, "rb");
  if (!fp) { afl->nv_http_status_fail++; return; }

  fseek(fp, 0, SEEK_END);
  long sz = ftell(fp);
  fseek(fp, 0, SEEK_SET);
  if (sz <= 0 || sz > 65536) { afl->nv_http_status_fail++; fclose(fp); return; }

  char *buf = ck_alloc(sz + 1);
  if (fread(buf, 1, sz, fp) != (size_t)sz) {
    ck_free(buf);
    fclose(fp);
    afl->nv_http_status_fail++;
    return;
  }
  buf[sz] = 0;
  fclose(fp);

  cJSON *root = cJSON_Parse(buf);
  ck_free(buf);
  if (!root) { afl->nv_http_status_fail++; return; }

  /* ---- Parse fields ---- */
  const cJSON *m  = cJSON_GetObjectItemCaseSensitive(root, "method");
  const cJSON *p  = cJSON_GetObjectItemCaseSensitive(root, "path");
  const cJSON *c  = cJSON_GetObjectItemCaseSensitive(root, "class");
  const cJSON *to = cJSON_GetObjectItemCaseSensitive(root, "timeout");
  const cJSON *nd = cJSON_GetObjectItemCaseSensitive(root, "ncov_delta");
  const cJSON *na = cJSON_GetObjectItemCaseSensitive(root, "nall");
  const cJSON *tsj = cJSON_GetObjectItemCaseSensitive(root, "ts_ms");
  const cJSON *bhj = cJSON_GetObjectItemCaseSensitive(root, "body_hash16");
  const cJSON *esj = cJSON_GetObjectItemCaseSensitive(root, "exec_seq");

  /* Execution identity, when the harness supplies one.  0 means "not
     reported" and makes the legacy timestamp stamp the fallback. */
  u64 exec_seq = (cJSON_IsNumber(esj) && esj->valuedouble > 0)
                     ? (u64)esj->valuedouble
                     : 0;

  u64 ts_ms = cJSON_IsNumber(tsj) ? (u64)tsj->valuedouble : 0;
  u32 body_hash16 = cJSON_IsNumber(bhj) ? (u32)bhj->valuedouble : 0;

  u64 stamp = ts_ms ? (ts_ms ^ ((u64)body_hash16 << 32)) : 0;
  if (!stamp) stamp = 1;

  afl->nv_http_status_ok++;

  /* Consume each execution's document exactly once.  Identity is the
     execution id when the harness reports one: two distinct executions can
     legitimately produce byte-identical documents, and dropping the second as
     a "replay" silently discarded real observations. */
  if (nv_status_is_fresh(exec_seq, stamp, &afl->nv_last_exec_seq,
                         &afl->nv_last_status_seq) == NV_STATUS_REPLAY) {
    afl->nv_sec_state_replays++;
    cJSON_Delete(root);
    return;
  }
  afl->nv_status_cnt++;

  /* ---- After dedup: Err/Rec accounting ---- */
  const cJSON *ie = cJSON_GetObjectItemCaseSensitive(root, "is_exception");
  int is_exc_flag = cJSON_IsNumber(ie) ? ie->valueint : 0;
  if (is_exc_flag) afl->nv_err_cnt++;

  const cJSON *rm = cJSON_GetObjectItemCaseSensitive(root, "recover_ms");
  u64 recover_ms = cJSON_IsNumber(rm) ? (u64)rm->valuedouble : 0;

  const cJSON *rcv = cJSON_GetObjectItemCaseSensitive(root, "recovered");
  int recovered = cJSON_IsNumber(rcv) ? rcv->valueint : 0;
  if (is_exc_flag && recovered) {
    afl->nv_rec_cnt++;
    afl->nv_rec_ms_sum += recover_ms;
  }

  /* ---- Coverage gain ---- */
  u64 ncov_delta = cJSON_IsNumber(nd) ? (u64)nd->valuedouble : 0;
  if (ncov_delta > 0) afl->nv_ncov_hit++;

  u64 nall = cJSON_IsNumber(na) ? (u64)na->valuedouble : 0;
  (void)nall;

  const char *method = (cJSON_IsString(m) && m->valuestring) ? m->valuestring : "UNK";
  const char *pathv  = (cJSON_IsString(p) && p->valuestring) ? p->valuestring : "/";
  const char *cls    = (cJSON_IsString(c) && c->valuestring) ? c->valuestring : "other";
  int timeout = cJSON_IsNumber(to) ? to->valueint : 0;

  /* ---- security state ----
     Every component of the key comes from the status document, so fuzzed
     bytes can reach it.  Fold each onto a finite set first, otherwise a
     mutated request line mints a fresh state per byte string and the covset
     saturates on garbage rather than on real behaviour. */
  const char *cmethod = nv_canon_method(method);
  const char *ccls    = nv_canon_class(cls);
  const char *cpath   = nv_canon_path_label(pathv);

  if (!cpath) {

    /* Structurally fine.  When the task config declares an endpoint
       allowlist, anything outside it is still fuzzer-invented rather than a
       real route, so it folds onto one state.  With no config loaded
       nv_is_allowed_pair() allows everything and the path passes through. */
    cpath = nv_is_allowed_pair(afl, cmethod, pathv) ? pathv : "unknown_path";

  }

  char key[1024];
  snprintf(key, sizeof(key), "%s %s|%s", cmethod, cpath, ccls);
  u64 h = nv_fnv1a64(key);
  /* A saturated table drops the state.  It must not be reported as new:
     that would manufacture a reward and a seed credit for a state the set
     never actually recorded. */
  int is_new = (nv_covset_insert(afl, h) == NV_COVSET_INSERTED);

  int is_exc = timeout || (strcmp(ccls, "5xx") == 0) ||
               (strcmp(ccls, "conn_refused") == 0);

  obs->has          = 1;
  obs->is_exception = is_exc ? 1 : 0;
  obs->recovered    = recovered ? 1 : 0;
  obs->is_4xx       = (strcmp(ccls, "4xx") == 0) ? 1 : 0;
  obs->ncov_delta   = ncov_delta;
  obs->new_states   = is_new ? 1 : 0;
  obs->state_id     = h;
  obs->exec_seq     = exec_seq;

  afl->nv_sec_state_obs++;
  afl->nv_sec_state_delta_last = obs->new_states;

  /* Opt-in audit trail: one line per *consumed* observation, so a reviewer can
     check which target execution each security state and reward came from.
     Off unless NV_STATE_TRACE_PATH is set; resolved once. */
  {

    static const char *tp = NULL;
    static u8 tp_resolved = 0;
    if (unlikely(!tp_resolved)) {

      const char *env = getenv("NV_STATE_TRACE_PATH");
      /* copied, not aliased: see the NV_STATUS_PATH note in common_fuzz_stuff */
      tp = (env && *env) ? (const char *)ck_strdup((u8 *)env) : NULL;
      tp_resolved = 1;

    }

    if (unlikely(tp && *tp)) {

      FILE *tf = fopen(tp, "a");
      if (tf) {

        fprintf(tf,
                "{\"exec_seq\":%llu,\"state\":\"%s\",\"state_id\":\"%llx\","
                "\"new\":%u}\n",
                (unsigned long long)obs->exec_seq, key,
                (unsigned long long)h, (unsigned)obs->new_states);
        fclose(tf);

      }

    }

  }

  if (is_new) {

    afl->nv_sec_state_new_total++;

    /* Closed loop A: credit the seed that reached this state so that
       select_next_queue_entry() can favour it. */
    if (afl->queue_cur) {

      afl->queue_cur->ss_cov_cnt++;
      afl->nv_sec_state_seed_credit++;

    }

  }

  cJSON_Delete(root);

}

/* Closed loop B: turn one observation into a bandit reward. */
static double nv_reward_from_obs(const nv_state_obs_t *obs) {

  if (!obs->has) return 0.0;

  double reward = 0.0;
  reward += NV_REWARD_HARNESS_NCOV * (double)obs->ncov_delta;
  reward += NV_REWARD_NEW_SECURITY_STATE * (double)obs->new_states;
  reward += obs->is_exception ? NV_REWARD_EXCEPTION : 0.0;
  reward += obs->recovered ? NV_REWARD_RECOVERED : 0.0;
  if (obs->is_4xx) reward -= NV_REWARD_4XX_PENALTY;

  return reward;

}

/* nv_arm_enabled / nv_mab_pick / nv_mab_update now live in
   src/afl-fuzz-nv-mab.c so they can be unit tested in isolation. */

/* --- NV 2.5: harness status json --- */
typedef struct {
  int has;          /* 1 if parsed ok */
  int is_exception; /* bool */
  int http_code;    /* int */
  int recovered;    /* bool */
  u64 recover_ms;   /* u64 */
} nv_status_t;

static int nv_read_status_json(afl_state_t *afl, nv_status_t *st) {

  memset(st, 0, sizeof(*st));

  const char *p = getenv("NV_STATUS_PATH");
  char fn[PATH_MAX];

  if (p && *p) snprintf(fn, sizeof(fn), "%s", p);
  else snprintf(fn, sizeof(fn), "%s/nv_status.json", afl->out_dir);

  int fd = open(fn, O_RDONLY);
  if (fd < 0) return 0;

  struct stat sb;
  if (fstat(fd, &sb) || sb.st_size <= 0 || sb.st_size > (128 * 1024)) {
    close(fd);
    return 0;
  }

  char *buf = ck_alloc(sb.st_size + 1);
  ssize_t r = read(fd, buf, sb.st_size);
  close(fd);
  if (r <= 0) { ck_free(buf); return 0; }
  buf[r] = 0;

  cJSON *root = cJSON_Parse(buf);
  ck_free(buf);
  if (!root) return 0;

  cJSON *je = cJSON_GetObjectItemCaseSensitive(root, "is_exception");
  cJSON *jh = cJSON_GetObjectItemCaseSensitive(root, "http_code");
  cJSON *jr = cJSON_GetObjectItemCaseSensitive(root, "recovered");
  cJSON *jm = cJSON_GetObjectItemCaseSensitive(root, "recover_ms");

  st->is_exception = (je && (cJSON_IsTrue(je) || (cJSON_IsNumber(je) && je->valuedouble != 0))) ? 1 : 0;
  st->http_code    = (jh && cJSON_IsNumber(jh)) ? (int)jh->valuedouble : 0;
  st->recovered    = (jr && (cJSON_IsTrue(jr) || (cJSON_IsNumber(jr) && jr->valuedouble != 0))) ? 1 : 0;
  st->recover_ms   = (jm && cJSON_IsNumber(jm) && jm->valuedouble > 0) ? (u64)jm->valuedouble : 0;

  st->has = 1;
  cJSON_Delete(root);
  return 1;

}

fsrv_run_result_t __attribute__((hot)) fuzz_run_target(afl_state_t      *afl,
                                                       afl_forkserver_t *fsrv,
                                                       u32 timeout) {

#ifdef PROFILING
  static u64      time_spent_start = 0;
  struct timespec spec;
  if (time_spent_start) {

    u64 current;
    clock_gettime(CLOCK_REALTIME, &spec);
    current = (spec.tv_sec * 1000000000) + spec.tv_nsec;
    time_spent_working += (current - time_spent_start);

  }

#endif
  fsrv_run_result_t res = afl_fsrv_run_target(fsrv, timeout, &afl->stop_soon);

  /* --- NV 2.6: valid exec counting + max_test_cases stop ---
    validity-skip happens before calling fuzz_run_target.
    Exclude dry_run / calibration, and require queue_cur to be in fuzzing loop.
  */
  u8 nv_counted = 0;
  if (likely(afl->queue_cur &&
            (!afl->stage_name ||
              (strcmp(afl->stage_name, "dry_run") &&
              strcmp(afl->stage_name, "calibration"))))) {
    afl->nv_total_valid_exec++;
    nv_counted = 1;

    if (afl->nv_task.max_test_cases &&
        afl->nv_total_valid_exec >= afl->nv_task.max_test_cases) {

      afl->stop_soon = 2;
      return res;

    }

  }

  /* --- NV 2.5: err/rec --- */
  int is_err = 0;
  nv_status_t st;

  if (res == FSRV_RUN_CRASH || res == FSRV_RUN_TMOUT || res == FSRV_RUN_ERROR) {

    is_err = 1;

    /* optional: also count recovery for crashes/timeouts if harness provides it */
    if (nv_read_status_json(afl, &st) && st.has) {

      afl->nv_rec_total++;
      if (st.recovered) {

        afl->nv_rec_success++;
        afl->nv_rec_time_sum_ms += st.recover_ms;

      }

    }

  } else if (res == FSRV_RUN_OK) {

    if (nv_read_status_json(afl, &st) && st.has) {

      if (st.is_exception || st.http_code >= 500) is_err = 1;

      if (nv_counted && is_err) {

        afl->nv_rec_total++;
        if (st.recovered) {

          afl->nv_rec_success++;
          afl->nv_rec_time_sum_ms += st.recover_ms;

        }

      }

    }

  }

  if (nv_counted && is_err) afl->nv_err_exec++;

#ifdef __AFL_CODE_COVERAGE
  if (unlikely(!fsrv->persistent_trace_bits)) {

    // On the first run, we allocate the persistent map to collect coverage.
    fsrv->persistent_trace_bits = (u8 *)malloc(fsrv->map_size);
    memset(fsrv->persistent_trace_bits, 0, fsrv->map_size);

  }

  for (u32 i = 0; i < fsrv->map_size; ++i) {

    if (fsrv->persistent_trace_bits[i] != 255 && fsrv->trace_bits[i]) {

      fsrv->persistent_trace_bits[i]++;

    }

  }

#endif

  /* If post_run() function is defined in custom mutator, the function will be
     called each time after AFL++ executes the target program. */

  if (unlikely(afl->custom_mutators_count)) {

    LIST_FOREACH(&afl->custom_mutator_list, struct custom_mutator, {

      if (unlikely(el->afl_custom_post_run)) {

        el->afl_custom_post_run(el->data);

      }

    });

  }

  /* Check for new IJON max values after execution */
  if (unlikely(fsrv->use_ijon && afl->ijon_state && afl->ijon_bits)) {

    /* UNIFIED SHARED MEMORY ACCESS: Always use dynamic allocation */

    // Get current input data for IJON processing
    u8 *input_data = NULL;
    u32 input_len = 0;

    /* Read input data from testcase file that was just executed */
    if (afl->fsrv.out_file) {

      struct stat st;
      if (stat(afl->fsrv.out_file, &st) == 0) {

        if (st.st_size > 0) {

          input_len = st.st_size;
          input_data = ck_alloc(input_len);

          int fd = open(afl->fsrv.out_file, O_RDONLY);
          if (fd >= 0) {

            ssize_t bytes_read = read(fd, input_data, input_len);
            close(fd);

            if (bytes_read != input_len) {

              ck_free(input_data);
              input_data = NULL;
              input_len = 0;

            }

          } else {

            ck_free(input_data);
            input_data = NULL;
            input_len = 0;

          }

        }

      }

    }

    if (input_data) {

      /* Use pre-initialized shared_access from afl state */
      ijon_update_max_dynamic(afl->ijon_state, afl->ijon_shared_access,
                              input_data, input_len);

    }

    if (input_data) {

      ck_free(input_data);
      input_data = NULL;

    }

  }

#ifdef PROFILING
  clock_gettime(CLOCK_REALTIME, &spec);
  time_spent_start = (spec.tv_sec * 1000000000) + spec.tv_nsec;
#endif

  return res;

}

/* Write modified data to file for testing. If afl->fsrv.out_file is set, the
   old file is unlinked and a new one is created. Otherwise, afl->fsrv.out_fd is
   rewound and truncated. */

typedef enum {
  NV_V_OK          = 0,
  NV_V_REJ_PARSE   = 1, /* HTTP/JSON parse failed */
  NV_V_REJ_RULE    = 2, /* legacy: generic rules reject */
  NV_V_REJ_RPC_FAIL= 3, /* external model RPC failed/timeout */

  /* --- fine-grained rule family (still counted into nv_invalid_rule_cnt) --- */
  NV_V_REJ_ALLOW   = 4, /* not in allowlist (METHOD PATH) */
  NV_V_REJ_DOCID   = 5, /* submit/approve/query missing docId */
  NV_V_REJ_BODY    = 6, /* body sanity (not JSON-like / malformed body start) */
  NV_V_REJ_SCORE   = 7  /* rejected by model score >= threshold */
} nv_vreason_t;

static inline int nv_v_is_reject(nv_vreason_t r) { return r != NV_V_OK; }

static int nv_parse_unix_path(const char *endpoint, char *out, size_t out_sz) {
  if (!endpoint || !out || out_sz < 2) return 0;

  const char *p = endpoint;

  /* case1: raw absolute path */
  if (p[0] == '/') {
    size_t n = strnlen(p, out_sz);
    if (n >= out_sz) return 0;
    memcpy(out, p, n + 1);
    return 1;
  }

  /* case2: unix://... */
  if (!strncmp(p, "unix://", 7)) {
    p += 7;

    /* allow unix:///tmp/x  OR unix://tmp/x */
    if (*p == '\0') return 0;

    if (*p == '/') {
      /* already absolute, keep all slashes */
      size_t n = strnlen(p, out_sz);
      if (n >= out_sz) return 0;
      memcpy(out, p, n + 1);
      return 1;
    } else {
      /* treat as "/"+p */
      int w = snprintf(out, out_sz, "/%s", p);
      return (w > 1 && (size_t)w < out_sz);
    }
  }

  /* optional: unix:/tmp/x */
  if (!strncmp(p, "unix:", 5)) {
    p += 5;
    if (*p == '\0') return 0;
    if (*p != '/') {
      int w = snprintf(out, out_sz, "/%s", p);
      return (w > 1 && (size_t)w < out_sz);
    }
    size_t n = strnlen(p, out_sz);
    if (n >= out_sz) return 0;
    memcpy(out, p, n + 1);
    return 1;
  }

  /* unsupported */
  return 0;
}


/* env:
 *   NV_RPC_FMT = "text" (default) or "bin"
 * protocol:
 *   request: [u32_le len][payload bytes]
 *   response:
 *     - text: ASCII like "0.123\n" (server can just send a string)
 *     - bin : IEEE754 double (8 bytes)
 */
static double nv_validity_rpc_score_unix(afl_state_t *afl,
                                         const u8 *buf, u32 len,
                                         int *ok) {

  if (ok) *ok = 0;

  const char *ep = afl->nv_task.validity_endpoint;
  if (!ep || !*ep) return 0.0;

  char sock_path[108] = {0};
  if (!nv_parse_unix_path(ep, sock_path, sizeof(sock_path))) return 0.0;

  int fd = socket(AF_UNIX, SOCK_STREAM, 0);
  if (fd < 0) return 0.0;

  struct sockaddr_un addr;
  memset(&addr, 0, sizeof(addr));
  addr.sun_family = AF_UNIX;
  strncpy(addr.sun_path, sock_path, sizeof(addr.sun_path) - 1);

  if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
    close(fd);
    return 0.0;
  }

  /* send request */
  uint32_t n = (uint32_t)len;
  uint8_t hdr[4];
  hdr[0] = (uint8_t)(n & 0xff);
  hdr[1] = (uint8_t)((n >> 8) & 0xff);
  hdr[2] = (uint8_t)((n >> 16) & 0xff);
  hdr[3] = (uint8_t)((n >> 24) & 0xff);

  int ok_send = nv_sendall(fd, hdr, sizeof(hdr)) &&
                (len == 0 ? 1 : nv_sendall(fd, buf, len));
  if (!ok_send) { close(fd); return 0.0; }

  const char *fmt = getenv("NV_RPC_FMT");
  int want_bin = (fmt && !strcmp(fmt, "bin"));

  double score = 0.0;

  if (want_bin) {

    /* ---- binary double response ---- */
    int ok_recv = nv_recvall(fd, &score, sizeof(score));
    close(fd);
    if (!ok_recv) return 0.0;

    if (ok) *ok = 1;
    return score;

  } else {

    /* ---- text response ----
       read up to 64 bytes and parse with strtod */
    char resp[64];
    memset(resp, 0, sizeof(resp));

    /* try to read at least 1 byte; simplest: read exactly 8 first, then more if available.
       If your nv_recvall insists on exact size, DO NOT use it here. Use recv loop. */
    ssize_t r = recv(fd, resp, sizeof(resp) - 1, 0);
    close(fd);

    if (r <= 0) return 0.0;
    resp[r] = 0;

    if (getenv("NV_DEBUG_RPC")) {
      /* hex dump */
      fprintf(stderr, "[NV_RPC] resp_text='%s'\n", resp);
      fprintf(stderr, "[NV_RPC] resp_hex=");
      for (ssize_t i = 0; i < r; i++) fprintf(stderr, "%02x ", (unsigned char)resp[i]);
      fprintf(stderr, "\n");
    }

    /* trim leading spaces */
    char *s = resp;
    while (*s && isspace((unsigned char)*s)) s++;

    errno = 0;
    char *endp = NULL;
    double v = strtod(s, &endp);
    if (errno != 0 || endp == s) return 0.0;

    if (ok) *ok = 1;
    return v;

  }

}

static inline void nv_account_invalid(afl_state_t *afl, nv_vreason_t vr) {

  afl->nv_invalid_cnt++;

  if (vr == NV_V_REJ_PARSE) {
    afl->nv_invalid_parse_cnt++;
    return;
  }

  if (vr == NV_V_REJ_RPC_FAIL) {
    afl->nv_invalid_rpc_fail_cnt++;
    return;
  }

  /* everything else is "rule family" -> keep legacy total */
  afl->nv_invalid_rule_cnt++;

  if (vr == NV_V_REJ_ALLOW) afl->nv_invalid_allow_cnt++;
  else if (vr == NV_V_REJ_DOCID) afl->nv_invalid_docid_cnt++;
  else if (vr == NV_V_REJ_BODY) afl->nv_invalid_body_cnt++;
  else if (vr == NV_V_REJ_SCORE) afl->nv_invalid_score_cnt++;

}

static inline void nv_account_valid(afl_state_t *afl) {

  afl->nv_valid_cnt++;

}

static inline nv_vreason_t nv_validity_check(afl_state_t *afl, const u8 *buf,
                                             u32 len) {

  /* rule: empty / too large -> reject */
  if (!buf || !len) return NV_V_REJ_RULE;
  if (len > 4096) return NV_V_REJ_RULE;

  /* ---- v1: HTTP first line parse ---- */
  const u8 *p = buf;
  const u8 *end = buf + len;

  const u8 *nl = memchr(p, '\n', end - p);
  if (!nl) return NV_V_REJ_PARSE;

  char line[512];
  size_t lsz = (size_t)(nl - p);
  if (lsz >= sizeof(line)) return NV_V_REJ_RULE;
  memcpy(line, p, lsz);
  line[lsz] = 0;

  char method[16] = {0}, path[256] = {0};
  if (sscanf(line, "%15s %255s", method, path) < 2) return NV_V_REJ_PARSE;

  for (char *q = method; *q; q++) *q = (char)toupper((unsigned char)*q);
  if (path[0] != '/') return NV_V_REJ_RULE;

  /* strip query string before allowlist matching */
  char *qmark = strchr(path, '?');
  if (qmark) *qmark = '\0';

  /* allowlist check: exact or prefix-match handled by nv_is_allowed_pair() */
  if (!nv_is_allowed_pair(afl, method, path)) return NV_V_REJ_ALLOW;

  /* lightweight JSON sanity: body present -> should start with { or [ */
  const u8 *sep = memmem(buf, len, "\n\n", 2);
  if (!sep) sep = memmem(buf, len, "\r\n\r\n", 4);

  if (sep) {

    const u8 *body = sep + ((sep[0] == '\r') ? 4 : 2);
    size_t blen = (size_t)(end - body);

    while (blen &&
           (*body == ' ' || *body == '\t' || *body == '\r' || *body == '\n')) {
      body++;
      blen--;
    }

    /* for JSON-oriented harnesses, body can be empty; if non-empty, keep it roughly JSON-like */
    if (blen > 0 && (*body != '{' && *body != '[')) return NV_V_REJ_BODY;

  }

  /* ---- v2: optional RPC score (SE-fAnoGAN-ES will live behind this) ---- */
  if (afl->nv_task.validity_endpoint && afl->nv_task.validity_endpoint[0]) {

    int ok = 0;
    double score = nv_validity_rpc_score_unix(afl, buf, len, &ok);
    if (!ok) return NV_V_REJ_RPC_FAIL;

    /* score >= threshold => reject */
    if (afl->nv_task.validity_threshold > 0.0 &&
        score >= afl->nv_task.validity_threshold) {
      return NV_V_REJ_SCORE;
    }

  }

  return NV_V_OK;
}

u32 __attribute__((hot)) write_to_testcase(afl_state_t *afl, void **mem,
                                           u32 len, u32 fix) {

  u8 sent = 0;

  if (unlikely(afl->custom_mutators_count)) {

    ssize_t new_size = len;
    u8     *new_mem = *mem;
    u8     *new_buf = NULL;

    LIST_FOREACH(&afl->custom_mutator_list, struct custom_mutator, {

      if (el->afl_custom_post_process) {

        new_size =
            el->afl_custom_post_process(el->data, new_mem, new_size, &new_buf);

        if (unlikely(!new_buf || new_size <= 0)) {

          new_size = 0;
          new_buf = new_mem;
          // FATAL("Custom_post_process failed (ret: %lu)", (long
          // unsigned)new_size);

        } else {

          new_mem = new_buf;

        }

      }

    });

    if (unlikely(!new_size)) {

      // perform dummy runs (fix = 1), but skip all others
      if (fix) {

        new_size = len;

      } else {

        return 0;

      }

    }

    if (unlikely(new_size < afl->min_length && !fix)) {

      new_size = afl->min_length;

    } else if (unlikely(new_size > afl->max_length)) {

      new_size = afl->max_length;

    }

    if (new_mem != *mem && new_mem != NULL && new_size > 0) {

      new_buf = afl_realloc(AFL_BUF_PARAM(out_scratch), new_size);
      if (unlikely(!new_buf)) { PFATAL("alloc"); }
      memcpy(new_buf, new_mem, new_size);

      /* if AFL_POST_PROCESS_KEEP_ORIGINAL is set then save the original memory
         prior post-processing in new_mem to restore it later */
      if (unlikely(afl->afl_env.afl_post_process_keep_original)) {

        new_mem = *mem;

      }

      *mem = new_buf;
      afl_swap_bufs(AFL_BUF_PARAM(out), AFL_BUF_PARAM(out_scratch));

    }

    LIST_FOREACH(&afl->custom_mutator_list, struct custom_mutator, {

      if (el->afl_custom_fuzz_send) {

        if (!afl->afl_env.afl_custom_mutator_late_send) {

          el->afl_custom_fuzz_send(el->data, *mem, new_size);

        } else {

          afl->fsrv.custom_input = *mem;
          afl->fsrv.custom_input_len = new_size;

        }

        sent = 1;

      }

    });

    if (likely(!sent)) {

      /* everything as planned. use the potentially new data. */
      afl_fsrv_write_to_testcase(&afl->fsrv, *mem, new_size);

    }

    if (likely(!afl->afl_env.afl_post_process_keep_original)) {

      len = new_size;

    } else {

      /* restore the original memory which was saved in new_mem */
      *mem = new_mem;
      afl_swap_bufs(AFL_BUF_PARAM(out), AFL_BUF_PARAM(out_scratch));

    }

  } else {                                   /* !afl->custom_mutators_count */

    if (unlikely(len < afl->min_length && !fix)) {

      len = afl->min_length;

    } else if (unlikely(len > afl->max_length)) {

      len = afl->max_length;

    }

    /* boring uncustom. */
    afl_fsrv_write_to_testcase(&afl->fsrv, *mem, len);

  }

#ifdef _AFL_DOCUMENT_MUTATIONS
  s32  doc_fd;
  char fn[PATH_MAX];
  snprintf(fn, PATH_MAX, "%s/mutations/%09u:%s", afl->out_dir,
           afl->document_counter++,
           describe_op(afl, 0, NAME_MAX - strlen("000000000:")));

  if ((doc_fd = open(fn, O_WRONLY | O_CREAT | O_TRUNC, afl->perm)) >= 0) {

    if (write(doc_fd, *mem, len) != len)
      PFATAL("write to mutation file failed: %s", fn);

    if (afl->chown_needed) {

      if (fchown(doc_fd, -1, afl->fsrv.gid) == -1) {

        PFATAL("fchown() failed");

      }

    }

    close(doc_fd);

  }

#endif

  return len;

}

/* The same, but with an adjustable gap. Used for trimming. */

static void write_with_gap(afl_state_t *afl, u8 *mem, u32 len, u32 skip_at,
                           u32 skip_len) {

  s32 fd = afl->fsrv.out_fd;
  u32 tail_len = len - skip_at - skip_len;

  /*
  This memory is used to carry out the post_processing(if present) after copying
  the testcase by removing the gaps. This can break though
  */
  u8 *mem_trimmed = afl_realloc(AFL_BUF_PARAM(out_scratch), len - skip_len + 1);
  if (unlikely(!mem_trimmed)) { PFATAL("alloc"); }

  ssize_t new_size = len - skip_len;
  u8     *new_mem = mem;

  bool post_process_skipped = true;

  if (unlikely(afl->custom_mutators_count)) {

    u8 *new_buf = NULL;
    new_mem = mem_trimmed;

    LIST_FOREACH(&afl->custom_mutator_list, struct custom_mutator, {

      if (el->afl_custom_post_process) {

        // We copy into the mem_trimmed only if we actually have custom mutators
        // *with* post_processing installed

        if (post_process_skipped) {

          if (skip_at) { memcpy(mem_trimmed, (u8 *)mem, skip_at); }

          if (tail_len) {

            memcpy(mem_trimmed + skip_at, (u8 *)mem + skip_at + skip_len,
                   tail_len);

          }

          post_process_skipped = false;

        }

        new_size =
            el->afl_custom_post_process(el->data, new_mem, new_size, &new_buf);

        if (unlikely(!new_buf && new_size <= 0)) {

          new_size = 0;
          new_buf = new_mem;
          // FATAL("Custom_post_process failed (ret: %lu)", (long
          // unsigned)new_size);

        } else {

          new_mem = new_buf;

        }

      }

    });

  }

  if (likely(afl->fsrv.use_shmem_fuzz)) {

    if (!post_process_skipped) {

      // If we did post_processing, copy directly from the new_mem buffer

      memcpy(afl->fsrv.shmem_fuzz, new_mem, new_size);

    } else {

      memcpy(afl->fsrv.shmem_fuzz, mem, skip_at);

      memcpy(afl->fsrv.shmem_fuzz + skip_at, mem + skip_at + skip_len,
             tail_len);

    }

    *afl->fsrv.shmem_fuzz_len = new_size;

#ifdef _DEBUG
    if (afl->debug) {

      fprintf(
          stderr, "FS crc: %16llx len: %u\n",
          hash64(afl->fsrv.shmem_fuzz, *afl->fsrv.shmem_fuzz_len, HASH_CONST),
          *afl->fsrv.shmem_fuzz_len);
      fprintf(stderr, "SHM :");
      for (u32 i = 0; i < *afl->fsrv.shmem_fuzz_len; i++)
        fprintf(stderr, "%02x", afl->fsrv.shmem_fuzz[i]);
      fprintf(stderr, "\nORIG:");
      for (u32 i = 0; i < *afl->fsrv.shmem_fuzz_len; i++)
        fprintf(stderr, "%02x", (u8)((u8 *)mem)[i]);
      fprintf(stderr, "\n");

    }

#endif

    return;

  } else if (unlikely(!afl->fsrv.use_stdin)) {

    if (unlikely(afl->no_unlink)) {

      fd = open(afl->fsrv.out_file, O_WRONLY | O_CREAT | O_TRUNC, afl->perm);

    } else {

      unlink(afl->fsrv.out_file);                         /* Ignore errors. */
      fd = open(afl->fsrv.out_file, O_WRONLY | O_CREAT | O_EXCL, afl->perm);

    }

    if (fd < 0) { PFATAL("Unable to create '%s'", afl->fsrv.out_file); }

    if (afl->chown_needed) {

      if (fchown(fd, -1, afl->fsrv.gid) == -1) { PFATAL("fchown() failed"); }

    }

  } else {

    lseek(fd, 0, SEEK_SET);

  }

  if (!post_process_skipped) {

    ck_write(fd, new_mem, new_size, afl->fsrv.out_file);

  } else {

    ck_write(fd, mem, skip_at, afl->fsrv.out_file);

    ck_write(fd, mem + skip_at + skip_len, tail_len, afl->fsrv.out_file);

  }

  if (afl->fsrv.use_stdin) {

    if (ftruncate(fd, new_size)) { PFATAL("ftruncate() failed"); }
    lseek(fd, 0, SEEK_SET);

  } else {

    close(fd);

  }

}

/* Calibrate a new test case. This is done when processing the input directory
   to warn about flaky or otherwise problematic test cases early on; and when
   new paths are discovered to detect variable behavior and so on. */

u8 calibrate_case(afl_state_t *afl, struct queue_entry *q, u8 *use_mem,
                  u32 handicap, u8 from_queue) {

  u8 fault = 0, new_bits = 0, var_detected = 0, hnb = 0,
     first_run = (q->exec_cksum == 0);
  u64 start_us, stop_us, diff_us;
  s32 old_sc = afl->stage_cur, old_sm = afl->stage_max;
  u32 use_tmout = afl->fsrv.exec_tmout;
  u8 *old_sn = afl->stage_name;

  u64 calibration_start_us = get_cur_time_us();
  if (unlikely(afl->shm.cmplog_mode)) { q->exec_cksum = 0; }

  /* Be a bit more generous about timeouts when resuming sessions, or when
     trying to calibrate already-added finds. This helps avoid trouble due
     to intermittent latency. */

  if (!from_queue || afl->resuming_fuzz) {

    use_tmout = MAX(afl->fsrv.exec_tmout + CAL_TMOUT_ADD,
                    afl->fsrv.exec_tmout * CAL_TMOUT_PERC / 100);

  }

  ++q->cal_failed;

  afl->stage_name = "calibration";
  afl->stage_max = afl->afl_env.afl_cal_fast ? CAL_CYCLES_FAST : CAL_CYCLES;

  /* Make sure the forkserver is up before we do anything, and let's not
     count its spin-up time toward binary calibration. */

  if (!afl->fsrv.fsrv_pid) {

    if (afl->fsrv.cmplog_binary &&
        afl->fsrv.init_child_func != cmplog_exec_child) {

      FATAL("BUG in afl-fuzz detected. Cmplog mode not set correctly.");

    }

    afl_fsrv_start(&afl->fsrv, afl->argv, &afl->stop_soon,
                   afl->afl_env.afl_debug_child);

    if (afl->fsrv.support_shmem_fuzz && !afl->fsrv.use_shmem_fuzz) {

      afl_shm_deinit(afl->shm_fuzz);
      ck_free(afl->shm_fuzz);
      afl->shm_fuzz = NULL;
      afl->fsrv.support_shmem_fuzz = 0;
      afl->fsrv.shmem_fuzz = NULL;

    }

  }

  u8 saved_afl_post_process_keep_original =
      afl->afl_env.afl_post_process_keep_original;
  afl->afl_env.afl_post_process_keep_original = 1;

  /* we need a dummy run if this is LTO + cmplog */
  /*
    if (unlikely(afl->shm.cmplog_mode)) {

      (void)write_to_testcase(afl, (void **)&use_mem, q->len, 1);

      fault = fuzz_run_target(afl, &afl->fsrv, use_tmout);

      // afl->stop_soon is set by the handler for Ctrl+C. When it's pressed,
      // we want to bail out quickly.

      if (afl->stop_soon || fault != afl->crash_mode) { goto abort_calibration;

  }

      if (!afl->non_instrumented_mode &&
          !count_bytes(afl, afl->fsrv.trace_bits)) {

        fault = FSRV_RUN_NOINST;
        goto abort_calibration;

      }

  #ifdef INTROSPECTION
      if (unlikely(!q->bitsmap_size)) { q->bitsmap_size = afl->bitsmap_size; }
  #endif

    }

  */

  if (q->exec_cksum) {

    memcpy(afl->first_trace, afl->fsrv.trace_bits, afl->fsrv.map_size);
    hnb = has_new_bits(afl, afl->virgin_bits);
    if (unlikely(hnb > new_bits)) { new_bits = hnb; }

  }

  start_us = get_cur_time_us();

  for (afl->stage_cur = 0; afl->stage_cur < afl->stage_max; ++afl->stage_cur) {

    if (unlikely(afl->debug)) {

      DEBUGF("calibration stage %d/%d\n", afl->stage_cur + 1, afl->stage_max);

    }

    u64 cksum;

    (void)write_to_testcase(afl, (void **)&use_mem, q->len, 1);

    fault = fuzz_run_target(afl, &afl->fsrv, use_tmout);

    // update the time spend in calibration after each execution, as those may
    // be slow
    update_calibration_time(afl, &calibration_start_us);

    /* afl->stop_soon is set by the handler for Ctrl+C. When it's pressed,
       we want to bail out quickly. */

    if (afl->stop_soon || fault != afl->crash_mode) { goto abort_calibration; }

    if (!afl->non_instrumented_mode &&
        !count_bytes(afl, afl->fsrv.trace_bits)) {

      fault = FSRV_RUN_NOINST;
      goto abort_calibration;

    }

#ifdef INTROSPECTION
    if (unlikely(!q->bitsmap_size)) { q->bitsmap_size = afl->bitsmap_size; }
#endif

    classify_counts(&afl->fsrv);
    cksum = hash64(afl->fsrv.trace_bits, afl->fsrv.map_size, HASH_CONST);

    if (unlikely(q->exec_cksum != cksum)) {

      hnb = has_new_bits(afl, afl->virgin_bits);

      if (unlikely(hnb > new_bits)) { new_bits = hnb; }

      if (likely(q->exec_cksum)) {

        u32 i;

        for (i = 0; i < afl->fsrv.map_size; ++i) {

          if (unlikely(!afl->var_bytes[i]) &&
              unlikely(afl->first_trace[i] != afl->fsrv.trace_bits[i])) {

            afl->var_bytes[i] = 1;
            // ignore the variable edge by setting it to fully discovered
            afl->virgin_bits[i] = 0;

          }

        }

        if (unlikely(!var_detected && !afl->afl_env.afl_no_warn_instability)) {

          // note: from_queue seems to only be set during initialization
          if (afl->afl_env.afl_no_ui || from_queue) {

            WARNF("instability detected during calibration: %s", q->fname);

          } else if (afl->debug) {

            DEBUGF("instability detected during calibration: %s\n", q->fname);

          }

        }

        var_detected = 1;
        afl->stage_max =
            afl->afl_env.afl_cal_fast ? CAL_CYCLES : CAL_CYCLES_LONG;

      } else {

        q->exec_cksum = cksum;
        memcpy(afl->first_trace, afl->fsrv.trace_bits, afl->fsrv.map_size);

      }

    }

  }

  if (unlikely(afl->fixed_seed)) {

    diff_us = (u64)(afl->fsrv.exec_tmout - 1) * (u64)afl->stage_max;

  } else {

    stop_us = get_cur_time_us();
    diff_us = stop_us - start_us;
    if (unlikely(!diff_us)) { ++diff_us; }

  }

  afl->total_cal_us += diff_us;
  afl->total_cal_cycles += afl->stage_max;

  /* OK, let's collect some stats about the performance of this test case.
     This is used for fuzzing air time calculations in calculate_score(). */

  if (unlikely(!afl->stage_max)) {

    // Pretty sure this cannot happen, yet scan-build complains.
    FATAL("BUG: stage_max should not be 0 here! Please report this condition.");

  }

  q->exec_us = diff_us / afl->stage_max;
  if (unlikely(!q->exec_us)) { q->exec_us = 1; }

  q->bitmap_size = count_bytes(afl, afl->fsrv.trace_bits);
  q->handicap = handicap;
  q->cal_failed = 0;

  afl->total_bitmap_size += q->bitmap_size;
  ++afl->total_bitmap_entries;

  update_bitmap_score(afl, q, true);

  /* If this case didn't result in new output from the instrumentation, tell
     parent. This is a non-critical problem, but something to warn the user
     about. */

  if (!afl->non_instrumented_mode && first_run && !fault && !new_bits) {

    fault = FSRV_RUN_NOBITS;

  }

abort_calibration:

  afl->afl_env.afl_post_process_keep_original =
      saved_afl_post_process_keep_original;

  if (new_bits == 2 && !q->has_new_cov) {

    q->has_new_cov = 1;
    ++afl->queued_with_cov;

  }

  /* Mark variable paths. */

  if (var_detected) {

    afl->var_byte_count = count_bytes(afl, afl->var_bytes);

    if (!q->var_behavior) { ++afl->queued_variable; }

  }

  afl->stage_name = old_sn;
  afl->stage_cur = old_sc;
  afl->stage_max = old_sm;

  if (!first_run) { show_stats(afl); }

  update_calibration_time(afl, &calibration_start_us);
  return fault;

}

/* Do not sync items that were synced from us */

static bool is_known_case(afl_state_t *afl, u8 *name) {

  static char coming_from_me_str[SYNC_ID_MAX_LEN + 2];
  static u32  coming_from_me_len = 0;
  static u32  min_len = 15 + 4 + 6;

  if (!coming_from_me_len) {

    snprintf(coming_from_me_str, sizeof(coming_from_me_str), "%s,",
             afl->sync_id);
    min_len += coming_from_me_len = strlen(coming_from_me_str);

  }

  // file name length long enough so it can be ours
  if (unlikely(strlen(name) < min_len)) { return false; }
  // is it based on a sync? allow optimizer to make an integer comparison
  if (likely(memcmp(name + 10, "sync", 4) != 0)) { return false; }
  // we jump over the ':' after 'sync' and compare to our sync name
  if (unlikely(memcmp(name + 15, coming_from_me_str, coming_from_me_len) !=
               0)) {

    return false;

  }

  /* We do not need this as we now look on startup how many files are in sync
     targets.
  int src_id = atoi(name + 15 + coming_from_me_len + 4);
  if (unlikely(src_id >= afl->queued_items)) return false;
  */

  // yes it is highly likely a current testcase we already know
  return true;

}

/* Write into .sync/INSTANCE.max how many queue files were there on startup */

void check_sync_fuzzers(afl_state_t *afl) {

  if (unlikely(afl->afl_env.afl_no_sync)) { return; }

  DIR           *sd, *dir;
  struct dirent *sd_ent, *entry;
  u8  qd_path[PATH_MAX], qd_synced_maxid[PATH_MAX], qd_main_path[PATH_MAX];
  int have_main = afl->is_main_node;

  sd = opendir(afl->sync_dir);
  if (!sd) { PFATAL("Unable to open '%s'", afl->sync_dir); }

  u64 sync_start_us = get_cur_time_us();
  // Look at the entries created for every other fuzzer in the sync directory.

  while ((sd_ent = readdir(sd))) {

    if (sd_ent->d_name[0] == '.' || !strcmp(afl->sync_id, sd_ent->d_name)) {

      continue;

    }

    sprintf(qd_path, "%s/%s/queue", afl->sync_dir, sd_ent->d_name);

    dir = opendir(qd_path);
    if (dir) {

      u32 max_start_id = 0;
      while ((entry = readdir(dir)) != NULL) {

        if (likely(entry->d_name[0] != '.')) { max_start_id++; }

      }

      if (max_start_id) {

        sprintf(qd_synced_maxid, "%s/.synced/%s.max", afl->out_dir,
                sd_ent->d_name);
        s32 max_fd = open(qd_synced_maxid, O_WRONLY | O_CREAT | O_TRUNC,
                          DEFAULT_PERMISSION);

        if (max_fd >= 0) {

          --max_start_id;  // counting from 0
          if (unlikely(write(max_fd, &max_start_id, sizeof(u32)) !=
                       sizeof(u32))) {

            /* Ignore write failure - sync will continue */

          }

          close(max_fd);

        }

      }

      closedir(dir);

    }

    if (!have_main) {

      sprintf(qd_main_path, "%s/%s/is_main_node", afl->sync_dir,
              sd_ent->d_name);
      if (access(qd_main_path, F_OK) == 0) { have_main = 1; }

    }

  }

  closedir(sd);

  if (!have_main) {

    afl->is_main_node = 1;
    sprintf(qd_path, "%s/is_main_node", afl->out_dir);
    int id_fd = open(qd_main_path, O_RDWR | O_CREAT, afl->perm);
    if (id_fd >= 0) { close(id_fd); }

  }

  update_sync_time(afl, &sync_start_us);

}

/* Grab interesting test cases from other fuzzers. */

void sync_fuzzers(afl_state_t *afl) {

  if (unlikely(afl->afl_env.afl_no_sync)) { return; }

  DIR           *sd;
  struct dirent *sd_ent;
  u32            sync_cnt = 0, synced = 0, entries = 0;
  u8             path[PATH_MAX + 1 + NAME_MAX];

  sd = opendir(afl->sync_dir);
  if (!sd) { PFATAL("Unable to open '%s'", afl->sync_dir); }

  afl->stage_max = afl->stage_cur = 0;
  afl->cur_depth = 0;

  u64 sync_start_us = get_cur_time_us();
  // Look at the entries created for every other fuzzer in the sync directory.

  while ((sd_ent = readdir(sd))) {

    // since sync can take substantial amounts of time, update time spend every
    // iteration
    update_sync_time(afl, &sync_start_us);

    u8  qd_synced_path[PATH_MAX], qd_path[PATH_MAX], qd_synced_maxid[PATH_MAX];
    u32 min_accept = 0, next_min_accept = 0, max_start_id = 0;
    s32 id_fd;

    // Skip dot files and our own output directory.

    if (unlikely(sd_ent->d_name[0] == '.' ||
                 !strcmp(afl->sync_id, sd_ent->d_name))) {

      continue;

    }

    entries++;

    // secondary nodes only syncs from main, the main node syncs from everyone
    if (likely(afl->is_secondary_node)) {

      sprintf(qd_path, "%s/%s/is_main_node", afl->sync_dir, sd_ent->d_name);
      int res = access(qd_path, F_OK);
      if (unlikely(afl->is_main_node)) {  // an elected temporary main node

        if (likely(res == 0)) {  // there is another main node? downgrade.

          afl->is_main_node = 0;
          sprintf(qd_path, "%s/is_main_node", afl->out_dir);
          unlink(qd_path);

        }

      } else {

        if (likely(res != 0)) { continue; }

      }

    }

    synced++;

    // Skip anything that doesn't have a queue/ subdirectory.

    sprintf(qd_path, "%s/%s/queue", afl->sync_dir, sd_ent->d_name);

    struct dirent **namelist = NULL;
    int             m = 0, n, o;

    n = scandir(qd_path, &namelist, NULL, alphasort);

    if (n < 1) {

      if (namelist) free(namelist);
      continue;

    }

    // Retrieve the ID of the last seen test case.

    sprintf(qd_synced_path, "%s/.synced/%s", afl->out_dir, sd_ent->d_name);

    id_fd = open(qd_synced_path, O_RDWR | O_CREAT, afl->perm);

    if (id_fd < 0) { PFATAL("Unable to create '%s'", qd_synced_path); }

    if (afl->chown_needed) {

      if (fchown(id_fd, -1, afl->fsrv.gid) == -1) { PFATAL("fchown() failed"); }

    }

    if (read(id_fd, &min_accept, sizeof(u32)) == sizeof(u32)) {

      next_min_accept = min_accept;
      lseek(id_fd, 0, SEEK_SET);

    }

    // now document the attempt to sync to this instance
    sprintf(qd_synced_path, "%s/.synced/%s.last", afl->out_dir, sd_ent->d_name);
    int id_fd2 =
        open(qd_synced_path, O_RDWR | O_CREAT | O_TRUNC, DEFAULT_PERMISSION);
    if (id_fd2 >= 0) close(id_fd2);

    // It could be that the target syncing instance was restarted, check!
    time_t      last_mtime = 0;
    char        id0[PATH_MAX];
    struct stat st;

    if (stat(qd_synced_path, &st) == 0) { last_mtime = st.st_mtime; }

    snprintf(id0, sizeof(id0), "%s/%s/cmdline", afl->sync_dir, sd_ent->d_name);

    if (likely(stat(id0, &st) == 0)) {

      if (unlikely(last_mtime && last_mtime <= st.st_mtime)) {

        // the first entry is newer than when we synced last - instance was
        // restarted - we have to reset our counter and will skip this instance
        // this time. It could also be this was trimmed later, or restated with
        // resume-in-place though but better be safe.
        min_accept = 0;
        ck_write(id_fd, &min_accept, sizeof(u32), qd_synced_path);
        goto close_sync;

      }

    }  // else { This is likely a non-AFL++ but compliant instance, e.g. SymCC }

    // check if there is a file documented the maximum id seen on startup
    sprintf(qd_synced_maxid, "%s/.synced/%s.max", afl->out_dir, sd_ent->d_name);
    s32 max_fd = open(qd_synced_maxid, O_RDONLY, DEFAULT_PERMISSION);

    if (likely(max_fd >= 0)) {

      if (unlikely(read(max_fd, &max_start_id, sizeof(u32)) != sizeof(u32))) {

        /* Use default value on read failure */
        max_start_id = 0;

      }

      close(max_fd);
      if (max_start_id < next_min_accept) { unlink(qd_synced_maxid); }

    }

    /* Show stats */

    snprintf(afl->stage_name_buf, STAGE_BUF_SIZE, "sync %u", ++sync_cnt);

    afl->stage_name = afl->stage_name_buf;
    afl->stage_cur = 0;
    afl->stage_max = 0;

    show_stats(afl);

    /* For every file queued by this fuzzer, parse ID and see if we have
       looked at it before; exec a test case if not. */

    u8 entry[12];
    sprintf(entry, "id:%06u", next_min_accept);

    while (m < n) {

      if (strncmp(namelist[m]->d_name, entry, 9)) {

        m++;

      } else {

        break;

      }

    }

    if (m >= n) { goto close_sync; }  // nothing new

    for (o = m; o < n; o++) {

      s32         fd;
      struct stat st;

      snprintf(path, sizeof(path), "%s/%s", qd_path, namelist[o]->d_name);
      afl->syncing_case = next_min_accept;
      next_min_accept++;

      /* Allow this to fail in case the other fuzzer is resuming or so... */

      fd = open(path, O_RDONLY);

      if (fd < 0) { continue; }

      if (fstat(fd, &st)) { WARNF("fstat() failed"); }

      /* Ignore zero-sized or oversized files. */

      if (st.st_size && st.st_size <= MAX_FILE) {

        if (likely(next_min_accept < max_start_id ||
                   !is_known_case(afl, namelist[o]->d_name))) {

          /* See what happens. We rely on save_if_interesting() to catch major
             errors and save the test case. */

          u8 *mem = mmap(0, st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);

          if (mem == MAP_FAILED) { PFATAL("Unable to mmap '%s'", path); }

          u32 new_len = write_to_testcase(afl, (void **)&mem, st.st_size, 1);

          u8 fault = fuzz_run_target(afl, &afl->fsrv, afl->fsrv.exec_tmout);

          if (afl->stop_soon) {

            munmap(mem, st.st_size);
            close(fd);

            goto close_sync;

          }

          afl->syncing_party = sd_ent->d_name;
          afl->queued_imported += save_if_interesting(afl, mem, new_len, fault);
          show_stats(afl);
          afl->syncing_party = 0;
          munmap(mem, st.st_size);

        }

      }

      close(fd);

    }

    ck_write(id_fd, &next_min_accept, sizeof(u32), qd_synced_path);

  close_sync:
    close(id_fd);
    if (n > 0)
      for (m = 0; m < n; m++)
        free(namelist[m]);
    free(namelist);

  }

  closedir(sd);

  // If we are a secondary and no main was found to sync then become the main
  if (unlikely(synced == 0) && likely(entries) &&
      likely(afl->is_secondary_node)) {

    // there is a small race condition here that another secondary runs at the
    // same time. If so, the first temporary main node running again will demote
    // themselves so this is not an issue

    //    u8 path2[PATH_MAX];
    afl->is_main_node = 1;
    sprintf(path, "%s/is_main_node", afl->out_dir);
    int fd = open(path, O_CREAT | O_RDWR, 0644);
    if (fd >= 0) { close(fd); }

  }

  if (afl->foreign_sync_cnt) read_foreign_testcases(afl, 0);

  // add time in sync one last time
  update_sync_time(afl, &sync_start_us);

  afl->last_sync_time = get_cur_time();
  afl->last_sync_cycle = afl->queue_cycle;

}

/* Trim all new test cases to save cycles when doing deterministic checks. The
   trimmer uses power-of-two increments somewhere between 1/16 and 1/1024 of
   file size, to keep the stage short and sweet. */

u8 trim_case(afl_state_t *afl, struct queue_entry *q, u8 *in_buf) {

  u8  needs_write = 0, fault = 0;
  u32 orig_len = q->len;
  u64 trim_start_us = get_cur_time_us();
  afl->bytes_trim_in += orig_len;

  /* Custom mutator trimmer */
  if (afl->custom_mutators_count) {

    u8   trimmed_case = 0;
    bool custom_trimmed = false;

    LIST_FOREACH(&afl->custom_mutator_list, struct custom_mutator, {

      if (el->afl_custom_trim) {

        trimmed_case = trim_case_custom(afl, q, in_buf, el);
        custom_trimmed = true;

      }

    });

    if (orig_len != q->len || custom_trimmed) {

      queue_testcase_retake(afl, q, orig_len);

    }

    if (custom_trimmed) {

      fault = trimmed_case;
      goto abort_trimming;

    }

  }

  u32 trim_exec = 0;
  u32 remove_len;
  u32 len_p2;

  u8 val_bufs[2][STRINGIFY_VAL_SIZE_MAX];

  /* Although the trimmer will be less useful when variable behavior is
     detected, it will still work to some extent, so we don't check for
     this. */

  if (unlikely(q->len < 5)) {

    fault = 0;
    goto abort_trimming;

  }

  afl->stage_name = afl->stage_name_buf;

  /* Select initial chunk len, starting with large steps. */

  len_p2 = next_pow2(q->len);

  remove_len = MAX(len_p2 / TRIM_START_STEPS, (u32)TRIM_MIN_BYTES);

  /* Continue until the number of steps gets too high or the stepover
     gets too small. */

  while (remove_len >= MAX(len_p2 / TRIM_END_STEPS, (u32)TRIM_MIN_BYTES)) {

    u32 remove_pos = remove_len;

    sprintf(afl->stage_name_buf, "trim %s/%s",
            u_stringify_int(val_bufs[0], remove_len),
            u_stringify_int(val_bufs[1], remove_len));

    afl->stage_cur = 0;
    afl->stage_max = q->len / remove_len;

    while (remove_pos < q->len) {

      u32 trim_avail = MIN(remove_len, q->len - remove_pos);
      u64 cksum;

      write_with_gap(afl, in_buf, q->len, remove_pos, trim_avail);

      /* --- NV 2.4 validity filter in trim loop --- */
      if (afl->nv_task.enable_validity) {

        nv_vreason_t vr = nv_validity_check(afl, in_buf, q->len);

        if (unlikely(nv_v_is_reject(vr))) {

          nv_account_invalid(afl, vr);

          continue; /* skip this trim attempt */

        }

        nv_account_valid(afl);

      }

      fault = fuzz_run_target(afl, &afl->fsrv, afl->fsrv.exec_tmout);

      update_trim_time(afl, &trim_start_us);

      /* If the deletion had no impact on the trace, make it permanent. This
         isn't perfect for variable-path inputs, but we're just making a
         best-effort pass, so it's not a big deal if we end up with false
         negatives every now and then. */

      if (cksum == q->exec_cksum) {

        u32 move_tail = q->len - remove_pos - trim_avail;

        q->len -= trim_avail;
        len_p2 = next_pow2(q->len);

        memmove(in_buf + remove_pos, in_buf + remove_pos + trim_avail,
                move_tail);

        /* Let's save a clean trace, which will be needed by
           update_bitmap_score once we're done with the trimming stuff. */
        if (!needs_write) {

          needs_write = 1;
          memcpy(afl->clean_trace, afl->fsrv.trace_bits, afl->fsrv.map_size);

        }

      } else {

        remove_pos += remove_len;

      }

      /* Since this can be slow, update the screen every now and then. */
      if (!(trim_exec++ % afl->stats_update_freq)) { show_stats(afl); }
      ++afl->stage_cur;

    }

    remove_len >>= 1;

  }

  /* If we have made changes to in_buf, we also need to update the on-disk
     version of the test case. */

  if (needs_write) {

    // run afl_custom_post_process

    if (unlikely(afl->custom_mutators_count) &&
        likely(!afl->afl_env.afl_post_process_keep_original)) {

      ssize_t new_size = q->len;
      u8     *new_mem = in_buf;
      u8     *new_buf = NULL;

      LIST_FOREACH(&afl->custom_mutator_list, struct custom_mutator, {

        if (el->afl_custom_post_process) {

          new_size = el->afl_custom_post_process(el->data, new_mem, new_size,
                                                 &new_buf);

          if (unlikely(!new_buf || new_size <= 0)) {

            new_size = 0;
            new_buf = new_mem;

          } else {

            new_mem = new_buf;

          }

        }

      });

      if (unlikely(!new_size)) {

        new_size = q->len;
        new_mem = in_buf;

      }

      if (unlikely(new_size < afl->min_length)) {

        new_size = afl->min_length;

      } else if (unlikely(new_size > afl->max_length)) {

        new_size = afl->max_length;

      }

      q->len = new_size;

      if (new_mem != in_buf && new_mem != NULL) {

        new_buf = afl_realloc(AFL_BUF_PARAM(out_scratch), new_size);
        if (unlikely(!new_buf)) { PFATAL("alloc"); }
        memcpy(new_buf, new_mem, new_size);

        in_buf = new_buf;

      }

    }

    s32 fd;

    if (unlikely(afl->no_unlink)) {

      fd = open(q->fname, O_WRONLY | O_CREAT | O_TRUNC, afl->perm);

      if (fd < 0) { PFATAL("Unable to create '%s'", q->fname); }

      u32 written = 0;
      while (written < q->len) {

        ssize_t result = write(fd, in_buf, q->len - written);
        if (result > 0) written += result;

      }

    } else {

      unlink(q->fname);                                    /* ignore errors */
      fd = open(q->fname, O_WRONLY | O_CREAT | O_EXCL, afl->perm);

      if (fd < 0) { PFATAL("Unable to create '%s'", q->fname); }

      ck_write(fd, in_buf, q->len, q->fname);

    }

    if (afl->chown_needed) {

      if (fchown(fd, -1, afl->fsrv.gid) == -1) { PFATAL("fchown() failed"); }

    }

    close(fd);

    queue_testcase_retake_mem(afl, q, in_buf, q->len, orig_len);

    memcpy(afl->fsrv.trace_bits, afl->clean_trace, afl->fsrv.map_size);
    update_bitmap_score(afl, q, true);

  }

abort_trimming:
  afl->bytes_trim_out += q->len;
  update_trim_time(afl, &trim_start_us);

  return fault;

}

/* Write a modified test case, run program, process results. Handle
   error conditions, returning 1 if it's time to bail out. This is
   a helper function for fuzz_one(). */

u8 __attribute__((hot)) common_fuzz_stuff(afl_state_t *afl, u8 *out_buf,
                                          u32 len) {

  u8 fault;

  if (unlikely(len = write_to_testcase(afl, (void **)&out_buf, len, 0)) == 0) {

    afl->nv_mab.pending_update = 0;
    afl->nv_mab.update_source = 0;
    return 0;

  }

  /* --- NV 2.4 validity filter: skip invalid before exec --- */
  if (afl->nv_task.enable_validity) {

    nv_vreason_t vr = nv_validity_check(afl, out_buf, len);

    if (unlikely(nv_v_is_reject(vr))) {

      nv_account_invalid(afl, vr);

      afl->nv_mab.pending_update = 0;
      afl->nv_mab.update_source = 0;
      return 0; /* skip execution, but do NOT bail out */

    }

    nv_account_valid(afl);

  }

  fault = fuzz_run_target(afl, &afl->fsrv, afl->fsrv.exec_tmout);

  /* Snapshot the security state of *this* execution before anything else can
     run the target again.  save_if_interesting() calls calibrate_case(), which
     re-executes the same input several times and overwrites the single status
     document; reading afterwards scored the mutation against the calibration
     run instead of its own.  The reward is applied further down, but only ever
     from this snapshot. */
  nv_state_obs_t obs;
  {

    /* Resolved once: this sits on the per-execution hot path.  The value is
       *copied* rather than caching getenv()'s pointer -- afl-fuzz-one.c calls
       setenv("NV_CUR_ARM") on every custom-mutator iteration, and POSIX allows
       that to invalidate a pointer returned by an earlier getenv().  Runtime
       mutation of NV_STATUS_PATH itself is not supported; the path is fixed
       for the lifetime of the process. */
    static const char *sp = NULL;
    if (unlikely(!sp)) {

      const char *env = getenv("NV_STATUS_PATH");
      sp = env ? (const char *)ck_strdup((u8 *)env) : "/tmp/nv_http_status.json";

    }

    nv_observe_security_state(afl, sp, &obs);

  }

  if (afl->stop_soon) {
    afl->nv_mab.pending_update = 0;
    afl->nv_mab.update_source = 0;
    return 1;
  }

  if (fault == FSRV_RUN_TMOUT) {

    if (afl->subseq_tmouts++ > TMOUT_LIMIT) {

      ++afl->cur_skipped_items;
      afl->nv_mab.pending_update = 0;
      afl->nv_mab.update_source = 0;
      return 1;

    }

  } else {

    afl->subseq_tmouts = 0;

  }

  /* Users can hit us with SIGUSR1 to request the current input
     to be abandoned. */

  if (afl->skip_requested) {

    afl->skip_requested = 0;
    ++afl->cur_skipped_items;
    afl->nv_mab.pending_update = 0;
    afl->nv_mab.update_source = 0;
    return 1;

  }

  /* This handles FAULT_ERROR for us: */

  afl->queued_discovered += save_if_interesting(afl, out_buf, len, fault);

  /* Hand the snapshot taken above to the bandit.  State accounting already
     happened for every execution -- the seed-scheduling loop must not depend
     on whether a bandit arm produced this input -- so only the reward
     hand-off is gated on pending_update. */
  if (afl->nv_mab.pending_update) {

    nv_arm_id_t reward_arm = afl->nv_mab.pending_arm;
    afl->nv_mab.pending_update = 0;
    afl->nv_mab.update_source = 0;

    afl->nv_sec_state_reward_src_seq = obs.exec_seq;
    nv_mab_update(&afl->nv_mab, reward_arm, nv_reward_from_obs(&obs));

  }
  if (!(afl->stage_cur % afl->stats_update_freq) ||
      afl->stage_cur + 1 == afl->stage_max) {

    show_stats(afl);

  }

  return 0;

}
