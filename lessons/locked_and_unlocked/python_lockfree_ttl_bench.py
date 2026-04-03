"""Lock-free TTL cache benchmark sketch inspired by ttl_cache_bench_lockfree.c.

Python에선 진짜 lock-free CAS 를 제공하지 않으므로, 아주 얇은 compare-and-swap
래퍼를 threading.Lock 으로 시뮬레이션했으며 알고리즘 플로우(낙관적 삽입,
재구성 기반 정리, 뜨거운 키 분포 등)만 재현한다.
"""

import math
import os
import random
import threading
import time
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class Config:
    num_workers: int = max(4, os.cpu_count() or 1)
    duration_sec: float = 5.0
    key_space: int = 1 << 18
    hot_key_space: int = 1 << 14
    hot_ratio_pct: int = 90
    ttl_ms: int = 750
    table_pow: int = 17
    cleanup_scan: int = 512
    value_size: int = 128
    get_ratio: float = 0.9
    set_ratio: float = 0.09
    delete_ratio: float = 0.01


cfg = Config()


class AtomicRef:
    def __init__(self) -> None:
        self._ptr = None
        self._lock = threading.Lock()

    def load(self):
        return self._ptr

    def compare_and_swap(self, old, new) -> bool:
        with self._lock:
            if self._ptr is old:
                self._ptr = new
                return True
            return False


class Node:
    __slots__ = ("key", "expire", "value", "next")

    def __init__(self, key: int, expire_ns: int, value: bytes, next_node: Optional["Node"]):
        self.key = key
        self.expire = expire_ns
        self.value = value
        self.next: Optional[Node] = next_node


class LockFreeCache:
    def __init__(self, pow_bits: int, ttl_ns: int) -> None:
        self.mask = (1 << pow_bits) - 1
        self.buckets: List[AtomicRef] = [AtomicRef() for _ in range(1 << pow_bits)]
        self.ttl_ns = ttl_ns
        self.cursor = 0
        self.cursor_lock = threading.Lock()

    def _bucket(self, key: int) -> AtomicRef:
        return self.buckets[key & self.mask]

    def get(self, key: int, now_ns: int, stats) -> bool:
        node = self._bucket(key).load()
        while node is not None:
            if node.key == key:
                if node.expire >= now_ns:
                    stats.incr("hits")
                    return True
                stats.incr("expired")
                return False
            node = node.next
        stats.incr("misses")
        return False

    def set(self, key: int, value: bytes, now_ns: int, stats) -> None:
        entry = Node(key, now_ns + self.ttl_ns, value, None)
        bucket = self._bucket(key)
        while True:
            head = bucket.load()
            entry.next = head
            if bucket.compare_and_swap(head, entry):
                stats.incr("sets")
                return

    def delete(self, key: int, stats) -> None:
        tombstone = Node(key, 0, b"", None)
        bucket = self._bucket(key)
        while True:
            head = bucket.load()
            tombstone.next = head
            if bucket.compare_and_swap(head, tombstone):
                stats.incr("deletes")
                return

    def cleanup(self, scan: int, now_ns: int, stats) -> None:
        for _ in range(scan):
            with self.cursor_lock:
                idx = self.cursor & self.mask
                self.cursor += 1
            bucket = self.buckets[idx]
            head = bucket.load()
            if head is None:
                continue
            rebuilt, changed = rebuild_chain(head, now_ns)
            if not changed:
                continue
            while True:
                if bucket.compare_and_swap(head, rebuilt):
                    stats.incr("cleanups")
                    break
                head = bucket.load()
                rebuilt, changed = rebuild_chain(head, now_ns)
                if not changed:
                    break


def rebuild_chain(head: Node, now_ns: int):
    keep: List[Node] = []
    changed = False
    node = head
    while node is not None:
        if node.expire >= now_ns and node.expire != 0:
            keep.append(node)
        else:
            changed = True
        node = node.next
    if not changed:
        return head, False
    new_head: Optional[Node] = None
    for item in keep:
        clone = Node(item.key, item.expire, item.value, new_head)
        new_head = clone
    return new_head, True


class Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters = {
            "ops": 0,
            "hits": 0,
            "misses": 0,
            "expired": 0,
            "sets": 0,
            "deletes": 0,
            "cleanups": 0,
        }

    def incr(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self):
        with self._lock:
            return dict(self._counters)


def sample_key(rng: random.Random) -> int:
    if rng.randint(1, 100) <= cfg.hot_ratio_pct:
        return rng.randrange(cfg.hot_key_space)
    return cfg.hot_key_space + rng.randrange(cfg.key_space - cfg.hot_key_space)


def random_value(rng: random.Random) -> bytes:
    return bytes(rng.randint(48, 122) for _ in range(cfg.value_size))


def worker(idx: int, cache: LockFreeCache, stats: Stats, stop: threading.Event) -> None:
    rng = random.Random(time.time_ns() + idx * 7919)
    while not stop.is_set():
        key = sample_key(rng)
        choice = rng.random()
        now = time.time_ns()
        if choice < cfg.get_ratio:
            cache.get(key, now, stats)
        elif choice < cfg.get_ratio + cfg.set_ratio:
            cache.set(key, random_value(rng), now, stats)
        else:
            cache.delete(key, stats)
        stats.incr("ops")


def start_cleaner(cache: LockFreeCache, stats: Stats, stop: threading.Event) -> threading.Thread:
    def _loop() -> None:
        while not stop.is_set():
            cache.cleanup(cfg.cleanup_scan, time.time_ns(), stats)
            stop.wait(0.05)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return thread


def main() -> None:
    print("lock-free TTL cache benchmark (Python example)")
    stats = Stats()
    cache = LockFreeCache(cfg.table_pow, cfg.ttl_ms * 1_000_000)
    stop = threading.Event()
    cleaner = start_cleaner(cache, stats, stop)

    workers = [
        threading.Thread(target=worker, args=(i, cache, stats, stop), daemon=True)
        for i in range(cfg.num_workers)
    ]
    for t in workers:
        t.start()

    time.sleep(cfg.duration_sec)
    stop.set()
    for t in workers:
        t.join()
    cleaner.join(timeout=0.1)

    snap = stats.snapshot()
    print("config:", asdict(cfg))
    print(
        "ops={ops} hits={hits} misses={misses} expired={expired} sets={sets} "
        "deletes={deletes} cleanups={cleanups}".format(**snap)
    )


if __name__ == "__main__":
    main()
