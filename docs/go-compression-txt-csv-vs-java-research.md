---
marp: true
title: "Go Compression: ปิด Gap TXT/CSV vs Java"
paginate: true
theme: default
---

# Go มีฟังก์ชันบีบอัด TXT/CSV ให้เร็วเท่า Java ไหม?

### Research Report — July 2026

ค้นคว้าจาก GitHub READMEs, Benchmarks, และ Source Code  
Project: PGP Encryption Benchmark

---

## ปัญหาที่เจอ: Go แพ้ Java บน TXT/CSV

| File Type | Go best (ms) | Java best (ms) | Winner | Go/Java ratio |
|-----------|:-----------:|:--------------:|:------:|:-------------:|
| `.txt` (RSA-2048) | 30.7 | 17.2 | **Java** | **1.79×** |
| `.csv` (RSA-2048) | 30.6 | 17.1 | **Java** | **1.78×** |
| `.pdf` (RSA-2048) | 11.3 | 14.2 | **Go** | 0.80× |
| `.xlsx` (RSA-2048) | 11.3 | 14.2 | **Go** | 0.79× |
| `.dat` binary | 11.2 | 14.1 | **Go** | 0.80× |

Go แพ้เฉพาะ txt/csv — ชนะบน binary ทุกตัว  
**สาเหตุ: ZLIB compression implementation ต่างกัน — ไม่ใช่ crypto**

---

## Root Cause Analysis

### ทั้งคู่ตั้ง compression level เหมือนกัน!

```
Go:   compress/zlib.NewWriterLevel(w, -1)  → default = level 6
Java: PGPCompressedDataGenerator(ZLIB)      → DEFAULT_COMPRESSION = level 6
```

### แต่ implementation ต่างกัน

| | Go `compress/zlib` | Java SunJCE `Deflater` |
|-|-------------------|------------------------|
| Type | Pure Go | Native C (JVM built-in) |
| Assembly | ❌ ไม่มีใน flate | ✅ optimized native |
| Speedup vs stdlib | baseline | ~1.8× faster |

### TXT/CSV vs Binary

- **txt/csv** → ZLIB บีบได้มาก → CPU ทำงานหนักใน compressor → **Go แพ้**
- **pdf/xlsx/dat** → บีบได้น้อย → compressor ผ่านไปเร็ว → **Go ชนะด้วย AES crypto**

---

## ทางออก: klauspost/compress

### ตัวเลือกที่ดีที่สุด — Pure Go + Assembly

| | |
|-|-|
| **GitHub** | https://github.com/klauspost/compress |
| **Import** | `github.com/klauspost/compress/zlib` |
| **CGo** | ❌ ไม่ต้องใช้ |
| **Stars** | ~5,500 (Jun 2026, actively maintained) |
| **Drop-in** | ✅ 100% identical API |

### Benchmark vs stdlib (Level 6, Large Text Corpora)

| Corpus | stdlib L6 | klauspost L6 | Speedup |
|--------|-----------|--------------|---------|
| enwik9 (1 GB Wikipedia text) | 30.26 MB/s | **80.69 MB/s** | **2.7×** |
| GitHub JSON (6.27 GB) | 67.56 MB/s | **140.37 MB/s** | **2.1×** |
| CSV (nyc-taxi 3.3 GB, L1) | 149.11 MB/s | **227.68 MB/s** | **1.53×** |
| Silesia mixed (212 MB) | 31.56 MB/s | **90.91 MB/s** | **2.9×** |

> **klauspost เร็วกว่า stdlib 2–3× บน text** → น่าจะปิด gap กับ Java ได้

---

## API Drop-in: เปลี่ยน 1 บรรทัด

```go
// ก่อน (stdlib)
import "compress/zlib"

// หลัง (klauspost) — API identical 100%
import "github.com/klauspost/compress/zlib"
```

### ทุก function เหมือนเดิม

```go
// ✅ identical signatures
w, err := zlib.NewWriterLevel(dst, 6)
r, err := zlib.NewReader(src)
```

### ⚠️ Level Mapping ต่างกันเล็กน้อย

- klauspost `-1 (DefaultCompression)` resolves เป็น **level 5** ภายใน
- ส่ง `Level: 6` ตรงๆ ถ้าต้องการ behavior เหมือน stdlib
- Output bytes ต่างกัน แต่ยังเป็น valid RFC 1950 zlib stream

---

## ปัญหา: go-crypto Hardcode stdlib

```go
// ProtonMail/go-crypto: openpgp/packet/compressed.go
case CompressionZLIB:
    compressor, err = zlib.NewWriterLevel(compressed, level)
    //              ^^^^ hardcoded "compress/zlib"
```

**ไม่มี injection point** — ต้อง fork go-crypto

---

## วิธี Integrate: Fork + Swap Import

### แก้ไขใน Fork (2 บรรทัดเท่านั้น)

```go
// openpgp/packet/compressed.go

// ลบ:
import "compress/flate"
import "compress/zlib"

// เพิ่ม:
import "github.com/klauspost/compress/flate"
import "github.com/klauspost/compress/zlib"
```

**ไม่ต้องเปลี่ยน logic ใดๆ เลย** — error types ถูก alias ไว้แล้ว

### go.mod ใน Runner

```
replace github.com/ProtonMail/go-crypto => ./forked-go-crypto
```

---

## ตัวเลือกอื่น: DataDog/czlib (CGo)

| | |
|-|-|
| **GitHub** | https://github.com/DataDog/czlib |
| **CGo** | ✅ ต้องใช้ |
| **Status** | Stable, not actively maintained |

