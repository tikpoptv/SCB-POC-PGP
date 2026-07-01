---
marp: true
title: Go vs Java PGP — ช่องว่างจากการบีบอัด (ZLIB) และแนวทางแก้
paginate: true
---

# Go แพ้ Java เพราะ "การบีบอัด" จริงหรือ?

การวิเคราะห์สาเหตุ + แนวทางทำให้ Go บีบอัด txt/csv ได้เร็วเท่า (หรือเกิน) Java

PGP Encryption Benchmark — Go vs Java

---

## TL;DR (สรุปให้ผู้บริหาร)

- **ใช่** — Go แพ้ Java เฉพาะข้อมูล **ที่บีบอัดได้** (txt, csv) เพราะฟังก์ชันบีบอัด ZLIB/DEFLATE
- สาเหตุ: Go ใช้ `compress/flate` แบบ **pure-Go** ส่วน Java ใช้ **native zlib (C)**
- บนข้อมูลที่บีบอัดไม่ได้ (pdf, zip, binary) **Go ชนะ** — แปลว่างาน RSA/AES ของ Go ไม่ได้ช้า
- แก้ได้ด้วยการเปลี่ยนไลบรารีบีบอัด → ปิดช่องว่างได้เกือบหมด หรือชนะ Java

---

## หลักฐานที่ 1 — โค้ดตั้งค่า ZLIB เหมือนกัน

ไม่ใช่บั๊กการตั้งค่า ทั้งสองฝั่งใช้ ZLIB level ปริยาย (= 6)

| ภาษา | โค้ด | เบื้องหลัง |
|------|------|-----------|
| Go | `packet.CompressionConfig{Level: -1}` | `compress/flate` (pure-Go) |
| Java | `new PGPCompressedDataGenerator(PGPCompressedData.ZLIB)` | `java.util.zip.Deflater` → native zlib (C) |

> จุดต่างคือ *implementation ของ deflate* ไม่ใช่ค่า config

---

## หลักฐานที่ 2 — ผลตามชนิดไฟล์ (p50, inmem-single)

| Corpus | ลักษณะ | Go | Java | ผล |
|--------|--------|-----|------|-----|
| txt | บีบอัดได้ดี | ~30.9 ms | ~17.2 ms | **Java ชนะขาด** |
| csv | บีบอัดได้ดี | ~30.8 ms | ~17.4 ms | **Java ชนะขาด** |
| pdf | บีบอัดแทบไม่ได้ | ~11.3 ms | ~14.7 ms | Go ชนะ |
| xlsx | บีบอัดแทบไม่ได้ | ~11.3 ms | ~14.6 ms | Go ชนะ |
| zip | บีบอัดแทบไม่ได้ | ~11.8 ms | ~14.5 ms | Go ชนะ |
| dat | random | ~11.3 ms | ~15.0 ms | Go ชนะ |

---

## หลักฐานที่ 3 — ข้อมูล binary สุ่ม (incompressible)

Go ชนะทุกขนาด เพราะ deflate แทบไม่ต้องทำงาน

| ขนาด | Go (inmem) | Java (inmem) |
|------|-----------|--------------|
| 128 KB | ~3.8 ms | ~19.9 ms |
| 256 KB | ~6.5 ms | ~17.0 ms |
| 512 KB | ~11.7 ms | ~19.8 ms |
| 1024 KB | ~22.1 ms | (สูงกว่า Go) |

---

## "ลายนิ้วมือ" ของปัญหา

ตัวแปรเดียวที่เปลี่ยนระหว่างสองกลุ่ม = ปริมาณงานของ stage บีบอัด

- **Go**: compressible ~30 ms → incompressible ~11 ms (ต่างกันเกือบ 3 เท่า)
- **Java**: compressible ~17 ms → incompressible ~14 ms (เกือบคงที่)

→ native zlib ของ Java เร็วกว่า `compress/flate` ของ Go มากบน input ที่บีบอัดได้

**สรุป: คอขวดคือฟังก์ชันบีบอัด ไม่ใช่ RSA หรือ AES**

---

