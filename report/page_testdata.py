"""page_testdata.py — Tab 4: ข้อมูลทดสอบ + Variants + Crypto Profile"""


def build() -> str:
    return """
<!-- ══ ชุดข้อมูลทดสอบ ══ -->
<div class="card">
  <h2><span class="sn">📁</span>ชุดข้อมูลทดสอบ (Test Corpus)</h2>
  <p style="margin-bottom:16px">
    ไฟล์ทดสอบสร้างจากโปรแกรมอัตโนมัติ ผลเหมือนกันทุกครั้ง (reproducible)
    วางบน <strong>RAM Disk</strong> — คือ disk เสมือนที่อยู่ใน RAM
    ทำให้ไม่มี disk I/O มาทำให้ผลการวัดคลาดเคลื่อน
  </p>
  <table>
    <thead><tr>
      <th>กลุ่มทดสอบ</th><th>จำนวนไฟล์</th><th>ขนาดต่อไฟล์</th>
      <th>ชนิดข้อมูล</th><th>บีบอัดได้?</th><th>วัตถุประสงค์</th>
    </tr></thead>
    <tbody>
      <tr><td><strong>small-comp</strong></td><td>20 ไฟล์</td><td>50 KB</td>
          <td>.txt / .csv (ข้อความที่มีรูปแบบซ้ำ)</td>
          <td><span style="color:#27ae60">✅ บีบได้ดีมาก</span></td>
          <td>ไฟล์เล็ก เนื้อหาบีบอัดได้ — เหมือนเอกสาร/รายงานทั่วไป</td></tr>
      <tr><td><strong>small-incomp</strong></td><td>20 ไฟล์</td><td>50 KB</td>
          <td>ข้อมูล binary สุ่ม (เหมือน PDF ที่มีรูป)</td>
          <td><span style="color:#e74c3c">❌ บีบแทบไม่ได้</span></td>
          <td>ไฟล์เล็ก เนื้อหาบีบไม่ได้ — เหมือนไฟล์ scan เอกสาร</td></tr>
      <tr><td><strong>medium-comp</strong></td><td>4 ไฟล์</td><td>5 MB</td>
          <td>.csv (ตาราง 5 MB)</td>
          <td><span style="color:#27ae60">✅ บีบได้ดีมาก</span></td>
          <td>ไฟล์กลาง — เหมือน export ข้อมูล ERP/SAP ประจำวัน</td></tr>
      <tr><td><strong>medium-incomp</strong></td><td>4 ไฟล์</td><td>5 MB</td>
          <td>ข้อมูล binary สุ่ม</td>
          <td><span style="color:#e74c3c">❌ บีบแทบไม่ได้</span></td>
          <td>ไฟล์กลาง binary — เหมือน PDF ที่มีรูปภาพความละเอียดสูง</td></tr>
      <tr><td><strong>manysmall</strong></td><td>100 ไฟล์</td><td>10 KB</td>
          <td>.txt (ข้อความสั้น ๆ)</td>
          <td><span style="color:#27ae60">✅ บีบได้ดี</span></td>
          <td>ไฟล์เล็กจำนวนมาก — เหมือน encrypt ใบสลิปหรือ voucher ทีละใบ</td></tr>
    </tbody>
  </table>
</div>

<!-- ══ ชนิดกุญแจ ══ -->
<div class="card">
  <h2><span class="sn">🔑</span>ชนิดกุญแจที่ทดสอบ — PGP ใช้กุญแจ 2 ชั้น</h2>

  <div class="info" style="margin-bottom:16px">
    <strong>PGP ทำงานยังไง?</strong><br>
    เหมือนการส่งของในกล่องล็อค 2 ชั้น:<br>
    <strong>ชั้นนอก (กุญแจ RSA/ECC)</strong> — ล็อคกุญแจ AES ไว้ เปิดได้เฉพาะผู้รับจริง<br>
    <strong>ชั้นใน (AES-256)</strong> — เข้ารหัสข้อมูลจริงอย่างรวดเร็วด้วย hardware
  </div>

  <div class="grid3">
    <div class="mbox">
      <h4>🔵 RSA-2048 — มาตรฐานทั่วไป</h4>
      <p style="margin-bottom:8px">
        <strong>ใช้อยู่ในปัจจุบัน</strong> — ระบบส่วนใหญ่ใช้อันนี้
      </p>
      <ul>
        <li>ขนาดกุญแจ 2,048 bit (256 ไบต์)</li>
        <li>NIST รับรองถึงปี 2030</li>
        <li>เร็วพอสำหรับงานทั่วไป</li>
        <li><strong>แนะนำสำหรับระบบปัจจุบัน</strong></li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>🟠 RSA-4096 — ความปลอดภัยสูง</h4>
      <p style="margin-bottom:8px">
        <strong>ใช้เมื่อข้อมูลต้องปลอดภัยนานหลายปี</strong>
      </p>
      <ul>
        <li>ขนาดกุญแจใหญ่กว่า 2 เท่า (512 ไบต์)</li>
        <li>ปลอดภัยกว่า RSA-2048 มาก</li>
        <li>ช้ากว่า RSA-2048 ประมาณ 3–4 เท่า</li>
        <li><strong>แนะนำสำหรับข้อมูลลับสำคัญมาก</strong></li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>🟣 Curve25519 ECC — ยุคใหม่</h4>
      <p style="margin-bottom:8px">
        <strong>เร็วที่สุด ปลอดภัยที่สุดในบรรดาสามชนิด</strong>
      </p>
      <ul>
        <li>กุญแจเล็กกว่า RSA มาก (32 ไบต์เท่านั้น)</li>
        <li>ปลอดภัยเทียบเท่า RSA-3072</li>
        <li>เร็วกว่า RSA อย่างชัดเจน</li>
        <li><strong>แนะนำสำหรับระบบใหม่ทุกระบบ</strong></li>
      </ul>
    </div>
  </div>
</div>

<!-- ══ Implementation Variants ══ -->
<div class="card">
  <h2><span class="sn">⚙️</span>วิธีเขียนซอฟต์แวร์ที่ทดสอบ (Variants) คืออะไร?</h2>

  <div class="info" style="margin-bottom:16px">
    <strong>ทำไมต้องมีหลาย Variant?</strong><br>
    เหมือนการแข่งรถ — แต่ละทีมมีรถหลายคัน (สูตรต่างกัน) ก่อนเลือกคันที่เร็วที่สุดมาแข่งรอบสุดท้าย
    เราทดสอบแต่ละภาษาหลายแบบ แล้วเอาแบบที่เร็วที่สุดมาแข่งกัน — เพื่อให้แต่ละภาษาได้แสดงศักยภาพสูงสุด
  </div>

  <h3>🔵 Go มี 3 วิธี:</h3>
  <div class="grid3" style="margin-bottom:20px">
    <div class="mbox">
      <h4>1. go-inmem-single<br><small style="font-weight:400;color:#888">โหลดทั้งไฟล์ก่อน (1 งาน)</small></h4>
      <p>
        <strong>วิธี:</strong> โหลดไฟล์ทั้งหมดเข้า RAM ก่อน แล้วค่อยเข้ารหัสทีเดียว
        ทำงาน 1 ไฟล์ต่อครั้ง
      </p>
      <p style="margin-top:8px;color:#27ae60"><strong>✅ เหมาะกับ:</strong> ไฟล์เล็กที่ RAM พอ</p>
      <p style="color:#e74c3c"><strong>⚠️ ข้อจำกัด:</strong> ไฟล์ใหญ่กิน RAM มาก</p>
    </div>
    <div class="mbox">
      <h4>2. go-stream-single<br><small style="font-weight:400;color:#888">อ่านทีละนิด (1 งาน)</small></h4>
      <p>
        <strong>วิธี:</strong> อ่านและเข้ารหัสทีละชิ้นเล็ก ๆ (64KB ต่อครั้ง)
        ไม่ต้องโหลดทั้งไฟล์เข้า RAM
        RAM ที่ใช้คงที่ไม่โตตามขนาดไฟล์
      </p>
      <p style="margin-top:8px;color:#27ae60"><strong>✅ เหมาะกับ:</strong> ไฟล์ขนาดใดก็ได้ RAM ประหยัด</p>
    </div>
    <div class="mbox">
      <h4>3. go-stream-parallel<br><small style="font-weight:400;color:#888">อ่านทีละนิด (หลายงานพร้อมกัน)</small></h4>
      <p>
        <strong>วิธี:</strong> เหมือน go-stream-single แต่รัน 4 งานพร้อมกัน
        ใช้ CPU หลาย Core พร้อมกัน เพิ่ม throughput
      </p>
      <p style="margin-top:8px;color:#27ae60"><strong>✅ เหมาะกับ:</strong> หลายไฟล์พร้อมกัน ต้องการ throughput สูง</p>
    </div>
  </div>

  <h3>🟠 Java มี 4 วิธี:</h3>
  <div class="grid4" style="margin-bottom:16px">
    <div class="mbox orange">
      <h4>1. java-inmem-single<br><small style="font-weight:400;color:#888">โหลดทั้งไฟล์ก่อน (1 งาน)</small></h4>
      <p>เหมือน go-inmem-single ฝั่ง Java — โหลดทั้งไฟล์เข้า RAM แล้วเข้ารหัสทีเดียว</p>
      <p style="margin-top:6px;color:#27ae60"><strong>✅</strong> ไฟล์เล็ก</p>
      <p style="color:#e74c3c"><strong>⚠️</strong> กิน RAM ตามขนาดไฟล์</p>
    </div>
    <div class="mbox orange">
      <h4>2. java-stream-single<br><small style="font-weight:400;color:#888">อ่านทีละนิด (1 งาน)</small></h4>
      <p>เหมือน go-stream-single ฝั่ง Java — อ่านทีละ 64KB ประหยัด RAM</p>
      <p style="margin-top:6px;color:#27ae60"><strong>✅</strong> ไฟล์ขนาดใดก็ได้</p>
    </div>
    <div class="mbox orange">
      <h4>3. java-stream-parallel<br><small style="font-weight:400;color:#888">อ่านทีละนิด (หลายงาน)</small></h4>
      <p>อ่านทีละ 64KB + ทำงาน 4 งานพร้อมกัน ใช้ CPU หลาย Core</p>
      <p style="margin-top:6px;color:#27ae60"><strong>✅</strong> throughput สูงสุดของ Java</p>
    </div>
    <div class="mbox orange">
      <h4>4. java-native-stream-parallel<br><small style="font-weight:400;color:#888">compile เป็น native binary</small></h4>
      <p>Compile Java ล่วงหน้าเป็น binary เหมือน Go — ไม่ต้องรอ JVM เปิด เริ่มเร็วกว่าปกติมาก</p>
      <p style="margin-top:6px;color:#aaa"><strong>ℹ️</strong> ยังไม่ได้ทดสอบรอบนี้ (ต้องติดตั้ง GraalVM เพิ่ม)</p>
    </div>
  </div>

  <div class="hi">
    <strong>🏆 เกณฑ์คัดเลือก "ตัวแทน" ของแต่ละภาษา:</strong>
    เลือก variant ที่มีเวลาเข้า+ถอดรหัสรวม (round-trip) น้อยที่สุด
    ถ้าเท่ากัน เลือกตัวที่ใช้ RAM น้อยกว่า
    variant ที่ให้ผลผิดพลาด (ข้อมูลหลังถอดรหัสไม่ตรง) ถูกตัดออกก่อนเลย
  </div>
</div>

<!-- ══ Crypto Profile ══ -->
<div class="card">
  <h2><span class="sn">🔒</span>สูตรการเข้ารหัสที่ใช้ (Crypto Profile)</h2>
  <p style="margin-bottom:14px">
    ค่าคงที่เดียวกันทุก variant ทุกภาษา — เพื่อให้เปรียบเทียบได้อย่างยุติธรรม
    เหมือนการแข่งขันที่ทุกคนใช้สนามเดียวกัน กติกาเดียวกัน
  </p>

  <div class="grid2">
    <div class="mbox">
      <h4>🔐 AES-256 — การเข้ารหัสข้อมูลจริง</h4>
      <p>
        AES คือ "ตัวล็อค" ที่เข้ารหัสข้อมูลจริง ใช้กุญแจขนาด 256 bit
        เป็นมาตรฐานสากลที่รัฐบาลสหรัฐฯ และองค์กรทั่วโลกใช้<br><br>
        <strong>ทำไมถึงเร็ว?</strong> CPU สมัยใหม่มีวงจรพิเศษ (AES-NI) ที่ทำ AES ได้โดยตรง
        เหมือนคิดเลขด้วยเครื่องคิดเลขแทนการคิดในหัว — เร็วกว่ากันมาก
        VM ของเราเปิดฟีเจอร์นี้ไว้แล้ว
      </p>
    </div>
    <div class="mbox orange">
      <h4>🗜 ZLIB — การบีบอัดก่อนเข้ารหัส</h4>
      <p>
        ก่อนเข้ารหัส ระบบบีบไฟล์ให้เล็กลงก่อน ทำให้ AES ทำงานน้อยลง = เร็วขึ้น<br><br>
        <strong>ไฟล์บีบได้ (.txt, .csv):</strong> ขนาดลดลง 60–80% ก่อนเข้ารหัส ประหยัดทั้งเวลาและพื้นที่<br>
        <strong>ไฟล์บีบไม่ได้ (.pdf ที่มีรูป, .zip):</strong> ZLIB ลองบีบแล้วไม่ได้ผล
        ข้ามไปเลย ไม่ทำให้ช้าลงมาก
      </p>
    </div>
  </div>

  <table style="margin-top:16px">
    <thead><tr>
      <th>ชั้นที่</th><th>ทำอะไร</th><th>เทคนิคที่ใช้</th><th>ความสำคัญ</th>
    </tr></thead>
    <tbody>
      <tr>
        <td><strong>1. กุญแจสาธารณะ</strong></td>
        <td>ล็อคกุญแจ AES ให้เฉพาะผู้รับเปิดได้</td>
        <td>RSA-2048 / RSA-4096 / Curve25519</td>
        <td>ความปลอดภัย — เฉพาะผู้รับอ่านได้</td>
      </tr>
      <tr>
        <td><strong>2. บีบอัดข้อมูล</strong></td>
        <td>ย่อไฟล์ให้เล็กก่อนเข้ารหัส</td>
        <td>ZLIB</td>
        <td>ประหยัดเวลา + พื้นที่จัดเก็บ</td>
      </tr>
      <tr>
        <td><strong>3. เข้ารหัสข้อมูลจริง</strong></td>
        <td>ล็อคเนื้อหาไฟล์ด้วย AES</td>
        <td>AES-256 (เร็วด้วย CPU hardware)</td>
        <td>งานหลัก — เร็วที่สุดในทุกชั้น</td>
      </tr>
      <tr>
        <td><strong>4. ลายนิ้วมือ</strong></td>
        <td>ตรวจว่าข้อมูลไม่ถูกแก้ไขระหว่างทาง</td>
        <td>SHA-256</td>
        <td>ตรวจจับการปลอมแปลง</td>
      </tr>
    </tbody>
  </table>
</div>"""
