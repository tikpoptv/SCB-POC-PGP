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

# 3b) รันแบบ production-scale (ไฟล์ทุกสกุลรวม ~300MB, จำนวนตามระบบเดิม+เผื่อ)
BIG=1 ROUNDS=5 WARMUP=3 python3 scripts/vm/run_klauspost_ab.py
```

ผลออกที่ `report/results_klauspost_ab.json` + ตารางสรุปบนจอ

## โหมด BIG (production-scale)
เปิดด้วย `BIG=1` — เพิ่ม scenario ตามจำนวนไฟล์จริงของระบบเดิม (เผื่อขึ้นเล็กน้อยเพื่อความปลอดภัย):

| สกุล | ระบบเดิม | เทสนี้ (ดีฟอลต์) | ขนาด/ไฟล์ | รวม |
|------|---------:|----------------:|----------:|----:|
| txt (compressible) | 1200 | **1300** | 128 KB | ~166 MB |
| csv (compressible) | 400  | **450**  | 128 KB | ~58 MB |
| pdf (incompressible) | 300 | **350** | 192 KB | ~70 MB |
| zip (incompressible) | 20  | **30**   | 256 KB | ~8 MB |
| **รวม** | | ~2130 ไฟล์ | | **~302 MB** |

ปรับจำนวน/ขนาดได้ผ่าน env: `PROD_TXT_N`, `PROD_CSV_N`, `PROD_PDF_N`, `PROD_ZIP_N`,
`PROD_TXT_KB`, `PROD_CSV_KB`, `PROD_PDF_KB`, `PROD_ZIP_KB`

⚠️ **ข้อควรรู้โหมด BIG:**
- corpus ~300MB — ถ้าใช้ tmpfs `/mnt/corpus` (2GB ตาม ENVIRONMENT.md) พอ; เผื่อพื้นที่ด้วย
- ใช้เวลานานขึ้นมาก (สร้าง corpus + รัน ~2100 ไฟล์ × 2 variant × 3 label × ROUNDS)
- ทุกไฟล์ ≤256KB → in-memory engine ปลอดภัยกับ RAM 8GB (โหลดทีละไฟล์)
- checksum ของ corpus ถูก cache แล้ว (ไม่ hash ซ้ำทุก invocation)

## อ่านผลยังไง
- คอลัมน์ `kp vs std` = go-stdlib / go-klauspost → >1 คือ klauspost เร็วกว่า stdlib
- คอลัมน์ `kp vs java` = java / go-klauspost → >1 คือ Go(klauspost) เร็วกว่า Java
- โฟกัสที่ scenario **txt / csv** (compressible) — จุดที่ Go เดิมแพ้ Java
- `dat` (incompressible) ใช้เช็คว่าไม่ทำให้เคสที่ Go ชนะอยู่แล้วแย่ลง

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
