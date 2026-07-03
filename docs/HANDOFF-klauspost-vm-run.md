# HANDOFF — Go klauspost experiment + Java zlib-ng comeback POC

> เปิดแชทใหม่แล้วอ่านไฟล์นี้ก่อน จะได้ต่อได้ทันที
> อัปเดตล่าสุด: 2026-07-03 — FULL head-to-head เสร็จแล้ว + รายงานสร้างแล้ว (เฟส 3 จบ)

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
3. **เฟสสาม (✅ เสร็จแล้ว):** FULL head-to-head **go-klauspost vs java+zlib-ng** matrix เต็ม 74 scenarios
   เงื่อนไขเดียวกับ FULL เดิมทุกอย่าง — รันเสร็จ 2026-07-02 (1 ชม. 42 นาที), correctness 100%, fails=0
   - ผล: `report/results_kp_vs_zlibng_full.json` + รายงาน `report/kp_vs_zlibng_report.html`
     (สร้างโดย `report/build_kp_vs_zlibng_report.py` — join java/go-stdlib จากรอบแรก, ตรวจ render ผ่านแล้ว)
   - **ข้อสรุป: klauspost ชนะ 64/74 สนาม median ~2.3× — zlib-ng แซงได้ 9 สนาม (csv ≥512KB ล้วน) ~5–10%**
   - cross-run sanity: go-klauspost สองรอบต่างกัน median 1.1% (max 7.8%) → join ข้ามรอบได้
   - decrypt ไฟล์ใหญ่ zlib-ng ชนะทุกสกุล ~2× (inflate format-locked, C+SIMD > pure Go)
     แต่ enc ครองสัดส่วนเวลา → roundtrip รวม klauspost ยังนำ

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

## ✅ สถานะ ณ ตอน handoff: ทั้ง 3 เฟสจบแล้ว — เหลือแต่งานนำเสนอ
- FULL head-to-head รันเสร็จบน VM (2026-07-02 09:48→11:31 UTC), log `~/kp_ng_full.log`
  ท้าย log เห็น `🔒 correctness: roundTripOk 100%` + fail(x)=0 ทั้งไฟล์
- ผลดึงมา local + สร้างรายงานแล้ว ทุกอย่าง commit บน branch นี้
- ถ้าจะ rerun: `rm ~/kp_ng_full.log` ก่อน (corpus `~/corpus-kp` เก็บไว้ใช้ซ้ำได้)

## ตัวเลขหลักที่จำไว้ตอบได้เลย (จาก FULL head-to-head)
- klauspost ชนะ **64/74** · zlib-ng แซง **9/74** (csv ล้วน: ft-csv×2, prod-csv-450, sg-csv 4MB→300MB) · เสมอ 1
- txt: klauspost นำ median **2.33×** · csv: zlib-ng แซง median **~1.07–1.10×**
- prod-txt-1300: kp นำ 1.7× · prod-csv-450: ng แซง 7%
- txt-128MB enc: kp 728ms vs ng 2,714ms (นำ 3.7×) · dec: ng 219ms vs kp 528ms (ng นำ 2.4×)
  → enc ครอง ~80% ของ roundtrip เลยยังแพ้รวม

## ขั้นตอนถัดไป (รอผู้ใช้สั่ง)
1. อัปเดตสไลด์ `docs/compression-gap-go-vs-java.md` ด้วยตัวเลข head-to-head
2. Grafana dashboard (metric prefix `pgp_bench_`, PromQL ใน `scripts/vm/README.md`)
3. เปิด PR: https://github.com/tikpoptv/SCB-POC-PGP/pull/new/experiment/go-klauspost-compression
4. ไอเดียที่คุยไว้แต่ยังไม่ได้ยืนยัน: เก็บ log รัน VM (~/kp_full.log, ~/zng_ab.log, ~/kp_ng_full.log)
   เข้า repo เป็นประวัติ — **ถามผู้ใช้ก่อนทำ**

## ไฟล์สำคัญ
- `scripts/vm/run_klauspost_ab.py` — FULL runner ต้นฉบับ 3 impl (เฟสแรก — อย่าแก้)
- `scripts/vm/run_java_zlibng_ab.py` — POC เล็ก 9 scenarios java vs java-zlibng vs go-kp (เฟสสอง)
- `scripts/vm/run_kp_vs_zlibng_full.py` — FULL head-to-head 2 impl (เฟสสาม — เสร็จแล้ว)
- `report/build_kp_vs_zlibng_report.py` — รายงาน head-to-head (join 4 impl, 4 แท็บ)
- `report/results_kp_vs_zlibng_full.json` — ผล FULL เฟสสาม
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