## แนวทางแก้ — ภาพรวม

เป้าหมาย: แทน deflate ของ Go ด้วยตัวที่เร็วกว่า **แต่ยังเป็น ZLIB/DEFLATE มาตรฐาน**
เพื่อให้ decrypt ข้ามภาษา (Go ↔ Java ↔ gpg) ได้เหมือนเดิม

3 ตัวเลือกหลัก:
1. `klauspost/compress/zlib` — Pure-Go, drop-in
2. `4kills/go-libdeflate` — cgo + libdeflate (เร็วสุดสำหรับ in-memory)
3. `4kills/go-zlib` — cgo wrap zlib C (โมเดลเดียวกับ Java)

---

## ตัวเลือก 1 — klauspost/compress ⭐ แนะนำเริ่มต้น

- Drop-in replacement ของ `compress/zlib`, `flate`, `gzip`, `zip` — เปลี่ยนแค่ import path
- เร็วกว่า stdlib **~2 เท่า** (ตาม README) โดย **ไม่ต้องใช้ cgo**
- Output เป็น zlib มาตรฐาน → interop ครบ
- ✅ build ง่าย, cross-compile ได้, ยัง maintain (release ก.พ. 2026)
- ⚠️ อาจ *เกือบ* เท่า native zlib แต่ไม่การันตีชนะทุกเคส

แหล่ง: github.com/klauspost/compress *(เรียบเรียงใหม่เพื่อลิขสิทธิ์)*

---

## ตัวเลือก 2 — 4kills/go-libdeflate 🚀 เร็วสุดสำหรับ in-memory

- เจ้าของ repo แนะนำเองสำหรับข้อมูลที่พอดีกับ RAM: **เร็วกว่า go-zlib อย่างน้อย 3 เท่า** และเข้ากันได้กับ zlib สมบูรณ์
- เหมาะกับ engine `inmem` ที่อ่านไฟล์ทั้งก้อนขึ้น buffer อยู่แล้ว
- libdeflate เป็น DEFLATE encoder ที่เร็วที่สุดตัวหนึ่ง → มีโอกาส **ชนะ** Java
- ⚠️ ต้องเปิด cgo + ติดตั้ง compiler/zlib, cross-compile ยากขึ้น

---

## ตัวเลือก 3 — 4kills/go-zlib ⚖️ แฟร์ที่สุดเชิงเปรียบเทียบ

- wrap zlib C ต้นฉบับ (Gailly/Adler) ด้วย cgo → ใช้ native zlib **ตัวเดียวกับ Java**
- benchmark ของเขา (Minecraft packets ~11.5 MB):
  - compression ใช้ ~88% ของเวลา stdlib
  - decompression เร็วกว่ามาก (~57% ของเวลา stdlib)
- ⚠️ ต้อง cgo เหมือนข้อ 2; ผลกับไฟล์ txt/csv ใหญ่อาจต่างจาก benchmark chunk เล็ก

---

## ⚠️ ประเด็นสำคัญ — จะเสียบเข้า PGP ยังไง

การบีบอัดเกิด **ภายใน** go-crypto (openpgp) ซึ่ง hardcode เรียก `compress/zlib` ของ stdlib
→ ไม่มี hook ให้ inject compressor ของเราตรงๆ

**2 ทางเลือก:**
1. ✅ **Fork/replace go-crypto**: ใช้ `replace` ใน go.mod ชี้ไป fork ที่แก้ import
   `compress/zlib` → `klauspost/compress/zlib` (drop-in, ไม่แก้ logic)
2. ❌ **บีบอัดเองนอก PGP**: output ไม่เป็น PGP packet มาตรฐาน → Java/gpg แกะไม่ออก

> ต้องยืนยันจุด inject ใน `packet/compressed.go` ของเวอร์ชันที่ pin ไว้ก่อนลงมือ

---

## อย่าใช้: zstd / S2 / brotli / lz4

- เร็วและอัตราส่วนดีกว่า **แต่ไม่ใช่ DEFLATE/ZLIB**
- ผิดสเปก PGP profile `ZLIB` → interop กับ Java พังทันที
- ใช้ได้เฉพาะกรณีเลิกยึด apples-to-apples กับ Java แล้วเท่านั้น

