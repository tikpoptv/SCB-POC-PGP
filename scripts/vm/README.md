# รันเทียบ klauspost บน VM (Step 1)

เทียบ **go-stdlib vs go-klauspost vs java** บน VM (ทรัพยากรนิ่งกว่าเครื่อง dev)
เพื่อวัดว่าการสลับ zlib เป็น klauspost ปิดช่องว่างที่ Go แพ้ Java บน txt/csv ได้จริงแค่ไหน

## ต้องมีบน VM
- อยู่บน branch `experiment/go-klauspost-compression` (มี fork go-crypto + replace directive)
- Go (stable), JDK + Maven, Python 3, `git`, มีเน็ต (สำหรับ `go mod tidy` ตอน build baseline)
- keys อยู่ที่ `keys/` (ไม่มี passphrase)

## ขั้นตอน

```bash
# 0) เข้า repo + checkout branch
cd ~/POC-Encryption
git fetch origin
git checkout experiment/go-klauspost-compression

# 1) จูน VM ให้ผลนิ่ง (ตาม docs/ENVIRONMENT.md)
sudo cpupower frequency-set -g performance || true

# 2) build ทั้ง 3 ตัว (go-klauspost, go-stdlib, java jar)
bash scripts/vm/build_klauspost_ab.sh

# 3) รันเทียบ (ปรับ ROUNDS/WARMUP ได้)
ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py

# 3b) โหมด "จำนวนไฟล์" (file-count load ตามระบบเดิม + เผื่อ)
BIG=1 ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py

# 3c) โหมด "ขนาดไฟล์มีผลแค่ไหน" (size gradient 1KB→300MB/ไฟล์ ครบทุกสกุล)
SIZEGRAD=1 ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py

# 3d) ⭐ โหมด FULL — กว้างเท่า run_v5 (แนะนำสำหรับผลสมบูรณ์)
FULL=1 ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py

# จะเปิดพร้อมกันก็ได้ (FULL ครอบ SIZEGRAD ให้อยู่แล้ว; เพิ่ม BIG ได้):
FULL=1 BIG=1 ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py
```

## โหมด FULL — ครอบทุกมิติเท่า run_v5 ⭐
เปิดด้วย `FULL=1` — ให้ครบสเกลเท่า `scripts/run_v5.py` แต่เทียบ 3 ทาง (go-stdlib/go-klauspost/java):

| เฟส | เนื้อหา |
|-----|---------|
| filetype matrix | 6 สกุล (txt,csv,pdf,xlsx,zip,dat) × 3 key alg (RSA-2048, RSA-4096, Curve25519) |
| count gradient | 100KB binary × 1,5,10,25,50,100,200,500,1000 ไฟล์ |
| many-small | 1kb×200, 10kb×200, 100kb×100 |
| concurrent | stream-parallel, concurrency 1/2/4/8 |
| size gradient | (รวมให้อัตโนมัติ) 1KB→300MB/ไฟล์ ทุกสกุล, in-memory cap 256MB |

| **file-count** (รวม BIG อัตโนมัติ) | txt 1300 / csv 450 / pdf 350 / zip 30 (ตามระบบเดิม +เผื่อ) |

**FULL ครอบทั้ง SIZEGRAD และ BIG ให้อัตโนมัติ** → `FULL=1` ครบทั้ง 2 เงื่อนไข:
1. ✅ ทุกสกุล (txt/csv/pdf/zip) วัดถึง **300MB/ไฟล์** (size gradient)
2. ✅ เทส **จำนวนไฟล์** ตามระบบเดิม txt 1200/csv 400/pdf 300/zip 20 (เทสจริง 1300/450/350/30)

ปรับได้ผ่าน env: `FULL_KEY_ALGS`, `FULL_FILETYPES`, `FULL_COUNTS`, `FULL_CONC`, `PROD_*_N/KB`, `SIZEGRAD_*`
- ⚠️ FULL ใช้เวลานานมาก (หลายชั่วโมง) — เหมาะรันทิ้งไว้บน VM
- ต้องมี key ครบ (rsa2048/rsa4096/cv25519) ใน `keys/`

ผลออกที่ `report/results_klauspost_ab.json` + ตารางสรุปบนจอ

## โหมด BIG — เทส "จำนวนไฟล์" (file-count load)
เปิดด้วย `BIG=1` — จำลองโหลดจริง: ไฟล์จำนวนมากขนาดปานกลาง ตามจำนวนของระบบเดิม (เผื่อขึ้นเล็กน้อย)
**(นี่คือ "จำนวนไฟล์" ไม่ใช่ผลรวมขนาด)**

| สกุล | ระบบเดิม | เทสนี้ (ดีฟอลต์) | ขนาด/ไฟล์ |
|------|---------:|----------------:|----------:|
| txt (compressible) | 1200 | **1300** | 128 KB |
| csv (compressible) | 400  | **450**  | 128 KB |
| pdf (incompressible) | 300 | **350** | 192 KB |
| zip (incompressible) | 20  | **30**   | 256 KB |

ปรับได้ผ่าน env: `PROD_TXT_N/PROD_CSV_N/PROD_PDF_N/PROD_ZIP_N`, `PROD_*_KB`
- ทุกไฟล์ ≤256KB → in-memory ปลอดภัยกับ RAM 8GB (โหลดทีละไฟล์)

## โหมด SIZEGRAD — เทส "ขนาดไฟล์มีผลแค่ไหน"
เปิดด้วย `SIZEGRAD=1` — ไฟล์เดียวต่อขนาด ไล่ **1KB → 300MB ต่อไฟล์** ครบทุกสกุล (txt/csv/pdf/zip)

