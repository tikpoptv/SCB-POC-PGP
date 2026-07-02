# HANDOFF — Go klauspost experiment + Java zlib-ng comeback POC

> เปิดแชทใหม่แล้วอ่านไฟล์นี้ก่อน จะได้ต่อได้ทันที
> อัปเดตล่าสุด: 2026-07-02 — ระหว่าง FULL head-to-head (go-klauspost vs java+zlib-ng) กำลังรันบน VM

## บริบทโดยย่อ (เรื่องอะไร)
1. **เฟสแรก (เสร็จแล้ว — report v3):** พิสูจน์ว่าสลับ zlib ของ Go จาก stdlib → **klauspost/compress**
   ทำให้ Go บีบอัด+เข้ารหัส PGP เร็วกว่า Java — FULL run 74 scenarios บน VM จบแล้ว,
   ผลอยู่ `report/results_klauspost_ab.json` + รายงาน `report/klauspost_report_v3.html`
   ข้อสรุป: Go+klauspost ชนะ txt ~2.3–2.5×, incompressible ~2.2× ; decrypt สูสี (format-locked)
2. **เฟสสอง (POC เล็กเสร็จแล้ว):** คำถาม "Java comeback ได้มั้ย?" → คำตอบ: **LD_PRELOAD zlib-ng**
   (JDK Deflater/Inflater เรียก libz.so แบบ dynamic → สลับเป็น zlib-ng 1.3.1 zlib-compat ได้โดยไม่แก้โค้ด Java)
   - POC 9 scenarios เสร็จ: `report/results_java_zlibng_ab.json` + รายงาน `report/java_zlibng_report.html`
   - ผล: **csv ฟื้น 2.9–3.2× จนแซง klauspost ~5–10%** แต่ **txt ได้แค่ 1.31–1.35× (klauspost ยังนำ 2.3–2.5×)**
   - โบนัส: zlib-ng เร่งทั้ง deflate+inflate → decrypt csv-128MB ชนะ klauspost เกือบ 2× (608ms vs 1108ms)
   - correctness ผ่านครบ: gpg interop byte-for-byte, packet algo=2 (ZLIB มาตรฐาน), roundTripOk 100%
3. **เฟสสาม (🔴 กำลังรัน):** FULL head-to-head **go-klauspost vs java+zlib-ng** matrix เต็ม 74 scenarios
   เงื่อนไขเดียวกับ FULL เดิมทุกอย่าง (FULL=1 ROUNDS=5 WARMUP=3, corpus เดิม seed เดิม)
   → scenario names ตรงกัน join กับผล java/go-stdlib จากรอบแรกได้

## Git
- branch: **`experiment/go-klauspost-compression`** (push ขึ้น GitHub แล้ว, ล่าสุด `a524f05`)
- remote: `git@github.com:tikpoptv/SCB-POC-PGP.git`
- working tree สะอาด — ทุกอย่าง commit + push แล้ว
- ส่งโค้ดขึ้น VM ด้วย **git bundle** (`git bundle create /tmp/kp.bundle <branch>` → scp → VM `git fetch`)
  (ระวัง: ถ้า VM มีไฟล์ untracked ชนกับไฟล์ใน commit ใหม่ ให้ rm ฝั่ง VM ก่อน merge)

## VM (10.110.1.42, user tikxd, VMID 122 ubuntu-2404)
- Go 1.24.3 (/usr/local/go), Java 25, python3.12, gpg, git ✅
- repo: `~/POC-Encryption` (branch นี้, sync ถึง `a524f05` แล้ว)
- binaries: `runners/go/go-runner-klauspost`, `go-runner-stdlib`, `runners/java/target/java-runner-0.1.0.jar`
- **zlib-ng 1.3.1:** build ด้วย `./configure --zlib-compat && make -j8` (VM ไม่มี cmake) →
  lib อยู่ที่ **`~/zlib-ng/libz.so.1`** (ไม่ใช่ build/ — จำ path นี้ให้ดี ต้องส่งผ่าน env `ZLIBNG_LIB`)
