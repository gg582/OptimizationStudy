# 1강: L1 Cache Hit Rate 이해와 실습

CPU의 L1 데이터 캐시는 코어 바로 옆에 있는 32~64KB 크기의 초고속 메모리입니다. 동일한 데이터를 반복적으로 접근하거나 인접한 데이터를 순차적으로 읽으면 **히트(hit)**가 늘어나고, 캐시에 없는 주소를 건드리면 **미스(miss)**가 발생합니다. `Hit Rate = Hits / (Hits + Misses)`로 계산하며, 값이 높을수록 메모리 계층을 효율적으로 사용하고 있다는 의미가 됩니다.

## 학습 목표
- 공간/시간 지역성을 높이는 데이터 접근 패턴 이해
- `perf stat -e L1-dcache-loads,L1-dcache-load-misses`와 같은 하드웨어 카운터로 히트율 관찰
- 동일한 알고리즘을 Go, C++, Python 3, C로 옮기면서 언어별 메모리 접근을 비교

## 폴더 구성
- `l1_cache_hit_rate.go`
- `l1_cache_hit_rate.cpp`
- `l1_cache_hit_rate.py`
- `l1_cache_hit_rate.c`

각 파일은 **두 가지 루프 패턴**을 번갈아 실행합니다.
1. `step=1` – 배열을 순차 접근하여 높은 L1 hit rate 유도
2. `step=64` – 64개의 `int64`를 건너뛰어 캐시 미스를 늘리고 실행 시간이 크게 증가하는지 확인

## 실행 방법 예시
```bash
# Go
(cd ../../.. && go run ./locked_and_unlocked/lessons/l1_cache_hit_rate/l1_cache_hit_rate.go)

# C++
(c++ -std=c++17 -O2 locked_and_unlocked/lessons/l1_cache_hit_rate/l1_cache_hit_rate.cpp -lpthread -o /tmp/l1 && /tmp/l1)

# Python
python3 locked_and_unlocked/lessons/l1_cache_hit_rate/l1_cache_hit_rate.py

# C
gcc -O2 locked_and_unlocked/lessons/l1_cache_hit_rate/l1_cache_hit_rate.c -o /tmp/l1c && /tmp/l1c
```

> **실험 팁:** 위 실행 명령 앞에 `perf stat -e L1-dcache-loads,L1-dcache-load-misses`를 붙이면 히트/미스 카운터를 수집할 수 있습니다.
