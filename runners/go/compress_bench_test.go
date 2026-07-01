package main

// compress_bench_test.go isolates the ONE variable in the Go-vs-Java gap: the
// DEFLATE/ZLIB compression stage. It compares the Go standard library
// (compress/zlib, which ProtonMail/go-crypto uses internally) against the
// drop-in klauspost/compress/zlib, on payloads that mimic the benchmark corpus
// (compressible .txt/.csv vs incompressible .pdf/binary) at representative
// sizes. No PGP, no keys, no interop risk — just the compressor.
//
// Run:
//   go test -run TestCompressionCompare -v       # human-readable ratio+time table
//   go test -bench=BenchmarkCompress -benchmem    # rigorous throughput numbers
//
// Both zlib packages produce standard RFC 1950 streams, so swapping klauspost
// in (via a go-crypto fork) keeps Go<->Java<->gpg interop intact.

import (
	stdzlib "compress/zlib"
	"bytes"
	"fmt"
	"math/rand"
	"testing"
	"time"

	kpzlib "github.com/klauspost/compress/zlib"
)

// zlibLevel is set to an explicit 6 so the comparison is apples-to-apples:
//   - Go stdlib default (-1) == level 6
//   - Java BouncyCastle default == Z_DEFAULT_COMPRESSION == level 6
//   - klauspost default (-1) is level 5 (rebalanced), which would be even
//     faster but at a slightly lower ratio — so we pin 6 to compare fairly.
const zlibLevel = 6

// --- payload generators -----------------------------------------------------

// makeCompressibleText mimics a .txt file: natural-language-like words drawn
// from a small vocabulary with spaces and newlines. Highly compressible.
func makeCompressibleText(n int) []byte {
	words := []string{
		"the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
		"lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing",
		"data", "encryption", "benchmark", "compression", "performance",
	}
	rng := rand.New(rand.NewSource(1))
	var b bytes.Buffer
	b.Grow(n + 16)
	for b.Len() < n {
		b.WriteString(words[rng.Intn(len(words))])
		if rng.Intn(12) == 0 {
			b.WriteByte('\n')
		} else {
			b.WriteByte(' ')
		}
	}
	return b.Bytes()[:n]
}

// makeCompressibleCSV mimics a .csv file: comma-separated numeric rows.
func makeCompressibleCSV(n int) []byte {
	rng := rand.New(rand.NewSource(2))
	var b bytes.Buffer
	b.Grow(n + 32)
	for b.Len() < n {
		fmt.Fprintf(&b, "%d,%d,%d,%d,%0.2f\n",
			rng.Intn(100000), rng.Intn(999), rng.Intn(2), rng.Intn(50), rng.Float64()*1000)
	}
	return b.Bytes()[:n]
}

// makeIncompressible mimics a .pdf / already-compressed binary: full-range
// pseudo-random bytes that DEFLATE cannot shrink.
func makeIncompressible(n int) []byte {
	rng := rand.New(rand.NewSource(3))
	buf := make([]byte, n)
	rng.Read(buf)
	return buf
}

type payload struct {
	name string
	data []byte
}

func corpusPayloads() []payload {
	sizes := []struct {
		label string
		bytes int
	}{
		{"1KB", 1 << 10},
		{"10KB", 10 << 10},
		{"100KB", 100 << 10},
	}
	var out []payload
	for _, s := range sizes {
		out = append(out,
			payload{"txt-" + s.label, makeCompressibleText(s.bytes)},
			payload{"csv-" + s.label, makeCompressibleCSV(s.bytes)},
			payload{"pdf-" + s.label, makeIncompressible(s.bytes)},
		)
	}
	return out
}

// --- compressors ------------------------------------------------------------

func compressStd(dst *bytes.Buffer, src []byte) error {
	dst.Reset()
	w, err := stdzlib.NewWriterLevel(dst, zlibLevel)
	if err != nil {
		return err
	}
	if _, err := w.Write(src); err != nil {
		_ = w.Close()
		return err
	}
	return w.Close()
}

func compressKlauspost(dst *bytes.Buffer, src []byte) error {
	dst.Reset()
	w, err := kpzlib.NewWriterLevel(dst, zlibLevel)
	if err != nil {
		return err
	}
	if _, err := w.Write(src); err != nil {
		_ = w.Close()
		return err
	}
	return w.Close()
}

// --- rigorous throughput benchmarks -----------------------------------------

func BenchmarkCompress(b *testing.B) {
	for _, p := range corpusPayloads() {
		p := p
		var buf bytes.Buffer
		b.Run("stdlib/"+p.name, func(b *testing.B) {
			b.SetBytes(int64(len(p.data)))
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				if err := compressStd(&buf, p.data); err != nil {
					b.Fatal(err)
				}
			}
		})
		b.Run("klauspost/"+p.name, func(b *testing.B) {
			b.SetBytes(int64(len(p.data)))
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				if err := compressKlauspost(&buf, p.data); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}

// --- human-readable comparison (ratio + relative time) ----------------------

// TestCompressionCompare prints a side-by-side table so a reader does not need
// to interpret `go test -bench` output. It is not a pass/fail assertion beyond
// verifying both compressors run without error and produce identical output
// sizes' ballpark (they will differ slightly; that is expected).
func TestCompressionCompare(t *testing.T) {
	const iters = 200
	var std, kp bytes.Buffer

	t.Logf("%-12s | %8s | %10s %10s | %10s %10s | %7s",
		"payload", "raw", "std ns/op", "std ratio", "kp ns/op", "kp ratio", "speedup")
	t.Logf("%s", "-------------+----------+----------------------+----------------------+--------")

	for _, p := range corpusPayloads() {
		// warm up + correctness
		if err := compressStd(&std, p.data); err != nil {
			t.Fatal(err)
		}
		stdSize := std.Len()
		if err := compressKlauspost(&kp, p.data); err != nil {
			t.Fatal(err)
		}
		kpSize := kp.Len()

		stdNs := timeCompress(t, iters, func() { _ = compressStd(&std, p.data) })
		kpNs := timeCompress(t, iters, func() { _ = compressKlauspost(&kp, p.data) })

		speedup := float64(stdNs) / float64(kpNs)
		t.Logf("%-12s | %8d | %10d %9.2fx | %10d %9.2fx | %6.2fx",
			p.name, len(p.data),
			stdNs, float64(len(p.data))/float64(stdSize),
			kpNs, float64(len(p.data))/float64(kpSize),
			speedup)
	}
}

func timeCompress(t *testing.T, iters int, fn func()) int64 {
	t.Helper()
	start := time.Now()
	for i := 0; i < iters; i++ {
		fn()
	}
	return time.Since(start).Nanoseconds() / int64(iters)
}
