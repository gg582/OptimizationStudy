#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <random>
#include <shared_mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

struct Config {
    int numThreads = std::thread::hardware_concurrency();
    int durationSec = 5;
    int valueSize = 256;
    int keySpace = 200'000;
    int hotPercent = 80;
    std::chrono::milliseconds ttl{500};
    std::chrono::milliseconds epoch{150};
    double getRatio = 0.8;
    double setRatio = 0.19;
    double delRatio = 0.01;
    int shardCount = 32;
};

static Config cfg;

struct Stats {
    std::atomic<uint64_t> ops{0};
    std::atomic<uint64_t> hits{0};
    std::atomic<uint64_t> misses{0};
    std::atomic<uint64_t> sets{0};
    std::atomic<uint64_t> deletes{0};
    std::atomic<uint64_t> expiries{0};
    std::atomic<uint64_t> cleanupNs{0};
};

struct Item {
    int64_t expires;
    std::string value;
};

struct Shard {
    std::shared_mutex mutex;
    std::unordered_map<int, Item> map;
};

class TTLCache {
  public:
    explicit TTLCache(int shards, std::chrono::nanoseconds ttl)
        : ttl_(ttl), shards_(shards) {}

    bool get(int key, int64_t now, Stats &stats) {
        Shard &sh = shardFor(key);
        std::shared_lock lock(sh.mutex);
        auto it = sh.map.find(key);
        if (it == sh.map.end()) {
            stats.misses.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        if (it->second.expires < now) {
            lock.unlock();
            std::unique_lock ulock(sh.mutex);
            auto jt = sh.map.find(key);
            if (jt != sh.map.end() && jt->second.expires < now) {
                sh.map.erase(jt);
                stats.expiries.fetch_add(1, std::memory_order_relaxed);
            }
            stats.misses.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        stats.hits.fetch_add(1, std::memory_order_relaxed);
        return true;
    }

    void set(int key, std::string value, int64_t now, Stats &stats) {
        Shard &sh = shardFor(key);
        std::unique_lock lock(sh.mutex);
        sh.map[key] = Item{now + ttl_.count(), std::move(value)};
        stats.sets.fetch_add(1, std::memory_order_relaxed);
    }

    void erase(int key, Stats &stats) {
        Shard &sh = shardFor(key);
        std::unique_lock lock(sh.mutex);
        auto erased = sh.map.erase(key);
        if (erased) {
            stats.deletes.fetch_add(1, std::memory_order_relaxed);
        }
    }

    void sweep(int64_t now, Stats &stats) {
        auto start = std::chrono::steady_clock::now();
        uint64_t removed = 0;
        for (auto &sh : shards_) {
            std::unique_lock lock(sh.mutex);
            for (auto it = sh.map.begin(); it != sh.map.end();) {
                if (it->second.expires < now) {
                    it = sh.map.erase(it);
                    ++removed;
                } else {
                    ++it;
                }
            }
        }
        if (removed) {
            stats.expiries.fetch_add(removed, std::memory_order_relaxed);
        }
        auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - start);
        stats.cleanupNs.fetch_add(elapsed.count(), std::memory_order_relaxed);
    }

  private:
    Shard &shardFor(int key) { return shards_[key % shards_.size()]; }

    std::chrono::nanoseconds ttl_;
    std::vector<Shard> shards_;
};

static inline int64_t nowNs() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

static int sampleKey(std::mt19937_64 &rng) {
    std::uniform_int_distribution<int> hot(0, cfg.keySpace / 5);
    std::uniform_int_distribution<int> cold(0, cfg.keySpace - 1);
    std::uniform_int_distribution<int> perc(1, 100);
    return perc(rng) <= cfg.hotPercent ? hot(rng) : cold(rng);
}

static std::string randomValue(std::mt19937_64 &rng) {
    std::string value(cfg.valueSize, '\0');
    std::uniform_int_distribution<int> letters('a', 'z');
    for (char &ch : value) {
        ch = static_cast<char>(letters(rng));
    }
    return value;
}

static void worker(int id, TTLCache &cache, Stats &stats,
                   std::atomic<bool> &running) {
    std::mt19937_64 rng(
        static_cast<uint64_t>(std::chrono::high_resolution_clock::now()
                                  .time_since_epoch()
                                  .count()) +
        id * 1337);
    std::uniform_real_distribution<double> unit(0.0, 1.0);
    while (running.load(std::memory_order_acquire)) {
        int key = sampleKey(rng);
        double op = unit(rng);
        int64_t ts = nowNs();
        if (op < cfg.getRatio) {
            cache.get(key, ts, stats);
        } else if (op < cfg.getRatio + cfg.setRatio) {
            cache.set(key, randomValue(rng), ts, stats);
        } else {
            cache.erase(key, stats);
        }
        stats.ops.fetch_add(1, std::memory_order_relaxed);
    }
}

int main() {
    std::cout << "locked TTL cache benchmark (C++ example)\n";
    TTLCache cache(cfg.shardCount, cfg.ttl);
    Stats stats;
    std::atomic<bool> running{true};

    std::thread cleaner([&] {
        while (running.load(std::memory_order_acquire)) {
            cache.sweep(nowNs(), stats);
            std::this_thread::sleep_for(cfg.epoch);
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
              << " misses=" << stats.misses.load() << " sets="
              << stats.sets.load() << " deletes=" << stats.deletes.load()
              << " expiries=" << stats.expiries.load() << " cleanup_ns="
              << stats.cleanupNs.load() << "\n";
    return 0;
}
