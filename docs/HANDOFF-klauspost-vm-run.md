# HANDOFF — Go klauspost experiment (รอบรันบน VM)

> เปิดแชทใหม่แล้วอ่านไฟล์นี้ก่อน จะได้ต่อได้ทันที
> อัปเดตล่าสุด: ระหว่าง FULL benchmark กำลังรันบน VM

## บริบทโดยย่อ (เรื่องอะไร)
พิสูจน์ว่าสลับ zlib ของ Go จาก stdlib → **klauspost/compress** ทำให้ Go บีบอัด+เข้ารหัส
PGP เร็วขึ้น (Go เดิมแพ้ Java เพราะ compress/flate ของ stdlib ช้า) ทำเป็น **experiment**
บน branch แยก โดย fork go-crypto v1.4.1 แล้วสลับ zlib ผ่าน go.mod `replace` — ไม่แก้โค้ด runner

## Git
- branch: **`experiment/go-klauspost-compression`** (local + บน VM ; **ยังไม่ push ขึ้น GitHub**)
- remote: `git@github.com:tikpoptv/SCB-POC-PGP.git`
- ส่งโค้ดขึ้น VM ด้วย **git bundle** (`git bundle create /tmp/kp.bundle <branch>` → scp → VM `git fetch`)
- ผลวัดจริงบน dev (compression stage): txt-1MB klauspost เร็วกว่า stdlib ~8x; end-to-end PGP txt-100KB ~5x

## VM (10.110.1.42, user tikxd, VMID 122 ubuntu-2404) — เตรียมครบแล้ว
- Go 1.24.3 (/usr/local/go), Java 25, python3.12, gpg, git, mvnw ✅
- repo: `~/POC-Encryption` (checkout branch นี้อยู่)
- build แล้ว 3 ตัว: `runners/go/go-runner-klauspost` (173 klauspost syms), `runners/go/go-runner-stdlib` (0), `runners/java/target/java-runner-0.1.0.jar`
- keys ครบ rsa2048/rsa4096/cv25519
- node_exporter รัน + textfile dir `/var/lib/node_exporter/textfile_collector` (tikxd เขียนได้) → Prometheus CT200:9090 → Grafana

## ✅ ผ่าน correctness ครบก่อนรัน (กันพลาดแบบ v2)
- `scripts/vm/verify_correctness.py`: 27/27 combo (3 impl × 3 variant × 3 keyAlg) — 8/8 ไฟล์, skip=0, roundTripOk=8/8 byte-for-byte (รวม empty + edge bytes + 4MB)
- gpg interop: go+klauspost encrypt → gpg (reference) ถอดได้ byte-for-byte
- Go test suite เต็มผ่าน (property + roundtrip)
- guard ในตัว benchmark: ถ้ามี skip หรือ roundtrip ไม่ครบ 100% จะพิมพ์ `❌❌ พบปัญหา correctness` ท้ายผล

## 🔴 สถานะ ณ ตอน handoff: FULL run กำลังรันบน VM
```
คำสั่งที่ใช้รัน (nohup):
cd ~/POC-Encryption && export PATH=$PATH:/usr/local/go/bin
POC_CORPUS=$HOME/corpus-kp FULL=1 ROUNDS=5 WARMUP=3 \
  NODE_EXPORTER_TEXTFILE_DIR=/var/lib/node_exporter/textfile_collector \
  nohup python3 scripts/vm/run_klauspost_ab.py > ~/kp_full.log 2>&1 &
```
- FULL = กว้างเท่า run_v5: 6 สกุล × 3 keyAlg + count gradient + many-small + concurrent
  + size gradient 1KB→**300MB**/ไฟล์ (txt/csv/pdf/zip, in-memory cap 256MB, >256MB=stream เท่านั้น)
  + file-count (prod) txt1300/csv450/pdf350/zip30
- log: `~/kp_full.log` | ผล JSON: `~/POC-Encryption/report/results_klauspost_ab.json`
- ล่าสุดที่เห็น: ~5 scenarios แรก (ft-txt/csv) เต็ม dots ไม่มี fail ; คาดใช้เวลา ~1–3 ชม.

