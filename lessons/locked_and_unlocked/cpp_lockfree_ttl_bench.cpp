#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <random>
#include <string>
#include <thread>
#include <utility>
#include <vector>

struct Config {
    int numThreads = std::thread::hardware_concurrency();
    int durationSec = 5;
    uint64_t keySpace = 1ull << 18;
    uint64_t hotKeySpace = 1ull << 14;
    int hotRatio = 90;
    std::chrono::nanoseconds ttl{750'000'000};
    unsigned tablePow = 17;
    size_t cleanupStride = 512;
    int valueSize = 128;
    double getRatio = 0.9;
    double setRatio = 0.09;
    double delRatio = 0.01;
};

static Config cfg;

struct Stats {
    std::atomic<uint64_t> ops{0};
    std::atomic<uint64_t> hits{0};
    std::atomic<uint64_t> misses{0};
    std::atomic<uint64_t> expired{0};
    std::atomic<uint64_t> sets{0};
    std::atomic<uint64_t> deletes{0};
    std::atomic<uint64_t> cleanups{0};
};

struct Node {
    uint64_t key;
    int64_t expire;
    std::string value;
    Node *next;
};

struct Bucket {
    std::atomic<Node *> head{nullptr};
};

class LockFreeCache {
  public:
    LockFreeCache(unsigned powBits, std::chrono::nanoseconds ttl)
        : ttl_(ttl.count()), mask_((1ull << powBits) - 1),
          buckets_(1ull << powBits) {}

    bool get(uint64_t key, int64_t now, Stats &stats) {
        Node *node = buckets_[index(key)].head.load(std::memory_order_acquire);
        while (node) {
            if (node->key == key) {
                if (node->expire >= now) {
                    stats.hits.fetch_add(1, std::memory_order_relaxed);
                    return true;
                }
                stats.expired.fetch_add(1, std::memory_order_relaxed);
                return false;
            }
            node = node->next;
        }
        stats.misses.fetch_add(1, std::memory_order_relaxed);
        return false;
    }

    void set(uint64_t key, std::string value, int64_t now, Stats &stats) {
        Node *entry = new Node{key, now + ttl_, std::move(value), nullptr};
        Bucket &bucket = buckets_[index(key)];
        Node *head = bucket.head.load(std::memory_order_relaxed);
        do {
            entry->next = head;
        } while (!bucket.head.compare_exchange_weak(
            head, entry, std::memory_order_release, std::memory_order_relaxed));
        stats.sets.fetch_add(1, std::memory_order_relaxed);
    }

    void erase(uint64_t key, Stats &stats) {
        Node *tomb = new Node{key, 0, std::string{}, nullptr};
        Bucket &bucket = buckets_[index(key)];
        Node *head = bucket.head.load(std::memory_order_relaxed);
        do {
            tomb->next = head;
        } while (!bucket.head.compare_exchange_weak(
            head, tomb, std::memory_order_release, std::memory_order_relaxed));
        stats.deletes.fetch_add(1, std::memory_order_relaxed);
    }

    void cleanup(size_t scan, int64_t now, Stats &stats) {
        for (size_t i = 0; i < scan; ++i) {
            uint64_t idx = cursor_.fetch_add(1, std::memory_order_relaxed) & mask_;
            Bucket &bucket = buckets_[idx];
            Node *head = bucket.head.load(std::memory_order_acquire);
            if (!head) {
                continue;
            }
            auto rebuilt = rebuildChain(head, now);
            if (!rebuilt.second) {
                continue;
            }
            while (true) {
                if (bucket.head.compare_exchange_weak(
                        head, rebuilt.first, std::memory_order_release,
                        std::memory_order_relaxed)) {
                    stats.cleanups.fetch_add(1, std::memory_order_relaxed);
                    break;
                }
                rebuilt = rebuildChain(head, now);
                if (!rebuilt.second) {
                    break;
                }
            }
        }
    }

  private:
    inline uint64_t index(uint64_t key) const { return key & mask_; }

    static std::pair<Node *, bool> rebuildChain(Node *head, int64_t now) {
        std::vector<Node *> keep;
        bool changed = false;
        for (Node *node = head; node; node = node->next) {
            if (node->expire >= now && node->expire != 0) {
                keep.push_back(node);
            } else {
                changed = true;
            }
        }
        if (!changed) {
            return {head, false};
        }
        Node *newHead = nullptr;
        for (Node *node : keep) {
            Node *clone = new Node{node->key, node->expire, node->value, newHead};
            newHead = clone;
        }
        return {newHead, true};
    }

    int64_t ttl_;
    uint64_t mask_;
    std::vector<Bucket> buckets_;
    std::atomic<uint64_t> cursor_{0};
};

static inline int64_t nowNs() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

static uint64_t sampleKey(std::mt19937_64 &rng) {
    std::uniform_int_distribution<uint64_t> hot(0, cfg.hotKeySpace - 1);
    std::uniform_int_distribution<uint64_t> cold(0, cfg.keySpace - 1);
    std::uniform_int_distribution<int> perc(1, 100);
    return perc(rng) <= cfg.hotRatio ? hot(rng) : cold(rng);
}

static std::string randValue(std::mt19937_64 &rng) {
    std::string value(cfg.valueSize, '\0');
    std::uniform_int_distribution<int> printable('0', 'z');
    for (char &c : value) {
        c = static_cast<char>(printable(rng));
    }
    return value;
}

static void worker(int id, LockFreeCache &cache, Stats &stats,
                   std::atomic<bool> &running) {
    std::mt19937_64 rng(
        static_cast<uint64_t>(std::chrono::high_resolution_clock::now()
                                  .time_since_epoch()
                                  .count()) +
        id * 7919);
    std::uniform_real_distribution<double> unit(0.0, 1.0);
    while (running.load(std::memory_order_acquire)) {
        uint64_t key = sampleKey(rng);
        double op = unit(rng);
        int64_t ts = nowNs();
        if (op < cfg.getRatio) {
            cache.get(key, ts, stats);
        } else if (op < cfg.getRatio + cfg.setRatio) {
            cache.set(key, randValue(rng), ts, stats);
        } else {
            cache.erase(key, stats);
        }
        stats.ops.fetch_add(1, std::memory_order_relaxed);
    }
}

int main() {
    std::cout << "lock-free TTL cache benchmark (C++ example)\n";
    LockFreeCache cache(cfg.tablePow, cfg.ttl);
    Stats stats;
    std::atomic<bool> running{true};

    std::thread cleaner([&] {
        while (running.load(std::memory_order_acquire)) {
            cache.cleanup(cfg.cleanupStride, nowNs(), stats);
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    });

    std::vector<std::thread> threads;
    for (int i = 0; i < cfg.numThreads; ++i) {
        threads.emplace_back(worker, i, std::ref(cache), std::ref(stats),
                             std::ref(running));
    }

    std::this_thread::sleep_for(std::chrono::seconds(cfg.durationSec));
    running.store(false, std::memory_order_release);

    for (auto &t : threads) {
        t.join();
    }
    cleaner.join();

    std::cout << "ops=" << stats.ops.load() << " hits=" << stats.hits.load()
              << " misses=" << stats.misses.load() << " expired="
              << stats.expired.load() << " sets=" << stats.sets.load()
              << " deletes=" << stats.deletes.load() << " cleanups="
              << stats.cleanups.load() << "\n";
    return 0;
}
