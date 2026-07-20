# pgp-go

Go implementation สำหรับเข้ารหัสและถอดรหัสไฟล์ด้วย OpenPGP รองรับทั้ง CLI และ synchronous HTTP service API โค้ดในไดเรกทอรีนี้แยกจาก POC benchmark และไม่มี corpus, key สำหรับระบบจริง, benchmark runner หรือรายงานผลทดสอบ

## คุณสมบัติหลัก

- OpenPGP binary literal data
- AES-256, SHA-256 และ ZLIB compression level `-1`
- ZLIB ผ่าน `github.com/klauspost/compress/zlib`
- Streaming ต่อไฟล์ด้วย reusable buffer ขนาด 64 KiB
- Batch หลายไฟล์ด้วย bounded worker pool
- จำนวนไฟล์ default 20 และปรับได้สูงสุด 1000
- Output แบบ atomic no-clobber ต่อไฟล์
- รองรับ armored และ binary key ring
- รองรับ encrypted private key ผ่าน passphrase file
- จำกัด key ring 16 MiB
- จำกัด plaintext หลัง decrypt default 1 GiB ต่อไฟล์

> 64 KiB เป็นขนาด payload copy buffer ไม่ใช่เพดาน memory ทั้ง process เพราะ OpenPGP metadata และ key material ยังถูก parse โดย dependency

## ความต้องการ

- Go 1.24
- Filesystem ที่รองรับ hard link

## Build

```sh
go build -o pgp-go ./cmd/pgp-go
```

คำสั่งหลักมี 3 แบบ:

```text
pgp-go serve   # HTTP service API
pgp-go encrypt # CLI encrypt แบบไฟล์เดียวหรือ batch
pgp-go decrypt # CLI decrypt แบบไฟล์เดียวหรือ batch
```

## Service API

Service หนึ่ง process ทำ operation เดียว โดยกำหนด `encrypt` หรือ `decrypt` ตอนเริ่ม process ผู้เรียก API ส่งเฉพาะ relative file paths และไม่สามารถกำหนด operation, filesystem root, key หรือ passphrase ผ่าน request ได้

### เริ่ม Encrypt Service

```sh
./pgp-go serve \
  -operation encrypt \
  -listen 127.0.0.1:8080 \
  -input-root /srv/incoming \
  -output-root /srv/encrypted \
  -api-token-file /run/secrets/pgp-api-token \
  -public-key /run/secrets/recipient-public.asc \
  -max-files 20 \
  -workers 0 \
  -max-concurrent-jobs 1 \
  -job-timeout 30m
```
### เริ่ม Decrypt Service

```sh
./pgp-go serve \
  -operation decrypt \
  -listen 127.0.0.1:8080 \
  -input-root /srv/encrypted \
  -output-root /srv/decrypted \
  -api-token-file /run/secrets/pgp-api-token \
  -private-key /run/secrets/recipient-private.asc \
  -passphrase-file /run/secrets/private-key.pass \
  -max-output-bytes 1073741824 \
  -max-files 20 \
  -workers 0 \
  -max-concurrent-jobs 1 \
  -job-timeout 30m
```

### TLS

HTTP ที่ไม่ใช้ TLS อนุญาตเฉพาะ loopback เช่น `127.0.0.1` และ `::1` หาก listen บน address อื่นต้องระบุ certificate และ private key ครบทั้งคู่:

```sh
./pgp-go serve \
  -operation encrypt \
  -listen 0.0.0.0:8443 \
  -tls-cert-file /run/secrets/tls.crt \
  -tls-key-file /run/secrets/tls.key \
  -input-root /srv/incoming \
  -output-root /srv/encrypted \
  -api-token-file /run/secrets/pgp-api-token \
  -public-key /run/secrets/recipient-public.asc
```

### ส่งงาน

`POST /v1/jobs` เป็น synchronous API: response จะถูกส่งหลังจากทุกไฟล์ใน job สำเร็จหรือล้มเหลวแล้ว

```sh
curl -i http://127.0.0.1:8080/v1/jobs \
  -X POST \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  --data '{
    "version": 1,
    "files": [
      {
        "id": "file-1",
        "input": "documents/input.pdf",
        "output": "documents/input.pdf.pgp"
      }
    ]
  }'
```

Request schema:

```json
{
  "version": 1,
  "files": [
    {
      "id": "file-1",
      "input": "documents/input.pdf",
      "output": "documents/input.pdf.pgp"
    }
  ]
}
```

