#include <chrono>
#include <iostream>
#include <vector>

constexpr std::size_t kSizeBytes = 1 << 20;
constexpr int kStride = 64;

template <int Step>
std::chrono::nanoseconds Measure() {
    std::vector<long long> data(kSizeBytes / sizeof(long long));
    volatile long long sum = 0;
    const auto start = std::chrono::steady_clock::now();
    for (std::size_t i = 0; i < data.size(); i += Step) {
        sum += data[i];
    }
    const auto end = std::chrono::steady_clock::now();
    return end - start;
}

int main() {
    const auto sequential = Measure<1>();
    const auto sparse = Measure<kStride>();
    std::cout << "Step=1 : " << sequential.count() << " ns\n";
    std::cout << "Stride=" << kStride << " : " << sparse.count() << " ns\n";
    return 0;
}
