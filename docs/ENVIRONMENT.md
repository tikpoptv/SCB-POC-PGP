# Benchmark Environment — VM ที่ใช้รัน POC

เอกสารนี้บันทึกสภาพแวดล้อมจริงที่ใช้รัน POC เปรียบเทียบ PGP (Go vs Java)
ทั้ง Go_Runner และ Java_Runner รันบน **VM เดียวกัน** ตาม Requirement 3 (Identical Environment)
ค่าที่ระบุนี้คือ baseline ที่ต้องบันทึกลง Result_Report ทุกครั้ง (Req 3.2)

## VM (Proxmox) — VMID 122 `ubuntu-2404`

| รายการ | ค่า |
|--------|-----|
| VMID | 122 |
| ชื่อ | ubuntu-2404 |
| OS | Ubuntu 24.04 LTS |
| Machine | q35 |
| BIOS | OVMF (UEFI) |
| CPU | `host`, 1 socket / 8 cores |
| NUMA | enabled |
| RAM | **8 GB (no ballooning — min = max)** ← baseline ทางการของ POC นี้ |
| Disk | 80 GB, virtio-scsi-single, cache=none, discard=on, ssd=1 |
| Network | virtio |
| Guest Agent | enabled |
| Cloud-init | enabled (ide2) |

> **CPU = `host` สำคัญ:** ส่ง flag `aes` ของ CPU จริงเข้า VM → ได้ AES-NI ตาม Requirement 23
> ตรวจยืนยันใน VM ด้วย: `grep -o aes /proc/cpuinfo | head -1` (ต้องเห็น `aes`)

## RAM profile (8 GB เป็น baseline ทางการ)

POC นี้ใช้ **8 GB เป็นสเปคจริง** และ scope การทดสอบถูกออกแบบให้พอดีกับ 8 GB ตั้งแต่ต้น (ไม่ใช่ของขาด) หลักคิดคือ: ไฟล์ใหญ่ใช้ **streaming** (RAM ไม่โตตามขนาดไฟล์) ส่วน **in-memory** จำกัดให้อยู่ในโควตา จึงครอบคลุมงานหลักของ PGP ได้ครบ

### Run profile สำหรับ 8 GB (ค่าที่ใช้จริง)

| รายการ | ค่าที่ใช้ |
|---|---|
| ขนาดไฟล์ small / medium | ตามสเปกปกติ (เล็ก ≤1MB, กลาง ≤100MB) |
| ขนาดไฟล์ large | สูงสุด ~**256 MB** สำหรับ in-memory; ไฟล์ใหญ่กว่านั้นใช้ **streaming** (Req 15.4) |
| tmpfs corpus | ~**2 GB** |
| JVM max heap | ~**3 GB** (`-Xmx3g`) |
| memory quota ต่อ runner | เท่ากันทั้งสอง runner (ส่วนต่าง = 0, Req 3.4) เช่นด้านละ ~3 GB |

### นอกขอบเขตของ environment นี้ (จงใจตัด)
- เคส **ไฟล์ ≥1GB แบบ in-memory** — ไม่จำเป็นต่อข้อสรุป และไฟล์ใหญ่ทดสอบผ่าน streaming ได้อยู่แล้ว
- ถ้าวันหลังมี RAM มากขึ้น ค่อยขยาย large-tier/in-memory เพิ่มได้โดยไม่ต้องแก้โครงสร้าง



- **8 cores** → ทดสอบ scaling แบบ single-thread → multi-thread (Req 16) และตั้ง concurrency = vCPU ได้
- **RAM 8 GB (baseline ทางการ)** → small/medium เต็มสเปก + large ผ่าน streaming + in-memory ภายในโควตา (ดู RAM profile ด้านบน)
- **CPU = host** → AES-NI ทำงานจริง เทียบ Go/Java แฟร์ (Req 23)
- **NVMe + cache=none** → I/O นิ่ง (แต่ corpus จริงรันบน tmpfs)
- **VM เดียว single-tenant** → ลด noise และทำให้เทียบ p95/p99 ได้น่าเชื่อถือ (Req 27)

## การจูนเพื่อให้ผลนิ่ง (ทำใน VM ก่อนรัน benchmark)

```bash
# 1) CPU governor = performance
sudo cpupower frequency-set -g performance || \
  echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# 2) (ทางเลือก) ปิด turbo เพื่อ determinism สูงสุด — ถ้าปิดไม่ได้ harness จะบันทึกสถานะไว้แทน (Req 27.1)
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || true

# 3) tmpfs สำหรับวาง Test_Corpus (Req 27.2) — ชั่วคราว 2 GB (เพราะ RAM รวม 8 GB)
sudo mkdir -p /mnt/corpus
sudo mount -t tmpfs -o size=2G tmpfs /mnt/corpus
```

> หมายเหตุ host-level (ทำที่ Proxmox host ถ้าเข้าถึงได้): pin vCPU ของ VM 122 ไปยัง physical core เฉพาะ, เลี่ยง hyperthread sibling, ปิด KSM ระหว่างวัด, และไม่รัน VM อื่นที่กินทรัพยากรบน host เดียวกันตอนทดสอบ

## Toolchain ที่ต้องติดตั้งใน VM

| เครื่องมือ | ใช้ทำอะไร |
|---|---|
| Go (stable ล่าสุด) | Go_Runner |
| JDK 25 (LTS) + GraalVM | Java_Runner + native image variant (Req 22) |
| Maven หรือ Gradle | build ฝั่ง Java |
| Python 3.12 + `numpy scipy psutil` | Benchmark_Harness + สถิติ (Req 26) |
| `gnupg` (gpg) | interoperability check (Req 25) |
| `git`, `build-essential` | ทั่วไป |

ตรวจเวอร์ชันจริงแล้วบันทึกลง Result_Report ตาม Requirement 2 (รูปแบบ major.minor.patch)

## ข้อจำกัดที่ควรรู้

- ถ้าปรับสเปก VM (CPU/RAM/quota) ระหว่างชุดการทดสอบ ผลชุดนั้นจะถูก mark `non-comparable` ตาม Req 3.5 — อย่าเปลี่ยนกลางคัน
- ใช้ x86_64 เท่านั้นในรอบเดียวกัน อย่าผสม ARM (crypto extension ต่างกัน เทียบไม่แฟร์)
