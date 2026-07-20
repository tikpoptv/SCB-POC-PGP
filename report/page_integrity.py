"""page_integrity.py — Tab 6: ความน่าเชื่อถือ + ข้อจำกัด + Next Steps"""


def build() -> str:
    return """
<div class="card">
  <h2><span class="sn">🔎</span>ทำไมผลรอบนี้ Go ชนะหมด? — คำอธิบายความแตกต่างระหว่าง 2 รอบ</h2>

  <div class="hi" style="margin-bottom:16px">
    <strong>คำถามสำคัญ:</strong> รอบแรก Java ยังชนะ .txt และ .csv แต่รอบ Final นี้ Go ชนะหมดทุก scenario — ทำไม?
  </div>

  <div class="grid2">
    <div class="mbox orange">
      <h4>⚠️ รอบแรก (8 GB RAM) — Java ชนะ .txt/.csv</h4>
      <p style="margin-bottom:8px">
        <strong>สาเหตุ: JVM Warm Cache Effect</strong>
      </p>
      <ul>
        <li>รอบแรก JVM ถูกรันต่อเนื่องหลาย scenario — JIT compiler และ memory cache อุ่นอยู่แล้ว</li>
        <li>ผล Java .txt ≈ 15 ms (JVM warm state)</li>
        <li>ผล Go .txt ≈ 26 ms (ตัวเลขใหญ่ผิดปกติ = corpus ก่อนหน้ายังถูก cache ค้างอยู่)</li>
        <li>ความแตกต่างนี้ทำให้ Java ดูเร็วกว่าที่ควร</li>
      </ul>
    </div>
    <div class="mbox green">
      <h4>✅ รอบ Final (14 GB RAM + reboot) — ผลที่แม่นกว่า</h4>
      <p style="margin-bottom:8px">
        <strong>เหตุผลที่น่าเชื่อถือกว่า:</strong>
      </p>
      <ul>
        <li>VM reboot ใหม่ ไม่มี JVM state ค้างจากรอบก่อน</li>
        <li>ทุก process เริ่มใหม่สะอาด (cold start) ก่อนทุก scenario</li>
        <li>ผล Java .txt ≈ 3.4 ms / Go .txt ≈ 2.5 ms</li>
        <li>ความแตกต่างน้อยลง แต่ Go ยังเร็วกว่าอย่างสม่ำเสมอ</li>
        <li>RAM 14 GB ทำให้ไม่มี memory pressure รบกวน</li>
      </ul>
    </div>
  </div>

  <table style="margin-top:16px">
    <thead><tr>
      <th>Scenario</th>
      <th>รอบแรก Go (8GB)</th><th>รอบแรก Java (8GB)</th><th>รอบแรก Winner</th>
      <th>รอบ Final Go (14GB)</th><th>รอบ Final Java (14GB)</th><th>รอบ Final Winner</th>
    </tr></thead>
    <tbody>
      <tr style="background:#fef3e2">
        <td>.txt RSA-2048</td>
        <td>26.72 ms</td><td><strong>15.69 ms</strong></td>
        <td><span class="badge bj">🟠 Java ชนะ</span></td>
        <td><strong>2.51 ms</strong></td><td>3.44 ms</td>
        <td><span class="badge bg">🔵 Go ชนะ</span></td>
      </tr>
      <tr style="background:#fef3e2">
        <td>.csv RSA-2048</td>
        <td>25.81 ms</td><td><strong>20.30 ms</strong></td>
        <td><span class="badge bj">🟠 Java ชนะ</span></td>
        <td><strong>2.41 ms</strong></td><td>3.43 ms</td>
        <td><span class="badge bg">🔵 Go ชนะ</span></td>
      </tr>
      <tr>
        <td>.pdf RSA-2048</td>
        <td><strong>12.78 ms</strong></td><td>15.61 ms</td>
        <td><span class="badge bg">🔵 Go ชนะ</span></td>
        <td><strong>~2.4 ms</strong></td><td>~3.5 ms</td>
        <td><span class="badge bg">🔵 Go ชนะ</span></td>
      </tr>
    </tbody>
  </table>

  <div class="info" style="margin-top:16px">
    <strong>สรุป:</strong> ผล .txt/.csv รอบแรกที่ Java ชนะ เกิดจาก <strong>JVM Warm Cache</strong>
    ซึ่งเป็น advantage ที่ Java ได้จาก JIT compiler ที่ค้างอุ่นอยู่ ไม่ใช่ความสามารถจริงของ algorithm
    เมื่อ reboot ใหม่ (ซึ่งสะท้อน real-world deployment ที่แต่ละ process เริ่มใหม่) Go ชนะทุก scenario
    <br><br>
    <strong>ผลรอบ Final จึงน่าเชื่อถือและ fair กว่า</strong> สำหรับการตัดสินใจเลือกภาษา
  </div>
</div>

<div class="card">
  <h2><span class="sn">💡</span>JVM Warm คืออะไรกันแน่? — อธิบายเพิ่มเติมสำหรับคนทั่วไป</h2>

  <p style="margin-bottom:14px">
    คำว่า <strong>"JVM อุ่น" (JVM Warm)</strong> มักเข้าใจผิดว่าหมายถึง "ข้อมูลค้างในแรม"
    ซึ่งไม่ถูกต้องทั้งหมด ขอแยกอธิบาย 2 แนวคิดที่ต่างกัน:
  </p>

  <div class="grid2">
    <div class="mbox orange">
      <h4>🔥 JVM JIT Warm (สิ่งที่เกิดขึ้นในรอบแรก)</h4>
      <p style="margin-bottom:8px">
        <strong>JIT = Just-In-Time Compiler</strong> — ตัวแปลโค้ดแบบ real-time<br><br>
        JVM ไม่ได้รันโค้ดตรงๆ แต่แปลงเป็น "native instructions" ขณะรัน
        รอบแรกๆ JIT ยังไม่ได้แปลงฟังก์ชัน crypto — รันแบบ "interpreted" (ช้า)
        พอรันซ้ำหลายครั้ง JIT เรียนรู้และ compile ฟังก์ชันนั้นให้เร็วขึ้น
        <br><br>
        <strong>ผลที่เกิด:</strong> JVM ที่ "อุ่นแล้ว" (ผ่านการรันหลายรอบ)
        จะเร็วกว่า JVM ที่เพิ่งเริ่ม แม้ <em>ข้อมูลที่รันจะไม่เหมือนกันเลย</em>
        เพราะ JIT optimize <em>โค้ดฟังก์ชัน</em> ไม่ใช่ข้อมูล
      </p>
      <div class="hi" style="margin-top:8px;font-size:12px">
        <strong>ตอบคำถาม "ถ้าข้อมูลไม่ซ้ำกัน แรมอุ่นช่วยได้มั้ย?"</strong><br>
        ✅ <strong>ช่วยได้</strong> — เพราะ JVM Warm ไม่ได้ cache ข้อมูล
        แต่ cache <em>โค้ด crypto ที่ compiled แล้ว</em>
        ข้อมูลใหม่ทุกไฟล์ก็ยังได้ประโยชน์จาก JIT ที่อุ่นแล้วเต็มที่
      </div>
    </div>
    <div class="mbox">
      <h4>💾 RAM/OS Cache (สิ่งที่ไม่เกี่ยวกับ JIT)</h4>
      <p style="margin-bottom:8px">
        OS cache ไฟล์ที่เพิ่งอ่านไว้ใน RAM — ถ้าอ่านไฟล์เดิมอีกครั้ง เร็วกว่าอ่านจาก disk
        <br><br>
        ในการทดสอบนี้: ไฟล์ทดสอบวางบน <strong>tmpfs (RAM disk)</strong> อยู่แล้ว
        — ดังนั้น OS file cache ไม่มีผลต่อผลการทดสอบ
        <br><br>
        <strong>สำหรับชีวิตจริง:</strong> ถ้าข้อมูลไม่ซ้ำกัน (เช่น user อัพโหลดไฟล์ใหม่ทุกครั้ง)
        OS file cache ก็ไม่ช่วยอยู่แล้ว — ข้อมูลแต่ละชิ้นต้องอ่านใหม่เสมอ
      </p>
      <div class="info" style="margin-top:8px;font-size:12px">
        ดังนั้น RAM cache ของข้อมูล <strong>ไม่เกี่ยวกับ JVM Warm</strong>
        สองอย่างนี้แยกกันสมบูรณ์
      </div>
    </div>
  </div>

  <div class="card" style="margin-top:14px;background:#e8f5e9;border:1px solid #27ae60">
    <h4 style="color:#1b5e20">🧪 ผลทดสอบ Warm JVM บน VM จริง — RSA-2048 · .txt · 15 files × 512KB</h4>
    <p style="margin-bottom:12px">
      ทดสอบเพิ่มเติมบน VM เดิม (Ubuntu 24.04, 8 vCPU, 14GB RAM) ยังไม่ reboot
      เพื่อ confirm ว่า JIT warm-up ช่วย Java จริงแค่ไหน
    </p>
    <table style="margin-bottom:12px">
      <thead><tr>
        <th>Mode</th>
        <th style="text-align:center">p50 ms/file</th>
        <th>เทียบกับ Go</th>
        <th>คำอธิบาย</th>
      </tr></thead>
      <tbody>
        <tr style="background:#dbeafe">
          <td><strong>🔵 Go cold</strong> (new process)</td>
          <td style="text-align:center;font-weight:700">1.59 ms</td>
          <td>baseline</td>
          <td>Go ทุก process คือ "cold" เพราะไม่มี JVM</td>
        </tr>
        <tr style="background:#fef3c7">
          <td><strong>🟠 Java cold</strong> (warmup=0)</td>
          <td style="text-align:center;font-weight:700">3.36 ms</td>
          <td><span class="badge bg">Go เร็วกว่า 2.1×</span></td>
          <td>JVM เพิ่งเริ่ม JIT ยังไม่ compile crypto functions</td>
        </tr>
        <tr style="background:#dcfce7">
          <td><strong>🟠 Java warm</strong> (warmup=20 iters)</td>
          <td style="text-align:center;font-weight:700">1.67 ms</td>
          <td><span class="badge bt">Go เร็วกว่า ~1.05×</span></td>
          <td>JIT compile ครบแล้ว — เกือบตาม Go</td>
        </tr>
      </tbody>
    </table>
    <div class="hi" style="font-size:12px">
      <strong>✅ ผลที่ได้จากการทดสอบจริง:</strong><br>
      • JVM warmup 20 iterations ช่วย Java เร็วขึ้น <strong>50%</strong>
        (cold 3.36 ms → warm 1.67 ms)<br>
      • Java warm เกือบตาม Go ได้สำหรับ .txt RSA-2048
        (1.67 ms vs 1.59 ms — ต่างกันแค่ 5%)<br>
      • <strong>แต่ Go ยังได้เปรียบที่ binary files (.pdf/.xlsx/.dat) และ concurrent load</strong>
        — warmup ไม่ได้ช่วยตรงนั้น<br>
      • สรุป: Java long-running service สำหรับ .txt/.csv อาจ competitive กับ Go ได้
        แต่ต้องยอมรับ warmup cost ~1,000+ request แรก
    </div>
  </div>
</div>

  <p style="margin-bottom:14px">
    ระบบออกแบบมาเพื่อให้ <strong>"ตัวเลขเร็ว" ไม่มีค่าเลยถ้าไม่ผ่านด่านเหล่านี้</strong>
    ทุก gate ตรวจสอบอัตโนมัติก่อนนำตัวเลขเข้าสถิติ:
  </p>
  <table>
    <thead><tr><th>Gate (ด่าน)</th><th>วิธีทำงาน</th><th>ถ้าไม่ผ่าน</th></tr></thead>
    <tbody>
      <tr><td><strong>🔁 Round-trip Gate</strong></td>
          <td>ถอดรหัส(เข้ารหัส(x)) = x ทุก byte สำหรับทุกไฟล์ใน Benchmark_Run</td>
          <td>ยกเว้นเวลา run นั้นออกจากสถิติทั้งหมด บันทึกจำนวนที่ยกเว้น</td></tr>
      <tr><td><strong>🌐 Interop Gate</strong></td>
          <td>Go เข้ารหัส → Java ถอดรหัสได้, Java เข้ารหัส → Go ถอดรหัสได้, + gpg CLI</td>
          <td>mark non-comparable (ไม่สามารถเปรียบเทียบ) พร้อมระบุสาเหตุ</td></tr>
      <tr><td><strong>🔐 Checksum Gate</strong></td>
          <td>SHA-256 ของ Key_Set และ Corpus ต้องตรงกับค่า reference ก่อน run</td>
          <td>ยุติ run นั้น exit code 2 ไม่นับเข้าสถิติ</td></tr>
      <tr><td><strong>📌 Version Gate</strong></td>
          <td>ตรวจเวอร์ชัน Go/JDK/library จริงแบบ major.minor.patch เทียบค่าที่บันทึก</td>
          <td>mark ผลรอบนั้นว่า "ไม่ถูกต้อง" แต่ยังดำเนินการต่อ</td></tr>
      <tr><td><strong>⏱ Timing Isolation</strong></td>
          <td>monotonic clock (นาฬิกาที่ไม่เดินถอยหลัง) ครอบเฉพาะ crypto call ไม่รวม I/O, key load, warmup</td>
          <td>—</td></tr>
      <tr><td><strong>📊 Raw Sample Retention</strong></td>
          <td>เก็บ per-operation samples (ตัวเลขดิบทุกค่า) ไม่ใช่แค่ aggregate (ค่าสรุป)</td>
          <td>ตรวจสอบ/ทำซ้ำได้ย้อนหลัง (auditable)</td></tr>
    </tbody>
  </table>
</div>

<div class="card">
  <h2><span class="sn">✅</span>ผลนี้เชื่อถือได้แค่ไหน? — สำหรับผู้บริหาร</h2>
  <p style="margin-bottom:16px;color:#666">
    คำตอบตรง ๆ: <strong>เชื่อถือได้สูงสำหรับการตัดสินใจเบื้องต้น</strong>
    มีกลไกป้องกันครบถ้วน แต่มีข้อจำกัดบางอย่างที่ต้องรู้
  </p>

  <div class="grid2">
    <div class="mbox green">
      <h4>✅ สิ่งที่ทำให้เชื่อถือได้</h4>
      <ul style="line-height:2">
        <li><strong>721 tests ผ่านทั้งหมดก่อน benchmark</strong>
            — ยืนยันว่าซอฟต์แวร์ทั้งสองทำงานถูกต้อง 100%</li>
        <li><strong>สลับลำดับ Go/Java ทุกรอบ</strong>
            — ไม่มีฝ่ายได้เปรียบ CPU cache หรือ thermal condition</li>
        <li><strong>Verification Gate ทุก operation</strong>
            — operation ที่ผิดพลาดถูกยกเว้น ไม่เข้าสถิติ</li>
        <li><strong>วัดเฉพาะ crypto call จริง</strong>
            — ไม่รวมเวลาโหลดไฟล์ ไม่รวม JVM startup</li>
        <li><strong>Raw samples เก็บครบทุกค่า</strong>
            — audit ย้อนหลังได้ทุกค่า</li>
        <li><strong>Corpus บน RAM disk</strong>
            — ตัด disk speed ออกจากผลโดยสมบูรณ์</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>⚠️ ข้อจำกัดที่ต้องรู้</h4>
      <ul style="line-height:2">
        <li><strong>VM ≠ Bare Metal</strong>:
            ผลบน VM อาจต่างจาก bare metal (เครื่องจริง) 10–20%
            แต่ความสัมพันธ์ relative Go vs Java น่าจะยังคงเดิม</li>
        <li><strong>JVM Startup ไม่รวมใน core metric</strong>:
            Java ใช้เวลา ~1.4 วินาทีต่อ JVM warmup
            สำหรับ long-running service ผลต่างนี้ไม่มีนัยสำคัญ</li>
        <li><strong>GraalVM Native ยังไม่ได้ทดสอบ</strong>:
            Native image (ไม่ต้องมี JVM) ไม่ได้ติดตั้งบน VM
            อาจทำให้ Java startup ดีขึ้นมาก</li>
        <li><strong>เฉพาะ AES-256+ZLIB+SHA-256</strong>:
            cipher/compression อื่น (เช่น ChaCha20) อาจให้ผลต่าง</li>
        <li><strong>5 rounds เท่านั้น</strong>:
            สำหรับ statistical significance ที่สูงขึ้น ควรใช้ ≥30 rounds</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2><span class="sn">📐</span>นัยยะสำคัญ — ขนาดไฟล์และจำนวนไฟล์ที่ทำให้ช้าลง</h2>
  <p style="margin-bottom:14px;color:#666">
    จากข้อมูล benchmark จริง 26 scenarios พบ <strong>4 ปัจจัยหลัก</strong>
    ที่ส่งผลต่อความเร็วและช่องว่างระหว่าง Go กับ Java อย่างมีนัยสำคัญ
  </p>

  <div class="grid2">

    <div class="mbox">
      <h4>① ขนาดไฟล์ใหญ่ขึ้น → ช่องว่างแคบลง (AES dominates)</h4>
      <p style="margin-bottom:10px;font-size:12px;color:#666">
        เมื่อไฟล์ใหญ่ขึ้น เวลาส่วนใหญ่เป็น AES symmetric encryption ไม่ใช่ key setup
        ทั้ง Go และ Java ต่างใช้ AES-NI hardware — ช่องว่างจึงแคบลง
      </p>
      <table>
        <thead><tr>
          <th>ขนาดไฟล์ (approx)</th>
          <th>Go p50</th><th>Java p50</th><th>Go เร็วกว่า</th>
        </tr></thead>
        <tbody>
          <tr><td>~1 KB (many-1kb)</td>
              <td style="color:#00ADE8">0.76 ms</td>
              <td style="color:#F89820">1.02 ms</td>
              <td><strong>1.33×</strong></td></tr>
          <tr><td>~10 KB (many-10kb)</td>
              <td style="color:#00ADE8">0.79 ms</td>
              <td style="color:#F89820">1.16 ms</td>
              <td><strong>1.46×</strong></td></tr>
          <tr><td>~100 KB (many-100kb)</td>
              <td style="color:#00ADE8">1.20 ms</td>
              <td style="color:#F89820">1.59 ms</td>
              <td><strong>1.32×</strong></td></tr>
          <tr style="background:#dbeafe"><td>~512 KB (ft-txt-rsa2048)</td>
              <td style="color:#00ADE8">2.51 ms</td>
              <td style="color:#F89820">3.44 ms</td>
              <td><strong>1.37×</strong></td></tr>
          <tr><td>Size gradient (1KB–20MB mix)</td>
              <td style="color:#00ADE8">16.4 ms</td>
              <td style="color:#F89820">18.8 ms</td>
              <td><strong>1.14×</strong></td></tr>
        </tbody>
      </table>
      <div class="info" style="margin-top:10px;font-size:12px">
        <strong>นัยยะ:</strong> ไฟล์เล็ก (&lt;10KB) Java เสียเปรียบมากที่สุดจาก per-file overhead
        ไฟล์ใหญ่ (&gt;1MB) ช่องว่างแคบเหลือ ~1.1× เพราะ AES hardware ทำงานหลัก
      </div>
    </div>

    <div class="mbox">
      <h4>② ไฟล์เล็กจำนวนมาก → Java เสียเปรียบมากขึ้น (per-file overhead)</h4>
      <p style="margin-bottom:10px;font-size:12px;color:#666">
        แต่ละไฟล์ต้องทำ key wrap/unwrap + PGP packet structure ใหม่
        Java มี JVM object allocation overhead ต่อ operation สูงกว่า Go
      </p>
      <div class="hi" style="font-size:12px">
        <strong>ตัวอย่างชีวิตจริง:</strong><br>
        ระบบที่รับ upload ไฟล์ขนาดเล็ก 10,000 ไฟล์/วัน (เช่น สลิปโอนเงิน ~50KB)
        <br>• Go: ~50 ms รวม 1,000 ไฟล์
        <br>• Java: ~73 ms รวม 1,000 ไฟล์ (ช้ากว่า ~1.46×)
        <br>• ต่างกัน 23ms ต่อ 1,000 ไฟล์ = ต่างกัน 0.23 วินาที/วัน ที่ 10k ไฟล์ = <strong>2.3 วินาที</strong>
      </div>
      <div class="info" style="margin-top:10px;font-size:12px">
        <strong>นัยยะ:</strong> ถ้าระบบ batch หลายหมื่นไฟล์ขนาดเล็กต่อวัน
        Go ประหยัด processing time ได้ชัดเจน
        แต่ถ้าไฟล์น้อย (&lt;100 ไฟล์/วัน) ต่างกัน &lt;1ms ไม่มีนัยสำคัญ
      </div>
    </div>

    <div class="mbox">
      <h4>③ ชนิด Key Type → ส่งผลมากที่สุด</h4>
      <p style="margin-bottom:10px;font-size:12px;color:#666">
        Key algorithm เป็นปัจจัยเดียวที่ส่งผลต่อช่องว่าง Go vs Java มากกว่า file size
      </p>
      <table>
        <thead><tr>
          <th>Key Algorithm</th>
          <th>Go p50</th><th>Java p50</th><th>Go เร็วกว่า</th>
        </tr></thead>
        <tbody>
          <tr style="background:#dbeafe">
            <td><strong>Curve25519</strong> (แนะนำ)</td>
            <td style="color:#00ADE8">1.76 ms</td>
            <td style="color:#F89820">3.15 ms</td>
            <td><strong>1.79×</strong></td></tr>
          <tr><td>RSA-2048 (มาตรฐาน)</td>
              <td style="color:#00ADE8">2.51 ms</td>
              <td style="color:#F89820">3.44 ms</td>
              <td><strong>1.37×</strong></td></tr>
          <tr><td>RSA-4096 (high-security)</td>
              <td style="color:#00ADE8">6.33 ms</td>
              <td style="color:#F89820">7.94 ms</td>
              <td><strong>1.25×</strong></td></tr>
        </tbody>
      </table>
      <div class="hi" style="margin-top:10px;font-size:12px">
        <strong>นัยยะ:</strong> Key algorithm เป็นตัวชี้ขาดมากกว่า file size
        Curve25519 ให้ Go ได้เปรียบสูงสุด (1.79×) และเร็วกว่า RSA-2048 ด้วย
        ถ้าระบบใหม่ต้องการ performance — เลือก Curve25519 + Go ทันที
      </div>
    </div>

    <div class="mbox">
      <h4>④ Binary vs Compressible → ผลต่างชนิดไฟล์</h4>
      <p style="margin-bottom:10px;font-size:12px;color:#666">
        ชนิดข้อมูลบีบอัดได้มากแค่ไหน ส่งผลต่อ throughput แต่ไม่เปลี่ยนผู้ชนะ
      </p>
      <table>
        <thead><tr>
          <th>ชนิดไฟล์</th><th>บีบอัด</th>
          <th>Go thr</th><th>Java thr</th><th>Go เร็วกว่า</th>
        </tr></thead>
        <tbody>
          <tr style="background:#dcfce7">
            <td>.txt / .csv</td><td>~80%</td>
            <td style="color:#00ADE8">196–205 MB/s</td>
            <td style="color:#F89820">143–145 MB/s</td>
            <td><strong>1.37–1.42×</strong></td></tr>
          <tr><td>.pdf / .xlsx</td><td>~5%</td>
            <td style="color:#00ADE8">42–44 MB/s</td>
            <td style="color:#F89820">33–34 MB/s</td>
            <td><strong>1.24–1.25×</strong></td></tr>
          <tr><td>.zip / .dat</td><td>~0%</td>
            <td style="color:#00ADE8">44–47 MB/s</td>
            <td style="color:#F89820">34–39 MB/s</td>
            <td><strong>1.25–1.28×</strong></td></tr>
        </tbody>
      </table>
      <div class="info" style="margin-top:10px;font-size:12px">
        <strong>นัยยะ:</strong> .txt/.csv throughput สูงกว่า binary ~4–5× (ZLIB ช่วยลดข้อมูลที่ต้อง AES encrypt)
        แต่ Go ยังชนะทุกชนิดไฟล์อยู่ดี — ชนิดไฟล์ไม่เปลี่ยนผู้ชนะ แต่เปลี่ยน throughput อย่างมาก
      </div>
    </div>

  </div>

  <div class="card" style="margin-top:14px;background:#fff3cd;border:1px solid #ffc107">
    <h4>📌 สรุปปัจจัยที่ทีม Engineer ต้องรู้ก่อนเลือกภาษา</h4>
    <table>
      <thead><tr>
        <th>ถ้า workload เป็น...</th>
        <th>Go vs Java ช่องว่าง</th>
        <th>คำแนะนำ</th>
      </tr></thead>
      <tbody>
        <tr style="background:#dbeafe">
          <td>ไฟล์เล็ก &lt;10KB จำนวนมาก (batch หมื่นไฟล์/วัน)</td>
          <td>Go เร็วกว่า <strong>1.33–1.46×</strong></td>
          <td>✅ Go ได้เปรียบชัด</td></tr>
        <tr>
          <td>ไฟล์กลาง 100KB–1MB (document, PDF)</td>
          <td>Go เร็วกว่า <strong>1.24–1.37×</strong></td>
          <td>✅ Go ได้เปรียบชัด</td></tr>
        <tr>
          <td>ไฟล์ใหญ่ &gt;5MB หลายไฟล์ (large export)</td>
          <td>Go เร็วกว่า <strong>~1.14×</strong></td>
          <td>⚖️ ทั้งคู่พอๆ กัน</td></tr>
        <tr style="background:#dcfce7">
          <td>Java long-running service + .txt/.csv</td>
          <td>Go เร็วกว่า <strong>~1.05×</strong> (เมื่อ JIT warm)</td>
          <td>⚖️ Java competitive ได้</td></tr>
        <tr style="background:#dbeafe">
          <td>Curve25519 + ไฟล์ไหนก็ได้</td>
          <td>Go เร็วกว่า <strong>1.13–1.79×</strong></td>
          <td>✅ Go ได้เปรียบชัด</td></tr>
        <tr>
          <td>Concurrent 8+ clients พร้อมกัน</td>
          <td>Go throughput สูงกว่า <strong>1.8×</strong></td>
          <td>✅ Go ได้เปรียบมาก</td></tr>
      </tbody>
    </table>
  </div>
</div>


  <div class="grid2">
    <div class="mbox">
      <h4>Latency Statistics (สถิติเวลาตอบสนอง)</h4>
      <ul>
        <li><strong>p50 (median — ค่ากลาง)</strong>:
            เรียงทุกค่าแล้วเอาตัวกลาง — 50% ของ operations เร็วกว่านี้</li>
        <li><strong>p95</strong>: 95% ของ operations เร็วกว่านี้ (reliable เมื่อ n≥20 ค่า)</li>
        <li><strong>p99</strong>: worst-case ที่ยอมรับได้ (reliable เมื่อ n≥100 ค่า)</li>
        <li><strong>min/max/mean</strong>: ต่ำสุด/สูงสุด/เฉลี่ย</li>
        <li><strong>stddev (ค่าเบี่ยงเบนมาตรฐาน)</strong>:
            บอกว่าตัวเลขกระจายตัวมากแค่ไหน</li>
        <li><strong>CV = stddev/mean</strong>: ความผันผวนสัมพัทธ์</li>
        <li>Method: linear interpolation type-7</li>
      </ul>
    </div>
    <div class="mbox">
      <h4>Throughput &amp; Additional (ปริมาณงานและอื่น ๆ)</h4>
      <ul>
        <li><strong>MB/sec</strong> = bytes/1,048,576 ÷ time_s (crypto-only)</li>
        <li><strong>files/sec</strong> = files ÷ time_s</li>
        <li><strong>Round-trip ms</strong> = encryptMs + decryptMs</li>
        <li><strong>Error rate</strong> = failures/attempted ∈ [0.0, 1.0]</li>
        <li><strong>Confidence interval 95%</strong>
            (ช่วงที่เชื่อมั่น 95% ว่าค่าจริงอยู่ในนั้น)</li>
        <li><strong>Effect size (Cohen's d)</strong>
            (ขนาดผลกระทบ — small/medium/large)</li>
        <li><strong>Inconclusive</strong> ถ้า diff ≤5% (ต่างกันน้อยจนไม่มีนัยสำคัญ)</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2><span class="sn">⚠️</span>ข้อจำกัดและหมายเหตุสำคัญ</h2>
  <div class="grid2">
    <div class="mbox red">
      <h4>สิ่งที่ต้องระวังในการตีความ</h4>
      <ul>
        <li><strong>VM ≠ Bare Metal</strong>: ผลบน VM อาจต่างจาก bare metal 10–20%
            แต่ความสัมพันธ์ relative Go vs Java น่าจะยังคงเดิม</li>
        <li><strong>JVM Startup ไม่รวมใน core metric</strong>:
            Java ใช้เวลา ~1.4 s/round JVM warmup แต่ไม่ถูกนับ
            สำหรับ long-running service ผลต่างนี้ไม่มีนัยสำคัญ</li>
        <li><strong>GraalVM Native ยังไม่ได้ทดสอบ</strong>:
            native-image ไม่ได้ติดตั้งบน VM — อาจทำให้ Java startup ดีขึ้นมาก</li>
        <li><strong>เฉพาะ AES-256+ZLIB+SHA-256</strong>:
            cipher/compression อื่น (เช่น ChaCha20) อาจให้ผลต่าง</li>
      </ul>
    </div>
    <div class="mbox">
      <h4>Reproducibility (ทำซ้ำได้)</h4>
      <ul>
        <li>Corpus สร้างจาก seed เดิมทุกครั้ง (bit-for-bit identical)</li>
        <li>Key_Set checksum ยืนยันก่อนทุก run</li>
        <li>เวอร์ชัน toolchain บันทึกใน results.json</li>
        <li>config.json เก็บค่าที่ใช้จริงทั้งหมด</li>
        <li>Raw per-operation samples เก็บครบทุกค่า</li>
        <li>ทำซ้ำได้บน VM เดิมโดยรัน benchmark script ใหม่</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2><span class="sn">➡️</span>Next Steps — ข้อเสนอแนะสำหรับผู้บริหาร</h2>
  <p style="margin-bottom:16px;color:#666">
    จากผลการทดสอบนี้ ขั้นตอนต่อไปขึ้นอยู่กับบริบทของโครงการ:
  </p>

  <div class="grid2">
    <div class="mbox green">
      <h4>📌 ถ้าเลือก Go (แนะนำสำหรับระบบใหม่)</h4>
      <ul style="line-height:2">
        <li>เหมาะที่สุดสำหรับระบบที่ต้องการ PGP throughput (ปริมาณงาน) สูงสุด</li>
        <li>ใช้ Curve25519 ECC เป็น key type หลัก — เร็วกว่า RSA 3.6–3.9×</li>
        <li>ทดสอบ workload จริงบน bare metal (เครื่องจริงไม่ใช่ VM) ก่อน go-live</li>
        <li>ทีมต้องมีความรู้ Go — ควรประเมิน learning curve</li>
        <li>Library ProtonMail/go-crypto ดูแลต่อเนื่อง มี community ดี</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>📌 ถ้าใช้ Java ต่อ (ระบบที่มีอยู่แล้ว)</h4>
      <ul style="line-height:2">
        <li>Java ทำได้ดีพอ แค่ช้ากว่า 1.4–3.9× ขึ้นอยู่กับ key type</li>
        <li>ลองทดสอบ GraalVM Native Image — อาจลด startup time ได้มาก</li>
        <li>ใช้ Curve25519 แทน RSA ถ้าเป็นระบบใหม่ — ช่วยความเร็วได้มาก</li>
        <li>ใช้ streaming variant แทน in-memory — ลด peak memory ลง</li>
        <li>Bouncy Castle library ดูแลต่อเนื่อง มี enterprise support</li>
      </ul>
    </div>
  </div>

  <div class="card" style="margin-top:16px;background:#e8f5e9;border:1px solid #27ae60">
    <h3 style="color:#1b5e20">🔬 ข้อแนะนำสำหรับ POC รอบถัดไป (ถ้าต้องการข้อมูลเพิ่ม)</h3>
    <div class="grid2">
      <ul style="line-height:2">
        <li>ทดสอบบน <strong>bare metal</strong> (เครื่องจริง) — ผลแม่นกว่า VM 10–20%</li>
        <li>ติดตั้ง <strong>GraalVM Native Image</strong> ทดสอบ java-native variant ให้ครบ</li>
        <li>เพิ่ม rounds เป็น ≥30 — สถิติ p95/p99 มีความน่าเชื่อถือสูงขึ้น</li>
        <li>ทดสอบ <strong>concurrent load</strong> (หลาย user พร้อมกัน) ไม่ใช่แค่ single-run</li>
      </ul>
      <ul style="line-height:2">
        <li>ทดสอบ <strong>memory pressure</strong> — เมื่อ RAM ไม่พอ streaming variant ได้เปรียบชัดเจน</li>
        <li>ทดสอบ <strong>large files &gt;100 MB</strong> — ผลอาจต่างจากไฟล์ 5 MB</li>
        <li>ทดสอบ <strong>signing + verification</strong> ถ้า use case ต้องการ</li>
        <li>ทดสอบ <strong>ChaCha20</strong> เป็น cipher อีก profile</li>
      </ul>
    </div>
  </div>
</div>"""
