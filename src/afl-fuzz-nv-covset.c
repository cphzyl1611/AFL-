/*
   american fuzzy lop++ - NV security-state coverage set
   ------------------------------------------------------

   The set of security states observed so far is an open-addressed table with
   linear probing.  It lives in its own translation unit so the probing logic
   can be driven to saturation by a unit test without linking the fuzzer or
   allocating the production-sized table.

 */

#include "afl-fuzz.h"

#include <ctype.h>
#include <string.h>

/* ---------------- security-state key canonicalisation ---------------- */

static const char *const NV_KNOWN_METHODS[] = {
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"};

static const char *const NV_KNOWN_CLASSES[] = {
    "2xx", "3xx", "4xx", "5xx", "conn_refused", "timeout"};

/* The single label every unusable path folds onto.  Returned by pointer so
   callers can compare identity, not just contents. */
static const char NV_PATH_MALFORMED[] = "malformed_path";

const char *nv_canon_method(const char *m) {

  if (!m) return "INVALID";

  while (*m && isspace((unsigned char)*m)) ++m;

  size_t n = strlen(m);
  while (n && isspace((unsigned char)m[n - 1])) --n;
  if (!n || n >= 16) return "INVALID";

  char up[16];
  for (size_t i = 0; i < n; ++i) up[i] = (char)toupper((unsigned char)m[i]);
  up[n] = 0;

  for (size_t i = 0; i < sizeof(NV_KNOWN_METHODS) / sizeof(*NV_KNOWN_METHODS);
       ++i) {

    if (strcmp(up, NV_KNOWN_METHODS[i]) == 0) return NV_KNOWN_METHODS[i];

  }

  return "INVALID";

}

const char *nv_canon_class(const char *c) {

  if (!c) return "other";

  for (size_t i = 0; i < sizeof(NV_KNOWN_CLASSES) / sizeof(*NV_KNOWN_CLASSES);
       ++i) {

    if (strcmp(c, NV_KNOWN_CLASSES[i]) == 0) return NV_KNOWN_CLASSES[i];

  }

  return "other";

}

const char *nv_canon_path_label(const char *p) {

  if (!p || p[0] != '/') return NV_PATH_MALFORMED;

  size_t n = strlen(p);
  if (n > NV_STATE_PATH_MAX) return NV_PATH_MALFORMED;

  for (size_t i = 0; i < n; ++i) {

    unsigned char ch = (unsigned char)p[i];
    if (ch < 0x20 || ch > 0x7e) return NV_PATH_MALFORMED;

  }

  return NULL;

}

/* ---------------------- status replay identity ---------------------- */

int nv_status_is_fresh(u64 exec_seq, u64 legacy_stamp, u64 *last_exec_seq,
                       u64 *last_stamp) {

  if (!last_exec_seq || !last_stamp) return NV_STATUS_ACCEPT;

  if (exec_seq) {

    /* exec_seq is a monotonic identity within one status namespace.  Equal
       ids are duplicate reads and lower ids are stale documents; neither may
       become a second fresh observation or move the high-water mark back. */
    if (exec_seq <= *last_exec_seq) return NV_STATUS_REPLAY;

    *last_exec_seq = exec_seq;
    return NV_STATUS_ACCEPT;

  }

  /* No execution id reported: fall back to content identity.  This cannot
     distinguish two identical-looking executions, which is exactly why
     exec_seq exists, but it preserves the historical behaviour. */
  if (legacy_stamp == *last_stamp) return NV_STATUS_REPLAY;

  *last_stamp = legacy_stamp;
  return NV_STATUS_ACCEPT;

}

/* ---------------------- observed-state coverage set ---------------------- */

int nv_covset_insert_into(u64 *slots, u32 cap, u32 *used, u64 h) {

  if (!slots || !cap || !used) return NV_COVSET_SATURATED;

  u32 mask = cap - 1;
  u32 i = (u32)h & mask;

  /* At most one sweep of the table.  Every slot is visited exactly once, so a
     present state is always found and an absent one is always decided; a full
     table reports saturation instead of probing forever. */
  for (u32 probe = 0; probe < cap; ++probe) {

    u64 cur = slots[i];
    if (!cur) { slots[i] = h; (*used)++; return NV_COVSET_INSERTED; }
    if (cur == h) return NV_COVSET_EXISTING;
    i = (i + 1) & mask;

  }

  return NV_COVSET_SATURATED;

}
