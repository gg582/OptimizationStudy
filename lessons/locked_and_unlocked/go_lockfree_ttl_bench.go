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

type lfConfig struct {
	NumWorkers    int
	Duration      time.Duration
	ValueSize     int
	KeySpace      uint64
	HotKeySpace   uint64
	HotKeyPct     int
	TTL           time.Duration
	TablePow      uint
	CleanupStride int
	GetRatio      float64
	SetRatio      float64
	DeleteRatio   float64
}

var lfCfg = lfConfig{
	NumWorkers:    runtime.NumCPU(),
	Duration:      5 * time.Second,
	ValueSize:     256,
	KeySpace:      1 << 18,
	HotKeySpace:   1 << 14,
	HotKeyPct:     85,
	TTL:           750 * time.Millisecond,
	TablePow:      17,
	CleanupStride: 256,
	GetRatio:      0.9,
	SetRatio:      0.09,
	DeleteRatio:   0.01,
}

type lfStats struct {
	ops      atomic.Uint64
	hits     atomic.Uint64
	misses   atomic.Uint64
	expired  atomic.Uint64
	sets     atomic.Uint64
	deletes  atomic.Uint64
	cleanups atomic.Uint64
}

type lfEntry struct {
	key    uint64
	expire int64
	value  []byte
	next   *lfEntry
}

type lfBucket struct {
	head atomic.Pointer[lfEntry]
}

type lockFreeCache struct {
	buckets []lfBucket
	mask    uint64
	ttl     time.Duration
	cursor  atomic.Uint64
}

func newLockFreeCache(pow uint, ttl time.Duration) *lockFreeCache {
	size := uint64(1) << pow
	buckets := make([]lfBucket, size)
	return &lockFreeCache{buckets: buckets, mask: size - 1, ttl: ttl}
}

func (c *lockFreeCache) bucket(key uint64) *lfBucket {
	return &c.buckets[key&c.mask]
}

func (c *lockFreeCache) get(key uint64, now int64, st *lfStats) bool {
	b := c.bucket(key)
	for node := b.head.Load(); node != nil; node = node.next {
		if node.key != key {
			continue
		}
		if node.expire >= now {
			st.hits.Add(1)
			return true
		}
		st.expired.Add(1)
		return false
	}
	st.misses.Add(1)
	return false
}

func (c *lockFreeCache) set(key uint64, val []byte, now int64, st *lfStats) {
	entry := &lfEntry{key: key, expire: now + int64(c.ttl), value: append([]byte(nil), val...)}
	b := c.bucket(key)
	for {
		head := b.head.Load()
		entry.next = head
		if b.head.CompareAndSwap(head, entry) {
			st.sets.Add(1)
			return
		}
	}
}

func (c *lockFreeCache) delete(key uint64, st *lfStats) {
	tombstone := &lfEntry{key: key, expire: 0}
	b := c.bucket(key)
	for {
		head := b.head.Load()
		tombstone.next = head
		if b.head.CompareAndSwap(head, tombstone) {
			st.deletes.Add(1)
			return
		}
	}
}

func (c *lockFreeCache) cleanup(n int, now int64, st *lfStats) {
	for i := 0; i < n; i++ {
		idx := int(c.cursor.Add(1)-1) & int(c.mask)
		b := &c.buckets[idx]
		head := b.head.Load()
		if head == nil {
			continue
		}
		rebuilt, changed := rebuildList(head, now)
		if !changed {
			continue
		}
		for {
			if b.head.CompareAndSwap(head, rebuilt) {
				st.cleanups.Add(1)
				break
			}
			head = b.head.Load()
			if head == nil {
				if rebuilt == nil {
					break
				}
			}
			rebuilt, changed = rebuildList(head, now)
			if !changed {
				break
			}
		}
	}
}

func rebuildList(head *lfEntry, now int64) (*lfEntry, bool) {
	var keep []*lfEntry
	changed := false
	for node := head; node != nil; node = node.next {
		if node.expire >= now && node.expire != 0 {
			keep = append(keep, node)
		} else {
			changed = true
		}
	}
	if !changed {
		return head, false
	}
	if len(keep) == 0 {
		return nil, true
	}
	var newHead *lfEntry
	for _, node := range keep {
		clone := &lfEntry{key: node.key, expire: node.expire, value: node.value, next: newHead}
		newHead = clone
	}
	return newHead, true
}

func lfSampleKey(r *rand.Rand) uint64 {
	if r.Intn(100) < lfCfg.HotKeyPct {
		return uint64(r.Intn(int(lfCfg.HotKeySpace)))
	}
	return lfCfg.HotKeySpace + uint64(r.Intn(int(lfCfg.KeySpace-lfCfg.HotKeySpace)))
}

func lfValue(r *rand.Rand) []byte {
	buf := make([]byte, lfCfg.ValueSize)
	for i := range buf {
		buf[i] = byte(r.Intn(10) + '0')
	}
	return buf
}

func lfWorker(id int, cache *lockFreeCache, st *lfStats, stop <-chan struct{}, wg *sync.WaitGroup) {
	defer wg.Done()
	rnd := rand.New(rand.NewSource(time.Now().UnixNano() + int64(id*7919)))
	for {
		select {
		case <-stop:
			return
		default:
		}
		key := lfSampleKey(rnd)
		op := rnd.Float64()
		now := time.Now().UnixNano()
		switch {
		case op < lfCfg.GetRatio:
			cache.get(key, now, st)
		case op < lfCfg.GetRatio+lfCfg.SetRatio:
			cache.set(key, lfValue(rnd), now, st)
		default:
			cache.delete(key, st)
		}
		st.ops.Add(1)
	}
}

func startLFCleaner(ctx context.Context, cache *lockFreeCache, st *lfStats) {
	ticker := time.NewTicker(100 * time.Millisecond)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case now := <-ticker.C:
				cache.cleanup(lfCfg.CleanupStride, now.UnixNano(), st)
			}
		}
	}()
}

func main() {
	fmt.Println("lock-free TTL cache benchmark (Go example)")
	cache := newLockFreeCache(lfCfg.TablePow, lfCfg.TTL)
	st := &lfStats{}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	startLFCleaner(ctx, cache, st)

	stop := make(chan struct{})
	var wg sync.WaitGroup
	for i := 0; i < lfCfg.NumWorkers; i++ {
		wg.Add(1)
		go lfWorker(i, cache, st, stop, &wg)
	}

	time.Sleep(lfCfg.Duration)
	close(stop)
	wg.Wait()
	cancel()

	fmt.Printf("ops=%d hits=%d misses=%d expired=%d sets=%d deletes=%d cleanups=%d\n",
		st.ops.Load(), st.hits.Load(), st.misses.Load(), st.expired.Load(), st.sets.Load(), st.deletes.Load(), st.cleanups.Load())
}
