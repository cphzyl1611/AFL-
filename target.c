#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char** argv){
  if(argc<2) return 0;
  FILE* f=fopen(argv[1],"rb");
  if(!f) return 0;
  char buf[4096]; size_t n=fread(buf,1,sizeof(buf)-1,f);
  fclose(f); buf[n]=0;
  if(n>3 && buf[0]=='A' && buf[1]=='F' && buf[2]=='L'){
    if(strstr(buf,"CRASH")){
      volatile int* p=(int*)0; *p=1;
    }
  }
  return 0;
}
