package main

import (
	"context"
	"fmt"
	"math/rand"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
)

// Config mirrors the shape of bench/ttl_cache_bench.c but is trimmed for readability.
type Config struct {
	NumWorkers    int
	Duration      time.Duration
	ValueSize     int
	KeySpace      int
	HotKeyPercent int
	TTL           time.Duration
	Epoch         time.Duration
	GetRatio      float64
	SetRatio      float64
	DeleteRatio   float64
	Shards        int
}

var cfg = Config{
	NumWorkers:    runtime.NumCPU(),
	Duration:      5 * time.Second,
	ValueSize:     256,
	KeySpace:      200_000,
	HotKeyPercent: 80,
	TTL:           500 * time.Millisecond,
	Epoch:         150 * time.Millisecond,
	GetRatio:      0.80,
	SetRatio:      0.19,
	DeleteRatio:   0.01,
	Shards:        32,
}

// stats collects counters using atomics so workers can update concurrently.
type stats struct {
	ops       atomic.Uint64
	hits      atomic.Uint64
	misses    atomic.Uint64
	sets      atomic.Uint64
	deletes   atomic.Uint64
	expiries  atomic.Uint64
	cleanTime atomic.Uint64
}

func (s *stats) snapshot() map[string]uint64 {
	return map[string]uint64{
		"ops":      s.ops.Load(),
		"hits":     s.hits.Load(),
		"misses":   s.misses.Load(),
		"sets":     s.sets.Load(),
		"deletes":  s.deletes.Load(),
		"expiries": s.expiries.Load(),
		"clean_ns": s.cleanTime.Load(),
	}
}

type cacheItem struct {
	expires int64
	value   []byte
}

type shard struct {
	mu    sync.Mutex
	items map[int]cacheItem
}

type ttlCache struct {
	shards []shard
	ttl    time.Duration
}

func newTTLCache(shards int, ttl time.Duration) *ttlCache {
	out := &ttlCache{ttl: ttl, shards: make([]shard, shards)}
	for i := range out.shards {
		out.shards[i].items = make(map[int]cacheItem, 1024)
	}
	return out
}

func (c *ttlCache) shardFor(key int) *shard {
	return &c.shards[key%len(c.shards)]
}

func (c *ttlCache) get(key int, now int64, st *stats) bool {
	s := c.shardFor(key)
	s.mu.Lock()
	defer s.mu.Unlock()

	item, ok := s.items[key]
	if !ok {
		st.misses.Add(1)
		return false
	}
	if item.expires < now {
		delete(s.items, key)
		st.expiries.Add(1)
		st.misses.Add(1)
		return false
	}
	st.hits.Add(1)
	return true
}

func (c *ttlCache) set(key int, val []byte, now int64, st *stats) {
	s := c.shardFor(key)
	s.mu.Lock()
	s.items[key] = cacheItem{expires: now + int64(c.ttl), value: append([]byte(nil), val...)}
	s.mu.Unlock()
	st.sets.Add(1)
}

func (c *ttlCache) del(key int, st *stats) {
	s := c.shardFor(key)
	s.mu.Lock()
	if _, ok := s.items[key]; ok {
		delete(s.items, key)
		st.deletes.Add(1)
	}
	s.mu.Unlock()
}

func (c *ttlCache) sweep(now int64, st *stats) {
	start := time.Now()
	removed := uint64(0)
	for i := range c.shards {
		sh := &c.shards[i]
		sh.mu.Lock()
		for k, v := range sh.items {
			if v.expires < now {
				delete(sh.items, k)
				removed++
			}
		}
		sh.mu.Unlock()
	}
	if removed > 0 {
		st.expiries.Add(removed)
	}
	st.cleanTime.Add(uint64(time.Since(start).Nanoseconds()))
}

func startCleaner(ctx context.Context, cache *ttlCache, st *stats) {
	ticker := time.NewTicker(cfg.Epoch)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case now := <-ticker.C:
				cache.sweep(now.UnixNano(), st)
			}
		}
	}()
}

func sampleKey(r *rand.Rand) int {
	if r.Intn(100) < cfg.HotKeyPercent {
		return r.Intn(cfg.KeySpace / 5)
	}
	return r.Intn(cfg.KeySpace)
}

func randomValue(r *rand.Rand) []byte {
	buf := make([]byte, cfg.ValueSize)
	for i := range buf {
		buf[i] = byte(r.Intn(26) + 'a')
	}
	return buf
}

func worker(id int, cache *ttlCache, st *stats, stop <-chan struct{}, wg *sync.WaitGroup) {
	defer wg.Done()
	rnd := rand.New(rand.NewSource(time.Now().UnixNano() + int64(id*1337)))
	for {
		select {
		case <-stop:
			return
		default:
		}

		key := sampleKey(rnd)
		op := rnd.Float64()
		now := time.Now().UnixNano()
		switch {
		case op < cfg.GetRatio:
			cache.get(key, now, st)
		case op < cfg.GetRatio+cfg.SetRatio:
			cache.set(key, randomValue(rnd), now, st)
		default:
			cache.del(key, st)
		}
		st.ops.Add(1)
	}
}

func main() {
	fmt.Println("locked TTL cache benchmark (Go example)")
	cache := newTTLCache(cfg.Shards, cfg.TTL)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	st := &stats{}
	startCleaner(ctx, cache, st)

	stop := make(chan struct{})
	var wg sync.WaitGroup
	for i := 0; i < cfg.NumWorkers; i++ {
		wg.Add(1)
		go worker(i, cache, st, stop, &wg)
	}

	time.Sleep(cfg.Duration)
	close(stop)
	wg.Wait()
	cancel()

	snap := st.snapshot()
	fmt.Printf("ops=%d hits=%d misses=%d sets=%d deletes=%d expiries=%d cleanup_ns=%d\n",
		snap["ops"], snap["hits"], snap["misses"], snap["sets"], snap["deletes"], snap["expiries"], snap["clean_ns"])
}
