#include <bitset>
#include <cstdint>
#include <iostream>

enum Permission : std::uint32_t {
    kRead = 1u << 0,
    kWrite = 1u << 1,
    kExecute = 1u << 2,
};

int main() {
    std::uint32_t perm = 0;
    perm |= kRead | kWrite;
    std::cout << "Set READ+WRITE -> " << std::bitset<3>(perm) << "\n";

    perm &= ~kWrite;
    std::cout << "Clear WRITE -> " << std::bitset<3>(perm) << "\n";

    const bool canExec = (perm & kExecute) != 0;
    std::cout << "Can execute? " << std::boolalpha << canExec << "\n";

    perm ^= kExecute;
    std::cout << "Toggle EXECUTE -> " << std::bitset<3>(perm) << "\n";
    return 0;
}
