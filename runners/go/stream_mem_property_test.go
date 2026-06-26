package main

import (
	"io"
	"runtime"
	"testing"
	"time"

	"pgregory.net/rapid"
)

// Feature: pgp-encryption-benchmark-go-java, Property 14: Streaming peak memory ไม่โตตามขนาดไฟล์
//
// Validates: Requirements 15.2
//
// For the streaming variant, increasing the input file size by large factors
// must not grow peak memory proportionally: it stays roughly constant, bounded
// by a function of the fixed buffer size rather than the file size. We rely on a
// structural fact of Go's GC (it paces collection relative to the live heap) and
// sample HeapAlloc during the operation, taking the peak delta over a forced-GC
// baseline. A single size-independent bound holding across a wide size range is
// the "does not grow with file size" property; TestInmemPeakMemoryGrowsWithFileSize
// proves the bound is discriminating.

const (
	// minStreamSize / maxStreamSize bound the generated input sizes; the ~128x
	// range makes a size-independent peak bound a real test of the invariant.
	minStreamSize = 64 * 1024       // 64 KiB
	maxStreamSize = 8 * 1024 * 1024 // 8 MiB

	// streamingPeakBoundBytes is the constant ceiling on the streaming variant's
	// peak heap delta: a function of the fixed buffers, not of the file size. It
	// is set below maxStreamSize so an in-memory variant would violate it at
	// large sizes, yet generous enough to absorb GC/runtime noise.
	streamingPeakBoundBytes = 6 * 1024 * 1024 // 6 MiB
)

// TestStreamPeakMemoryDoesNotGrowWithFileSize is the rapid property test for
// Property 14: across a wide range of input sizes the streaming variant's peak
// heap growth during Encrypt stays under a single size-independent bound.
//
// **Validates: Requirements 15.2**
func TestStreamPeakMemoryDoesNotGrowWithFileSize(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	profile := aes256Zlib("RSA-2048")
	eng := streamSingleEngine{}

	rapid.Check(t, func(rt *rapid.T) {
		size := rapid.IntRange(minStreamSize, maxStreamSize).Draw(rt, "size")
		seed := rapid.Uint64().Draw(rt, "seed") | 1 // non-zero for xorshift

		peak := measurePeakHeapDelta(func() {
			// The source generates `size` bytes lazily and the sink discards
			// them, so the test never holds the whole file in memory.
			src := &patternReader{remaining: size, seed: seed}
			sink := &countingDiscardWriter{}
			if _, err := eng.Encrypt(src, sink, profile, keys); err != nil {
				rt.Fatalf("stream encrypt (size=%d): %v", size, err)
			}
			if sink.n == 0 {
				rt.Fatalf("stream encrypt produced no output (size=%d)", size)
			}
		})

		if peak > streamingPeakBoundBytes {
			rt.Fatalf("streaming peak heap delta = %d bytes for input size %d exceeds the "+
				"size-independent bound %d bytes — peak memory must not grow with file size (Req 15.2)",
				peak, size, streamingPeakBoundBytes)
		}
	})
}

// patternReader emits `remaining` pseudo-random bytes lazily via an xorshift
// generator, without storing them, so a streaming consumer can be fed an
// arbitrarily large input without the test allocating it. The bytes are
// effectively incompressible, preventing zlib from masking buffering behaviour.
type patternReader struct {
	remaining int
	seed      uint64
}

func (r *patternReader) Read(p []byte) (int, error) {
	if r.remaining <= 0 {
		return 0, io.EOF
	}
	n := len(p)
	if n > r.remaining {
		n = r.remaining
	}
	s := r.seed
	for i := 0; i < n; i++ {
		s ^= s << 13
		s ^= s >> 7
		s ^= s << 17
		p[i] = byte(s)
	}
	r.seed = s
	r.remaining -= n
	return n, nil
}

// countingDiscardWriter discards everything written while counting the bytes.
type countingDiscardWriter struct{ n int64 }

func (w *countingDiscardWriter) Write(p []byte) (int, error) {
	w.n += int64(len(p))
	return len(p), nil
}

// measurePeakHeapDelta runs fn while sampling the runtime heap and returns the
// peak HeapAlloc observed above a forced-GC baseline.
func measurePeakHeapDelta(fn func()) uint64 {
	runtime.GC()
	runtime.GC()
	var base runtime.MemStats
	runtime.ReadMemStats(&base)

	stop := make(chan struct{})
	done := make(chan struct{})
	peak := base.HeapAlloc
	go func() {
		defer close(done)
		var m runtime.MemStats
		for {
			select {
			case <-stop:
				return
			default:
				runtime.ReadMemStats(&m)
				if m.HeapAlloc > peak {
					peak = m.HeapAlloc
				}
				time.Sleep(100 * time.Microsecond)
			}
		}
	}()

	fn()

	close(stop)
	<-done

	// Final reading in case the peak landed at the end of the operation.
	var after runtime.MemStats
	runtime.ReadMemStats(&after)
	if after.HeapAlloc > peak {
		peak = after.HeapAlloc
	}

	if peak < base.HeapAlloc {
		return 0
	}
	return peak - base.HeapAlloc
}

// TestInmemPeakMemoryGrowsWithFileSize is a meaningfulness guard for Property
// 14, not a property test itself: it proves the streaming bound is
// discriminating. The in-memory variant blows past streamingPeakBoundBytes at a
// large input size, whereas the streaming variant stays under it for the same
// size.
func TestInmemPeakMemoryGrowsWithFileSize(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	profile := aes256Zlib("RSA-2048")

	// Large enough that the whole-file buffer dwarfs the streaming bound.
	const largeSize = 24 * 1024 * 1024 // 24 MiB
	inmemPeak := measurePeakHeapDelta(func() {
		src := &patternReader{remaining: largeSize, seed: 0x9e3779b97f4a7c15}
		sink := &countingDiscardWriter{}
		if _, err := (inmemSingleEngine{}).Encrypt(src, sink, profile, keys); err != nil {
			t.Fatalf("inmem encrypt: %v", err)
		}
	})
	if inmemPeak <= streamingPeakBoundBytes {
		t.Fatalf("in-memory peak heap delta = %d bytes at size %d did NOT exceed the streaming "+
			"bound %d bytes; the streaming property test may pass vacuously",
			inmemPeak, largeSize, streamingPeakBoundBytes)
	}

	streamPeak := measurePeakHeapDelta(func() {
		src := &patternReader{remaining: largeSize, seed: 0x9e3779b97f4a7c15}
		sink := &countingDiscardWriter{}
		if _, err := (streamSingleEngine{}).Encrypt(src, sink, profile, keys); err != nil {
			t.Fatalf("stream encrypt: %v", err)
		}
	})
	if streamPeak > streamingPeakBoundBytes {
		t.Fatalf("streaming peak heap delta = %d bytes at size %d exceeded the bound %d bytes",
			streamPeak, largeSize, streamingPeakBoundBytes)
	}

	t.Logf("at %d bytes: inmem peak=%d bytes, stream peak=%d bytes, bound=%d bytes",
		largeSize, inmemPeak, streamPeak, streamingPeakBoundBytes)
}
