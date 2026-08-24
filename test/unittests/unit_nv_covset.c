/*
   Deterministic unit tests for the NV security-state coverage set.

   Built and executed by tests/test_nv_covset_unit.py, which imposes a wall
   clock timeout: case 3 drives the table to saturation, and the defect this
   suite guards against is a probe loop that never returns.  The binary
   therefore flushes each result as it goes, so a hang is still diagnosable
   from the partial output.

   Links only src/afl-fuzz-nv-covset.c -- no fuzzer runtime required.
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

  fflush(stdout);

}

#define CAP 8u

/* Hashes are never 0 in production (nv_fnv1a64 folds 0 to 1) because 0 is the
   empty-slot sentinel, so the fixtures avoid it too. */
static u64 state_id(u32 n) { return 0x9E3779B97F4A7C15ULL * (u64)(n + 1); }

int main(void) {

  u64 slots[CAP];
  u32 used = 0;
  memset(slots, 0, sizeof(slots));

  /* ---- Case 1: fill every slot ---- */
  int all_inserted = 1;
  for (u32 n = 0; n < CAP; ++n) {

    if (nv_covset_insert_into(slots, CAP, &used, state_id(n)) !=
        NV_COVSET_INSERTED) {

      all_inserted = 0;

    }

  }

  expect(all_inserted && used == CAP, "fill_reports_every_slot_inserted",
         "expected %u insertions, used=%u", CAP, used);

  /* Snapshot so case 3 can prove a dropped state overwrites nothing. */
  u64 snapshot[CAP];
  memcpy(snapshot, slots, sizeof(slots));

  /* ---- Case 2: a state already present must resolve without probing on ---- */
  int r_dup = nv_covset_insert_into(slots, CAP, &used, state_id(3));
  expect(r_dup == NV_COVSET_EXISTING && used == CAP,
         "full_table_finds_existing_state",
         "expected EXISTING(%d) and used=%u, got %d and used=%u",
         NV_COVSET_EXISTING, CAP, r_dup, used);

  /* ---- Case 3: the defect.  A brand new state against a full table ---- */
  printf("PROBE saturating_insert_start\n");
  fflush(stdout);

  int r_sat = nv_covset_insert_into(slots, CAP, &used, state_id(999));

  printf("PROBE saturating_insert_returned rc=%d\n", r_sat);
  fflush(stdout);

  expect(r_sat == NV_COVSET_SATURATED, "full_table_reports_saturation",
         "expected SATURATED(%d), got %d", NV_COVSET_SATURATED, r_sat);

  expect(used == CAP, "saturated_insert_does_not_bump_used",
         "used moved from %u to %u", CAP, used);

  expect(memcmp(snapshot, slots, sizeof(slots)) == 0,
         "saturated_insert_evicts_nothing",
         "a dropped state overwrote an existing entry");

  /* ---- The table must stay usable after saturation ---- */
  int r_after = nv_covset_insert_into(slots, CAP, &used, state_id(5));
  expect(r_after == NV_COVSET_EXISTING, "lookup_still_works_after_saturation",
         "expected EXISTING(%d) after a saturated insert, got %d",
         NV_COVSET_EXISTING, r_after);

  /* ---- Freeing a slot must make the table accept new states again ---- */
  u32 freed = 0;
  for (u32 i = 0; i < CAP; ++i) {

    if (slots[i] == state_id(2)) { slots[i] = 0; used--; freed = 1; break; }

  }

  if (freed) {

    int r_reuse = nv_covset_insert_into(slots, CAP, &used, state_id(1000));
    expect(r_reuse == NV_COVSET_INSERTED, "space_reclaimed_accepts_new_state",
           "expected INSERTED(%d) once a slot was free, got %d",
           NV_COVSET_INSERTED, r_reuse);

  }

  /* ================= M-1C: the state key must be bounded ================= */

  /* METHOD collapses to a finite verb set. */
  expect(strcmp(nv_canon_method("get"), "GET") == 0 &&
             strcmp(nv_canon_method("  PoSt "), "POST") == 0,
         "method_is_canonicalised",
         "got '%s' and '%s'", nv_canon_method("get"),
         nv_canon_method("  PoSt "));

  expect(strcmp(nv_canon_method("AAAA1"), "INVALID") == 0 &&
             strcmp(nv_canon_method("AAAA2"), "INVALID") == 0 &&
             strcmp(nv_canon_method(""), "INVALID") == 0 &&
             strcmp(nv_canon_method(NULL), "INVALID") == 0,
         "unknown_methods_collapse_to_one_token",
         "fuzz bytes in the method must not create new states");

  /* RESPONSE_CLASS collapses to a finite set. */
  expect(strcmp(nv_canon_class("2xx"), "2xx") == 0 &&
             strcmp(nv_canon_class("conn_refused"), "conn_refused") == 0 &&
             strcmp(nv_canon_class("timeout"), "timeout") == 0,
         "known_classes_survive",
         "a known response class was rewritten");

  expect(strcmp(nv_canon_class("9xx"), "other") == 0 &&
             strcmp(nv_canon_class("zzz"), "other") == 0 &&
             strcmp(nv_canon_class(NULL), "other") == 0,
         "unknown_classes_collapse_to_other",
         "got '%s'", nv_canon_class("9xx"));

  /* PATH: structurally invalid shapes collapse to one label. */
  expect(nv_canon_path_label("/api/doc/list") == NULL,
         "wellformed_path_is_passed_through",
         "a normal path was relabelled");

  expect(nv_canon_path_label(NULL) != NULL &&
             nv_canon_path_label("") != NULL &&
             nv_canon_path_label("no-leading-slash") != NULL,
         "malformed_paths_are_labelled",
         "a malformed path was passed through unchanged");

  {

    /* An over-long path is the cardinality bomb: without a cap, every fuzzed
       byte string becomes its own security state. */
    char longp[NV_STATE_PATH_MAX + 64];
    longp[0] = '/';
    memset(longp + 1, 'A', sizeof(longp) - 2);
    longp[sizeof(longp) - 1] = 0;

    expect(nv_canon_path_label(longp) != NULL,
           "overlong_path_is_labelled",
           "a %zu-char path was accepted verbatim", strlen(longp));

    /* split so "\x02" cannot swallow the following hex-looking characters */
    char ctrl[] = "/api/\x01" "\x02" "bad";
    expect(nv_canon_path_label(ctrl) != NULL,
           "nonprintable_path_is_labelled",
           "a path with control bytes was accepted verbatim");

  }

  /* All labels must come from the same finite pool, so a million distinct
     malformed paths still produce exactly one state. */
  expect(nv_canon_path_label("bad-one") == nv_canon_path_label("bad-two"),
         "malformed_paths_share_one_label",
         "distinct malformed paths produced distinct labels");

  /* ============ M-3: replay identity is the execution, not content ========= */
  {

    u64 last_seq = 0, last_stamp = 0;

    /* Test A: the same execution's document offered twice. */
    int a1 = nv_status_is_fresh(100, 0xAAAA, &last_seq, &last_stamp);
    int a2 = nv_status_is_fresh(100, 0xAAAA, &last_seq, &last_stamp);
    expect(a1 == NV_STATUS_ACCEPT && a2 == NV_STATUS_REPLAY,
           "same_execution_consumed_twice_is_a_replay",
           "expected ACCEPT then REPLAY, got %d then %d", a1, a2);

    /* Test B: a *different* execution that happens to look identical.  Two
       real requests can legitimately produce the same body and the same
       response in the same millisecond; only one of them being counted was
       the over-rejection defect. */
    int b = nv_status_is_fresh(101, 0xAAAA, &last_seq, &last_stamp);
    expect(b == NV_STATUS_ACCEPT,
           "identical_content_from_a_new_execution_is_accepted",
           "a distinct execution with identical content was dropped as a "
           "replay (rc=%d)", b);

    /* Test C1: no execution id at all -- fall back to content identity so
       older harnesses keep working. */
    u64 l2 = 0, s2 = 0;
    int c1 = nv_status_is_fresh(0, 0x1234, &l2, &s2);
    int c2 = nv_status_is_fresh(0, 0x1234, &l2, &s2);
    int c3 = nv_status_is_fresh(0, 0x5678, &l2, &s2);
    expect(c1 == NV_STATUS_ACCEPT && c2 == NV_STATUS_REPLAY &&
               c3 == NV_STATUS_ACCEPT,
           "legacy_stamp_fallback_still_works",
           "expected ACCEPT/REPLAY/ACCEPT, got %d/%d/%d", c1, c2, c3);

    /* Test C2: exec_seq is a monotonic identity.  A lower value after a
       higher one is stale evidence, not a counter-restart signal. */
    u64 l3 = 5000, s3 = 0;
    int d1 = nv_status_is_fresh(1, 0x1, &l3, &s3);
    expect(d1 == NV_STATUS_REPLAY && l3 == 5000,
           "stale_sequence_is_replay_and_preserves_high_water_mark",
           "expected REPLAY and last=5000, got %d and last=%llu", d1,
           (unsigned long long)l3);

    int d2 = nv_status_is_fresh(5001, 0x2, &l3, &s3);
    expect(d2 == NV_STATUS_ACCEPT && l3 == 5001,
           "newer_sequence_after_stale_is_accepted",
           "expected ACCEPT and last=5001, got %d and last=%llu", d2,
           (unsigned long long)l3);

    int d3 = nv_status_is_fresh(5001, 0x2, &l3, &s3);
    expect(d3 == NV_STATUS_REPLAY, "accepted_sequence_replay_is_rejected",
           "expected REPLAY, got %d", d3);

  }

  printf("FAILURES %d\n", g_failures);
  fflush(stdout);
  return g_failures ? 1 : 0;

}
