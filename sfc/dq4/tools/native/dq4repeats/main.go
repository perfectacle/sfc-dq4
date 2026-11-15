// dq4repeats is the native form of dq4soundcompact._repeats: repeated runs of an int array
// (negative values are distinct walls) found from its suffix array and LCP intervals. The
// output must equal the Python generator item for item, in the same order;
// sfc/dq4/tools/test_dq4soundcompact.py compares the two.
//
// Protocol on stdin/stdout, little-endian int32: a request is n, maxTokens, then n values
// (n < 0 ends the process). The reply is the group count, then per group the length, the
// position count and the positions.
package main

import (
	"bufio"
	"encoding/binary"
	"io"
	"os"
	"sort"
)

func repeats(arr []int32, maxTokens int) [][]int32 {
	n := len(arr)
	order := make([]int, n)
	for i := range order {
		order[i] = i
	}
	// Python sorts by the slice arr[i:i+maxTokens] (a shorter equal prefix sorts first) and
	// keeps index order among equal keys.
	sort.SliceStable(order, func(x, y int) bool {
		a, b := order[x], order[y]
		la, lb := min(maxTokens, n-a), min(maxTokens, n-b)
		for m := 0; m < la && m < lb; m++ {
			if arr[a+m] != arr[b+m] {
				return arr[a+m] < arr[b+m]
			}
		}
		return la < lb
	})
	lcp := make([]int, n)
	for k := 1; k < n; k++ {
		a, b := order[k-1], order[k]
		m := 0
		for m < maxTokens && a+m < n && b+m < n && arr[a+m] == arr[b+m] && arr[a+m] >= 0 {
			m++
		}
		lcp[k] = m
	}
	type entry struct{ length, left int }
	stack := []entry{{0, 0}}
	var out [][]int32
	for k := 1; k <= n; k++ {
		value := 0
		if k < n {
			value = lcp[k]
		}
		left := k - 1
		for value < stack[len(stack)-1].length {
			top := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			left = top.left
			if top.length >= 2 {
				group := make([]int32, 0, 2+k-left)
				group = append(group, int32(top.length), int32(k-left))
				for _, p := range order[left:k] {
					group = append(group, int32(p))
				}
				out = append(out, group)
			}
		}
		if value > stack[len(stack)-1].length {
			stack = append(stack, entry{value, left})
		}
	}
	return out
}

func main() {
	r := bufio.NewReaderSize(os.Stdin, 1<<20)
	w := bufio.NewWriterSize(os.Stdout, 1<<20)
	var head [2]int32
	for {
		if err := binary.Read(r, binary.LittleEndian, &head); err != nil {
			if err == io.EOF {
				return
			}
			panic(err)
		}
		if head[0] < 0 {
			return
		}
		arr := make([]int32, head[0])
		if err := binary.Read(r, binary.LittleEndian, arr); err != nil {
			panic(err)
		}
		groups := repeats(arr, int(head[1]))
		total := 1
		for _, g := range groups {
			total += len(g)
		}
		flat := make([]int32, 0, total)
		flat = append(flat, int32(len(groups)))
		for _, g := range groups {
			flat = append(flat, g...)
		}
		if err := binary.Write(w, binary.LittleEndian, flat); err != nil {
			panic(err)
		}
		if err := w.Flush(); err != nil {
			panic(err)
		}
	}
}
