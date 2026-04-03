#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

enum { SIZE_BYTES = 1 << 20, STRIDE = 64 };

long measure(int step) {
    const size_t length = SIZE_BYTES / sizeof(int64_t);
    int64_t *data = calloc(length, sizeof(int64_t));
    if (!data) {
        perror("calloc");
        exit(1);
    }
    volatile int64_t sum = 0;
    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (size_t i = 0; i < length; i += step) {
        sum += data[i];
    }
    clock_gettime(CLOCK_MONOTONIC, &end);
    free(data);
    return (end.tv_sec - start.tv_sec) * 1000000000L +
           (end.tv_nsec - start.tv_nsec);
}

int main(void) {
    printf("Step=1   : %ld ns\n", measure(1));
    printf("Stride=%d: %ld ns\n", STRIDE, measure(STRIDE));
    return 0;
}
