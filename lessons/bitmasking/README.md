# 1강: 비트마스킹(Bitmasking) 기초

비트마스킹은 정수의 각 비트를 독립적인 플래그로 간주해 여러 상태를 하나의 값으로 관리하는 기법입니다. 내부 자료구조의 메모리 사용량을 줄이고 분기 없는 연산으로 처리 속도를 높일 수 있어, 캐시 효율과 지연시간 측면에서도 이득을 줍니다.

## 학습 목표
- Set / Clear / Toggle / Check 연산을 비트 단위로 구현하기
- 권한 플래그, 상태 머신 등에 적용되는 패턴 이해
- Go, C++, Python 3, C 네 언어의 비트 연산 문법 비교

## 폴더 구성
- `bitmasking.go`
- `bitmasking.cpp`
- `bitmasking.py`
- `bitmasking.c`

각 예제는 동일한 권한 플래그 시나리오(READ/WRITE/EXECUTE)를 사용하여 아래 연산을 수행합니다.
1. 여러 권한을 한 번에 Set
2. 특정 권한 토글/해제
3. 비트 연산을 통해 권한을 확인하고 결과를 출력

## 실행 방법 예시
```bash
(cd ../../.. && go run ./locked_and_unlocked/lessons/bitmasking/bitmasking.go)
(c++ -std=c++17 -O2 locked_and_unlocked/lessons/bitmasking/bitmasking.cpp -o /tmp/bmask && /tmp/bmask)
python3 locked_and_unlocked/lessons/bitmasking/bitmasking.py
(gcc -O2 locked_and_unlocked/lessons/bitmasking/bitmasking.c -o /tmp/bmask_c && /tmp/bmask_c)
```

> **확장 과제:** 플래그 변수를 `std::atomic<uint32_t>` 또는 Go의 `atomic.Uint32`와 결합하면 락-프리 상태 토글기를 만들 수 있습니다.
