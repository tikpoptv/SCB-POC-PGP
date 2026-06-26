# ข้อมูลกุญแจ PGP (POC เท่านั้น)

> ⚠️ กุญแจชุดนี้ **ไม่มี passphrase** และสร้างเพื่อใช้ทดสอบ POC เท่านั้น ห้ามนำไปใช้งานจริง

| ไฟล์ | ชนิด | ใช้ทำอะไร |
|---|---|---|
| `rsa2048-public.asc`  | RSA-2048 public key  | ใช้ตอน **encrypt** |
| `rsa2048-private.asc` | RSA-2048 secret key  | ใช้ตอน **decrypt** |
| `rsa4096-public.asc`  | RSA-4096 public key  | ใช้ตอน **encrypt** |
| `rsa4096-private.asc` | RSA-4096 secret key  | ใช้ตอน **decrypt** |
| `cv25519-public.asc`  | Curve25519 ECC public key  | ใช้ตอน **encrypt** |
| `cv25519-private.asc` | Curve25519 ECC secret key  | ใช้ตอน **decrypt** |

> Curve25519 ECC ถูกเพิ่มเพื่อรองรับ key-type coverage (Req 14.1/14.2): primary เป็น EdDSA (ed25519) และ subkey เข้ารหัสเป็น ECDH (cv25519)

## Fingerprints
- RSA-2048: `4754A7211179C6F00575ED57878CA4B359203F26`  (uid: poc-rsa2048@example.com)
- RSA-4096: `258B9290B9E058B2049F5CA4795CE2AB12CC42CE`  (uid: poc-rsa4096@example.com)
- Curve25519: `AB8A7D6A37F781564C710B94AA7397CE95F32AE6`  (uid: poc-cv25519@example.com)

## Manifest (fingerprint + key spec + checksum)
Harness สร้าง/ตรวจสอบ Key_Set และบันทึก manifest ผ่านโมดูล `harness.keys`:
```python
from harness.keys import build_manifest
manifest = build_manifest("keys")   # raise KeyGenerationError ระบุ spec ที่ล้มเหลว ถ้าไม่ครบ (Req 31.4)
manifest.to_dict()                   # -> keySetChecksum + keySet[] (type/bits/curve/fingerprint/checksum)
```

## สำหรับงานของน้อง (java-inmem-single)
ใช้คู่ **RSA-2048** ก็พอ:
- encrypt ด้วย `rsa2048-public.asc`
- decrypt ด้วย `rsa2048-private.asc` (ไม่มี passphrase)

## สร้างกุญแจใหม่ได้ด้วย
```
bash scripts/gen-keys.sh
```
