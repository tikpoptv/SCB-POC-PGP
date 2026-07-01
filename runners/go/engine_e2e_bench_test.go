package main

// engine_e2e_bench_test.go measures the FULL PGP encrypt pipeline
// (RSA key-encryption + AES + ZLIB compression + literal packet + IO) through
// the real inmemSingleEngine, so the compression-stage win can be seen in
// end-to-end terms. Which zlib implementation runs depends on the go.mod
// `replace` directive:
//   - replace active  -> forked go-crypto -> klauspost/compress/zlib
//   - replace removed -> upstream go-crypto -> stdlib compress/zlib
//
// Run the same command with and without the replace directive to get an A/B:
//   go test -bench=BenchmarkEngineEncrypt -benchtime=50x -run='^$'

import (
	"bytes"
	"testing"
)

func BenchmarkEngineEncrypt(b *testing.B) {
	ks, err := LoadKeySet(repoKeysDir)
	if err != nil {
		b.Skipf("repo key set unavailable: %v", err)
	}
	if !ks.HasKeyFor("RSA-2048") {
		b.Skip("RSA-2048 key unavailable")
	}
	eng := inmemSingleEngine{}
	profile := aes256Zlib("RSA-2048")

	cases := []struct {
		name string
		data []byte
	}{
		{"txt-10KB", makeCompressibleText(10 << 10)},
		{"csv-10KB", makeCompressibleCSV(10 << 10)},
		{"txt-100KB", makeCompressibleText(100 << 10)},
		{"csv-100KB", makeCompressibleCSV(100 << 10)},
		{"pdf-100KB", makeIncompressible(100 << 10)},
	}

	for _, c := range cases {
		c := c
		b.Run(c.name, func(b *testing.B) {
			b.SetBytes(int64(len(c.data)))
			for i := 0; i < b.N; i++ {
				var ct bytes.Buffer
				if _, err := eng.Encrypt(bytes.NewReader(c.data), &ct, profile, ks); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