## คำสั่งเช็คจากเครื่อง dev (VPN ต่ออยู่)
```bash
# เสร็จรึยัง
ssh tikxd@10.110.1.42 'pgrep -f "[s]cripts/vm/run_klauspost_ab.py" >/dev/null && echo "⏳ ยังรัน (elapsed $(ps -o etime= -p $(pgrep -f "[s]cripts/vm/run_klauspost_ab.py")))" || (grep -q "ผลบันทึกที่" ~/kp_full.log && echo "✅ เสร็จ" || echo "⚠️ ตายก่อนจบ")'

# ความคืบหน้า + เช็ค fail (ต้องเป็น 0)
ssh tikxd@10.110.1.42 'echo "scenarios: $(grep -c "^\[" ~/kp_full.log)"; echo "fail(x): $(grep -E "^  (go-|java)" ~/kp_full.log | grep -c x)"; tail -6 ~/kp_full.log'

# ตารางสรุปตอนจบ (ต้องเห็น 🔒 correctness: roundTripOk 100%)
ssh tikxd@10.110.1.42 'tail -45 ~/kp_full.log'

# metric ทะลุ Grafana ไหม
ssh tikxd@10.110.1.42 'curl -s localhost:9100/metrics | grep -c "^pgp_bench_"'
```

## ขั้นตอนถัดไป (หลัง FULL เสร็จ)
1. ตรวจท้าย log ต้องเห็น `🔒 correctness: roundTripOk 100% และไม่มีไฟล์ถูก skip` — ถ้าเห็น `❌❌` ให้หยุดวิเคราะห์ก่อน (อย่าใช้ผล)
2. ดึง `results_klauspost_ab.json` จาก VM มาที่ `report/` แล้ว **สร้าง report v3 สำหรับพรีเซนต์**:
   ```bash
   scp tikxd@10.110.1.42:~/POC-Encryption/report/results_klauspost_ab.json report/
   python3 report/build_klauspost_report.py          # → report/klauspost_report_v3.html
   open report/klauspost_report_v3.html              # เปิดดู (self-contained, ไม่ต้องต่อเน็ต)
   ```
   - report v3 = HTML หน้าเดียว มีแท็บ: สรุปผล / Filetype×KeyAlg / Size Gradient / Production Load / Scaling / Correctness
   - กราฟเป็น inline SVG (ไม่พึ่ง CDN) → เปิดออฟไลน์ตอนพรีเซนต์ได้
   - มี banner correctness (แดงถ้าเจอ roundTripOk<100% หรือ skip) + ตารางแจกแจงทุก variant
   - speedup 2 คอลัมน์: kp vs stdlib, kp vs java (เขียว=klauspost เร็วกว่า)
3. อัปเดตสไลด์ `docs/compression-gap-go-vs-java.md` ด้วยตัวเลข VM จริง
4. จัด Grafana dashboard (metric prefix `pgp_bench_`, PromQL ตัวอย่างใน `scripts/vm/README.md`)
5. **Step 2 (ค้าง)**: push branch ขึ้น remote + เปิด PR — ยังไม่ทำ รอผู้ใช้ตัดสินใจ

## ไฟล์สำคัญ
- `scripts/vm/run_klauspost_ab.py` — ตัวรัน benchmark (มีโหมด FULL/BIG/SIZEGRAD + export .prom)
- `scripts/vm/build_klauspost_ab.sh` — build 3 binary
- `scripts/vm/verify_correctness.py` — ด่าน correctness
- `report/build_klauspost_report.py` — สร้าง report v3 HTML จาก `results_klauspost_ab.json` (self-contained, พร้อมใช้แล้ว ทดสอบ render ผ่าน)
- `scripts/vm/README.md` — วิธีรัน + Grafana/PromQL + gotchas
- `docs/PROGRESS-go-klauspost-experiment.md` — progress ละเอียด
- `runners/go/third_party/go-crypto/` — fork (สลับ zlib ใน openpgp/packet/compressed.go)

## Gotchas
- ต้องมี WARMUP≥3 (ไม่งั้น Java JIT cold ตัวเลขเพี้ยน)
- pgrep -f อย่าใช้ pattern ตรงๆ จะ match คำสั่งตัวเอง (ใช้ `[s]cripts/...`)
- `.prom` เขียนตอนจบเท่านั้น (Grafana ยังไม่เห็นระหว่างรัน)
- ถ้าจะ rerun: `rm -rf ~/corpus-kp ~/kp_full.log` ก่อน

## Snapshot ล่าสุด (ตอนเขียน handoff)
- running=yes, elapsed ~9:45 นาthat, scenarios เริ่มไป **11**, fails=**0**
- กำลังทำ: `ft-xlsx-RSA-4096` (ยังอยู่เฟส filetype matrix — เหลือ count/many/concurrent/sizegrad อีกเยอะ)