---

## คำแนะนำสรุป

| เป้าหมาย | เลือก |
|----------|-------|
| เร็วขึ้นทันที + build ง่าย ไม่ยุ่ง cgo | **klauspost/compress/zlib** |
| อยากชนะ Java + รับ cgo ได้ + in-memory | **4kills/go-libdeflate** |
| เทียบแบบยุติธรรมสุด (native zlib เดียวกับ Java) | **4kills/go-zlib** |

---

## 🔬 ยืนยันจากซอร์สจริง — go-crypto v1.4.1

โปรเจกต์ pin `github.com/ProtonMail/go-crypto v1.4.1` ไฟล์ `packet/compressed.go`:

```go
// SerializeCompressed()  — จุดที่บีบอัดเกิดขึ้นจริง
case CompressionZLIB:
    compressor, err = zlib.NewWriterLevel(compressed, level) // ← stdlib compress/zlib!
```

- ใช้ `compress/zlib` ของ stdlib แบบ hardcode → **ไม่มี hook ให้เปลี่ยน compressor**
- `CompressionConfig` เปิดให้ตั้งได้แค่ `Level int` เท่านั้น (ไม่มี interface ให้ inject)

**สรุป: ต้อง fork/replace go-crypto เพื่อสลับ compressor — ยืนยันแล้ว ไม่ใช่แค่สมมติฐาน**

---

## 🔬 ตัวอย่างการ fork (แก้บรรทัดเดียว)

ใน fork ของ go-crypto แก้ import ใน `packet/compressed.go`:

```diff
- import "compress/zlib"
+ import zlib "github.com/klauspost/compress/zlib"
```

แล้วผูกด้วย go.mod ของ Go runner:

```
replace github.com/ProtonMail/go-crypto => ./third_party/go-crypto-fork
```

- API เหมือนกันเป๊ะ (drop-in) → ไม่ต้องแก้ logic อื่น
- Output ยังเป็น zlib มาตรฐาน → Java/gpg decrypt ได้เหมือนเดิม
- klauspost = pure-Go → ไม่ต้องเปิด cgo

---

## 🔬 ตัวเลข libdeflate ของจริง (เคส OpenEXR)

จากบทความวัดผลจริงของ Aras Pranckevičius (แทน zlib ด้วย libdeflate v1.8):

| ระดับ | zlib | libdeflate | ผล |
|-------|------|-----------|-----|
| เขียน level 6 | 213 MB/s | 549 MB/s | **เร็วขึ้น ~2.6 เท่า** |
| เขียน level 4 | 456 MB/s | 640 MB/s | เร็วขึ้น ~1.4 เท่า |
| อัตราส่วน level 6 | 2.452x | 2.447x | เกือบเท่ากัน |

- "ฟอร์แมตไฟล์เหมือนเดิมทุกอย่าง" → interop ปลอดภัย
- ⚠️ ข้อควรระวังจากผู้เขียน: libdeflate battle-test เรื่อง malformed data น้อยกว่า zlib

แหล่ง: aras-p.info *(เรียบเรียงใหม่เพื่อลิขสิทธิ์)*

---

## ✅ ผลวัดจริงบนเครื่องเรา (measured — Apple M-series, go1.24)

แยกวัดเฉพาะ stage บีบอัด ZLIB **level 6 เท่ากัน** (stdlib = go-crypto ใช้อยู่ vs klauspost) —
โค้ด: `runners/go/compress_bench_test.go`

| payload | stdlib ns/op | klauspost ns/op | **speedup** | throughput (std → kp) |
|---------|-----:|-----:|:---:|:---:|
| txt-1KB | 108,053 | 94,912 | 1.14x | 14.7 → 11.1 MB/s |
| csv-1KB | 69,745 | 84,500 | 0.83x | 11.8 → 10.1 MB/s |
| txt-10KB | 276,866 | 133,000 | 2.08x | 34.7 → 66.0 MB/s |
| csv-10KB | 277,137 | 177,524 | 1.56x | 34.9 → 50.4 MB/s |
| **txt-100KB** | 4,014,316 | 600,392 | **6.69x** | 25.7 → 174.6 MB/s |
| **csv-100KB** | 4,772,897 | 1,383,088 | **3.45x** | 17.9 → 58.1 MB/s |
| pdf-100KB (random) | 1,507,689 | 148,560 | 10.15x | 59.6 → 605 MB/s |

