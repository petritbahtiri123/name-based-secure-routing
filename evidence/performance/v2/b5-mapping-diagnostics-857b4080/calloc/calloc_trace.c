#define _GNU_SOURCE
#include <errno.h>
#include <execinfo.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

/* Isolated glibc diagnostic. Delegate allocation unchanged; trace large calloc
 * only. Never use this library for accepted capacity/soak measurements. */
extern void *__libc_calloc(size_t, size_t);
static _Thread_local int tracing;
void *calloc(size_t count, size_t size) {
    void *result = __libc_calloc(count, size);
    int saved_errno = errno;
    if (!tracing && result && size && count <= SIZE_MAX / size && count * size >= 1048576) {
        tracing = 1;
        const char *path = getenv("NBSR_CALLOC_TRACE");
        if (path) {
            int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
            if (fd >= 0) {
                char line[256];
                int length = snprintf(line, sizeof line, "CALLOC pid=%ld bytes=%zu pointer=%p\n", (long)getpid(), count * size, result);
                if (length > 0 && length < (int)sizeof line) {
                    (void)write(fd, line, (size_t)length);
                }
                void *stack[24];
                int frames = backtrace(stack, 24);
                backtrace_symbols_fd(stack, frames, fd);
                (void)close(fd);
            }
        }
        tracing = 0;
    }
    errno = saved_errno;
    return result;
}
