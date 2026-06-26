package main

import (
	"bytes"
	"testing"

	"pgregory.net/rapid"
)

// Feature: pgp-encryption-benchmark-go-java, Property 1: Round-trip คืนข้อมูลเดิมแบบ byte-for-byte
//
// For any byte payload and every registered Go variant and supported RSA key
// type, decrypt(encrypt(x)) must return x byte-for-byte.

// roundTripVariants are the Go variant ids exercised by the property.
var roundTripVariants = []string{
	"go-inmem-single",
	"go-stream-single",
	"go-stream-parallel",
}

// roundTripPubAlgs are the supported asymmetric key types backed by the repo
// Key_Set.
var roundTripPubAlgs = []string{"RSA-2048", "RSA-4096"}

// genPayload produces arbitrary byte payloads: empty, small/large, and content
// ranging from highly compressible to incompressible, plus mixtures.
func genPayload(t *rapid.T) []byte {
	kind := rapid.SampledFrom([]string{"random", "compressible", "mixed", "empty"}).Draw(t, "kind")
	switch kind {
	case "empty":
		return []byte{}
	case "compressible":
		motif := rapid.SliceOfN(rapid.Byte(), 1, 8).Draw(t, "motif")
		reps := rapid.IntRange(0, 4000).Draw(t, "reps")
		return bytes.Repeat(motif, reps)
	case "mixed":
		motif := rapid.SliceOfN(rapid.Byte(), 1, 16).Draw(t, "motif")
		reps := rapid.IntRange(0, 500).Draw(t, "reps")
		noise := rapid.SliceOfN(rapid.Byte(), 0, 2048).Draw(t, "noise")
		return append(bytes.Repeat(motif, reps), noise...)
	default: // "random"
		return rapid.SliceOfN(rapid.Byte(), 0, 16*1024).Draw(t, "random")
	}
}

// TestRoundTripProperty is the rapid property test for Property 1.
func TestRoundTripProperty(t *testing.T) {
	keys := loadRepoKeys(t)

	rapid.Check(t, func(rt *rapid.T) {
		variantID := rapid.SampledFrom(roundTripVariants).Draw(rt, "variant")
		pubAlg := rapid.SampledFrom(roundTripPubAlgs).Draw(rt, "pubAlg")
		if !keys.HasKeyFor(pubAlg) {
			rt.Skipf("no key for %s in repo set", pubAlg)
		}

		eng, ok := NewEngine(variantID)
		if !ok {
			rt.Fatalf("variant %q not registered", variantID)
		}

		plain := genPayload(rt)
		profile := aes256Zlib(pubAlg)

		var ct bytes.Buffer
		if _, err := eng.Encrypt(bytes.NewReader(plain), &ct, profile, keys); err != nil {
			rt.Fatalf("%s/%s encrypt failed (len=%d): %v", variantID, pubAlg, len(plain), err)
		}

		var pt bytes.Buffer
		if _, err := eng.Decrypt(bytes.NewReader(ct.Bytes()), &pt, profile, keys); err != nil {
			rt.Fatalf("%s/%s decrypt failed (len=%d): %v", variantID, pubAlg, len(plain), err)
		}

		if !bytes.Equal(pt.Bytes(), plain) {
			rt.Fatalf("%s/%s round-trip mismatch: got %d bytes, want %d bytes",
				variantID, pubAlg, pt.Len(), len(plain))
		}
	})
}
