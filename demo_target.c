// demo_target.c
// AFL-friendly demo target: many branches + structured parsing + controlled crash/timeout.
// Input: stdin (recommended), but also supports @@ file via AFL's default behavior.

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t rotl32(uint32_t x, int r) { return (x << r) | (x >> (32 - r)); }

// Simple hash to create branchy behavior
static uint32_t mix_hash(const uint8_t *p, size_t n) {
  uint32_t h = 0x811C9DC5u;
  for (size_t i = 0; i < n; ++i) {
    h ^= p[i];
    h *= 0x01000193u;
    h = rotl32(h, (int)(p[i] & 31));
  }
  return h;
}

static int read_all_stdin(uint8_t *buf, size_t cap, size_t *out_len) {
  size_t n = fread(buf, 1, cap, stdin);
  *out_len = n;
  return 0;
}

int main(void) {

  uint8_t buf[4096];
  size_t  len = 0;
  read_all_stdin(buf, sizeof(buf), &len);

  if (len < 4) return 0;

  // ---- Layer 1: magic header branches
  if (buf[0] == 'A' && buf[1] == 'F' && buf[2] == 'L') {
    // AFL...
  } else if (buf[0] == 0x7F && buf[1] == 'E' && buf[2] == 'L' && buf[3] == 'F') {
    // looks like ELF
  } else if (buf[0] == 'P' && buf[1] == 'K') {
    // zip-like
  } else if (buf[0] == '{' || buf[0] == '[') {
    // json-like
  } else {
    // random
  }

  // ---- Layer 2: structured TLV-ish parsing
  // Format: [tag][length][payload...], repeated
  size_t i = 0;
  uint32_t score = 0;
  while (i + 2 <= len) {
    uint8_t tag = buf[i++];
    uint8_t l   = buf[i++];

    if (i + l > len) break; // truncated

    const uint8_t *p = &buf[i];
    uint32_t h = mix_hash(p, l);

    // Many small branches
    switch (tag & 0x0F) {
      case 0x0: score ^= (h & 0xFF); break;
      case 0x1: score += (h & 0x3FF); break;
      case 0x2: score = rotl32(score, 3) ^ h; break;
      case 0x3: score = (score * 33u) + (h ^ 0xA5A5A5A5u); break;
      case 0x4: if ((h & 7u) == 0) score ^= 0xDEADBEEFu; break;
      case 0x5: if ((h & 0xFFu) == 0x42u) score += 0x1337u; break;
      case 0x6: if (l > 8 && p[0] == 'X' && p[1] == 'Y') score ^= 0xCAFEBABEu; break;
      case 0x7: if (l == 0) score ^= 0x0u; break;
      case 0x8: score ^= (uint32_t)(p[0] << 24); break;
      case 0x9: score += (uint32_t)(p[l - 1]); break;
      case 0xA: if ((tag & 0xF0) == 0xA0) score ^= 0xAAAA5555u; break;
      case 0xB: if ((tag & 0xF0) == 0xB0) score ^= 0x12345678u; break;
      case 0xC: if ((tag & 0xF0) == 0xC0) score ^= 0x87654321u; break;
      case 0xD: score ^= (h >> 16); break;
      case 0xE: score += (h & 0xFFFFu); break;
      case 0xF: score ^= h; break;
      default: break;
    }

    // ---- Layer 3: deep comparisons to create gradual coverage
    if (l >= 4) {
      if (!memcmp(p, "PING", 4)) score ^= 0x11111111u;
      if (!memcmp(p, "PONG", 4)) score ^= 0x22222222u;
      if (!memcmp(p, "HELO", 4)) score ^= 0x33333333u;
      if (!memcmp(p, "AUTH", 4)) score ^= 0x44444444u;
      if (!memcmp(p, "DATA", 4)) score ^= 0x55555555u;
    }
    if (l >= 8) {
      if (!memcmp(p, "USERroot", 8)) score ^= 0xABCDEF01u;
      if (!memcmp(p, "PASS1234", 8)) score ^= 0x10FEDCBAu;
    }
    if (l >= 12) {
      if (!memcmp(p, "CMD:GET/FLAG", 12)) score ^= 0x0F0F0F0Fu;
    }

    // ---- Controlled timeout path (rare)
    if (l >= 3 && p[0] == 'S' && p[1] == 'L' && p[2] == 'O') {
      // spin a bit to simulate hang-ish behavior
      volatile uint32_t x = 0;
      for (uint32_t k = 0; k < 3000000u; ++k) x += (k ^ score);
      if (x == 0xFFFFFFFFu) putchar('!'); // keep compiler honest
    }

    // ---- Controlled crash paths (reachable but not too trivial)
    // 1) score-dependent crash
    if ((score ^ 0xA5A5A5A5u) == 0xDEADC0DEu) {
      *(volatile uint32_t *)0 = 0xDEAD; // SEGV
    }
    // 2) magic payload crash
    if (l >= 6 && !memcmp(p, "CRASH!", 6)) {
      abort();
    }

    i += l;
  }

  // Additional end-of-file condition branches
  if ((score & 0xFFu) == 0x7Fu) return 7;
  if ((score & 0xFFFu) == 0xBEEu) return 9;
  if ((score & 0xFFFFu) == 0xC0DEu) return 11;

  return 0;
}