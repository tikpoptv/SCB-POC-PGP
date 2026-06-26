# ข้อมูลกุญแจ PGP (POC เท่านั้น)

> ⚠️ กุญแจชุดนี้ **ไม่มี passphrase** และสร้างเพื่อใช้ทดสอบ POC เท่านั้น ห้ามนำไปใช้งานจริง

| ไฟล์ | ชนิด | ใช้ทำอะไร |
|---|---|---|
| `rsa2048-public.asc`  | RSA-2048 public key  | ใช้ตอน **encrypt** |
| `rsa2048-private.asc` | RSA-2048 secret key  | ใช้ตอน **decrypt** |
| `rsa4096-public.asc`  | RSA-4096 public key  | ใช้ตอน **encrypt** |
| `rsa4096-private.asc` | RSA-4096 secret key  | ใช้ตอน **decrypt** |

## Fingerprints
- RSA-2048: `4754A7211179C6F00575ED57878CA4B359203F26`  (uid: poc-rsa2048@example.com)
- RSA-4096: `258B9290B9E058B2049F5CA4795CE2AB12CC42CE`  (uid: poc-rsa4096@example.com)

## สำหรับงานของน้อง (java-inmem-single)
ใช้คู่ **RSA-2048** ก็พอ:
- encrypt ด้วย `rsa2048-public.asc`
- decrypt ด้วย `rsa2048-private.asc` (ไม่มี passphrase)

## สร้างกุญแจใหม่ได้ด้วย
```
bash scripts/gen-keys.sh
```
