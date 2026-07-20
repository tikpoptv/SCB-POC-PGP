# pgp-go (Final Go Deliverable)

ไดเรกทอรีนี้คือ implementation ภาษา Go ฉบับสุดท้ายที่แยกออกจาก POC benchmark ให้เป็นแพ็กเกจที่นำกลับมาใช้ได้และ CLI สำหรับไฟล์ ไม่ใช่ benchmark runner และไม่มี timing, variant registry, corpus หรือรายงาน benchmark

## โปรไฟล์การเข้ารหัส

ค่าถูกกำหนดตายตัวตามผลชนะของ POC:

- OpenPGP binary literal data (`b`)
- AES-256
- ZLIB ผ่าน local fork ที่ใช้ `github.com/klauspost/compress/zlib`
- SHA-256
- compression level `-1` (default)
- streaming payload ด้วย buffer 64 KiB ที่ใช้ซ้ำได้ โดยไม่อ่านไฟล์ทั้งหมดเข้า memory
- จำกัด key input ที่ 16 MiB ต่อ key ring
- decryption จำกัด plaintext แบบ inclusive ที่ 1 GiB โดย default และตั้ง internal decompression budget แยกเพื่อเผื่อ OpenPGP packet framing

> ขอบเขต memory 64 KiB ใช้กับการ copy payload เท่านั้น metadata ของ OpenPGP/key ถูก parse โดย dependency และไม่อยู่ภายใต้ขอบเขต buffer นี้ จึงยังต้องทำ threat-model/security review ก่อนรับ input จากแหล่งที่ไม่เชื่อถือ

พฤติกรรม benchmark ชื่อ `go-stream-parallel` ถูกนำมาใช้เป็นสองชั้น: แพ็กเกจ `pgpcrypto` ทำ streaming ต่อไฟล์ ส่วน CLI batch จัด bounded worker pool สำหรับหลายไฟล์ โดยจำกัดจำนวนงานพร้อมกันตามค่าที่ขอ, `GOMAXPROCS` และจำนวนไฟล์

## Build และใช้งาน CLI

ต้องใช้ Go 1.24:

```sh
go build -o pgp-go ./cmd/pgp-go

./pgp-go encrypt \
  -in plaintext.bin \
  -out message.pgp \
  -public-key recipient-public.asc

./pgp-go decrypt \
  -in message.pgp \
  -out plaintext.bin \
  -private-key recipient-private.asc \
  -passphrase-file private-key.pass \
  -max-output-bytes 1073741824
```

`-passphrase-file` ใช้ได้เฉพาะ `decrypt` และ CLI ไม่มี flag สำหรับส่ง passphrase โดยตรง เพื่อลดการรั่วผ่าน process list โดยจะตัด line ending หนึ่งชุด (`LF` หรือ `CRLF`) ท้ายไฟล์ passphrase หาก private key ไม่ได้เข้ารหัสให้ละ flag นี้ได้
CLI รับเฉพาะ input/output แบบไฟล์ ปฏิเสธกรณี input และ output resolve เป็นไฟล์เดียวกัน และ **ไม่รองรับ overwrite**: destination ที่มีอยู่แล้วรวมถึง symlink จะถูกปฏิเสธเสมอ CLI resolve directory ปลายทางครั้งเดียว เขียน temporary file mode `0600` ใน directory นั้น แล้ว publish แบบ atomic no-clobber ด้วย hard link เมื่อเกิดข้อผิดพลาดจะลบ temporary output และไม่ทิ้ง final output ที่เขียนไม่ครบ วิธีนี้ไม่ใช่ crash-durability guarantee เพราะไม่ได้ `fsync` directory และ filesystem ต้องรองรับ hard link

## Batch หลายไฟล์

คำสั่ง `encrypt` และ `decrypt` เดิมรองรับ batch ด้วย `-manifest` โดยห้ามใช้ร่วมกับ `-in` หรือ `-out` manifest v1 เป็น JSON รูปแบบตายตัวและไม่รับ field ที่ไม่รู้จักหรือ JSON ต่อท้าย:

```json
{"version":1,"files":[{"id":"file-1","input":"documents/input.pdf","output":"documents/input.pdf.pgp"}]}
```

