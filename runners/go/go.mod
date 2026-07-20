module github.com/poc-encryption/pgp-benchmark/go-runner

go 1.24

require (
	github.com/ProtonMail/go-crypto v1.4.1
	github.com/klauspost/compress v1.19.0
	golang.org/x/sys v0.35.0
	pgregory.net/rapid v1.3.0
)

require (
	github.com/cloudflare/circl v1.6.2 // indirect
	golang.org/x/crypto v0.41.0 // indirect
)

// EXPERIMENT: use a local fork of go-crypto whose compressed-data packet
// swaps stdlib compress/zlib for klauspost/compress/zlib (faster DEFLATE).
// Output stays standard RFC 1950, so Go<->Java<->gpg interop is preserved.
replace github.com/ProtonMail/go-crypto => ./third_party/go-crypto