→ **klauspost ชนะชัดบนไฟล์ compressible ขนาดกลาง–ใหญ่** (ตรงจุดที่ Go แพ้ Java พอดี)

---

## ข้อสังเกตจากผลวัดจริง

- **ไฟล์ใหญ่ (100KB)**: klauspost เร็วกว่า stdlib 3–7 เท่า → น่าจะปิดช่องว่างกับ Java (ที่ ~17 ms บน txt) ได้
- **ไฟล์เล็ก 1KB**: เกือบเท่ากัน (csv-1KB klauspost ช้ากว่านิดเดียว 0.83x) — setup ครอบงำ
- **ไม่ต้องใช้ cgo เลย** → แก้คำแนะนำเดิมของผม: pure-Go klauspost แรงพอ ไม่จำเป็นต้องพึ่ง libdeflate/cgo เพื่อปิดช่องว่าง
- **ข้อแลกเปลี่ยน**: ratio ของ klauspost ที่ level 6 ต่ำกว่า stdlib เล็กน้อย (txt 6.26x → 5.64x) = ไฟล์ผลลัพธ์ใหญ่ขึ้นราว ~10% แลกกับความเร็วหลายเท่า
- ⚠️ ตัวเลขนี้คือ stage บีบอัดล้วน **ยังไม่ผ่าน pipeline PGP จริง** — ผลรวมจริงต้องฝัง klauspost เข้า go-crypto (fork) แล้ววัดซ้ำ

---

## เปรียบเทียบตัวเลือกแบบสรุป

| เกณฑ์ | klauspost/compress | go-libdeflate | go-zlib |
|-------|:---:|:---:|:---:|
| ต้อง cgo | ❌ ไม่ต้อง | ✅ ต้อง | ✅ ต้อง |
| เร็วกว่า stdlib | ~2x | ~2.6x+ (lvl6) | ~1.1–1.7x |
| โมเดลเหมือน Java | คล้าย (pure-Go) | native C | native zlib เป๊ะ |
| cross-compile ง่าย | ✅ | ❌ | ❌ |
| interop PGP | ✅ | ✅ | ✅ |
| streaming ไฟล์ใหญ่ | ✅ | ⚠️ เน้น in-memory | ✅ |

---

## ขั้นตอนถัดไป (ข้อเสนอ)

1. เปิดอ่าน go-crypto ที่ pin ไว้ → ยืนยันจุด inject compressor
2. เพิ่ม variant ใหม่ เช่น `go-inmem-libdeflate` เข้า benchmark
3. รันเทียบ txt/csv กับ Java → วัดผลจริงว่าปิดช่องว่างได้แค่ไหน
4. ตรวจ interop: Go(ใหม่) encrypt → Java/gpg decrypt ต้องผ่าน

---

## อ้างอิง (References)

- go-crypto v1.4.1 — `openpgp/packet/compressed.go` (ProtonMail/go-crypto)
- klauspost/compress — Optimized Go Compression Packages (github.com/klauspost/compress)
- 4kills/go-libdeflate & 4kills/go-zlib (github.com/4kills)
- libdeflate โดย Eric Biggers (github.com/ebiggers/libdeflate)
- "EXR: libdeflate is great" — Aras Pranckevičius, ส.ค. 2021 (aras-p.info)
- ข้อมูล benchmark ภายใน: `report/results_extended.json`, `report/filecount_result.json`

> เนื้อหาจากแหล่งภายนอกถูกเรียบเรียงใหม่เพื่อให้เป็นไปตามข้อกำหนดลิขสิทธิ์

---

# ขอบคุณครับ

คำถาม / ข้อเสนอแนะ?
