#include <stdint.h>
#include <stdio.h>

enum Permission {
    PERM_READ = 1u << 0,
    PERM_WRITE = 1u << 1,
    PERM_EXEC = 1u << 2,
};

int main(void) {
    uint32_t perm = 0;
    perm |= PERM_READ | PERM_WRITE;
    printf("Set READ+WRITE -> 0x%X\n", perm);

    perm &= ~PERM_WRITE;
    printf("Clear WRITE -> 0x%X\n", perm);

    perm ^= PERM_EXEC;
    printf("Toggle EXEC -> 0x%X\n", perm);

    printf("Readable? %d\n", (perm & PERM_READ) != 0);
    printf("Writable? %d\n", (perm & PERM_WRITE) != 0);
    printf("Executable? %d\n", (perm & PERM_EXEC) != 0);
    return 0;
}
