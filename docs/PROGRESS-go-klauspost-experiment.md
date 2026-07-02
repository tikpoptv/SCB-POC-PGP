# Progress — Go klauspost compression experiment

> จุดประสงค์: ทำให้ Go runner บีบอัด txt/csv เร็วขึ้นเพื่อลบช่องว่างที่ Go แพ้ Java
> สถานะ: **รอเทสบน VM** — โค้ด+สคริปต์พร้อมหมดแล้ว, ผู้ใช้กำลังจะเปิด VM มารันเทียบ (เก่า/ใหม่/java)
> อัปเดตล่าสุด: ก่อนรอบเทสบน VM

---

## 🎯 กำลังจะทำอะไรต่อ (รอบเทสบน VM)

เป้าหมายรอบนี้: วัดจริงบน VM ว่า **go-stdlib (เก่า) vs go-klauspost (ใหม่) vs java** ต่างกันแค่ไหน

Checklist บน VM (ทำตาม `scripts/vm/README.md`):
- [ ] `cd ~/POC-Encryption && git fetch && git checkout experiment/go-klauspost-compression`
      (ถ้ายังไม่ push ให้ push ก่อน — ดู Step 2 ด้านล่าง)
- [ ] จูน VM: `sudo cpupower frequency-set -g performance || true`
- [ ] `bash scripts/vm/build_klauspost_ab.sh` → ได้ go-runner-klauspost + go-runner-stdlib + java jar
- [ ] รอบเร็ว: `ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py`
- [ ] รอบจำนวนไฟล์ (file-count load, txt 1300/csv 450/pdf 350/zip 30):
      `BIG=1 ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py`
- [ ] รอบขนาดไฟล์ (size gradient 1KB→300MB/ไฟล์ ทุกสกุล, in-memory cap 256MB):
      `SIZEGRAD=1 ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py`
- [ ] ⭐ รอบ FULL (กว้างเท่า run_v5: 6 สกุล × 3 key alg + count + many + concurrent + size gradient):
      `FULL=1 ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py`  ← ใช้เวลาหลายชั่วโมง
- [ ] เอา `report/results_klauspost_ab.json` + ตารางสรุป กลับมาให้ Kiro อัปเดต report/สไลด์
- [ ] (ทางเลือก) interop: `cd runners/go && go test -run TestInteropKlauspostCiphertextDecryptsWithGPG -v`

⚠️ ต้องมี **WARMUP ≥ 3** ไม่งั้น Java ช้าผิดปกติ (JIT cold) — เห็นชัดในเคสไฟล์เดียว
⚠️ ต้องมีเน็ตบน VM ตอน build (baseline stdlib ต้อง `go mod tidy` ดึง go-crypto upstream)

หมายเหตุ: ตอนนี้ branch **ยังไม่ push** → ก่อนรันบน VM ต้อง push ก่อน (หรือ copy ขึ้นไป)
ถ้าจะ push ให้ทำ Step 2 ด้านล่าง

---

## Branch & Git

