# Not a Part of libttak – TTL Cache Bench Examples

이 디렉토리는 libttak의 메모리 최적화 연구와는 무관하며, 리포지터리를 읽는 사람들이 `ttl_cache_bench.c`와 `ttl_cache_bench_lockfree.c`에서 사용하는 알고리즘의 개념을 이해할 수 있도록 참고용 예제 코드를 담고 있다. 코드는 Go, Python 3, C++17로 작성된 **잠금 기반(locked)** TTL 캐시 벤치마크와 **락-프리(lock-free)** TTL 캐시 벤치마크를 각각 흉내 내며, libttak의 API를 사용하지 않는다.

## 파일 구성

- `go_locked_ttl_bench.go` – 샤드별 뮤텍스를 사용하는 Go TTL 캐시 벤치마크
- `go_lockfree_ttl_bench.go` – `atomic.Pointer` 기반의 Go 락-프리 TTL 캐시 벤치마크
- `python_locked_ttl_bench.py` – 파이썬 스레드와 `threading.Lock`을 사용하는 잠금 기반 TTL 캐시 벤치마크
- `python_lockfree_ttl_bench.py` – 파이썬에서 단일 생산자-소비자 CAS 시뮬레이션을 흉내 낸 락-프리 TTL 캐시 벤치마크 (GIL 때문에 실제 lock-free 는 아니지만 알고리즘 플로우를 재현)
- `cpp_locked_ttl_bench.cpp` – C++17 `std::shared_mutex`를 사용하는 잠금 기반 TTL 캐시 벤치마크
- `cpp_lockfree_ttl_bench.cpp` – C++17 `std::atomic`과 단순 체인드 버킷을 이용한 락-프리 TTL 캐시 벤치마크

각 예제는 `--help` 없이도 기본 구성을 사용하여 약 5초 동안 워커 스레드를 실행하고 통계를 출력한다. 실험 목적에 따라 소스 코드 상단의 `Config` 구조체 값을 수정하면 된다.

## 실행 방법 예시

```bash
# locked Go 버전
(cd ../../.. && go run ./bench/ttl-cache-multithread-bench/not_a_part_of_libttak_mem_optimization_study/go_locked_ttl_bench.go)

# lock-free Python 버전
python3 bench/ttl-cache-multithread-bench/not_a_part_of_libttak_mem_optimization_study/python_lockfree_ttl_bench.py

# locked C++ 버전
c++ -std=c++17 -O2 bench/ttl-cache-multithread-bench/not_a_part_of_libttak_mem_optimization_study/cpp_locked_ttl_bench.cpp -lpthread -o /tmp/locked && /tmp/locked
```

> **주의:** 예제는 학습/설명용이며, libttak 빌드/벤치 파이프라인에는 사용되지 않는다.
