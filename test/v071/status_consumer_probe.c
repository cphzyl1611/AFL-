/*
   v0.7.1 -- does the C replay consumer actually accept what the real HTTP
   harness now writes?

   Reads status documents produced by a real nv_http_harness.py execution and
   drives the production replay decision over them, in order.  The extraction
   below is a transcription of nv_observe_security_state() in
   src/afl-fuzz-run.c: same field names, same cJSON predicates, same legacy
   stamp construction, same call into nv_status_is_fresh().  If those ever
   diverge this probe is the thing that should be corrected.

   Links src/afl-fuzz-nv-covset.c (the real nv_status_is_fresh) and cJSON.
   No fuzzer runtime required.

   Usage: status_consumer_probe <status.json> [<status.json> ...]
   Prints one line per document: ACCEPT or REPLAY, with the parsed identity.
 */

#include "afl-fuzz.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/third_party/cjson/cJSON.h"

/* Replay state, exactly the two fields afl_state_t carries. */
static u64 g_last_exec_seq = 0;
static u64 g_last_stamp    = 0;

static char *slurp(const char *path) {

  FILE *fp = fopen(path, "rb");
  if (!fp) return NULL;

  fseek(fp, 0, SEEK_END);
  long sz = ftell(fp);
  fseek(fp, 0, SEEK_SET);
  if (sz <= 0 || sz > 65536) { fclose(fp); return NULL; }

  char *buf = malloc((size_t)sz + 1);
  if (!buf) { fclose(fp); return NULL; }

  if (fread(buf, 1, (size_t)sz, fp) != (size_t)sz) {

    free(buf);
    fclose(fp);
    return NULL;

  }

  buf[sz] = 0;
  fclose(fp);
  return buf;

}

static int consume(const char *path) {

  char *buf = slurp(path);
  if (!buf) { printf("ERROR unreadable %s\n", path); return 1; }

  cJSON *root = cJSON_Parse(buf);
  free(buf);
  if (!root) { printf("ERROR unparseable %s\n", path); return 1; }

  /* --- transcribed from nv_observe_security_state() --- */
  const cJSON *tsj = cJSON_GetObjectItemCaseSensitive(root, "ts_ms");
  const cJSON *bhj = cJSON_GetObjectItemCaseSensitive(root, "body_hash16");
  const cJSON *esj = cJSON_GetObjectItemCaseSensitive(root, "exec_seq");

  u64 exec_seq = (cJSON_IsNumber(esj) && esj->valuedouble > 0)
                     ? (u64)esj->valuedouble
                     : 0;

  u64 ts_ms       = cJSON_IsNumber(tsj) ? (u64)tsj->valuedouble : 0;
  u32 body_hash16 = cJSON_IsNumber(bhj) ? (u32)bhj->valuedouble : 0;

  u64 stamp = ts_ms ? (ts_ms ^ ((u64)body_hash16 << 32)) : 0;
  if (!stamp) stamp = 1;

  int fresh = nv_status_is_fresh(exec_seq, stamp, &g_last_exec_seq,
                                 &g_last_stamp);
  /* ---------------------------------------------------- */

  printf("%s exec_seq=%llu stamp=%llx identity=%s\n",
         fresh == NV_STATUS_ACCEPT ? "ACCEPT" : "REPLAY",
         (unsigned long long)exec_seq, (unsigned long long)stamp,
         exec_seq ? "exec_seq" : "legacy_stamp");
  fflush(stdout);

  cJSON_Delete(root);
  return 0;

}

int main(int argc, char **argv) {

  if (argc < 2) {

    fprintf(stderr, "usage: %s <status.json> [...]\n", argv[0]);
    return 2;

  }

  for (int i = 1; i < argc; ++i) {

    if (consume(argv[i])) return 1;

  }

  return 0;

}
