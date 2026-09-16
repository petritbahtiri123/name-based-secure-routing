#define _GNU_SOURCE
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static unsigned long private_kib(void) {
    FILE *f = fopen("/proc/self/smaps_rollup", "r");
    if (!f) exit(2);
    char line[256];
    unsigned long total = 0, n;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "Private_Clean: %lu kB", &n) == 1 ||
            sscanf(line, "Private_Dirty: %lu kB", &n) == 1) total += n;
    }
    if (ferror(f) || fclose(f)) exit(3);
    return total;
}
static void sample(const char *mode, const char *phase, size_t owned) {
    struct timespec a, b;
    if (clock_gettime(CLOCK_MONOTONIC, &a)) exit(4);
    struct mallinfo2 m = mallinfo2();
    if (clock_gettime(CLOCK_MONOTONIC, &b)) exit(4);
    long long ns = (b.tv_sec-a.tv_sec)*1000000000LL + b.tv_nsec-a.tv_nsec;
    unsigned long resident = private_kib();
    printf("{\"mode\":\"%s\",\"phase\":\"%s\",\"owned_requested_bytes\":%zu,"
           "\"arena\":%zu,\"uordblks\":%zu,\"fordblks\":%zu,\"hblkhd\":%zu,"
           "\"hblks\":%zu,\"keepcost\":%zu,\"private_bytes\":%lu,\"mallinfo2_ns\":%lld}\n",
           mode,phase,owned,m.arena,m.uordblks,m.fordblks,m.hblkhd,m.hblks,m.keepcost,resident*1024,ns);
}
int main(int argc, char **argv) {
    if (argc != 2 || (strcmp(argv[1],"large") && strcmp(argv[1],"small"))) return 1;
    setvbuf(stdout,NULL,_IONBF,0);
    (void)private_kib();
    (void)mallinfo2();
    const int large = !strcmp(argv[1],"large");
    const size_t count = large ? 1 : 16384;
    const size_t bytes = large ? 3014656 : 64;
    void *blocks[16384];
    sample(argv[1],"baseline",0);
    for (size_t i=0;i<count;i++) {
        blocks[i]=calloc(1,bytes);
        if (!blocks[i]) return 5;
    }
    sample(argv[1],"allocated",count*bytes);
    long page=sysconf(_SC_PAGESIZE);
    if (page<=0) return 6;
    for (size_t i=0;i<count;i++) {
        volatile unsigned char *p=blocks[i];
        size_t limit=large && bytes>(size_t)page*100 ? (size_t)page*100 : bytes;
        for (size_t j=0;j<limit;j+=(size_t)page) p[j]=1;
    }
    sample(argv[1],"partial_touch",count*bytes);
    for (size_t i=0;i<count;i++) {
        volatile unsigned char *p=blocks[i];
        for (size_t j=0;j<bytes;j+=(size_t)page) p[j]=2;
        p[bytes-1]=2;
    }
    sample(argv[1],"full_touch",count*bytes);
    for (size_t i=0;i<count;i++) free(blocks[i]);
    sample(argv[1],"freed",0);
    struct timespec wait = {.tv_sec=1,.tv_nsec=0};
    if (nanosleep(&wait,NULL)) return 7;
    sample(argv[1],"cooldown",0);
    return 0;
}
