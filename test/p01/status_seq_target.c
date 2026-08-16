/* Deterministic instrumented target for P0.1 finding M-2.

   M-2 is a lifecycle ordering defect: common_fuzz_stuff() used to read the
   status document *after* save_if_interesting(), which re-executes the target
   through calibrate_case().  The observation consumed therefore belonged to
   the last calibration run rather than to the mutation that was being scored.

   This target makes the two distinguishable.  It remembers which inputs it
   has already seen, and reports a different security state on a repeat:

     first execution of an input  ->  path "/first"
     any later execution of it    ->  path "/repeat"

   Calibration only ever re-runs an input the fuzzer has already executed, so
   every calibration execution reports "/repeat".  A correct fuzzer consumes
   only "/first" observations and its covset therefore holds exactly one
   security state; a fuzzer that reads after calibration also records
   "/repeat" and ends up with two.

   The branch ladder exists so afl-clang-fast instrumentation yields new edges
   and save_if_interesting() actually reaches calibrate_case().

   ts_ms and body_hash16 are derived from the execution id so that every
   execution has a distinct legacy replay stamp.  That isolates this test from
   finding M-3: the point here is which observation is consumed, not how many.

   Not a platform target.  No network.  Not a real O2OA/Alfresco/Flowable
   service.
*/

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define MAX_SEEN 4096

static uint64_t fnv1a64(const unsigned char *p, size_t n) {

  uint64_t h = 1469598103934665603ULL;
  for (size_t i = 0; i < n; ++i) { h ^= p[i]; h *= 1099511628211ULL; }
  return h ? h : 1;

}

/* Sidecar files keep the target itself stateless between forks: the
   forkserver clones a fresh process every execution, so "have I seen this
   input" has to live outside the process image. */
static const char *env_or(const char *k, const char *d) {

  const char *v = getenv(k);
  return (v && *v) ? v : d;

}

/* Returns 1 the first time this hash is offered, 0 afterwards. */
static int claim_first_sighting(const char *path, uint64_t h) {

  uint64_t seen[MAX_SEEN];
  size_t   n = 0;

  FILE *f = fopen(path, "rb");
  if (f) {

    n = fread(seen, sizeof(uint64_t), MAX_SEEN, f);
    fclose(f);

  }

  for (size_t i = 0; i < n; ++i)
    if (seen[i] == h) return 0;

  if (n < MAX_SEEN) {

    f = fopen(path, "ab");
    if (f) { fwrite(&h, sizeof(h), 1, f); fclose(f); }

  }

  return 1;

}

/* Strictly increasing execution id, shared across forks. */
static uint64_t next_exec_seq(const char *path) {

  uint64_t seq = 0;
  FILE    *f = fopen(path, "rb");
  if (f) { if (fread(&seq, sizeof(seq), 1, f) != 1) seq = 0; fclose(f); }

  seq++;

  f = fopen(path, "wb");
  if (f) { fwrite(&seq, sizeof(seq), 1, f); fclose(f); }

  return seq;

}

int main(int argc, char **argv) {

  unsigned char buf[256];
  size_t        n = 0;

  if (argc > 1 && strcmp(argv[1], "-") != 0) {

    FILE *f = fopen(argv[1], "rb");
    if (!f) return 0;
    n = fread(buf, 1, sizeof(buf), f);
    fclose(f);

  } else {

    n = fread(buf, 1, sizeof(buf), stdin);

  }

  /* Branch ladder: gives AFL real edges to discover so that
     save_if_interesting() -> calibrate_case() is actually exercised. */
  int shape = 0;
  if (n >= 1 && buf[0] == 'A') {

    shape = 1;
    if (n >= 2 && buf[1] == 'B') {

      shape = 2;
      if (n >= 3 && buf[2] == 'C') {

        shape = 3;
        if (n >= 4 && buf[3] == 'D') { shape = 4; }

      }

    }

  } else if (n >= 1 && buf[0] == 'Z') {

    shape = 5;

  }

  const char *status = env_or("NV_STATUS_PATH", "/tmp/nv_http_status.json");
  const char *seenf  = env_or("NV_P01_SEEN_PATH", "/tmp/nv_p01_seen.bin");
  const char *seqf   = env_or("NV_P01_SEQ_PATH", "/tmp/nv_p01_seq.bin");
  const char *logf   = getenv("NV_P01_EXEC_LOG");

  uint64_t h     = fnv1a64(buf, n);
  uint64_t seq   = next_exec_seq(seqf);
  int      first = claim_first_sighting(seenf, h);

  const char *path = first ? "/first" : "/repeat";

  char tmp[1024];
  snprintf(tmp, sizeof(tmp), "%s.tmp", status);

  FILE *f = fopen(tmp, "w");
  if (f) {

    fprintf(f,
            "{\"method\":\"POST\",\"path\":\"%s\",\"http_code\":200,"
            "\"class\":\"2xx\",\"timeout\":0,\"recovered\":0,"
            "\"latency_ms\":0,\"body_hash16\":%u,\"ncov_delta\":0,"
            "\"ncov_total\":0,\"nall\":0,\"ts_ms\":%llu,\"is_exception\":0,"
            "\"recover_ms\":0,\"exec_seq\":%llu}\n",
            path,
            /* NV_P01_STATIC_STAMP pins the legacy identity fields so every
               execution looks byte-identical to the pre-exec_seq replay
               check.  That is the M-3 over-rejection scenario: distinct
               executions that the content stamp cannot tell apart. */
            getenv("NV_P01_STATIC_STAMP") ? 0u
                                          : (unsigned)((h ^ seq) & 0xFFFF),
            getenv("NV_P01_STATIC_STAMP")
                ? 1786000000000ULL
                : (unsigned long long)(1786000000000ULL + seq),
            (unsigned long long)seq);
    fclose(f);
    rename(tmp, status);

  }

  if (logf) {

    f = fopen(logf, "a");
    if (f) {

      fprintf(f,
              "{\"exec_seq\":%llu,\"path\":\"%s\",\"first\":%d,"
              "\"input_hash\":\"%llx\",\"shape\":%d}\n",
              (unsigned long long)seq, path, first,
              (unsigned long long)h, shape);
      fclose(f);

    }

  }

  return 0;

}