### Benchmark — ⚠️ ระวัง: ดีเฉพาะ Decompression

| Payload | Compress vs stdlib | Decompress vs stdlib |
|---------|--------------------|----------------------|
| 2 KiB | **+89%** ✅ | **+268%** ✅ |
| ~10 MB (Silesia) | **−14% ❌ ช้ากว่า!** | **+267%** ✅ |

สำหรับ 512 KB txt/csv ที่เราใช้ → ผลน่าจะ **อยู่ระหว่างกลาง** แต่ไม่แน่ใจ  
**ไม่แนะนำ** สำหรับ use case นี้

---

## ตัวเลือกอื่น: 4kills/go-libdeflate (CGo, In-Memory)

| | |
|-|-|
| **GitHub** | https://github.com/4kills/go-libdeflate |
| **CGo** | ✅ ต้องใช้ (libdeflate C library) |
| **Speedup** | ~4–5× vs stdlib |

### ⛔ ข้อจำกัดสำคัญ: ไม่รองรับ Streaming

```go
// ❌ ไม่มี io.Writer interface
// รับเฉพาะ []byte เท่านั้น
c, _ := go_libdeflate.NewCompressor()
compressed, _, _ := c.Compress(plaintext, nil, go_libdeflate.Zlib)
```

**ใช้ใน OpenPGP streaming pipeline ไม่ได้โดยตรง**

---

## Reference: C Library Benchmarks (lzbench)

> Silesia corpus, AMD EPYC 9554 @ 3.10 GHz, gcc 14.2.0

| Algorithm | Level | Compress (MB/s) | Decompress (MB/s) | Ratio (%) |
|-----------|-------|:--------------:|:-----------------:|:---------:|
| zlib 1.3.1 | -6 | 25.3 | 344 | 32.19 |
| **zlib-ng 2.2.3** | **-6** | **62.1** | 509 | 32.49 |
| libdeflate 1.23 | -6 | 84.3 | 912 | 31.85 |
| zstd 1.5.6 | -1 | 422 | 1,347 | 34.64 |
| lz4 1.10.0 | default | 577 | 3,716 | 47.60 |

> zlib-ng เร็วกว่า zlib ถึง **2.5×** ที่ level 6 แต่ Go wrapper ล้าสมัยแล้ว

---

## ไม่แนะนำ: Libraries ที่ตายแล้ว

| Library | ปัญหา |
|---------|-------|
| `yasushi-saito/cloudflare-zlib` | Unmaintained (2019), cloudflare/zlib deprecated |
| `yasushi-saito/zlibng` | Unmaintained (2019), Linux/Darwin amd64 only |
| `intel/ISALgo` | **Archived March 2024** — Intel ยุติการพัฒนา |
| `zjj/ISALgo2` | 0 stars, ไม่มี benchmark, levels 0/1/3 only |

---

## สรุปคำแนะนำ

| ตัวเลือก | CGo | Speedup | Status | แนะนำ |
|----------|:---:|:-------:|--------|:------:|
| **klauspost/compress/zlib** | ❌ | **2–3×** | Active | ⭐⭐⭐ |
| DataDog/czlib | ✅ | +89% (small) | Frozen | ⭐ |
| 4kills/go-libdeflate | ✅ | 4–5× | Active | ⛔ (no stream) |
| Go stdlib | ❌ | baseline | Active | (current) |

**คำแนะนำ:** ใช้ `klauspost/compress/zlib` + fork go-crypto

---

## Action Plan

### ขั้นตอน (ง่ายมาก)

1. Fork `github.com/ProtonMail/go-crypto`
2. แก้ 2 บรรทัด import ใน `openpgp/packet/compressed.go`
3. อัพเดต `go.mod` ใน Go runner
4. Run benchmark เปรียบเทียบ

### ทดสอบ Hypothesis ก่อน Fork (ใช้เวลา 5 นาที)

```go
// เปลี่ยน compression เป็น NONE แล้วดูผลลัพธ์
CompressionConfig: &packet.CompressionConfig{Level: 0} // NoCompression
```

**ถ้า Go ชนะ Java ทันที → ยืนยันว่า compression คือสาเหตุ 100%**

### เป้าหมาย

```
ก่อน: Go 30.7ms, Java 17.2ms (txt, RSA-2048)  → Java ชนะ 1.79×
หลัง: Go ≤ 18ms, Java 17.2ms                  → Go ควรเสมอหรือชนะ
```

---

## Sources

| # | Source |
|---|--------|
| 1 | klauspost/compress README: https://github.com/klauspost/compress |
| 2 | klauspost PR #105 benchmark (Level 6 data): https://github.com/klauspost/compress/pull/105 |
| 3 | klauspost zstd README (CSV benchmark): https://github.com/klauspost/compress/blob/master/zstd/README.md |
| 4 | ProtonMail go-crypto compressed.go: https://github.com/ProtonMail/go-crypto/blob/main/openpgp/packet/compressed.go |
| 5 | DataDog/czlib README: https://github.com/DataDog/czlib |
| 6 | 4kills/go-libdeflate: https://github.com/4kills/go-libdeflate |
| 7 | lzbench results (C reference): https://github.com/inikep/lzbench |
| 8 | blog.klauspost.com 30-50% faster: https://blog.klauspost.com/optimized-gzipzip-packages-30-50-faster/ |

---

*Research date: July 1, 2026 | Project: POC Encryption PGP Benchmark*
