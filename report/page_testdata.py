"""page_testdata.py — Tab 4: ข้อมูลทดสอบและ Variants"""


def build() -> str:
    return """
<div class="card">
  <h2><span class="sn">📁</span>ชุดข้อมูลทดสอบ (Test Corpus)</h2>
  <p style="margin-bottom:14px">
    ชุดไฟล์ทดสอบสร้างแบบ deterministic (ผลเหมือนกันทุกครั้งจาก seed เดิม — reproducible)
    วางบน <strong>tmpfs (RAM disk — disk เสมือนในหน่วยความจำ)</strong>
    เพื่อตัด disk I/O ออกจากการวัดทั้งหมด
  </p>
  <table>
    <thead><tr>
      <th>Scenario ID</th><th>จำนวนไฟล์</th><th>ขนาดต่อไฟล์</th>
      <th>ชนิดข้อมูล</th><th>Compressibility (บีบอัดได้)</th><th>วัตถุประสงค์</th>
    </tr></thead>
    <tbody>
      <tr><td><strong>small-comp</strong></td><td>20 ไฟล์</td><td>50 KB</td>
          <td>.txt / .csv (ข้อความซ้ำ)</td><td>สูง (bzip2 &gt;80%)</td>
          <td>ไฟล์เล็กบีบอัดได้ วัด per-file overhead + ZLIB benefit</td></tr>
      <tr><td><strong>small-incomp</strong></td><td>20 ไฟล์</td><td>50 KB</td>
          <td>Random binary (pseudo-PDF)</td><td>ต่ำ (&lt;5%)</td>
          <td>ไฟล์เล็กบีบไม่ได้ วัดผล AES-only ไม่มี ZLIB benefit</td></tr>
      <tr><td><strong>medium-comp</strong></td><td>4 ไฟล์</td><td>5 MB</td>
          <td>.csv (ตัวเลขซ้ำ)</td><td>สูงมาก</td>
          <td>ไฟล์กลาง workload งาน batch processing ทั่วไป</td></tr>
      <tr><td><strong>medium-incomp</strong></td><td>4 ไฟล์</td><td>5 MB</td>
          <td>Random binary</td><td>ต่ำมาก</td>
          <td>ไฟล์กลาง binary เช่น PDF ที่มี embedded images</td></tr>
      <tr><td><strong>manysmall</strong></td><td>100 ไฟล์</td><td>10 KB</td>
          <td>.txt (ข้อความ)</td><td>สูง</td>
          <td>วัด overhead ต่อไฟล์ — สำคัญสำหรับ batch encrypt หลายไฟล์พร้อมกัน</td></tr>
    </tbody>
  </table>

  <h3 style="margin-top:16px">🔑 ชนิดกุญแจที่ทดสอบ</h3>
  <div class="grid3">
    <div class="mbox">
      <h4>RSA-2048</h4>
      <ul>
        <li>มาตรฐานที่ใช้งานทั่วไปปัจจุบัน</li>
        <li>กุญแจ 2,048 bit = 256 bytes</li>
        <li>NIST แนะนำถึงปี 2030</li>
        <li>Balance ระหว่างความเร็วและความปลอดภัย</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>RSA-4096</h4>
      <ul>
        <li>ความปลอดภัยสูงกว่าสำหรับข้อมูลสำคัญ</li>
        <li>กุญแจ 4,096 bit = 512 bytes</li>
        <li>งาน asymmetric ช้ากว่า 3–4× เมื่อเทียบ RSA-2048</li>
        <li>แนะนำสำหรับ long-term data protection (ข้อมูลที่ต้องปลอดภัยหลายปี)</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>Curve25519 ECC</h4>
      <ul>
        <li>Elliptic Curve algorithm (algorithm กราฟโค้ง) ยุคใหม่</li>
        <li>กุญแจเล็กกว่า RSA มาก (32 bytes)</li>
        <li>ปลอดภัยระดับ RSA-3072 ที่ความเร็วสูงกว่ามาก</li>
        <li>แนะนำสำหรับระบบใหม่ที่ออกแบบจากศูนย์</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2><span class="sn">⚙️</span>Implementation Variants คืออะไร?</h2>
  <p style="margin-bottom:14px">
    แต่ละภาษามีหลายรูปแบบการเขียนซอฟต์แวร์ (variants) เพื่อหา "ตัวเก่งที่สุด"
    ของภาษานั้นก่อน แล้วจึงนำมาแข่ง head-to-head กัน — เพื่อความยุติธรรม
  </p>
  <div class="grid2">
    <div>
      <h3>Go Variants (3 รูปแบบ)</h3>
      <table>
        <thead><tr><th>Variant ID</th><th>วิธีจัดการหน่วยความจำ</th><th>Threading</th></tr></thead>
        <tbody>
          <tr><td><strong>go-inmem-single</strong></td>
              <td>โหลดทั้งไฟล์เข้า RAM ก่อน encrypt</td>
              <td>1 goroutine (1 งาน)</td></tr>
          <tr><td><strong>go-stream-single</strong></td>
              <td>io.Pipe + buffered — peak memory (หน่วยความจำสูงสุด) คงที่</td>
              <td>1 goroutine</td></tr>
          <tr><td><strong>go-stream-parallel</strong></td>
              <td>Streaming + worker pool (กลุ่มงานรัน parallel)</td>
              <td>N goroutines (= concurrency)</td></tr>
        </tbody>
      </table>
    </div>
    <div>
      <h3>Java Variants (4 รูปแบบ)</h3>
      <table>
        <thead><tr><th>Variant ID</th><th>วิธีจัดการหน่วยความจำ</th><th>Threading</th></tr></thead>
        <tbody>
          <tr><td><strong>java-inmem-single</strong></td>
              <td>readAllBytes() โหลดทั้งไฟล์ก่อน encrypt</td>
              <td>1 thread (1 งาน)</td></tr>
          <tr><td><strong>java-stream-single</strong></td>
              <td>Streaming 64 KB buffer</td>
              <td>1 thread</td></tr>
          <tr><td><strong>java-stream-parallel</strong></td>
              <td>Streaming + ExecutorService (parallel pool)</td>
              <td>N threads</td></tr>
          <tr><td><strong>java-native-stream-parallel</strong></td>
              <td>GraalVM Native Image (AOT — compile ไว้ล่วงหน้า)</td>
              <td>N threads</td></tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="info" style="margin-top:12px">
    <strong>Best Variant Selection (เกณฑ์คัดเลือก):</strong>
    เกณฑ์หลักคือ p50 round-trip (ค่ากลางของเวลาเข้า+ถอดรหัส) ต่ำที่สุด
    tie-break (ตัดสิน) ด้วย p99 ต่ำสุด แล้ว peak RAM (หน่วยความจำสูงสุด) ต่ำสุด
    — variant ที่ไม่ผ่าน correctness gate (ด่านความถูกต้อง) ถูกตัดออก
  </div>
</div>

<div class="card">
  <h2><span class="sn">🔒</span>Crypto Profile ที่ใช้</h2>
  <p style="margin-bottom:12px">
    ค่า algorithm (ชุดคำสั่งเข้ารหัส) คงที่ทุก runner ทุก variant ทุก scenario
    เพื่อความยุติธรรมในการเปรียบเทียบ:
  </p>
  <div class="grid2" style="margin-top:12px">
    <div class="mbox">
      <h4>AES-256 — ทำไมถึงเร็ว?</h4>
      <p>CPU สมัยใหม่มี <strong>AES-NI</strong>
         (Hardware Acceleration — การเร่งความเร็วด้วย hardware)
         ซึ่งเป็นคำสั่ง CPU ระดับ hardware ที่ทำ AES โดยตรง
         ไม่ต้องผ่าน software loop ช้า ๆ
         VM ของเราเปิด cpu=host ทำให้ flag aes ส่งผ่านเข้า VM</p>
    </div>
    <div class="mbox orange">
      <h4>ZLIB Compression — ผลต่าง?</h4>
      <p>ไฟล์ที่บีบอัดได้ (เช่น .txt, .csv) จะถูก ZLIB บีบก่อน encrypt
         ทำให้ ciphertext (ข้อมูลที่เข้ารหัสแล้ว) เล็กลง และ AES ทำงานน้อยลง
         ไฟล์ที่บีบไม่ได้ (random binary เช่น PDF ที่มีรูปภาพ)
         ZLIB แทบไม่ช่วย แต่ก็ไม่ทำให้แย่ลงมาก</p>
    </div>
  </div>
  <table style="margin-top:16px">
    <thead><tr>
      <th>Component</th><th>Algorithm ที่ใช้</th><th>หน้าที่</th><th>หมายเหตุ</th>
    </tr></thead>
    <tbody>
      <tr><td>Public Key (กุญแจสาธารณะ)</td>
          <td>RSA-2048 / RSA-4096 / Curve25519</td>
          <td>แลกเปลี่ยนกุญแจ symmetric อย่างปลอดภัย</td>
          <td>ทดสอบแยกทั้ง 3 แบบ</td></tr>
      <tr><td>Symmetric Cipher (การเข้ารหัสจริง)</td>
          <td>AES-256</td>
          <td>เข้ารหัส payload จริง — เร็วด้วย hardware</td>
          <td>AES-NI accelerated</td></tr>
      <tr><td>Compression (การบีบอัด)</td>
          <td>ZLIB</td>
          <td>บีบข้อมูลก่อน encrypt ลด ciphertext size</td>
          <td>ช่วยไฟล์ที่มีข้อความซ้ำ</td></tr>
      <tr><td>Hash (ลายนิ้วมือ)</td>
          <td>SHA-256</td>
          <td>ตรวจความสมบูรณ์ของข้อมูล</td>
          <td>detect tampering (การแก้ไข)</td></tr>
      <tr><td>Output Encoding</td>
          <td>Binary</td>
          <td>ขนาดไฟล์เล็กที่สุด ไม่มี overhead ของ ASCII</td>
          <td>ไม่ใช่ ASCII-armored</td></tr>
    </tbody>
  </table>
</div>"""
