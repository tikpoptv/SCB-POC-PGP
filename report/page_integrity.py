"""page_integrity.py — Tab 6: ความน่าเชื่อถือ + ข้อจำกัด + Next Steps"""


def build() -> str:
    return """
<div class="card">
  <h2><span class="sn">🛡</span>กลไกป้องกันการโกง (Anti-Fake Architecture)</h2>
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
  <h2><span class="sn">📊</span>Statistics ที่คำนวณ</h2>
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