- corpus FULL: `~/corpus-kp` (3.7GB, generate แล้ว ใช้ซ้ำได้ — seed คงที่)
- gpg keyring บน VM import `keys/rsa2048-private.asc` แล้ว (ใช้ทดสอบ interop)
- node_exporter + textfile dir `/var/lib/node_exporter/textfile_collector` → Prometheus CT200:9090 → Grafana

## 🔴 สถานะ ณ ตอน handoff: FULL head-to-head กำลังรันบน VM
```
คำสั่งที่ใช้รัน (nohup):
cd ~/POC-Encryption && export PATH=$PATH:/usr/local/go/bin
FULL=1 ROUNDS=5 WARMUP=3 POC_CORPUS=$HOME/corpus-kp ZLIBNG_LIB=$HOME/zlib-ng/libz.so.1 \
  nohup python3 scripts/vm/run_kp_vs_zlibng_full.py > ~/kp_ng_full.log 2>&1 &
```
- runner: `scripts/vm/run_kp_vs_zlibng_full.py` (cp จาก run_klauspost_ab.py, เหลือ 2 impl,
  ผลออก `report/results_kp_vs_zlibng_full.json`, ไม่เขียน .prom, มี verify_preload gate)
- log: `~/kp_ng_full.log` — เริ่มรัน ~2026-07-02 (เห็น `🔗 preload OK` ต้นไฟล์)
- **snapshot ล่าสุด: 26/74 scenarios, elapsed ~14 นาที, fails=0** (อยู่ช่วง count gradient)
- ETA รวม ~2.5–3 ชม. (2 impl แทน 3)

## คำสั่งเช็คจากเครื่อง dev (VPN ต่ออยู่)
```bash
# เสร็จรึยัง
ssh tikxd@10.110.1.42 'pgrep -f "[s]cripts/vm/run_kp_vs_zlibng_full.py" >/dev/null && echo "⏳ ยังรัน" || (grep -q "ผลบันทึกที่" ~/kp_ng_full.log && echo "✅ เสร็จ" || echo "⚠️ ตายก่อนจบ")'

# ความคืบหน้า + เช็ค fail (ต้องเป็น 0)
ssh tikxd@10.110.1.42 'echo "scenarios: $(grep -c "^\[" ~/kp_ng_full.log)"; echo "fail(x): $(grep -E "^  (go-|java)" ~/kp_ng_full.log | grep -c x)"; tail -6 ~/kp_ng_full.log'

# ดู log สด
ssh -t tikxd@10.110.1.42 'tail -n 40 -f ~/kp_ng_full.log'

# ตารางสรุปตอนจบ (ต้องเห็น 🔒 correctness: roundTripOk 100%)
ssh tikxd@10.110.1.42 'tail -90 ~/kp_ng_full.log'
```

## ขั้นตอนถัดไป (หลัง FULL head-to-head เสร็จ)
1. ตรวจท้าย log ต้องเห็น `🔒 correctness: roundTripOk 100% และไม่มีไฟล์ถูก skip` — ถ้า `❌❌` หยุดวิเคราะห์
2. ดึงผลมา local + commit:
   ```bash
   scp tikxd@10.110.1.42:~/POC-Encryption/report/results_kp_vs_zlibng_full.json report/
   ```
3. **สร้างรายงาน head-to-head ฉบับเต็ม** — join คอลัมน์ java (libz เดิม) + go-stdlib จาก
   `report/results_klauspost_ab.json` ได้เลย (scenario names/corpus/seed ตรงกัน)
   reuse เอนจินกราฟจาก `report/build_klauspost_report.py` แบบเดียวกับที่
   `report/build_java_zlibng_report.py` ทำ (import base + update LABEL_DISP/LABEL_COLOR,
   java-zlibng ใช้สี `#27ae60`)
