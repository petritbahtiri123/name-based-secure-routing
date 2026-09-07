#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
int main(void) {
    size_t sizes[] = {1, 8192, 3014656};
    for (size_t n = 0; n < sizeof sizes / sizeof sizes[0]; ++n) {
        unsigned char *value = calloc(sizes[n], 1);
        assert(value);
        for (size_t i = 0; i < sizes[n]; ++i) assert(value[i] == 0);
        value[sizes[n]-1] = 7;
        free(value);
    }
    volatile size_t enormous = SIZE_MAX;
    errno = 0;
    assert(calloc(enormous, 2) == NULL);
    assert(errno == ENOMEM);
    puts("CALLOC_PASSTHROUGH_PASS");
}
