# งานมอบหมาย (Hand-off): Java PGP Runner — 2 variants

> งานนี้ตัดออกมาจากโปรเจกต์ POC เปรียบเทียบ PGP ระหว่าง Go กับ Java
> ทำคนเดียวจบในตัว ไม่ต้องแตะ harness/สถิติ/รายงาน (พี่ทำเอง)
> ภาษา: **Java + Bouncy Castle**
> แนวทาง: เราให้ "โจทย์และสัญญา" แต่ **วิธีทำให้ไป research เอง** — อยากให้ได้ลองเยอะ ๆ

## เป้าหมาย

เขียนโปรแกรม Java (CLI) ที่ทำ **PGP encrypt/decrypt ไฟล์** โดยมี **2 รูปแบบ (variant)**:

1. `java-inmem-single` — โหลดทั้งไฟล์เข้า memory แล้วเข้ารหัส (single-thread)
2. `java-stream-single` — ประมวลผลแบบ streaming เป็นช่วง ๆ โดย **peak memory ไม่โตตามขนาดไฟล์** (single-thread)

ทั้งสอง variant ต้องให้ผล round-trip ตรงกัน ต่างกันแค่กลยุทธ์การจัดการหน่วยความจำ

## สิ่งที่ต้องส่งมอบ (ทำเองทั้งหมด)

1. โค้ดที่ทำ encrypt/decrypt ได้ทั้ง 2 variant
2. ตัวโปรแกรม CLI: อ่านคำสั่ง JSON จาก **stdin** → ทำงาน → พิมพ์ผล JSON ออก **stdout** (log ออก stderr)
3. การจับเวลา encrypt/decrypt (เขียนเอง — อ่านหัวข้อ "กฎการจับเวลา")
4. การจัดการ edge case: ไฟล์ว่าง (0 byte), ไฟล์ใหญ่, ไฟล์ `.ctrl`/`.ctl` ต้อง **ข้าม ไม่เข้ารหัส**
5. เทสต์ของตัวเอง: อย่างน้อยพิสูจน์ round-trip ของทั้ง 2 variant และเคสไฟล์ว่าง

> เราจะให้แค่ pom.xml, กุญแจ และไฟล์ทดสอบไว้ให้ ที่เหลือเขียนเอง

## นอกขอบเขต (ยังไม่ต้องทำ)

- ❌ parallel/virtual threads, GraalVM native — มีคนอื่นทำ
- ❌ เก็บ CPU/RAM, GC, สถิติ p95/p99, รายงานสรุป — harness ทำให้
- ❌ signing/verify signature, DB/API/network
- ❌ สร้างกุญแจเอง (ใช้ที่ให้ไว้ใน `keys/`)

## Crypto profile (ค่าคงที่ ห้ามเปลี่ยน)

- Public-key: RSA (ใช้ `keys/rsa2048-*.asc`; ลองกับ `rsa4096-*` ด้วยถ้ามีเวลา)
- Symmetric cipher: **AES-256**
- Compression: **ZLIB**
- Hash: **SHA-256**
- Output encoding: **binary** (ไม่ใช่ ASCII-armored)

## สัญญา Input/Output (ทำตามนี้เป๊ะ — ส่วนที่เหลือออกแบบเอง)

### Input — JSON ทาง stdin
```json
{
  "command": "run",
  "variantId": "java-inmem-single",   // หรือ "java-stream-single"
  "keySetPath": "../../keys",
  "corpusPath": "../../corpus",
  "outputDir": "./out"
}
```

### Output — JSON ทาง stdout
```json
{
  "runnerId": "java",
  "variantId": "java-inmem-single",
  "operations": [
    {
      "fileName": "sample.txt",
      "originalBytes": 123,
      "ciphertextBytes": 200,
      "encryptMs": 1.83,
      "decryptMs": 2.04,
      "roundTripOk": true,
      "skipped": false,
      "outputFileName": "sample.txt.pgp"
    }
  ]
}
```
- หนึ่ง object ต่อหนึ่งไฟล์
- ไฟล์ `.ctrl`/`.ctl`: `skipped=true`, ไม่มี encrypt/decrypt
- log/debug ออก **stderr** เท่านั้น

## กฎการตั้งชื่อไฟล์ผลลัพธ์
- encrypt: ต่อท้ายชื่อเดิมด้วย `.pgp` เช่น `report.pdf` → `report.pdf.pgp`
- decrypt: ถอดกลับมาเทียบกับไฟล์ต้นฉบับว่าตรงทุก byte

## กฎการจับเวลา (สำคัญ — อย่าให้เพี้ยน)
- ใช้ `System.nanoTime()`
- จับเวลา **เฉพาะการเรียก encrypt/decrypt** เท่านั้น
- **ห้ามนับรวม** เวลาโหลดกุญแจ และเวลาอ่าน/เขียนไฟล์ลงดิสก์
- คิดเองว่าจะวาง boundary การจับเวลายังไงให้ยุติธรรมกับทั้ง in-memory และ streaming

## เกณฑ์ว่า "เสร็จแล้ว" (Definition of Done)
- [ ] ทำได้ทั้ง `java-inmem-single` และ `java-stream-single`
- [ ] encrypt `.txt`/`.csv`/`.pdf` → `<ชื่อ>.pgp` (binary), decrypt กลับมาตรงทุก byte
- [ ] `.ctrl`/`.ctl` ถูกข้าม (`skipped=true`)
- [ ] ไฟล์ว่าง (0 byte) round-trip ได้ ไม่ crash
- [ ] ใช้ AES-256 + ZLIB + SHA-256 + RSA
- [ ] จับเวลาเฉพาะ crypto ไม่รวม I/O/โหลดกุญแจ
- [ ] streaming variant: peak memory ไม่โตตามขนาดไฟล์ (ลองไฟล์ใหญ่เทียบดู)
- [ ] มีเทสต์ของตัวเองที่พิสูจน์ round-trip ทั้ง 2 variant + เคสไฟล์ว่าง
- [ ] log ออก stderr, ผลออก stdout เท่านั้น

## สิ่งที่อยากให้ไป research เอง (จุดที่จะได้เรียนรู้)
- Bouncy Castle OpenPGP API: encrypt/compress/literal-data pipeline และฝั่ง decrypt
- ความต่างของการเขียนแบบ in-memory (`byte[]`) กับ streaming (ทำงานบน `InputStream`/`OutputStream` เป็นช่วง ๆ)
- การโหลด armored key (public/secret) เข้ามาใช้
- วิธีวัด peak memory ของ JVM เพื่อยืนยันว่า streaming ไม่โตตามไฟล์ (เช่น ลองไฟล์ใหญ่ ๆ)

## ส่งงาน
- โค้ดอยู่ใน `runners/java/` (มี pom.xml ให้แล้ว) จัด package/โครงเอง
- README สั้น ๆ บอกวิธี build/run
- พี่จะกลับมา review เอง แล้วเอาไปต่อกับ harness

## ถ้าติด
- ติดเรื่อง crypto profile/สัญญา input-output → ถามพี่ ห้ามเดา
- ติดเรื่อง API การเขียน → ลองหาเองก่อน (นี่คือส่วนที่อยากให้ได้ฝึก) แล้วค่อยมาคุยถ้าตันจริง ๆ
