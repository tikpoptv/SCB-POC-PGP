# Go PGP Runner

Go implementation of the PGP benchmark Runner (`Go_Runner`).

- Module: `github.com/poc-encryption/pgp-benchmark/go-runner`
- Go: 1.24+ (POC targets the latest stable Go; recorded in `Result_Report` per Req 2)
- PGP library (added in task 4.x): `github.com/ProtonMail/go-crypto/openpgp`

## Scope guard
No network/DB/web dependencies. The Runner reads a Command JSON from **stdin**
and writes a single `RunnerOutput` JSON to **stdout**; logs go to **stderr**
(see the Runner CLI Contract in `design.md`).

## Build & Run
```bash
cd runners/go
go build ./...
go vet ./...
echo '{"command":"run","variantId":"go-inmem-single"}' | go run .
```

## Planned variants (task 4.x)
- `go-inmem-single` — in-memory, single-thread
- `go-stream-single` — streaming, single-thread
- `go-stream-parallel` — streaming + worker pool = GOMAXPROCS (best candidate)
