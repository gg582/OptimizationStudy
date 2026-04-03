import array
import time

SIZE_BYTES = 1 << 20
STRIDE = 64

def measure(step: int) -> int:
    data = array.array("l", [0]) * (SIZE_BYTES // 8)
    acc = 0
    start = time.perf_counter_ns()
    for i in range(0, len(data), step):
        acc += data[i]
    if acc == 42:
        print("impossible")
    return time.perf_counter_ns() - start

if __name__ == "__main__":
    print(f"Step=1   : {measure(1)} ns")
    print(f"Stride={STRIDE}: {measure(STRIDE)} ns")
