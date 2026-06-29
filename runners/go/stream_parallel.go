package main

import (
	"bufio"
	"fmt"
	"io"
	"runtime"
	"sync"

	"github.com/ProtonMail/go-crypto/openpgp"
)

// streamParallelEngine is the "go-stream-parallel" variant: per file it is
// streaming (bounded, reusable buffer so peak memory stays constant), and across
// files it is parallel — it advertises a worker-pool size via ConcurrencyHint
// and the shell dispatches corpus files across a pool of that size. The engine
// is stateless and safe for concurrent use; the only shared state is a
// concurrency-safe sync.Pool of byte buffers that reduces GC pressure.
type streamParallelEngine struct{}

const streamParallelVariantID = "go-stream-parallel"

// parallelStreamBufferSize bounds peak memory per in-flight file, independent of
// file size.
const parallelStreamBufferSize = 64 * 1024

// bufferPool hands out reusable streaming-copy buffers, reused across the many
// files a worker pool churns through to keep allocation low.
var bufferPool = sync.Pool{
	New: func() any {
		b := make([]byte, parallelStreamBufferSize)
		return &b
	},
}

func init() {
	RegisterEngine(streamParallelVariantID, func() CryptoEngine { return streamParallelEngine{} })
}

func (streamParallelEngine) VariantID() string { return streamParallelVariantID }

// WorkerPoolSize sizes the shell's worker pool to the commanded concurrency
// level, clamped to at least 1 and capped at GOMAXPROCS so the pool never
// oversubscribes the CPUs.
func (streamParallelEngine) WorkerPoolSize(concurrency int) int {
	n := concurrency
	if n < 1 {
		n = 1
	}
	if max := runtime.GOMAXPROCS(0); n > max {
		n = max
	}
	return n
}

// Encrypt streams plaintext through the OpenPGP encrypt writer using a pooled,
// fixed-size buffer so peak memory is bounded regardless of file size.
func (e streamParallelEngine) Encrypt(plaintext io.Reader, out io.Writer, profile CryptoProfile, keys *KeySet) (Timing, error) {
	config, err := buildPacketConfig(profile)
	if err != nil {
		return Timing{}, err
	}
	recipients, err := keys.EncryptionKeys(profile.PubAlg)
	if err != nil {
		return Timing{}, fmt.Errorf("encryption keys: %w", err)
	}

	bufPtr := bufferPool.Get().(*[]byte)
	defer bufferPool.Put(bufPtr)
	buf := *bufPtr

	bw := bufio.NewWriterSize(out, parallelStreamBufferSize)

	nanos, cryptoErr := MeasureNanos(func() error {
		w, encErr := openpgp.Encrypt(bw, recipients, nil, binaryHints, config)
		if encErr != nil {
			return encErr
		}
		if _, encErr = io.CopyBuffer(w, plaintext, buf); encErr != nil {
			_ = w.Close()
			return encErr
		}
		// Close must be inside the timed region: it flushes the last block of
		// ciphertext.
		if encErr = w.Close(); encErr != nil {
			return encErr
		}
		return bw.Flush()
	})
	if cryptoErr != nil {
		return Timing{}, fmt.Errorf("openpgp stream encrypt: %w", cryptoErr)
	}

	return Timing{
		TotalNanos:    nanos,
		AsymNanos:     NotSeparable,
		SymNanos:      NotSeparable,
		HardwareAccel: hardwareAccelFor(profile.Cipher),
	}, nil
}

// Decrypt streams ciphertext through the OpenPGP reader using a pooled,
// fixed-size buffer. ReadMessage is lazy, so the copy that triggers symmetric
// decryption must sit inside the timed region.
func (e streamParallelEngine) Decrypt(ciphertext io.Reader, out io.Writer, profile CryptoProfile, keys *KeySet) (Timing, error) {
	config, err := buildPacketConfig(profile)
	if err != nil {
		return Timing{}, err
	}
	decryptKeys, err := keys.DecryptionKeys(profile.PubAlg)
	if err != nil {
		return Timing{}, fmt.Errorf("decryption keys: %w", err)
	}

	bufPtr := bufferPool.Get().(*[]byte)
	defer bufferPool.Put(bufPtr)
	buf := *bufPtr

	br := bufio.NewReaderSize(ciphertext, parallelStreamBufferSize)
	bw := bufio.NewWriterSize(out, parallelStreamBufferSize)

	nanos, cryptoErr := MeasureNanos(func() error {
		md, readErr := openpgp.ReadMessage(br, decryptKeys, nil, config)
		if readErr != nil {
			return readErr
		}
		if _, readErr = io.CopyBuffer(bw, md.UnverifiedBody, buf); readErr != nil {
			return readErr
		}
		return bw.Flush()
	})
	if cryptoErr != nil {
		return Timing{}, fmt.Errorf("openpgp stream decrypt: %w", cryptoErr)
	}

	return Timing{
		TotalNanos:    nanos,
		AsymNanos:     NotSeparable,
		SymNanos:      NotSeparable,
		HardwareAccel: hardwareAccelFor(profile.Cipher),
	}, nil
}

func (streamParallelEngine) SupportsProfile(profile CryptoProfile) error {
	if _, err := mapCipher(profile.Cipher); err != nil {
		return err
	}
	if _, err := mapCompression(profile.Compression); err != nil {
		return err
	}
	if _, err := mapHash(profile.Hash); err != nil {
		return err
	}
	return nil
}
