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
```

ผลออกที่ `report/results_klauspost_ab.json` + ตารางสรุปบนจอ

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
