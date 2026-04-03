package main

import "fmt"

const (
	Read = 1 << iota
	Write
	Execute
)

func main() {
	var perm uint32
	perm |= Read | Write
	fmt.Printf("Set READ+WRITE -> 0b%03b\n", perm)

	perm ^= Write
	fmt.Printf("Toggle WRITE -> 0b%03b\n", perm)

	if perm&Read != 0 {
		fmt.Println("Read allowed")
	}

	perm &^= Read
	fmt.Printf("Clear READ -> 0b%03b\n", perm)

	perm |= Execute
	fmt.Printf("Add EXECUTE -> 0b%03b (exec? %t)\n", perm, perm&Execute != 0)
}