`id` ต้องไม่ว่างหลัง trim และยาวไม่เกิน 256 bytes ส่วน `input`/`output` ต้องเป็น relative path ที่ไม่ว่าง ห้าม absolute path และ path traversal ทุก batch ต้องระบุ `-input-root` กับ `-output-root`; CLI จะ resolve root และ symlink ล่วงหน้า ตรวจว่า canonical path ยังอยู่ภายใน root, input มีอยู่จริง, output ยังไม่มีแม้เป็น symlink และตรวจ duplicate ID/canonical output ก่อนเริ่มแปลงไฟล์ใด ๆ directory แม่ของ output ต้องมีอยู่แล้ว

ตัวอย่างเข้ารหัส:

```sh
./pgp-go encrypt \
  -manifest encrypt-manifest.json \
  -input-root ./incoming \
  -output-root ./encrypted \
  -public-key recipient-public.asc \
  -max-files 20 \
  -workers 0
```

ตัวอย่างถอดรหัส (manifest ระบุ path ของ ciphertext ใต้ input root และ plaintext ใต้ output root):

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

จำนวนไฟล์สูงสุด default เท่ากับ **20** ปรับได้ด้วย `-max-files` เป็นค่าบวกแต่ห้ามเกิน safety cap 1000; batch ว่างหรือเกิน limit จะถูกปฏิเสธก่อนทำงาน `-workers 0` หมายถึงเลือกอัตโนมัติจาก `GOMAXPROCS` หากกำหนดค่าบวก จำนวน worker ที่ใช้จริงจะไม่เกินค่าที่ขอ และทุกกรณีจะไม่เกิน `GOMAXPROCS` หรือจำนวนไฟล์ โดยใช้อย่างน้อย 1 worker ค่า `-max-output-bytes` ของ `decrypt` บังคับแยกต่อไฟล์ ไม่ใช่ยอดรวมทั้ง batch

เมื่อ manifest และ config ถูกต้อง CLI จะเขียน compact JSON หนึ่ง object ไป stdout โดยมี `version`, `operation`, `maxFiles`, `workers` และ `results` ที่เรียงตามลำดับใน manifest เสมอ แต่ละผลมีสถานะ `success` หรือ `failed`; failure ใช้ `errorCode` คงที่ `operation_failed` พร้อมข้อความที่ sanitize แล้ว ไฟล์หนึ่งล้มเหลวจะไม่ยกเลิกไฟล์อื่น และ process exit 1 หลังเขียน JSON หากมี failure อย่างน้อยหนึ่งไฟล์

Batch เป็น **atomic ต่อไฟล์ ไม่ใช่ all-or-nothing**: แต่ละไฟล์ยังใช้ temporary mode `0600` และ publish แบบ hard-link no-clobber จึงไม่มี final file ที่เขียนไม่ครบจาก job ที่ล้มเหลว แต่ output ของ job ที่สำเร็จจะคงอยู่แม้ job อื่นล้มเหลว

การตรวจ canonical path ป้องกัน path traversal จากค่าใน manifest แต่ไม่ใช่ filesystem sandbox สำหรับ directory tree ที่ process อื่นสามารถ rename หรือเปลี่ยน symlink ระหว่างรันได้ ดังนั้น `-input-root`, `-output-root` และ ancestor directories ต้องอยู่ภายใต้การควบคุมของระบบที่เรียก CLI ตลอดอายุของ batch

## Service API แบบ synchronous

คำสั่ง `serve` เปิด HTTP API โดยกำหนด operation ตายตัวตอนเริ่ม process ผู้เรียก API ไม่สามารถเลือก operation, root, key หรือ passphrase ใน request ได้ API ทำงานแบบ **synchronous**: `POST /v1/jobs` จะรอจนทุกไฟล์สำเร็จหรือล้มเหลวแล้วจึงส่ง batch report กลับ

ตัวอย่าง service สำหรับ encrypt (คำสั่งเต็ม):

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

ตัวอย่าง service สำหรับ decrypt (คำสั่งเต็ม):

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

