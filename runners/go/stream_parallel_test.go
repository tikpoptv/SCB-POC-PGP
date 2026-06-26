package main

import (
	"bytes"
	"runtime"
	"sync"
	"testing"
	"time"
)

func TestStreamParallelVariantID(t *testing.T) {
	if id := (streamParallelEngine{}).VariantID(); id != "go-stream-parallel" {
		t.Errorf("VariantID() = %q, want go-stream-parallel", id)
	}
}

func TestStreamParallelRegistered(t *testing.T) {
	eng, ok := NewEngine("go-stream-parallel")
	if !ok {
		t.Fatal("go-stream-parallel not registered")
	}
	if _, isSup := eng.(ProfileSupporter); !isSup {
		t.Error("engine should implement ProfileSupporter")
	}
	if _, isHint := eng.(ConcurrencyHint); !isHint {
		t.Error("engine should implement ConcurrencyHint")
	}
}

// TestStreamParallelRoundTripByteForByte is the core correctness gate: the
// streaming variant must decrypt(encrypt(x)) back to x across representative
// payloads and the supported RSA key sizes.
func TestStreamParallelRoundTripByteForByte(t *testing.T) {
	keys := loadRepoKeys(t)
	eng := streamParallelEngine{}

	payloads := map[string][]byte{
		"empty":        {},
		"short-text":   []byte("the quick brown fox jumps over the lazy dog"),
		"compressible": bytes.Repeat([]byte("AAAA-BBBB-CCCC-"), 5000),
		// Larger than the streaming buffer so multiple CopyBuffer iterations run.
		"binary-multibuf": binaryPayload(512 * 1024),
	}
	pubAlgs := []string{"RSA-2048", "RSA-4096"}

	for _, pubAlg := range pubAlgs {
		if !keys.HasKeyFor(pubAlg) {
			t.Logf("skipping %s: no key in repo set", pubAlg)
			continue
		}
		profile := aes256Zlib(pubAlg)
		for name, plain := range payloads {
			t.Run(pubAlg+"/"+name, func(t *testing.T) {
				var ct bytes.Buffer
				encT, err := eng.Encrypt(bytes.NewReader(plain), &ct, profile, keys)
				if err != nil {
					t.Fatalf("encrypt: %v", err)
				}
				if encT.TotalNanos <= 0 {
					t.Errorf("encrypt TotalNanos = %d, want > 0", encT.TotalNanos)
				}
				if ct.Len() == 0 {
					t.Fatal("ciphertext is empty")
				}
				if len(plain) > 0 && bytes.Equal(ct.Bytes(), plain) {
					t.Error("ciphertext equals plaintext")
				}

				var pt bytes.Buffer
				decT, err := eng.Decrypt(bytes.NewReader(ct.Bytes()), &pt, profile, keys)
				if err != nil {
					t.Fatalf("decrypt: %v", err)
				}
				if decT.TotalNanos <= 0 {
					t.Errorf("decrypt TotalNanos = %d, want > 0", decT.TotalNanos)
				}
				if !bytes.Equal(pt.Bytes(), plain) {
					t.Errorf("round-trip mismatch: got %d bytes, want %d bytes", pt.Len(), len(plain))
				}
			})
		}
	}
}

// TestStreamParallelConcurrentRoundTrip exercises the engine the way the worker
// pool does: many files crypto'd concurrently on the same stateless engine
// instance, sharing the sync.Pool buffer. All round-trips must stay correct and
// the shared buffer must not corrupt output.
func TestStreamParallelConcurrentRoundTrip(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	eng := streamParallelEngine{}
	profile := aes256Zlib("RSA-2048")

	const files = 32
	var wg sync.WaitGroup
	errs := make([]error, files)
	for i := 0; i < files; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			plain := binaryPayload(1024 + idx*131)
			var ct bytes.Buffer
			if _, err := eng.Encrypt(bytes.NewReader(plain), &ct, profile, keys); err != nil {
				errs[idx] = err
				return
			}
			var pt bytes.Buffer
			if _, err := eng.Decrypt(bytes.NewReader(ct.Bytes()), &pt, profile, keys); err != nil {
				errs[idx] = err
				return
			}
			if !bytes.Equal(pt.Bytes(), plain) {
				t.Errorf("file %d: round-trip mismatch", idx)
			}
		}(i)
	}
	wg.Wait()
	for i, err := range errs {
		if err != nil {
			t.Errorf("file %d: %v", i, err)
		}
	}
}

func TestStreamParallelWorkerPoolSize(t *testing.T) {
	eng := streamParallelEngine{}
	maxProcs := runtime.GOMAXPROCS(0)

	cases := []struct {
		concurrency int
		want        int
	}{
		{1, 1},
		{0, 1},  // defensively clamped up to 1
		{-3, 1}, // defensively clamped up to 1
		{2, min(2, maxProcs)},
	}
	for _, tc := range cases {
		if got := eng.WorkerPoolSize(tc.concurrency); got != tc.want {
			t.Errorf("WorkerPoolSize(%d) = %d, want %d", tc.concurrency, got, tc.want)
		}
	}
	// Asking for more than GOMAXPROCS must cap at GOMAXPROCS (no oversubscribe).
	if got := eng.WorkerPoolSize(maxProcs + 5); got != maxProcs {
		t.Errorf("WorkerPoolSize(%d) = %d, want %d (capped at GOMAXPROCS)", maxProcs+5, got, maxProcs)
	}
}

func TestStreamParallelTimingNotSeparable(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	eng := streamParallelEngine{}
	profile := aes256Zlib("RSA-2048")

	var ct bytes.Buffer
	encT, err := eng.Encrypt(bytes.NewReader([]byte("hello")), &ct, profile, keys)
	if err != nil {
		t.Fatalf("encrypt: %v", err)
	}
	if encT.AsymNanos != NotSeparable || encT.SymNanos != NotSeparable {
		t.Errorf("asym/sym should be NotSeparable(-1), got asym=%d sym=%d", encT.AsymNanos, encT.SymNanos)
	}
}

func TestStreamParallelSupportsProfile(t *testing.T) {
	eng := streamParallelEngine{}
	if err := eng.SupportsProfile(aes256Zlib("RSA-2048")); err != nil {
		t.Errorf("supported profile rejected: %v", err)
	}
	bad := CryptoProfile{PubAlg: "RSA-2048", Cipher: "BLOWFISH", Compression: "ZLIB", Hash: "SHA-256"}
	if err := eng.SupportsProfile(bad); err == nil {
		t.Error("expected unsupported cipher to be rejected")
	}
}

// TestRunWithStreamParallelEngine drives the full shell end-to-end with the
// parallel engine over a multi-file corpus, confirming the worker-pool path
// produces correct, in-order, byte-for-byte round-trips.
func TestRunWithStreamParallelEngine(t *testing.T) {
	cmd := baseCommand(t, "go-stream-parallel")
	cmd.Concurrency = 4
	cmd.WarmupIterations = 0
	out, err := Run(cmd, time.Now(), quietLog)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	doc := findOp(out, "doc.txt")
	if doc == nil {
		t.Fatal("missing doc.txt operation")
	}
	if !doc.RoundTripOk {
		t.Errorf("doc.txt roundTripOk = false, want true")
	}
	if doc.EncryptMs == nil || doc.DecryptMs == nil {
		t.Fatal("doc.txt missing encrypt/decrypt timing")
	}
}
