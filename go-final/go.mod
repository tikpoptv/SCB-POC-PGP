module github.com/poc-encryption/pgp-go

go 1.24

require github.com/ProtonMail/go-crypto v1.4.1

require (
	github.com/cloudflare/circl v1.6.2 // indirect
	github.com/klauspost/compress v1.19.0 // indirect
	golang.org/x/crypto v0.41.0 // indirect
	golang.org/x/sys v0.35.0 // indirect
)

replace github.com/ProtonMail/go-crypto => ./third_party/go-crypto
