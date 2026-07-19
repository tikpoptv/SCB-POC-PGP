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

พฤติกรรม benchmark ชื่อ `go-stream-parallel` ถูกแทนด้วย streaming package นี้ ส่วน parallelism ตั้งใจให้ caller จัดการเอง เช่น หนึ่ง goroutine ต่อไฟล์ภายใต้ bounded worker pool เพื่อจำกัดจำนวนไฟล์และ buffer ที่ทำงานพร้อมกัน

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