- ทำงานบน branch: **`experiment/go-klauspost-compression`** (แตกจาก `main`)
- Remote: `SCB-POC-PGP` (https://github.com/tikpoptv/SCB-POC-PGP.git) — **ยังไม่ push**
- Commits บน branch นี้ (ใหม่ล่าสุดอยู่บน):
  - `fc56bd2` extend benchmarks to 500KB/1MB + level tradeoff
  - `616bb44` integrate klauspost zlib into PGP path via go-crypto fork
  - `84f42eb` add zlib compression benchmark (stdlib vs klauspost)
- หมายเหตุ: มีไฟล์ `report/*` และ `report_v2/`, `scripts/*` ที่ค้างใน working tree (งานอื่น ไม่เกี่ยวกับ experiment นี้ — **ยังไม่ได้ commit** โดยตั้งใจ)

---

## สิ่งที่ทำเสร็จแล้ว ✅

### 1. วิเคราะห์ต้นตอ
- Go แพ้ Java เฉพาะข้อมูล compressible (txt/csv) เพราะ `compress/flate` (pure-Go) ช้ากว่า native zlib ของ Java
- บนข้อมูล incompressible (pdf/binary) Go ชนะ → RSA/AES ไม่ใช่ปัญหา

### 2. Full integration (klauspost เข้า PGP path จริง)
- Fork go-crypto v1.4.1 → `runners/go/third_party/go-crypto/` (167 ไฟล์)
- แก้ `openpgp/packet/compressed.go`: `compress/zlib` → `github.com/klauspost/compress/zlib`
- ผูกด้วย `replace` directive ใน `runners/go/go.mod`
- เพิ่ม dependency `github.com/klauspost/compress v1.19.0`

### 3. ทดสอบ + วัดผล
- ไฟล์ทดสอบที่เพิ่ม (ทั้งหมดอยู่ใน `runners/go/`):
  - `compress_bench_test.go` — เทียบ stage บีบอัดล้วน stdlib vs klauspost (มี `TestCompressionCompare`, `TestCompressionCompareLevels`, `BenchmarkCompress`)
  - `engine_e2e_bench_test.go` — วัด PGP encrypt เต็ม (`BenchmarkEngineEncrypt`)
  - `interop_gpg_test.go` — Go(klauspost) encrypt → gpg decrypt byte-for-byte (`TestInteropKlauspostCiphertextDecryptsWithGPG`)
- ผลยืนยัน:
  - test เดิมทั้งหมด (round-trip byte-for-byte, property tests) ผ่านครบกับ fork
  - **Interop ผ่าน**: gpg ถอด klauspost-ZLIB ได้ → Java BouncyCastle ถอดได้แน่นอน
  - **End-to-end PGP encrypt A/B** (RSA-2048+AES-256+ZLIB, level 6):
    - txt-100KB: **5.06x** (4.16ms → 0.82ms), csv-100KB: 3.10x, pdf-100KB: 2.79x
  - **Compression stage** (ไฟล์ใหญ่): txt-1MB 8.37x, csv-1MB 4.09x, pdf-1MB 29.74x
  - klauspost L6 เร็วกว่า + บีบดีกว่า stdlib L1

### เอกสาร
- `docs/compression-gap-go-vs-java.md` — สไลด์พรีเซนต์ (Marp) มีผลวัดจริง + interop + ตารางเทียบ
- `docs/go-compression-txt-csv-vs-java-research.md` — งานวิจัยตัวเลือกไลบรารี

---

## สิ่งที่เหลือ (ทำต่อตามลำดับ) ⏭️

### Step 1 — รัน harness เต็ม เทียบ Go(klauspost) vs Java  ← พร้อมรันบน VM แล้ว
**สคริปต์พร้อมแล้ว** (smoke-test บนเครื่อง dev ผ่าน): รันบน VM ได้เลย
- `scripts/vm/build_klauspost_ab.sh` — build go-runner-klauspost + go-runner-stdlib + java jar
- `scripts/vm/run_klauspost_ab.py` — เทียบ 3 ทาง (go-stdlib/go-klauspost/java) → `report/results_klauspost_ab.json` + ตารางสรุป
- `scripts/vm/README.md` — ขั้นตอนบน VM

วิธีรันบน VM (ย่อ):
```bash
cd ~/POC-Encryption && git checkout experiment/go-klauspost-compression
sudo cpupower frequency-set -g performance || true
bash scripts/vm/build_klauspost_ab.sh
ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py
```
- smoke-test บน dev (ROUNDS=1): go-klauspost ชนะ go-stdlib 2.6–5x บน txt/csv/dat ✅
- ⚠️ **ต้องใช้ WARMUP ≥ 3** ไม่งั้น Java ช้าผิดปกติ (JIT cold)
- ยังเหลือ: รันจริงบน VM แล้วเอา `results_klauspost_ab.json` มาอัปเดต report/สไลด์

### Step 2 — Push branch + เปิด PR
- `git push -u origin experiment/go-klauspost-compression`
- เปิด PR ด้วย `gh pr create` (base = main)
- ⚠️ ต้องขออนุญาต user ก่อน push (กระทบ remote)
- PR ควรอธิบาย: fork go-crypto, ผลวัด, interop verified, ข้อแลกเปลี่ยน ratio ~10%

---

## วิธีรันซ้ำ (คำสั่งสำคัญ) — cwd = `runners/go`

```bash
# เทียบ stage บีบอัด (อ่านง่าย)
go test -run 'TestCompressionCompare$' -v

# เทียบ level 1 vs 6
go test -run TestCompressionCompareLevels -v

# end-to-end PGP encrypt (klauspost = replace active)
go test -bench=BenchmarkEngineEncrypt -benchtime=50x -run='^$'

# interop กับ gpg
go test -run TestInteropKlauspostCiphertextDecryptsWithGPG -v

# ทั้งหมด
go test ./... -count=1
```

### วิธีทำ A/B (klauspost vs stdlib) end-to-end
ใน `runners/go/go.mod` คอมเมนต์/เปิด บรรทัด:
```
replace github.com/ProtonMail/go-crypto => ./third_party/go-crypto
```
- เปิดไว้ = klauspost | คอมเมนต์ = stdlib
- หลังแก้ต้อง `go mod tidy` แล้วรัน benchmark
- **สำคัญ: จบงานต้องเปิด replace กลับ** (branch นี้ควรเป็น klauspost) — ตอน save นี้ replace เปิดอยู่ (klauspost active) ✅

---

## ข้อควรรู้ / gotchas
- go-crypto v1.4.1 hardcode stdlib zlib ใน `SerializeCompressed` → ไม่มี hook ต้อง fork เท่านั้น
- gpg interop test: GNUPGHOME ต้องเป็น path สั้น (ใช้ `/tmp/...`) ไม่งั้น socket ยาวเกิน limit บน macOS
- keys ใน `keys/` ไม่มี passphrase (POC)
- ข้อแลกเปลี่ยน: klauspost level 6 ให้ ratio ต่ำกว่า stdlib เล็กน้อย (~10% ไฟล์ใหญ่ขึ้น) แลกกับเร็วหลายเท่า
