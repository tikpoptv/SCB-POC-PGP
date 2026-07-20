"""pages/method.py — Tab 4: วิธีการทดสอบ"""


def build() -> str:
    return """
<div class="card">
  <h2>🎯 วัตถุประสงค์</h2>
  <p>เปรียบเทียบประสิทธิภาพการเข้ารหัส PGP ระหว่าง Go และ Java
  ภายใต้เงื่อนไขที่ยุติธรรมและทำซ้ำได้ เพื่อช่วยตัดสินใจเลือกภาษาสำหรับระบบใหม่</p>
  <div class="info" style="margin-top:10px">
    <strong>ขอบเขต:</strong> วัดเฉพาะ PGP encrypt และ decrypt —
    ไม่รวม I/O, network, database, JVM startup
  </div>
</div>

<div class="card">
  <h2>⚙️ สภาพแวดล้อมการทดสอบ</h2>
  <div class="grid3">
    <div class="mbox">
      <h3>🖥 VM</h3>
      <ul>
        <li>Ubuntu 24.04 LTS</li>
        <li>8 vCPU</li>
        <li>14 GB RAM</li>
        <li>Corpus บน tmpfs (RAM disk)</li>
      </ul>
    </div>
    <div class="mbox go">
      <h3>🔵 Go Runner</h3>
      <ul>
        <li>Go 1.24.4</li>
        <li>ProtonMail/go-crypto</li>
        <li>3 variants: inmem-single, stream-single, stream-parallel</li>
      </ul>
    </div>
    <div class="mbox java">
      <h3>🟠 Java Runner</h3>
      <ul>
        <li>JDK 25 + Spring Boot 4.x</li>
        <li>Bouncy Castle (bcpg + bcprov)</li>
        <li>3 variants: inmem-single, stream-single, stream-parallel</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2>📐 วิธีวัด</h2>
  <div class="grid2">
    <div class="mbox green">
      <h3>✅ สิ่งที่วัด</h3>
      <ul>
        <li>เวลา encrypt() จริง (นาฬิกา monotonic)</li>
        <li>เวลา decrypt() จริง</li>
        <li>Round-trip = encrypt + decrypt รวมกัน</li>
      </ul>
    </div>
    <div class="mbox red">
      <h3>❌ สิ่งที่ไม่วัด</h3>
      <ul>
        <li>การโหลดกุญแจจาก disk</li>
        <li>JVM startup time</li>
        <li>Warmup iterations (รันก่อนวัดจริง)</li>
        <li>Disk I/O (corpus อยู่บน RAM disk)</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2>⚖️ มาตรการความยุติธรรม</h2>
  <div class="grid2">
    <div class="mbox">
      <h3>🔄 Alternating Order</h3>
      <p>สลับลำดับ Go/Java ทุกรอบ — round 1: Go→Java, round 2: Java→Go
      ป้องกัน CPU cache bias ที่ฝ่ายใดฝ่ายหนึ่งได้เปรียบ</p>
    </div>
    <div class="mbox">
      <h3>📦 แยก Process</h3>
      <p>Go และ Java รันแยก process สมบูรณ์ ไม่แย่งทรัพยากรกัน
      corpus บน tmpfs เหมือนกัน 100%</p>
    </div>
    <div class="mbox">
      <h3>✅ Verification Gate</h3>
      <p>ทุก operation ต้องผ่าน: decrypt(encrypt(x)) = x byte-for-byte
      operation ที่ผิดพลาดถูก skip ออกจากสถิติ</p>
    </div>
    <div class="mbox">
      <h3>📊 ชุดข้อมูลเดียวกัน</h3>
      <p>corpus plaintext เดียวกัน ทั้ง 6 ชนิดไฟล์ (txt/csv/pdf/xlsx/zip/dat)
      ขนาด 512KB ต่อไฟล์ × 15 ไฟล์ต่อ scenario</p>
    </div>
  </div>
</div>

<div class="card">
  <h2>📋 Coverage — สิ่งที่ทดสอบ</h2>
  <table>
    <thead><tr><th>หมวด</th><th>รายละเอียด</th><th>จำนวน</th></tr></thead>
    <tbody>
      <tr><td>File types</td><td>txt, csv, pdf, xlsx, zip, dat × 3 key algorithms</td><td>18 scenarios</td></tr>
      <tr><td>Many-small files</td><td>100–200 files × 1KB, 10KB, 100KB</td><td>3 scenarios</td></tr>
      <tr><td>Size gradient</td><td>ไฟล์เดียว ขนาด 1KB→10MB (binary + text) เพื่อดู size effect</td><td>22 จุด</td></tr>
      <tr><td>Count gradient</td><td>100KB binary × 1→1000 ไฟล์ เพื่อดู file-count effect</td><td>9 จุด</td></tr>
      <tr><td>Concurrent load</td><td>1, 2, 4, 8 clients พร้อมกัน</td><td>4 levels</td></tr>
      <tr style="background:#f8f9fa"><td><strong>รวม</strong></td><td>3 key algorithms (RSA-2048, RSA-4096, Curve25519) × 3 rounds · cold start</td><td><strong>21 scenarios + gradient</strong></td></tr>
    </tbody>
  </table>
</div>"""