ข้อกำหนด:

- `id` ต้องไม่ว่าง, ไม่ซ้ำ และยาวไม่เกิน 256 bytes
- `input` และ `output` ต้องเป็น relative path ใต้ root ที่กำหนดตอน startup
- ไม่รับ absolute path, NUL, path traversal, unknown JSON field หรือ JSON ต่อท้าย
- Input ต้องมีอยู่และ directory แม่ของ output ต้องมีอยู่แล้ว
- Output ต้องยังไม่มีและห้าม canonical output ซ้ำกันใน job เดียว

### Response

สำเร็จทั้งหมดจะได้ `200 OK`:

```json
{
  "version": 1,
  "operation": "encrypt",
  "maxFiles": 20,
  "workers": 1,
  "results": [
    {
      "id": "file-1",
      "input": "documents/input.pdf",
      "output": "documents/input.pdf.pgp",
      "status": "success"
    }
  ]
}
```

หากมีบางไฟล์ล้มเหลวจะได้ `207 Multi-Status` ผลลัพธ์ยังเรียงตาม request และไฟล์อื่นจะทำงานต่อ:

```json
{
  "id": "file-1",
  "input": "documents/input.pdf",
  "output": "documents/input.pdf.pgp",
  "status": "failed",
  "errorCode": "operation_failed",
  "error": "operation failed"
}
```

HTTP API ใช้ข้อความผิดพลาดทั่วไปเพื่อไม่เปิดเผย absolute path หรือ internal error

### HTTP Status

| Status | ความหมาย |
|---|---|
| `200` | ทุกไฟล์สำเร็จ |
| `207` | มี operation failure อย่างน้อยหนึ่งไฟล์ |
| `400` | JSON ผิดรูปแบบ, unknown field หรือมี JSON ต่อท้าย |
| `401` | Bearer token ไม่ถูกต้อง |
| `404` | ไม่พบ endpoint |
| `405` | HTTP method ไม่ถูกต้อง |
| `413` | Request body เกิน 1 MiB |
| `415` | `Content-Type` ไม่ใช่ `application/json` |
| `422` | Job ไม่ผ่าน preflight validation |
| `429` | จำนวน in-flight jobs เต็ม |
| `500` | Internal server error |

Error ระดับ request ใช้ schema เดียวกัน:

```json
{
  "version": 1,
  "error": {
    "code": "invalid_job",
    "message": "job validation failed"
  }
}
```

### Health Check

```http
GET /healthz
```

```json
{"status":"ok"}
```

Health endpoint ไม่ต้องใช้ bearer token และไม่คืน operation, root หรือข้อมูล key
### Service Limits

| ค่า | Default | ขอบเขต |
|---|---:|---:|
| `-max-files` | `20` | `1–1000` ไฟล์ต่อ job |
| `-workers` | `0` | `0` ใช้ค่าจาก `GOMAXPROCS` |
| `-max-concurrent-jobs` | `1` | `1–100` jobs |
| `-job-timeout` | `30m` | ต้องมากกว่า `0` |
| Request body | — | 1 MiB |
| Request header | — | 16 KiB |
| Token file | — | 4 KiB |
| Key ring | — | 16 MiB |
| Decrypted plaintext | 1 GiB | ต่อไฟล์ |

Worker ต่อ job จะไม่เกินค่าที่ขอ, `GOMAXPROCS` หรือจำนวนไฟล์ จำนวน file transforms สูงสุดทั้ง process คือ `max-concurrent-jobs × effective workers`

เมื่อ request ถูกยกเลิกหรือหมดเวลา ระบบจะหยุด dispatch งานใหม่และหยุด streaming ที่ read/write boundary หากยกเลิกก่อน hard-link commit point จะไม่มี final output แต่หาก cancellation เกิดพร้อม commit พอดี output ที่เขียนครบแล้วอาจถูก publish สำเร็จและจะไม่ถูก rollback

## CLI

### ไฟล์เดียว

Encrypt:

```sh
./pgp-go encrypt \
  -in plaintext.bin \
  -out message.pgp \
  -public-key recipient-public.asc
```

Decrypt:

```sh
./pgp-go decrypt \
  -in message.pgp \
  -out plaintext.bin \
  -private-key recipient-private.asc \
  -passphrase-file private-key.pass \
  -max-output-bytes 1073741824
```