`-listen` มี default `127.0.0.1:8080`; HTTP ที่ไม่ใช้ TLS อนุญาตเฉพาะ loopback เท่านั้น หาก bind ไปยัง address อื่นต้องระบุ `-tls-cert-file` และ `-tls-key-file` ครบทั้งคู่ และเรียก API ผ่าน HTTPS เพื่อป้องกัน bearer token กับ path metadata ระหว่างส่งข้อมูล `-operation`, `-input-root`, `-output-root` และ `-api-token-file` เป็นค่าบังคับ รวมถึง `-public-key` สำหรับ encrypt หรือ `-private-key` สำหรับ decrypt ส่วน `-passphrase-file` ใช้ได้เฉพาะ decrypt ระบบจะ resolve และตรวจ root, อ่าน bearer token และ parse keyเพียงครั้งเดียวก่อนเริ่มรับ request พร้อมล้าง passphrase bytes หลัง parse key

ตรวจสุขภาพได้โดยไม่ต้องส่ง token:

```http
GET /healthz
```

response `200 OK`:

```json
{"status":"ok"}
```

ส่ง job โดยใช้ manifest v1 เดียวกับ CLI ทุก path ต้องเป็น relative path ใต้ root ที่กำหนดตอน startup:

```sh
curl -i http://127.0.0.1:8080/v1/jobs \
  -X POST \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  --data '{"version":1,"files":[{"id":"file-1","input":"documents/input.pdf","output":"documents/input.pdf.pgp"}]}'
```

request รับเฉพาะ JSON รูปแบบนี้ ไม่รับ field ที่ไม่รู้จักหรือ JSON ต่อท้าย และไม่รับ operation, root, key หรือ passphrase:

```json
{"version":1,"files":[{"id":"file-1","input":"documents/input.pdf","output":"documents/input.pdf.pgp"}]}
```

เมื่อทุกไฟล์สำเร็จจะได้ `200 OK`; ถ้ามี operation failure อย่างน้อยหนึ่งไฟล์จะได้ `207 Multi-Status` พร้อม report ที่เรียงตาม manifest เสมอ:

```json
{"version":1,"operation":"encrypt","maxFiles":20,"workers":1,"results":[{"id":"file-1","input":"documents/input.pdf","output":"documents/input.pdf.pgp","status":"success"}]}
```

failure ต่อไฟล์ใน HTTP ใช้ข้อความทั่วไปที่คงที่และไม่เปิดเผย absolute path หรือ internal error:

```json
{"id":"file-1","input":"documents/input.pdf","output":"documents/input.pdf.pgp","status":"failed","errorCode":"operation_failed","error":"operation failed"}
```

error ระดับ request ใช้ schema คงที่:

```json
{"version":1,"error":{"code":"invalid_job","message":"job validation failed"}}
```

HTTP status ที่ API ใช้คือ `200` เมื่อสำเร็จทั้งหมด, `207` เมื่อมี per-file operation failure, `400` สำหรับ JSON ผิดรูปแบบ/unknown field/trailing JSON, `401` เมื่อ bearer token ไม่ถูกต้อง, `405` เมื่อ method ไม่ถูกต้อง, `413` เมื่อ body เกิน 1 MiB, `415` เมื่อ `Content-Type` ไม่ใช่ `application/json`, `422` เมื่อ JSON ถูกต้องแต่ job ไม่ผ่าน preflight validation, `429` เมื่อจำนวน in-flight jobs เต็ม และ `500` สำหรับ internal error

ไฟล์ token จำกัด 4 KiB ตัด line ending ท้ายไฟล์หนึ่งชุด (`LF` หรือ `CRLF`) และต้องไม่ว่าง `POST /v1/jobs` ต้องส่ง `Authorization: Bearer <token>`; service เปรียบเทียบ token แบบ constant-time และไม่คืน config ที่ละเอียดอ่อนผ่าน health endpoint

`-max-files` default 20 และมี hard cap 1000; request body จำกัด 1 MiB; header จำกัด 16 KiB; `-workers 0` เลือกจาก `GOMAXPROCS` และจำนวน worker จริงต่อ job จะถูก clamp ด้วย `GOMAXPROCS` กับจำนวนไฟล์ `-max-concurrent-jobs` default 1 ต้องเป็นค่าบวกและไม่เกิน 100 ส่วน `-job-timeout` default `30m` และต้องเป็นค่าบวก ดังนั้นจำนวน file transforms ที่ active พร้อมกันสูงสุดของ process คือ `max-concurrent-jobs * effective workers` การยกเลิก request, timeout หรือ graceful shutdown จะหยุด dispatch งานใหม่และหยุด streaming ที่ read/write boundary พร้อมลบ temporary file หาก cancellation เกิดก่อน hard-link commit point; หาก commit เกิดขึ้นพร้อม cancellation พอดี final output ที่เขียนครบแล้วอาจถูก publish สำเร็จและจะไม่ถูก rollback

