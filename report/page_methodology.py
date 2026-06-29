"""page_methodology.py — Tab 3: วิธีการทดสอบ (Methodology)"""


def build() -> str:
    return """
<div class="card">
  <h2><span class="sn">🎯</span>วัตถุประสงค์ของ POC</h2>
  <p>POC นี้มีเป้าหมายเดียวที่ชัดเจน: <strong>เปรียบเทียบประสิทธิภาพการเข้ารหัส PGP
  ระหว่างภาษา Go และ Java ภายใต้เงื่อนไขที่ยุติธรรมและทำซ้ำได้</strong>
  เพื่อช่วยตัดสินใจเลือกภาษาสำหรับระบบที่ต้องทำ PGP encryption ในอนาคต</p>
  <div class="info">
    <strong>ขอบเขตที่ชัดเจน:</strong> วัดเฉพาะ <strong>PGP encrypt และ decrypt</strong> เท่านั้น
    — ไม่รวม signing, verify signature, network, database, HTTP API, หรือบริการภายนอก
  </div>
</div>

<div class="card">
  <h2><span class="sn">🏗</span>สถาปัตยกรรมการทดสอบ</h2>
  <p style="margin-bottom:14px">ระบบแบ่งเป็น 3 ส่วนหลักที่แยกกันชัดเจน:</p>
  <div class="grid3">
    <div class="mbox">
      <h4>🔵 Go Runner</h4>
      <ul>
        <li>ภาษา Go 1.24.4</li>
        <li>Library: ProtonMail/go-crypto (fork ที่ดูแลต่อเนื่อง)</li>
        <li>3 Implementation Variants</li>
        <li>Binary ขนาดเล็ก startup เร็ว</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>🟠 Java Runner</h4>
      <ul>
        <li>JDK 25 + Spring Boot 4.x (CLI only)</li>
        <li>Library: Bouncy Castle (bcpg + bcprov)</li>
        <li>4 Implementation Variants</li>
        <li>JVM JIT warm-up (อุ่นเครื่อง) ก่อนเก็บผล</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>🐍 Benchmark Harness (ตัวกลาง)</h4>
      <ul>
        <li>ซอฟต์แวร์ Python 3.12+ — เป็นกลาง ไม่เข้าข้างฝ่ายใด</li>
        <li><strong>ไม่ทำ crypto เอง</strong> — แค่สั่งงานและวัดเวลา</li>
        <li>แยก process Go/Java ออกจากกันสมบูรณ์</li>
        <li>ควบคุม timing, resource, alternating order</li>
      </ul>
    </div>
  </div>
  <div class="hi" style="margin-top:14px">
    <strong>ทำไมต้องแยก subprocess (กระบวนการแยกกัน)?</strong>
    เพราะ memory (หน่วยความจำ), GC (garbage collection — การเก็บขยะหน่วยความจำ),
    JIT (Just-In-Time compiler — ตัวแปลภาษา) ของแต่ละภาษาจะแยกกันสมบูรณ์
    ไม่ปนกัน ผล benchmark จึงสะท้อนความสามารถจริงของแต่ละภาษา
  </div>
</div>

<div class="card">
  <h2><span class="sn">🔄</span>ขั้นตอนการทดสอบทีละขั้น</h2>
  <ul class="timeline">
    <li data-n="1">
      <div class="tl-title">ตรวจสอบการตั้งค่า (Validate Config)</div>
      อ่านและตรวจสอบ config.json — ถ้าค่าไหนผิดช่วง (เช่น จำนวนรอบนอกช่วง 1–1,000 ครั้ง)
      หยุดทันทีก่อนเริ่มทดสอบ แจ้งชื่อค่าที่มีปัญหา
    </li>
    <li data-n="2">
      <div class="tl-title">บันทึกสภาพแวดล้อม (Detect Environment)</div>
      บันทึกสเปก VM: vCPU (จำนวน processor), RAM (หน่วยความจำ), OS, CPU arch,
      storage type, สถานะ AES-NI (hardware acceleration), turbo/governor
      บันทึกเวอร์ชันจริงของ Go/JDK/Spring Boot/Bouncy Castle/go-crypto
    </li>
    <li data-n="3">
      <div class="tl-title">สร้างข้อมูลและกุญแจ (Generate Shared Inputs)</div>
      สร้างไฟล์ทดสอบแบบ deterministic (ผลเหมือนเดิมทุกครั้ง) วางบน RAM disk
      เพื่อตัด disk I/O ออกจากการวัด — สร้างและตรวจสอบกุญแจ RSA-2048, RSA-4096, Curve25519
    </li>
    <li data-n="4">
      <div class="tl-title">Build ซอฟต์แวร์</div>
      Build Go binary (ไฟล์รัน) และ Java JAR (ไฟล์รัน) บันทึกเวอร์ชัน toolchain
      ถ้า GraalVM native build ล้มเหลว ข้ามเฉพาะ variant นั้น ไม่หยุดทั้งชุด
    </li>
    <li data-n="5">
      <div class="tl-title">สลับลำดับ (Alternating Execution) — หัวใจหลัก</div>
      วนหลาย Round สลับลำดับ Go/Java ทุกรอบ:
      รอบ 1 = [Go, Java], รอบ 2 = [Java, Go], รอบ 3 = [Go, Java] ...
      เพื่อให้ทั้งสองฝ่ายได้ CPU cache และ thermal condition เท่ากัน
      ไม่มีฝ่ายได้เปรียบจากการรันก่อนเสมอ
    </li>
    <li data-n="6">
      <div class="tl-title">ด่านความถูกต้อง (Verification Gate)</div>
      ทุก operation ต้องผ่าน: ถอดรหัสกลับได้ byte-for-byte ก่อนเวลาเข้าสถิติ
      ตรวจ checksum (ลายนิ้วมือดิจิทัล), เวอร์ชัน, interoperability Go↔Java↔gpg
    </li>
    <li data-n="7">
      <div class="tl-title">คำนวณสถิติ (Statistics Engine)</div>
      คำนวณ p50/p95/p99 (ค่า percentile), mean/min/max, stddev (ค่าเบี่ยงเบน),
      CV, confidence interval (ช่วงความเชื่อมั่น), effect size (ขนาดผลกระทบ)
      คัดเลือก variant ดีที่สุดของแต่ละภาษา เปรียบเทียบ head-to-head
    </li>
    <li data-n="8">
      <div class="tl-title">สร้างรายงาน (Report Generator)</div>
      สร้าง results.json (ข้อมูลดิบ) และรายงาน HTML ที่อ่านได้
      ต้องเสร็จภายใน 60 วินาทีหลังจบ — เขียนแบบ atomic (ครบหรือไม่มีเลย)
    </li>
  </ul>
</div>

<div class="card">
  <h2><span class="sn">📏</span>วิธีจับเวลา (Timing Methodology)</h2>
  <div class="grid2">
    <div class="mbox">
      <h4>✅ สิ่งที่จับเวลา (นับเข้าผล)</h4>
      <ul>
        <li>การเรียก <strong>encrypt() function</strong> จริง — เข้ารหัส</li>
        <li>การเรียก <strong>decrypt() function</strong> จริง — ถอดรหัส</li>
        <li>เฉพาะ crypto transform เท่านั้น</li>
        <li>Go: monotonic clock (นาฬิกาที่ไม่เดินถอยหลัง)</li>
        <li>Java: System.nanoTime() (จับเวลาระดับ nanosecond)</li>
      </ul>
    </div>
    <div class="mbox red">
      <h4>❌ สิ่งที่ไม่จับเวลา (ไม่นับเข้าผล)</h4>
      <ul>
        <li>การโหลดกุญแจจาก disk (hard drive)</li>
        <li>การอ่าน/เขียนไฟล์ (disk I/O)</li>
        <li>JVM startup time (เวลาเปิด Java)</li>
        <li>JIT warm-up iterations (รอบอุ่นเครื่อง)</li>
        <li>Warm_Up_Iteration rounds</li>
        <li>Harness overhead (เวลาตัวกลาง)</li>
      </ul>
    </div>
  </div>
  <div class="hi" style="margin-top:12px">
    <strong>Cold_Start metric</strong> (เวลา process startup + JIT warm-up รวม) ถูกบันทึกแยกต่างหาก
    เป็น "metric เสริม" ไม่ถูกนำไปรวมกับ core crypto-time ที่ใช้เปรียบเทียบ
  </div>
</div>

<div class="card">
  <h2><span class="sn">⚖️</span>มาตรการความยุติธรรม (Fairness Measures)</h2>
  <div class="grid4">
    <div class="mbox">
      <h4>🔄 Alternating Order (สลับลำดับ)</h4>
      <p>สลับลำดับ Go/Java ทุกรอบ เพื่อลด bias (ความเอนเอียง) จากการที่
         ซอฟต์แวร์หนึ่งได้ CPU warm cache (หน่วยความจำแคชที่ร้อน) ก่อนเสมอ</p>
    </div>
    <div class="mbox">
      <h4>🔑 Input เดียวกัน (Shared Inputs)</h4>
      <p>ชุดกุญแจเดียว, ชุดไฟล์ทดสอบเดียว, crypto algorithm เดียวกัน
         checksum (ลายนิ้วมือดิจิทัล) ยืนยันว่า ซอฟต์แวร์ทั้งสองใช้ข้อมูล
         byte-for-byte เหมือนกันทุก bit</p>
    </div>
    <div class="mbox">
      <h4>💾 Resource เท่ากัน</h4>
      <p>CPU cores (จำนวน processor) และ memory quota (โควต้าหน่วยความจำ)
         เท่ากันทั้งสองฝ่าย มี 1 ซอฟต์แวร์ active ต่อเวลา ไม่แย่งทรัพยากรกัน</p>
    </div>
    <div class="mbox">
      <h4>📦 Isolated Process (แยก process)</h4>
      <p>Go และ Java รันเป็น subprocess แยกกันสมบูรณ์
         GC (garbage collection), memory heap, JIT (compiler) ของ Java
         ไม่ส่งผลต่อ Go และในทางกลับกัน</p>
    </div>
  </div>
</div>"""