`-passphrase-file` ใช้เฉพาะ decrypt และตัด line ending ท้ายไฟล์หนึ่งชุด (`LF` หรือ `CRLF`) หาก private key ไม่ได้เข้ารหัสไม่ต้องระบุ flag นี้

### Batch

CLI batch ใช้ manifest schema เดียวกับ Service API:

```sh
./pgp-go encrypt \
  -manifest encrypt-manifest.json \
  -input-root ./incoming \
  -output-root ./encrypted \
  -public-key recipient-public.asc \
  -max-files 20 \
  -workers 0
```

```sh
./pgp-go decrypt \
  -manifest decrypt-manifest.json \
  -input-root ./encrypted \
  -output-root ./decrypted \
  -private-key recipient-private.asc \
  -passphrase-file private-key.pass \
  -max-output-bytes 1073741824 \
  -workers 4
```

CLI เขียน compact JSON report ไป stdout หากมี failure อย่างน้อยหนึ่งไฟล์จะเขียน report ให้ครบก่อน exit ด้วย code `1`

## Package API

แพ็กเกจ `pgpcrypto` เป็น streaming core ต่อไฟล์:

```go
keyFile, err := os.Open("recipient-public.asc")
if err != nil {
    return err
}
defer keyFile.Close()

encryptor, err := pgpcrypto.NewEncryptor(keyFile)
if err != nil {
    return err
}

return encryptor.Encrypt(destination, source)
```

สำหรับ decrypt ใช้ `pgpcrypto.NewDecryptor(privateKeyReader, passphrase, config)` โดย `nil` config ใช้ plaintext limit default 1 GiB เมธอด `Encrypt` และ `Decrypt` ใช้พร้อมกันหลาย goroutine ได้หลัง constructor สำเร็จ

Package API อาจเขียน destination บางส่วนก่อนคืน error ผู้เรียกที่ต้องการ atomic file ควรใช้ temporary file ก่อน publish หรือใช้ CLI/Service API

## Output Safety

- ไม่มี overwrite mode
- Destination ที่มีอยู่แล้วรวมถึง symlink จะถูกปฏิเสธ
- Temporary output ใช้ permission `0600`
- Final output ถูก publish ด้วย hard link แบบ atomic no-clobber
- Batch เป็น atomic ต่อไฟล์ ไม่ใช่ transaction ทั้ง job
- Output ที่สำเร็จจะคงอยู่แม้ไฟล์อื่นใน job ล้มเหลว

ข้อจำกัด:

- Filesystem ต้องรองรับ hard link
- ไม่มี directory `fsync` จึงไม่รับประกัน crash durability
- Canonical-path validation ป้องกัน traversal จาก request แต่ไม่ใช่ filesystem sandbox
- Input/output roots และ ancestor directories ต้องไม่ถูก process ที่ไม่น่าเชื่อถือ rename หรือสลับ symlink ระหว่างทำงาน

## Security Notes

- Service API บังคับ Bearer authentication สำหรับ `POST /v1/jobs`
- Token ถูกเปรียบเทียบแบบ constant-time และต้องเป็น single-line value ที่ไม่ว่าง
- ห้ามเก็บ operational key, token หรือ passphrase ใน source code, command line หรือ log
- Private key ที่ปลดล็อกแล้วอยู่ใน process memory ตลอดอายุ service
- Ciphertext มี integrity protection แต่ระบบนี้ไม่มี signing และไม่ยืนยันตัวผู้ส่ง
- ควรให้ผู้เชี่ยวชาญตรวจ cryptography, key lifecycle, dependency และ threat model ก่อนใช้งาน production

โฟลเดอร์นี้ไม่มี operational key หรือ passphrase ของระบบจริง แต่ local fork อาจมี test fixtures จาก upstream ซึ่ง secret scanner สามารถรายงานได้

## Local `go-crypto` Fork

`third_party/go-crypto` เป็น local fork ของ `github.com/ProtonMail/go-crypto v1.4.1` เพื่อเปลี่ยน OpenPGP ZLIB implementation จาก standard library เป็น `github.com/klauspost/compress/zlib v1.19.0` โดยยังคงรูปแบบ ZLIB/RFC 1950 และ OpenPGP interoperability

รายละเอียด upstream commit, checksum และ intentional diff อยู่ใน [FORK.md](FORK.md)

## Validation และ Security Scan

```sh
go build ./...
go vet ./...
go test ./...
go test -race ./...
(cd third_party/go-crypto && go test ./...)
govulncheck ./...  # ต้องติดตั้ง govulncheck ก่อน
```