- สเต็ปดีฟอลต์: `1,64,512,4096,16384,65536,131072,262144,307200` KB (1KB..300MB)
- **in-memory จำกัดที่ `INMEM_CAP_MB` (ดีฟอลต์ 256MB)** ตาม ENVIRONMENT.md — ไฟล์ใหญ่กว่านั้น
  วัดเฉพาะ **streaming** (scenario จะมี suffix `S`) กัน OOM บน RAM 8GB
- ปรับได้: `SIZEGRAD_STEPS_KB="1,1024,..."`, `SIZEGRAD_TYPES="txt,pdf"`, `INMEM_CAP_MB=256`

⚠️ **ข้อควรรู้ทั้ง BIG/SIZEGRAD:**
- corpus ใหญ่ (SIZEGRAD สร้างไฟล์ 300MB/สกุล) — ต้องมีพื้นที่ tmpfs/disk พอ (≥ ~1.5GB ถ้าครบ 4 สกุล)
- ใช้เวลานานขึ้นมาก — เหมาะรันบน VM ที่ปล่อยยาวได้
- corpus checksum ถูก cache แล้ว (ไม่ hash ซ้ำทุก invocation — สำคัญมากกับไฟล์ 300MB)

## อ่านผลยังไง
- คอลัมน์ `kp vs std` = go-stdlib / go-klauspost → >1 คือ klauspost เร็วกว่า stdlib
- คอลัมน์ `kp vs java` = java / go-klauspost → >1 คือ Go(klauspost) เร็วกว่า Java
- โฟกัสที่ scenario **txt / csv** (compressible) — จุดที่ Go เดิมแพ้ Java
- `dat` (incompressible) ใช้เช็คว่าไม่ทำให้เคสที่ Go ชนะอยู่แล้วแย่ลง

## 📈 ดูผลบน Grafana (Prometheus)

สคริปต์เขียนไฟล์ `.prom` ให้ **node_exporter textfile collector** อัตโนมัติ →
node_exporter (VM 122:9100) expose → Prometheus (CT200:9090) scrape → Grafana

### ตั้งค่าครั้งเดียวบน VM
1. node_exporter ต้องเปิด textfile collector:
   ```bash
   # เช็คว่าเปิดหรือยัง
   ps aux | grep node_exporter | grep -o 'collector.textfile.directory=[^ ]*'
   ```
   ถ้ายังไม่เปิด ให้เพิ่ม flag ตอนสตาร์ท (แล้ว restart service):
   ```
   --collector.textfile.directory=/var/lib/node_exporter/textfile_collector
   ```
2. ชี้ให้สคริปต์เขียนตรง dir นั้น (ดีฟอลต์ตรงกับข้างบนแล้ว):
   ```bash
   export NODE_EXPORTER_TEXTFILE_DIR=/var/lib/node_exporter/textfile_collector
   ```
   ถ้า dir ต้องใช้ sudo เขียน ให้ `sudo chown $USER` dir นั้น หรือรันสคริปต์ด้วย sudo

### metric ที่ export (prefix `pgp_bench_`)
| metric | ความหมาย | labels |
|--------|----------|--------|
| `pgp_bench_roundtrip_p50_ms` / `_p95_ms` | เวลา encrypt+decrypt/ไฟล์ | impl, variant, scenario, branch |
| `pgp_bench_encrypt_p50_ms` / `pgp_bench_decrypt_p50_ms` | แยก encrypt/decrypt | " |
| `pgp_bench_throughput_mbps` | throughput MB/s | " |
| `pgp_bench_compression_ratio` | orig/ciphertext | " |
| `pgp_bench_roundtrip_ok_ratio` | สัดส่วน byte-for-byte ผ่าน | " |
| `pgp_bench_files` | จำนวนไฟล์ที่วัด | " |
| `pgp_bench_speedup_ratio` | klauspost เร็วกว่า baseline กี่เท่า | scenario, baseline(stdlib/java), branch |

### ตัวอย่าง PromQL สำหรับ panel
```promql
# เทียบ p50 3 ทาง ต่อ scenario
pgp_bench_roundtrip_p50_ms

# speedup klauspost เทียบ java
pgp_bench_speedup_ratio{baseline="java"}

# compression ratio เทียบ impl
pgp_bench_compression_ratio
```
> textfile collector รายงานค่าเดิมทุก scrape จนกว่าจะรันใหม่ (เหมาะกับ benchmark แบบ batch — ดู "ค่าล่าสุด")

## หมายเหตุ / gotchas
- **ต้องมี WARMUP ≥ 3** ไม่งั้นตัวเลข Java จะสูงผิดปกติ (JIT ยังไม่ร้อน) — เคสไฟล์เดียวยิ่งชัด
- `build_klauspost_ab.sh` ใช้ GNU sed (Linux) — ออกแบบมาสำหรับ VM ไม่ใช่ macOS
- build baseline ปิด `replace` ชั่วคราวแล้ว restore ด้วย `git checkout` (มี trap กันพลาด) — จบแล้ว replace เปิดกลับ (klauspost active)
- binary `go-runner-klauspost` / `go-runner-stdlib` ถูก gitignore แล้ว
- corpus สร้างที่ `/mnt/corpus` (ถ้า mount tmpfs ไว้) ไม่งั้น `/tmp/corpus-klauspost` — override ได้ด้วย env `POC_CORPUS`

## เอา checksum interop มายืนยันด้วย (ทางเลือก)
บน VM มี gpg → รัน interop test ของ Go ได้เลย:
```bash
cd runners/go && go test -run TestInteropKlauspostCiphertextDecryptsWithGPG -v
```
