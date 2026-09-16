#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <malloc.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static pthread_t worker;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t wake;
static int started, stopping, output=-1;
static uint64_t nanos(struct timespec t) {
    return (uint64_t)t.tv_sec*1000000000ULL+(uint64_t)t.tv_nsec;
}
static void sample(const char *phase) {
    struct timespec a,b;
    if(clock_gettime(CLOCK_MONOTONIC,&a)) return;
    struct mallinfo2 m=mallinfo2();
    if(clock_gettime(CLOCK_MONOTONIC,&b)) return;
    char line[1024];
    int n=snprintf(line,sizeof line,
        "{\"schema\":\"nbsr-diagnostic-mallinfo2-v1\",\"pid\":%ld,\"phase\":\"%s\","
        "\"timestamp_ns\":%llu,\"end_ns\":%llu,\"arena\":%zu,\"ordblks\":%zu,"
        "\"smblks\":%zu,\"hblks\":%zu,\"hblkhd\":%zu,\"usmblks\":%zu,"
        "\"fsmblks\":%zu,\"uordblks\":%zu,\"fordblks\":%zu,\"keepcost\":%zu}\n",
        (long)getpid(),phase,(unsigned long long)nanos(a),(unsigned long long)nanos(b),
        m.arena,m.ordblks,m.smblks,m.hblks,m.hblkhd,m.usmblks,m.fsmblks,m.uordblks,m.fordblks,m.keepcost);
    if(n<=0 || n>=(int)sizeof line) return;
    size_t done=0;
    while(done<(size_t)n) {
        ssize_t wrote=write(output,line+done,(size_t)n-done);
        if(wrote<0 && errno==EINTR) continue;
        if(wrote<=0) return;
        done+=(size_t)wrote;
    }
}
static void *observe(void *unused) {
    (void)unused;
    for(;;) {
        sample("sample");
        struct timespec deadline;
        if(clock_gettime(CLOCK_MONOTONIC,&deadline)) break;
        deadline.tv_sec+=10;
        pthread_mutex_lock(&lock);
        int error=0;
        while(!stopping && !error) error=pthread_cond_timedwait(&wake,&lock,&deadline);
        int end=stopping || (error && error!=ETIMEDOUT);
        pthread_mutex_unlock(&lock);
        if(end) break;
    }
    return NULL;
}
__attribute__((constructor)) static void begin(void) {
    const char *dir=getenv("NBSR_ALLOCATOR_TRACE_DIR");
    if(!dir || !*dir) return;
    char exe[4096];
    ssize_t n=readlink("/proc/self/exe",exe,sizeof exe-1);
    if(n<=0 || n==(ssize_t)sizeof exe-1) return;
    exe[n]=0;
    const char *name=strrchr(exe,'/');
    name=name ? name+1 : exe;
    if(strcmp(name,"perf_rust_source") && strcmp(name,"wp8_interop_server")) return;
    char path[4096];
    int length=snprintf(path,sizeof path,"%s/%ld.ndjson",dir,(long)getpid());
    if(length<=0 || length>=(int)sizeof path) return;
    output=open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    if(output<0) return;
    pthread_condattr_t attr;
    if(pthread_condattr_init(&attr)) goto fail;
    int error=pthread_condattr_setclock(&attr,CLOCK_MONOTONIC);
    if(!error) error=pthread_cond_init(&wake,&attr);
    pthread_condattr_destroy(&attr);
    if(error) goto fail;
    if(pthread_create(&worker,NULL,observe,NULL)) {
        pthread_cond_destroy(&wake);
        goto fail;
    }
    started=1;
    return;
fail:
    close(output); output=-1;
}
__attribute__((destructor)) static void end(void) {
    if(!started) return;
    pthread_mutex_lock(&lock); stopping=1;
    pthread_cond_signal(&wake); pthread_mutex_unlock(&lock);
    pthread_join(worker,NULL);
    sample("final");
    close(output);
    pthread_cond_destroy(&wake);
}
