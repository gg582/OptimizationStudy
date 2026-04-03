"""Threaded TTL cache benchmark that mirrors ttl_cache_bench.c's locked version.

The code keeps the control flow simple so it can be used as a teaching aid.
"""

import os
import random
import threading
import time
from dataclasses import dataclass, asdict
from typing import Dict, Tuple


@dataclass
class Config:
    num_workers: int = max(4, os.cpu_count() or 1)
    duration_sec: float = 5.0
    value_size: int = 256
    key_space: int = 200_000
    hot_ratio_pct: int = 80
    ttl_ms: int = 500
    epoch_ms: int = 150
    get_ratio: float = 0.8
    set_ratio: float = 0.19
    delete_ratio: float = 0.01
    shards: int = 16


cfg = Config()


class Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {
            "ops": 0,
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "expiries": 0,
            "cleanup_ns": 0,
        }

    def incr(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counters)


class TTLCache:
    def __init__(self, shards: int, ttl_ms: int) -> None:
        self.ttl_ns = ttl_ms * 1_000_000
        self.shards = [
            {"lock": threading.Lock(), "items": {}}  # type: ignore[var-annotated]
            for _ in range(shards)
        ]

    def _shard(self, key: int) -> Dict:
        return self.shards[key % len(self.shards)]

    def get(self, key: int, now_ns: int, stats: Stats) -> bool:
        sh = self._shard(key)
        with sh["lock"]:
            item = sh["items"].get(key)
            if item is None:
                stats.incr("misses")
                return False
            expires_ns, _ = item
            if expires_ns < now_ns:
                del sh["items"][key]
                stats.incr("misses")
                stats.incr("expiries")
                return False
            stats.incr("hits")
            return True

    def set(self, key: int, value: bytes, now_ns: int, stats: Stats) -> None:
        sh = self._shard(key)
        expires = now_ns + self.ttl_ns
        with sh["lock"]:
            sh["items"][key] = (expires, value)
        stats.incr("sets")

    def delete(self, key: int, stats: Stats) -> None:
        sh = self._shard(key)
        with sh["lock"]:
            removed = sh["items"].pop(key, None) is not None
        if removed:
            stats.incr("deletes")

    def sweep(self, now_ns: int, stats: Stats) -> None:
        start = time.perf_counter_ns()
        removed = 0
        for sh in self.shards:
            with sh["lock"]:
                keys = list(sh["items"].keys())
                for k in keys:
                    expires, _ = sh["items"][k]
                    if expires < now_ns:
                        del sh["items"][k]
                        removed += 1
        if removed:
            stats.incr("expiries", removed)
        stats.incr("cleanup_ns", time.perf_counter_ns() - start)


def sample_key(rng: random.Random) -> int:
    if rng.randint(1, 100) <= cfg.hot_ratio_pct:
        return rng.randint(0, cfg.key_space // 5)
    return rng.randint(0, cfg.key_space)


def random_value(rng: random.Random) -> bytes:
    return bytes(rng.randint(97, 122) for _ in range(cfg.value_size))


def worker(idx: int, cache: TTLCache, stats: Stats, stop: threading.Event) -> None:
    rng = random.Random(time.time_ns() + idx * 1337)
    while not stop.is_set():
        key = sample_key(rng)
        op = rng.random()
        now_ns = time.time_ns()
        if op < cfg.get_ratio:
            cache.get(key, now_ns, stats)
        elif op < cfg.get_ratio + cfg.set_ratio:
            cache.set(key, random_value(rng), now_ns, stats)
        else:
            cache.delete(key, stats)
        stats.incr("ops")


def start_cleaner(cache: TTLCache, stats: Stats, stop: threading.Event) -> threading.Thread:
    def _loop() -> None:
        while not stop.is_set():
            cache.sweep(time.time_ns(), stats)
            stop.wait(cfg.epoch_ms / 1000.0)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


def main() -> None:
    print("locked TTL cache benchmark (Python example)")
    stats = Stats()
    cache = TTLCache(cfg.shards, cfg.ttl_ms)
    stop = threading.Event()
    cleaner = start_cleaner(cache, stats, stop)

    threads = [
        threading.Thread(target=worker, args=(i, cache, stats, stop), daemon=True)
        for i in range(cfg.num_workers)
    ]
    for t in threads:
        t.start()

    time.sleep(cfg.duration_sec)
    stop.set()
    for t in threads:
        t.join()
    cleaner.join(timeout=0.1)

    snap = stats.snapshot()
    print("config:", asdict(cfg))
    print(
        "ops={ops} hits={hits} misses={misses} sets={sets} deletes={deletes} "
        "expiries={expiries} cleanup_ns={cleanup_ns}".format(**snap)
    )


if __name__ == "__main__":
    main()
