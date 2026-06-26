package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestStreamVariantID(t *testing.T) {
	if id := (streamSingleEngine{}).VariantID(); id != "go-stream-single" {
		t.Errorf("VariantID() = %q, want go-stream-single", id)
	}
}

func TestStreamRegistered(t *testing.T) {
	eng, ok := NewEngine("go-stream-single")
	if !ok {
		t.Fatal("go-stream-single not registered")
	}
	if _, isSup := eng.(ProfileSupporter); !isSup {
		t.Error("engine should implement ProfileSupporter")
	}
}

// TestStreamRoundTripByteForByte is the core correctness gate: for the supported
// RSA key sizes and representative payloads, the streaming variant's
// decrypt(encrypt(x)) == x.
func TestStreamRoundTripByteForByte(t *testing.T) {
	keys := loadRepoKeys(t)
	eng := streamSingleEngine{}

	payloads := map[string][]byte{
		"empty":        {},
		"short-text":   []byte("the quick brown fox jumps over the lazy dog"),
		"compressible": bytes.Repeat([]byte("AAAA-BBBB-CCCC-"), 5000),
		"binary":       binaryPayload(64 * 1024),
		// Larger than streamBufferSize so the data spans many buffer flushes.
		"multi-buffer": binaryPayload(7*streamBufferSize + 123),
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

// TestStreamRoundTripNoCompression confirms the NONE compression mapping also
// round-trips through the streaming pipeline.
func TestStreamRoundTripNoCompression(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	eng := streamSingleEngine{}
	profile := CryptoProfile{PubAlg: "RSA-2048", Cipher: "AES-256", Compression: "NONE", Hash: "SHA-256"}
	plain := []byte("no compression streaming payload \x00\x01\x02 with binary bytes")

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

// TestStreamCrossDecryptWithInmem confirms the streaming and in-memory variants
// produce interoperable OpenPGP output: ciphertext from one decrypts with the
// other byte-for-byte.
func TestStreamCrossDecryptWithInmem(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	profile := aes256Zlib("RSA-2048")
	plain := binaryPayload(3*streamBufferSize + 17)

	// Encrypt with streaming, decrypt with in-memory.
	var ct bytes.Buffer
	if _, err := (streamSingleEngine{}).Encrypt(bytes.NewReader(plain), &ct, profile, keys); err != nil {
		t.Fatalf("stream encrypt: %v", err)
	}
	var pt bytes.Buffer
	if _, err := (inmemSingleEngine{}).Decrypt(bytes.NewReader(ct.Bytes()), &pt, profile, keys); err != nil {
		t.Fatalf("inmem decrypt: %v", err)
	}
	if !bytes.Equal(pt.Bytes(), plain) {
		t.Error("stream->inmem round-trip mismatch")
	}

	// Encrypt with in-memory, decrypt with streaming.
	var ct2 bytes.Buffer
	if _, err := (inmemSingleEngine{}).Encrypt(bytes.NewReader(plain), &ct2, profile, keys); err != nil {
		t.Fatalf("inmem encrypt: %v", err)
	}
	var pt2 bytes.Buffer
	if _, err := (streamSingleEngine{}).Decrypt(bytes.NewReader(ct2.Bytes()), &pt2, profile, keys); err != nil {
		t.Fatalf("stream decrypt: %v", err)
	}
	if !bytes.Equal(pt2.Bytes(), plain) {
		t.Error("inmem->stream round-trip mismatch")
	}
}

// TestStreamTimingSeparationNotSeparable asserts the asym/sym breakdown reports
// the not-separable sentinel.
func TestStreamTimingSeparationNotSeparable(t *testing.T) {
	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable")
	}
	eng := streamSingleEngine{}
	profile := aes256Zlib("RSA-2048")

	var ct bytes.Buffer
	encT, err := eng.Encrypt(bytes.NewReader([]byte("hello stream")), &ct, profile, keys)
	if err != nil {
		t.Fatalf("encrypt: %v", err)
	}
	if encT.AsymNanos != NotSeparable || encT.SymNanos != NotSeparable {
		t.Errorf("asym/sym should be NotSeparable(-1), got asym=%d sym=%d", encT.AsymNanos, encT.SymNanos)
	}
}

func TestStreamSupportsProfile(t *testing.T) {
	eng := streamSingleEngine{}

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
