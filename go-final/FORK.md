# Local `go-crypto` fork

`third_party/go-crypto` is an intentional local copy of the ProtonMail `go-crypto` replacement used by the POC and labeled `v1.4.1` there. The top-level module pins `github.com/ProtonMail/go-crypto v1.4.1` and replaces it with this directory.

## Intentional source change

In `openpgp/packet/compressed.go`, OpenPGP `CompressionZLIB` reading and writing use:

```go
github.com/klauspost/compress/zlib
```

instead of the Go standard library `compress/zlib`. Both paths continue to read and emit the standard ZLIB/RFC 1950 representation carried by OpenPGP compressed-data packets, so the message format remains interoperable. OpenPGP `CompressionZIP` continues to use `compress/flate`, and BZIP2 behavior is unchanged.

The copied module preserves upstream license/provenance files, including `LICENSE`, `PATENTS`, `AUTHORS`, and `CONTRIBUTORS`.

## Verified upstream reference and current diff

The official module metadata was resolved with `go mod download -json github.com/ProtonMail/go-crypto@v1.4.1`:

- tag: `v1.4.1`
- upstream commit: `2e73b118bb72881b92b292f85cb2d057c3d7bef0`
- module sum: `h1:9RfcZHqEQUvP8RzecWEUafnZVtEvrBVL9BiF67IQOfM=`
- `go.mod` sum: `h1:e1OaTyu5SYVrO9gKOEhTc+5UcXtTUa+P3uLudwcgPqo=`

A `git diff --no-index --stat` comparison against the official module cache found six differing paths:

1. `openpgp/packet/compressed.go` — the intentional klauspost ZLIB source change.
2. `go.mod` — adds klauspost and was normalized by Go 1.24 tooling (`go 1.24`, `toolchain go1.24.3`).
3. `go.sum` — adds the pinned klauspost checksums.
4. `.github/test-suite/build_gosop.sh` — file-mode-only difference.
5. `.github/test-suite/build_gosop_v1.sh` — file-mode-only difference.
6. `.github/test-suite/prepare_config.sh` — file-mode-only difference.

## Provenance caveat

The upstream reference above makes this copy auditable, but release automation must reproduce and verify the complete diff and checksums rather than trust this prose. The local copy and all transitive dependencies still require normal security, license, and vulnerability review before production use.
