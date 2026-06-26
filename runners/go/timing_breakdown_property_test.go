package main

import (
	"bytes"
	"testing"

	"pgregory.net/rapid"
)

// Feature: pgp-encryption-benchmark-go-java, Property 23: breakdown asym/sym สอดคล้องกับเวลารวม
//
// Validates: Requirements 24.2
//
// For any operation that reports both an asymmetric and a symmetric time, the
// two are non-negative and their sum does not exceed the total time. When a
// Runner cannot isolate the two it records the NotSeparable sentinel and makes
// no claim, so the invariant holds vacuously. The invariant lives in the pure
// Timing.breakdownConsistent helper.

// genConsistentTiming produces plausible Timing values that must satisfy the
// consistency invariant, in both the claimed/separable and sentinel shapes.
func genConsistentTiming() *rapid.Generator[Timing] {
	return rapid.Custom(func(t *rapid.T) Timing {
		hw := rapid.Bool().Draw(t, "hardwareAccel")
		if rapid.Bool().Draw(t, "notSeparable") {
			total := rapid.Int64Range(0, 1_000_000_000).Draw(t, "total")
			return Timing{
				TotalNanos:    total,
				AsymNanos:     NotSeparable,
				SymNanos:      NotSeparable,
				HardwareAccel: hw,
			}
		}
		asym := rapid.Int64Range(0, 1_000_000_000).Draw(t, "asym")
		sym := rapid.Int64Range(0, 1_000_000_000).Draw(t, "sym")
		overhead := rapid.Int64Range(0, 1_000_000).Draw(t, "overhead")
		total := asym + sym + overhead
		if total <= 0 {
			total = 1
		}
		return Timing{
			TotalNanos:    total,
			AsymNanos:     asym,
			SymNanos:      sym,
			HardwareAccel: hw,
		}
	})
}

// TestProperty23BreakdownConsistentWithTotal is the rapid property: every
// plausible Timing satisfies the asym/sym-vs-total consistency invariant.
func TestProperty23BreakdownConsistentWithTotal(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		ti := genConsistentTiming().Draw(t, "timing")
		if !ti.breakdownConsistent() {
			t.Fatalf("breakdownConsistent() = false for plausible timing %+v "+
				"(asym=%d sym=%d total=%d)", ti, ti.AsymNanos, ti.SymNanos, ti.TotalNanos)
		}
		// When the breakdown is claimed, re-state the invariant explicitly.
		if ti.AsymNanos != NotSeparable && ti.SymNanos != NotSeparable {
			if ti.AsymNanos < 0 || ti.SymNanos < 0 {
				t.Fatalf("claimed breakdown has a negative part: asym=%d sym=%d", ti.AsymNanos, ti.SymNanos)
			}
			if ti.TotalNanos <= 0 {
				t.Fatalf("claimed breakdown with non-positive total: %d", ti.TotalNanos)
			}
			if ti.AsymNanos+ti.SymNanos > ti.TotalNanos {
				t.Fatalf("asym+sym (%d) exceeds total (%d)", ti.AsymNanos+ti.SymNanos, ti.TotalNanos)
			}
		}
	})
}

// TestProperty23RealEngineTimingConsistent runs the real Go variants against
// the repo Key_Set and asserts every Timing they return satisfies the invariant.
// The current variants report the NotSeparable sentinel, so it holds vacuously,
// but this guards against any future variant emitting an inconsistent breakdown.
func TestProperty23RealEngineTimingConsistent(t *testing.T) {
	keys := loadRepoKeys(t)

	payloads := map[string][]byte{
		"empty":      {},
		"short-text": []byte("the quick brown fox jumps over the lazy dog"),
		"binary":     binaryPayload(32 * 1024),
	}
	pubAlgs := []string{"RSA-2048", "RSA-4096"}

	for _, variantID := range RegisteredVariants() {
		for _, pubAlg := range pubAlgs {
			if !keys.HasKeyFor(pubAlg) {
				continue
			}
			profile := aes256Zlib(pubAlg)
			for name, plain := range payloads {
				t.Run(variantID+"/"+pubAlg+"/"+name, func(t *testing.T) {
					eng, ok := NewEngine(variantID)
					if !ok {
						t.Fatalf("variant %q not registered", variantID)
					}

					var ct bytes.Buffer
					encT, err := eng.Encrypt(bytes.NewReader(plain), &ct, profile, keys)
					if err != nil {
						t.Fatalf("encrypt: %v", err)
					}
					if !encT.breakdownConsistent() {
						t.Fatalf("encrypt timing breakdown inconsistent: %+v", encT)
					}

					var pt bytes.Buffer
					decT, err := eng.Decrypt(bytes.NewReader(ct.Bytes()), &pt, profile, keys)
					if err != nil {
						t.Fatalf("decrypt: %v", err)
					}
					if !decT.breakdownConsistent() {
						t.Fatalf("decrypt timing breakdown inconsistent: %+v", decT)
					}
				})
			}
		}
	}
}

// TestBreakdownConsistentRejectsInconsistent is a focused unit test ensuring the
// helper rejects known-bad claimed breakdowns and accepts the sentinel and
// well-formed claimed shapes.
func TestBreakdownConsistentRejectsInconsistent(t *testing.T) {
	cases := []struct {
		name string
		t    Timing
		want bool
	}{
		{"sentinel both", Timing{TotalNanos: 0, AsymNanos: NotSeparable, SymNanos: NotSeparable}, true},
		{"sentinel with total", Timing{TotalNanos: 1234, AsymNanos: NotSeparable, SymNanos: NotSeparable}, true},
		{"claimed valid sum below total", Timing{TotalNanos: 100, AsymNanos: 40, SymNanos: 30}, true},
		{"claimed valid sum equals total", Timing{TotalNanos: 100, AsymNanos: 60, SymNanos: 40}, true},
		{"claimed sum exceeds total", Timing{TotalNanos: 100, AsymNanos: 70, SymNanos: 40}, false},
		{"claimed negative asym", Timing{TotalNanos: 100, AsymNanos: -5, SymNanos: 10}, false},
		{"claimed negative sym", Timing{TotalNanos: 100, AsymNanos: 10, SymNanos: -5}, false},
		{"claimed non-positive total", Timing{TotalNanos: 0, AsymNanos: 0, SymNanos: 0}, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := tc.t.breakdownConsistent(); got != tc.want {
				t.Errorf("breakdownConsistent(%+v) = %v, want %v", tc.t, got, tc.want)
			}
		})
	}
}