4. commit + push (ตาม convention เดิม: `poc(...)`/`report(...)`)
5. งานค้างจาก handoff เดิม (รอผู้ใช้สั่ง): อัปเดตสไลด์ `docs/compression-gap-go-vs-java.md`,
   Grafana dashboard, เปิด PR (https://github.com/tikpoptv/SCB-POC-PGP/pull/new/experiment/go-klauspost-compression)
6. ไอเดียที่คุยไว้แต่ยังไม่ได้ยืนยัน: เก็บ log รัน VM (~/kp_full.log, ~/zng_ab.log, ~/kp_ng_full.log)
   เข้า repo เป็นประวัติ — **ถามผู้ใช้ก่อนทำ**

## ไฟล์สำคัญ
- `scripts/vm/run_klauspost_ab.py` — FULL runner ต้นฉบับ 3 impl (เฟสแรก — อย่าแก้)
- `scripts/vm/run_java_zlibng_ab.py` — POC เล็ก 9 scenarios java vs java-zlibng vs go-kp (เฟสสอง)
- `scripts/vm/run_kp_vs_zlibng_full.py` — FULL head-to-head 2 impl (เฟสสาม — กำลังรัน)
- `report/build_klauspost_report.py` — เอนจิน report v3 (CSS/svg_grouped/svg_lines/best_ms — ตัว base ให้ reuse)
- `report/build_java_zlibng_report.py` — รายงาน POC zlib-ng (ตัวอย่างวิธี reuse base)
- `report/results_klauspost_ab.json` — ผล FULL เฟสแรก (java/go-stdlib/go-klauspost) — แหล่ง join
- `report/results_java_zlibng_ab.json` — ผล POC เฟสสอง
- `scripts/vm/verify_correctness.py` — ด่าน correctness
- `runners/go/third_party/go-crypto/` — fork (สลับ zlib ใน openpgp/packet/compressed.go —
  บรรทัด 13 import klauspost, บรรทัด 88 zlib.NewReader → klauspost ช่วยทั้ง compress และ decompress)

## ความรู้เชิงเทคนิคที่สรุปแล้ว (กันถามซ้ำ)
- **OpenPGP จำกัด compression แค่ Uncompressed/ZIP/ZLIB/BZip2** (RFC 4880/9580) —
  S2/Snappy/LZ4/zstd ใช้ไม่ได้ จะหลุด interop กับ gpg
- **deflate มีอิสระเชิงอัลกอริทึม → klauspost ชนะ encrypt 6×; inflate ถูก format lock →
  ชนะกันได้แค่ระดับ machine code (C/SIMD > pure Go)** — เหตุที่ Go แพ้ decrypt บางสนาม
- **zlib-ng gain ขึ้นกับชนิดข้อมูลแรงมาก:** csv (แพทเทิร์นสั้นซ้ำถี่ SIMD ช่วยเต็ม) 2.9–3.2× แต่ txt 1.3×
- **LD_PRELOAD ใช้กับ Go binary ไม่ได้** — pure Go ไม่ได้ link libz.so; ถ้าอยากใช้ zlib-ng ฝั่ง Go
  ต้อง cgo (เสียข้อดี pure-Go build/cross-compile) — ประเมินแล้วว่าไม่คุ้มสำหรับ gap decrypt ส่วนน้อย

## Gotchas
- ต้องมี WARMUP≥3 (ไม่งั้น Java JIT cold ตัวเลขเพี้ยน)
- pgrep -f อย่าใช้ pattern ตรงๆ จะ match คำสั่งตัวเอง (ใช้ `[s]cripts/...`)
- LD_PRELOAD ล้มแบบ**เงียบ**ได้ (แค่ warn บน stderr แล้วใช้ libz เดิมต่อ → ตัวเลขออกมาเท่า java เดิม)
  → runner มี `verify_preload()` ดักก่อนรันแล้ว แต่ถ้ารันมือให้เช็ค `🔗 preload OK` ต้น log เสมอ
- อย่าเขียน .prom จาก runner ใหม่ (กันทับ pgp_bench.prom ของ FULL เดิมบน Grafana)
- ถ้าจะ rerun head-to-head: `rm ~/kp_ng_full.log` ก่อน (corpus ~/corpus-kp เก็บไว้ใช้ซ้ำได้)
