#include <unistd.h>
int main() {
  char b[4];
  int n = read(0, b, 4);
  if (n > 2 && b[0] == 'B' && b[1] == 'U' && b[2] == 'G') {
    *(volatile int*)0 = 0; // SIGSEGV
  }
  return 0;
}
