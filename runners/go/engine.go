package main

import (
	"fmt"
	"io"
	"sort"
	"sync"
	"time"
)

// Timing carries the crypto-only timing of a single encrypt or decrypt call, in
// nanoseconds (monotonic clock). Asym/Sym are NotSeparable when they cannot be
// measured separately.
type Timing struct {
	TotalNanos    int64
	AsymNanos     int64
	SymNanos      int64
	HardwareAccel bool
}

// NotSeparable is the sentinel for an asym/sym sub-measurement the engine cannot
// isolate.
const NotSeparable int64 = -1

// breakdownConsistent reports whether the asym/sym breakdown is consistent with
// the total time. If either part is NotSeparable, no claim is made and the
// invariant holds vacuously; otherwise both must be non-negative, the total
// positive, and asym+sym <= total.
func (t Timing) breakdownConsistent() bool {
	if t.AsymNanos == NotSeparable || t.SymNanos == NotSeparable {
		return true
	}
	if t.AsymNanos < 0 || t.SymNanos < 0 {
		return false
	}
	if t.TotalNanos <= 0 {
		return false
	}
	return t.AsymNanos+t.SymNanos <= t.TotalNanos
}

// CryptoEngine is the contract every Go Implementation_Variant implements.
// Encrypt/Decrypt time only the crypto call; key loading and file I/O are the
// shell's concern and are not part of the returned Timing.
type CryptoEngine interface {
	Encrypt(plaintext io.Reader, out io.Writer, profile CryptoProfile, keys *KeySet) (Timing, error)
	Decrypt(ciphertext io.Reader, out io.Writer, profile CryptoProfile, keys *KeySet) (Timing, error)
	VariantID() string
}

// ProfileSupporter is an optional interface an engine may implement to reject a
// Crypto_Profile it does not support (exit code 4).
type ProfileSupporter interface {
	SupportsProfile(profile CryptoProfile) error
}

// ConcurrencyHint is an optional interface a variant implements to tell the
// shell it benefits from processing corpus files across a worker pool. Engines
// that do not implement it are driven sequentially.
type ConcurrencyHint interface {
	// WorkerPoolSize returns how many corpus files to process concurrently for
	// the commanded concurrency level. A value of 1 means sequential.
	WorkerPoolSize(concurrency int) int
}

// engineRegistry maps variantId -> factory. Variants register themselves via
// RegisterEngine so the shell can dispatch without importing them directly.
var (
	registryMu      sync.RWMutex
	engineFactories = map[string]func() CryptoEngine{}
)

// RegisterEngine registers a variant factory under its id. Registering the same
// id twice panics.
func RegisterEngine(id string, factory func() CryptoEngine) {
	registryMu.Lock()
	defer registryMu.Unlock()
	if _, exists := engineFactories[id]; exists {
		panic(fmt.Sprintf("engine already registered: %q", id))
	}
	engineFactories[id] = factory
}

// NewEngine constructs the engine registered for id, or reports not found.
func NewEngine(id string) (CryptoEngine, bool) {
	registryMu.RLock()
	defer registryMu.RUnlock()
	factory, ok := engineFactories[id]
	if !ok {
		return nil, false
	}
	return factory(), true
}

// RegisteredVariants returns the sorted set of known variant ids.
func RegisteredVariants() []string {
	registryMu.RLock()
	defer registryMu.RUnlock()
	ids := make([]string, 0, len(engineFactories))
	for id := range engineFactories {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

// MeasureNanos runs fn and returns its wall-clock duration in nanoseconds using
// the monotonic clock.
func MeasureNanos(fn func() error) (int64, error) {
	start := time.Now()
	err := fn()
	return time.Since(start).Nanoseconds(), err
}

// runnerError pairs an error message with the process exit code the shell must
// return (contract/exit-codes.json).
type runnerError struct {
	code int
	msg  string
}

func (e *runnerError) Error() string { return e.msg }

func (e *runnerError) ExitCode() int { return e.code }

func errWithCode(code int, format string, args ...any) *runnerError {
	return &runnerError{code: code, msg: fmt.Sprintf(format, args...)}
}