## Package API

รองรับ public/private key ring ทั้ง ASCII-armored และ binary constructor ฝั่ง encrypt ต้องการเฉพาะ public key ส่วน constructor ฝั่ง decrypt รับ passphrase แบบ optional และถอดรหัสทั้ง primary key กับ subkeys ที่เข้ารหัส

```go
package main

import (
    "os"

    "github.com/poc-encryption/pgp-go/pgpcrypto"
)

func encrypt() error {
    keyFile, err := os.Open("recipient-public.asc")
    if err != nil {
        return err
    }
    defer keyFile.Close()

    encryptor, err := pgpcrypto.NewEncryptor(keyFile)
    if err != nil {
        return err
    }
    src, err := os.Open("plaintext.bin")
    if err != nil {
        return err
    }
    defer src.Close()
    dst, err := os.Create("message.pgp")
    if err != nil {
        return err
    }
    defer dst.Close()
    return encryptor.Encrypt(dst, src)
}
```

ใช้ `pgpcrypto.NewDecryptor(privateKeyReader, passphrase, nil)` เพื่อใช้ขีดจำกัด plaintext 1 GiB แบบ inclusive หรือส่ง `&pgpcrypto.DecryptConfig{MaxOutputBytes: n}` โดย `n` ต้องมากกว่าศูนย์ แล้วเรียก `Decrypt(dst, src)` ค่า internal decompression budget จะสูงกว่า plaintext limit เล็กน้อยเพื่อรองรับ OpenPGP literal-packet framing แต่ plaintext ที่เขียนจะไม่เกิน `MaxOutputBytes`

private key ring ต้องไม่เข้ารหัสทั้งหมด หรือ encrypted primary/subkey ทุกตัวใน ring ต้องปลดล็อกได้ด้วย passphrase เดียวที่ส่งให้ constructor

เมธอด package เป็น streaming API แต่ destination อาจมีข้อมูลบางส่วนเมื่อ library คืน error (รวม MDC/integrity error ที่พบตอนอ่านถึง EOF) caller ที่ต้องการ atomic file ต้องเขียน temporary file และ rename เอง หรือใช้ CLI นี้

## Static/security scanning

```sh
go vet ./...
go test ./...
(cd third_party/go-crypto && go test ./...)
govulncheck ./...  # เมื่อได้ติดตั้ง govulncheck แล้ว
```
## ข้อควรระวังสำหรับ production

โฟลเดอร์นี้ไม่มี operational/application key หรือ passphrase ของระบบจริง แต่ vendored dependency มี non-production test key fixtures จาก upstream ซึ่ง secret scanner อาจรายงาน ระบบจริงควรเก็บ key ใน KMS หรือ secret manager ที่เหมาะสม กำหนดสิทธิ์ขั้นต่ำ และมีนโยบาย rotation/revocation ที่ทดสอบแล้ว ห้ามเก็บ passphrase ใน source code, command line หรือ log

การเข้ารหัสนี้ **ไม่มีการ sign และไม่ยืนยันตัวผู้ส่ง** ผู้รับทราบได้ว่า ciphertext ผ่าน integrity protection แต่ไม่ควรตีความว่าเป็น sender authentication หากระบบต้องการ authenticity ต้องออกแบบ signing และ trust policy แยกต่างหาก

`third_party/go-crypto` เป็น local fork จาก POC เพื่อเปลี่ยน ZLIB implementation รายละเอียดและ upstream commit/checksum ที่ตรวจไว้มีใน [FORK.md](FORK.md) แม้รูปแบบ output ยัง interoperable กับ OpenPGP แต่ release pipeline ต้อง reproduce และ verify diff จริง ไม่ควรเชื่อเอกสารเพียงอย่างเดียว ผู้ตรวจสอบยังต้องประเมิน dependency risk, key lifecycle, interoperability, metadata limits และ threat model ก่อนใช้ production รวมถึงทำ security/cryptography review โดยผู้เชี่ยวชาญ
