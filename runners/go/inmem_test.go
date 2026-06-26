package main

import (
	"bytes"
	"strings"
	"testing"
)

// loadRepoKeys loads the shared Key_Set checked into the repo (../../keys).
func loadRepoKeys(t *testing.T) *KeySet {
	t.Helper()
	ks, err := LoadKeySet(repoKeysDir)
	if err != nil {
		t.Skipf("repo key set unavailable (%s): %v", repoKeysDir, err)
	}
	return ks
}

func aes256Zlib(pubAlg string) CryptoProfile {
	return CryptoProfile{PubAlg: pubAlg, Cipher: "AES-256", Compression: "ZLIB", Hash: "SHA-256"}
}

func TestInmemVariantID(t *testing.T) {
	if id := (inmemSingleEngine{}).VariantID(); id != "go-inmem-single" {
		t.Errorf("VariantID() = %q, want go-inmem-single", id)
	}
}

func TestInmemRegistered(t *testing.T) {
	eng, ok := NewEngine("go-inmem-single")
	if !ok {
		t.Fatal("go-inmem-single not registered")
	}
	if _, isSup := eng.(ProfileSupporter); !isSup {
		t.Error("engine should implement ProfileSupporter")
	}
}

// TestInmemRoundTripByteForByte is the core correctness gate: for the supported
// RSA key sizes and representative payloads, decrypt(encrypt(x)) == x.
func TestInmemRoundTripByteForByte(t *testing.T) {
	keys := loadRepoKeys(t)
	eng := inmemSingleEngine{}

	payloads := map[string][]byte{
		"empty":        {},
		"short-text":   []byte("the quick brown fox jumps over the lazy dog"),
		"compressible": bytes.Repeat([]byte("AAAA-BBBB-CCCC-"), 5000),
		"binary":       binaryPayload(64 * 1024),
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

// TestInmemRoundTripNoCompression confirms the NONE compression mapping also
// round-trips.
func TestInmemRoundTripNoCompression(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	eng := inmemSingleEngine{}
	profile := CryptoProfile{PubAlg: "RSA-2048", Cipher: "AES-256", Compression: "NONE", Hash: "SHA-256"}
	plain := []byte("no compression payload \x00\x01\x02 with binary bytes")

	var ct bytes.Buffer
	if _, err := eng.Encrypt(bytes.NewReader(plain), &ct, profile, keys); err != nil {
		t.Fatalf("encrypt: %v", err)
	}
	var pt bytes.Buffer
	if _, err := eng.Decrypt(bytes.NewReader(ct.Bytes()), &pt, profile, keys); err != nil {
		t.Fatalf("decrypt: %v", err)
	}
	if !bytes.Equal(pt.Bytes(), plain) {
		t.Errorf("round-trip mismatch with NONE compression")
	}
}

// TestInmemTimingSeparationNotSeparable asserts the asym/sym breakdown reports
// the not-separable sentinel for the high-level OpenPGP API.
func TestInmemTimingSeparationNotSeparable(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	eng := inmemSingleEngine{}
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

func TestInmemSupportsProfile(t *testing.T) {
	eng := inmemSingleEngine{}

	if err := eng.SupportsProfile(aes256Zlib("RSA-2048")); err != nil {
		t.Errorf("supported profile rejected: %v", err)
	}

	cases := []struct {
		name    string
		profile CryptoProfile
		wantSub string
	}{
		{"bad cipher", CryptoProfile{PubAlg: "RSA-2048", Cipher: "BLOWFISH", Compression: "ZLIB", Hash: "SHA-256"}, "unsupported cipher"},
		{"bad compression", CryptoProfile{PubAlg: "RSA-2048", Cipher: "AES-256", Compression: "BZIP2", Hash: "SHA-256"}, "unsupported compression"},
		{"bad hash", CryptoProfile{PubAlg: "RSA-2048", Cipher: "AES-256", Compression: "ZLIB", Hash: "MD5"}, "unsupported hash"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := eng.SupportsProfile(tc.profile)
			if err == nil {
				t.Fatalf("expected error for %s", tc.name)
			}
			re, ok := err.(*runnerError)
			if !ok {
				t.Fatalf("expected *runnerError, got %T", err)
			}
			if re.code != exitUnsupportedProf {
				t.Errorf("exit code = %d, want %d", re.code, exitUnsupportedProf)
			}
			if !strings.Contains(re.msg, tc.wantSub) {
				t.Errorf("error %q does not contain %q", re.msg, tc.wantSub)
			}
		})
	}
}

func TestInmemHardwareAccelOnlyForAES(t *testing.T) {
	if got := hardwareAccelFor("CHACHA20"); got {
		t.Error("non-AES cipher must not report hardware accel")
	}
	// For AES the value must agree with the CPU feature detector (runs on any arch).
	if got, want := hardwareAccelFor("AES-256"), aesHardwareAvailable(); got != want {
		t.Errorf("AES hardware accel = %v, want %v", got, want)
	}
}

// binaryPayload builds a deterministic pseudo-binary buffer of n bytes.
func binaryPayload(n int) []byte {
	b := make([]byte, n)
	for i := range b {
		b[i] = byte((i*31 + 7) & 0xff)
	}
	return b
}
