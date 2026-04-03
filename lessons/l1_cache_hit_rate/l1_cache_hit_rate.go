package main

import (
	"fmt"
	"time"
)

const (
	sizeBytes = 1 << 20 // 1 MiB
	stride    = 64
)

func measure(step int) time.Duration {
	data := make([]int64, sizeBytes/8)
	start := time.Now()
	var sum int64
	for i := 0; i < len(data); i += step {
		sum += data[i]
	}
	if sum == 42 {
		fmt.Println("impossible")
	}
	return time.Since(start)
}

func main() {
	seq := measure(1)
	sparse := measure(stride)
	fmt.Printf("Sequential step=1: %v\n", seq)
	fmt.Printf("Sparse stride=%d: %v\n", stride, sparse)
}
