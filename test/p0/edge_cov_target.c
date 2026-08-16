/* Minimal instrumented target for the AFL native edge-coverage wiring smoke.
   This exists only to show that AFL's bitmap feedback works in this build.
   It is NOT the project's security-state coverage metric. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {

  unsigned char buf[64];
  size_t n = 0;

  if (argc > 1) {
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 0;
    n = fread(buf, 1, sizeof(buf), f);
    fclose(f);
  } else {
    n = fread(buf, 1, sizeof(buf), stdin);
  }

  if (n < 4) return 0;

  if (buf[0] == 'P') {
    if (buf[1] == '0') {
      if (buf[2] == 'C') { if (buf[3] == 'V') return 3; }
      return 2;
    }
    return 1;
  }
  if (buf[0] == 'Z') { return 4; }
  return 0;

}
