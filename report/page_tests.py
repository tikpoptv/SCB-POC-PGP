"""page_tests.py — Tab 5: Test Suite 721 Tests + PBT คืออะไร + Timeline"""


def build() -> str:
    return """
<div class="card">
  <h2><span class="sn">🧪</span>ภาพรวม Test Suite — 721 Tests</h2>
  <p style="margin-bottom:14px">
    ก่อนนำตัวเลขประสิทธิภาพมาเปรียบเทียบ ซอฟต์แวร์มี test suite (ชุดทดสอบ)
    ที่ครอบคลุม 3 ชั้น เพื่อยืนยันว่า <strong>ตัวเลขเหล่านั้นมาจากการ crypto ที่ถูกต้อง</strong>
    — ไม่ใช่แค่เร็ว แต่ถูกต้องด้วย
  </p>
  <div class="stats">
    <div class="sbox green-b"><div class="val">81</div><div class="lbl">Java Tests (mvn test)</div></div>
    <div class="sbox go-b"><div class="val">~100+</div><div class="lbl">Go Tests (go test)</div></div>
    <div class="sbox" style="border-color:#9b59b6"><div class="val" style="color:#9b59b6">640</div><div class="lbl">Python Harness Tests</div></div>
    <div class="sbox green-b"><div class="val">721</div><div class="lbl">รวมทั้งหมด</div></div>
    <div class="sbox green-b"><div class="val">0</div><div class="lbl">Failures (ล้มเหลว)</div></div>
    <div class="sbox green-b"><div class="val">100%</div><div class="lbl">Pass Rate (ผ่านทั้งหมด)</div></div>
  </div>
</div>

<div class="card">
  <h2><span class="sn">🔍</span>Timeline: ชุดทดสอบทำงานอย่างไรก่อนถึง Benchmark?</h2>
  <p style="margin-bottom:14px;color:#666">
    ทุกครั้งที่นักพัฒนา push ซอฟต์แวร์ใหม่ หรือก่อน benchmark run ทุกครั้ง
    ระบบรัน test suite ตามลำดับนี้ก่อนเสมอ:
  </p>
  <ul class="timeline">
    <li data-n="1">
      <div class="tl-title">Java Tests (mvn test) — 81 tests</div>
      ทดสอบ Java engine โดยตรง: ทุก variant × ทุก key type × ทุก edge case
      รัน Property-Based Tests ด้วย jqwik (200 iterations ต่อ property)
      ใช้เวลาประมาณ 2–3 นาที
    </li>
    <li data-n="2">
      <div class="tl-title">Go Tests (go test) — ~100+ tests</div>
      ทดสอบ Go engine: round-trip, streaming memory, timing breakdown, classification
      รัน Property-Based Tests ด้วย pgregory.net/rapid (100 iterations ต่อ property)
      ใช้เวลาประมาณ 30 วินาที
    </li>
    <li data-n="3">
      <div class="tl-title">Python Harness Tests — 640 tests</div>
      ทดสอบตัวกลางที่ orchestrate ทั้งระบบ: config validation, statistics, fairness,
      interoperability, corpus generation, resource sampling
      ใช้เวลาประมาณ 1–2 นาที
    </li>
    <li data-n="4">
      <div class="tl-title">Integration Gate (ด่านรวม) — ผ่านทั้งหมดก่อนดำเนินการต่อ</div>
      ถ้า test ใดล้มเหลว → หยุดทันที ไม่อนุญาตให้รัน benchmark
      ต้องแก้ไขปัญหาก่อน → รัน test ใหม่ทั้งหมด → ผ่านทุก test → รัน benchmark ได้
    </li>
    <li data-n="5">
      <div class="tl-title">Benchmark Run — เก็บผลจริง</div>
      ทดสอบประสิทธิภาพ alternating execution (สลับลำดับ), warm-up ก่อนเก็บผล,
      verification gate ทุก operation, statistics engine คำนวณผล
    </li>
    <li data-n="6">
      <div class="tl-title">Report Generation — สร้างรายงานนี้</div>
      สร้าง results.json + HTML report ที่คุณกำลังอ่านอยู่
    </li>
  </ul>
</div>

<div class="card">
  <h2><span class="sn">📋</span>Property-Based Testing (PBT) คืออะไร? — อธิบายให้ไม่รู้ซอฟต์แวร์เข้าใจ</h2>
  <div class="grid2">
    <div class="mbox">
      <h4>🔵 Unit Test ทั่วไป — แบบที่คุ้นเคย</h4>
      <p style="margin-bottom:10px">
        เหมือนการทดสอบสูตรอาหารด้วยตัวอย่างที่เลือกเอง:<br>
        "เอา แป้ง 100g + ไข่ 1 ฟอง → ควรได้เค้ก 1 ชิ้น"<br>
        ครอบคลุมเฉพาะ case ที่นักพัฒนานึกออก
        ถ้าลืม edge case บางอย่าง (เช่น แป้ง 0g?) — test จะไม่ตรวจ
      </p>
      <p><strong>ข้อจำกัด:</strong> ถ้าไม่นึกถึง input แปลก ๆ test จะไม่เห็น bug</p>
    </div>
    <div class="mbox green">
      <h4>🟢 Property-Based Test — แบบที่ใช้ใน POC นี้</h4>
      <p style="margin-bottom:10px">
        เหมือนการกำหนด "กฎธรรมชาติ" แล้วให้ระบบสุ่มทดสอบเอง:<br>
        "ถ้าเข้ารหัสข้อมูลอะไรก็ตาม แล้วถอดรหัส ต้องได้ข้อมูลเดิมเสมอ"<br>
        Framework สุ่ม input 200 แบบอัตโนมัติ — รวมถึงข้อมูลว่าง, binary แปลก ๆ,
        ขนาดสุดโต่ง — ที่นักพัฒนาอาจไม่นึกถึง
      </p>
      <p><strong>ข้อดี:</strong> ค้นหา bug ที่ซ่อนอยู่ใน edge case ที่ไม่มีใครคาดคิด</p>
    </div>
  </div>
  <div class="hi" style="margin-top:16px">
    <strong>ตัวอย่างกฎ (Properties) ที่ทดสอบ:</strong><br>
    ① ถอดรหัส(เข้ารหัส(X)) = X เสมอ — ไม่ว่า X จะเป็นอะไร (ข้อมูลว่าง, 50 KB, binary, ฯลฯ)<br>
    ② หน่วยความจำสูงสุดระหว่าง streaming ต้องไม่โตตามขนาดไฟล์ (คงที่ที่ &lt;12 MB)<br>
    ③ เวลาเข้ารหัส + เวลาถอดรหัส ≤ เวลารวมที่รายงาน เสมอ<br>
    Framework ที่ใช้: <strong>jqwik</strong> (Java), <strong>pgregory.net/rapid</strong> (Go),
    <strong>hypothesis</strong> (Python) — รัน ≥100 iterations ต่อ property
  </div>
</div>

<div class="card">
  <h2><span class="sn">🔵</span>Go Tests — รายละเอียด</h2>
  <div class="grid2">
    <div class="mbox green">
      <h4>Property 1: Round-trip byte-for-byte</h4>
      <p>กฎ: ถอดรหัส(เข้ารหัส(X)) = X ทุก byte สำหรับ payload ทุกรูปแบบ:</p>
      <ul>
        <li>Empty file (0 bytes — ไฟล์ว่าง)</li>
        <li>Lone CR (\r) — ต้องไม่ถูก normalize เป็น CRLF</li>
        <li>ทุก 256 byte values (0x00–0xFF)</li>
        <li>Compressible text (.txt, .csv — ข้อความบีบอัดได้)</li>
        <li>Incompressible binary (.pdf-like — binary บีบไม่ได้)</li>
        <li>Medium payloads 64 KB–512 KB</li>
      </ul>
    </div>
    <div class="mbox green">
      <h4>Property 3: File classification rules</h4>
      <p>กฎ: การจำแนกชนิดไฟล์และตั้งชื่อผลลัพธ์ต้องสม่ำเสมอ:</p>
      <ul>
        <li>.txt/.xlsx/.csv/.pdf/.zip → ชื่อ + ".pgp"</li>
        <li>.zip-of-many → ชื่อ + ".zip.pgp"</li>
        <li>.ctrl/.ctl → skipped=true (ข้าม) ไม่ encrypt</li>
        <li>นามสกุลไม่รองรับ → skip + reason "unsupported"</li>
        <li>Case insensitive (.TXT = .txt เหมือนกัน)</li>
      </ul>
    </div>
    <div class="mbox green">
      <h4>Property 14: Streaming peak memory O(1)</h4>
      <p>กฎ: สำหรับ streaming variant หน่วยความจำสูงสุดต้องคงที่ ไม่โตตามไฟล์:</p>
      <ul>
        <li>ทดสอบไฟล์ขนาด 1 MB–16 MB แบบสุ่ม</li>
        <li>วัด retained heap (หน่วยความจำที่ยังใช้งาน) ระหว่าง stream</li>
        <li>Peak memory &lt;12 MB เสมอ ไม่ว่าไฟล์จะใหญ่แค่ไหน</li>
        <li>มี guard test ยืนยันว่า in-memory จะเกิน 12 MB (เพื่อพิสูจน์ว่า test ไม่ผ่านง่าย ๆ)</li>
      </ul>
    </div>
    <div class="mbox green">
      <h4>Property 23: asym/sym breakdown invariant</h4>
      <p>กฎ: เมื่อรายงาน breakdown เวลา ตัวเลขต้องสอดคล้องกัน:</p>
      <ul>
        <li>asymNanos (เวลา key exchange) + symNanos (เวลา AES) ≤ totalNanos</li>
        <li>ทั้งสองค่าต้องไม่ติดลบ</li>
        <li>totalNanos &gt; 0 เสมอสำหรับ operation จริง</li>
        <li>NOT_SEPARABLE (-1) ถ้าวัดแยกไม่ได้ = valid</li>
      </ul>
    </div>
  </div>
  <h3 style="margin-top:16px">Unit Tests เพิ่มเติม</h3>
  <ul>
    <li><strong>Checksum tests</strong>: SHA-256 deterministic (ผลเหมือนเดิมทุกครั้ง), mismatch detection, round-trip verify</li>
    <li><strong>Contract tests</strong>: Command JSON parse, RunnerOutput JSON serialize, exit codes</li>
    <li><strong>Runner shell tests</strong>: checksum gate, variant lookup, warm-up exclusion</li>
    <li><strong>Classifier tests</strong>: extension matching case-insensitive, skip logic</li>
  </ul>
</div>

<div class="card">
  <h2><span class="sn">🟠</span>Java Tests — รายละเอียด (81 tests)</h2>
  <div class="grid2">
    <div class="mbox orange">
      <h4>RoundTripPropertyTest (jqwik)</h4>
      <p>ครอบคลุม <strong>ทุก 4 variants</strong> × <strong>ทุก 3 key types</strong>:</p>
      <ul>
        <li>java-inmem-single + java-stream-single</li>
        <li>java-stream-parallel + java-native-stream-parallel</li>
        <li>RSA-2048, RSA-4096, Curve25519</li>
        <li>200 tries × small payloads (เล็ก), 100 tries × medium (กลาง)</li>
        <li>No-compression profile (AES-256 เท่านั้น ไม่บีบ)</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>InMemSingleEngineTest + StreamSingleEngineTest</h4>
      <p>Unit tests ครอบคลุมทุก edge case:</p>
      <ul>
        <li>RSA-2048, RSA-4096, Curve25519 round-trip</li>
        <li>Empty payload (0 bytes)</li>
        <li>Lone carriage return (\r) — binary fidelity (ความแม่นยำ binary)</li>
        <li>All 256 byte values</li>
        <li>Large input 3–5 MB</li>
        <li>Unsupported cipher rejection (ปฏิเสธ cipher ที่ไม่รองรับ)</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>Cross-Variant Interoperability</h4>
      <p>ข้อมูลเข้ารหัสจาก variant หนึ่ง ต้อง variant อื่น decrypt ได้:</p>
      <ul>
        <li>inmem-single → stream-parallel decrypt ได้</li>
        <li>stream-parallel → inmem-single decrypt ได้</li>
        <li>stream-single ↔ inmem-single interop</li>
        <li>ยืนยัน OpenPGP format ถูกต้องมาตรฐาน</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>StreamMemoryPropertyTest</h4>
      <p>Java streaming peak memory (หน่วยความจำสูงสุด):</p>
      <ul>
        <li>Input สร้าง lazy (ทีละส่วน) — ไม่ materialise ทั้งก้อน</li>
        <li>1 MiB – 16 MiB (random size, 100 tries)</li>
        <li>Retained heap &lt;12 MB ตลอด</li>
        <li>Guard test: in-memory &gt;12 MB ที่ 16 MB input (พิสูจน์ว่า test ไม่ pass ฟรี)</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>EngineRegistryVariantTest</h4>
      <ul>
        <li>ระบบ auto-discover ทุก 3 JVM variants ได้ถูกต้อง</li>
        <li>java-native ไม่ถูกโหลดโดยอัตโนมัติ (ต้องเรียกเฉพาะ)</li>
        <li>ลงทะเบียน variant โดยตรงทำงานได้</li>
        <li>ชื่อ variant ถูกต้องตามสัญญา</li>
      </ul>
    </div>
    <div class="mbox orange">
      <h4>TimingBreakdownPropertyTest</h4>
      <ul>
        <li>Plausible timings: asym+sym ≤ total เสมอ</li>
        <li>Inconsistent breakdown reject ได้</li>
        <li>honest() scrubs contradictory breakdown (ล้างค่าที่ขัดแย้ง)</li>
        <li>Real engine output consistent (ผลจริงสม่ำเสมอ)</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2><span class="sn">🐍</span>Python Harness Tests — รายละเอียด (640 tests)</h2>
  <div class="grid4">
    <div class="mbox purple">
      <h4>Pipeline Integration Tests</h4>
      <ul>
        <li>SubprocessDriver → VerificationGate (ตัวกลาง → ด่านตรวจ)</li>
        <li>Checksum mismatch detection (ตรวจจับลายนิ้วมือผิด)</li>
        <li>Round-trip failure exclusion (ยกเว้น operation ที่ผิด)</li>
        <li>Multi-runner verification summary</li>
        <li>Atomic results.json write (เขียนครบหรือไม่มีเลย)</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>Interoperability Tests</h4>
      <ul>
        <li>Go↔Java cross-language decrypt (ถอดรหัสข้ามภาษา)</li>
        <li>Tampered output detection (ตรวจจับข้อมูลที่ถูกแก้ไข)</li>
        <li>Pending endpoint handling</li>
        <li>InteropSummary to_dict shape</li>
        <li>Property: interop symmetric (ถอดรหัสได้สองทาง)</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>Statistics Engine Tests</h4>
      <ul>
        <li>Throughput formula: bytes/MB/time</li>
        <li>Round-trip = encrypt + decrypt</li>
        <li>Error rate calculation</li>
        <li>Warm-up exclusion (ยกเว้นรอบอุ่นเครื่อง)</li>
        <li>Inconclusive 5% threshold (เสมอถ้าต่างน้อยกว่า 5%)</li>
        <li>Best_Variant selection + tie-break</li>
        <li>Cost per million operations</li>
        <li>Noise floor CV + mean diff</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>Config Validation Tests</h4>
      <ul>
        <li>rounds (จำนวนรอบ) ∈ [1, 1,000]</li>
        <li>warmup (รอบอุ่นเครื่อง) ∈ [0, 100]</li>
        <li>concurrency ≤ vCPU</li>
        <li>customSizeBytes &gt; 0</li>
        <li>outputEncoding ∈ {binary, armored}</li>
        <li>หยุดก่อน Result_Report ถ้า config ผิด</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>Corpus &amp; Key Tests</h4>
      <ul>
        <li>Deterministic generation (seed เดิม → corpus เดิม)</li>
        <li>Checksum round-trip verify</li>
        <li>Mismatch detection (1 byte changed)</li>
        <li>Key manifest validation (ตรวจสอบ manifest กุญแจ)</li>
        <li>Size tier coverage</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>Fairness Tests</h4>
      <ul>
        <li>All runners use same Key_Set (ชุดกุญแจเดียวกัน)</li>
        <li>CPU/memory quota equal (เท่ากัน)</li>
        <li>Non-comparable propagation</li>
        <li>Sampling interval consistent</li>
        <li>Order alternation property (สลับลำดับถูกต้อง)</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>Resource Sampler Tests</h4>
      <ul>
        <li>CPU sampling ทุก interval</li>
        <li>RAM peak/avg calculation (คำนวณสูงสุด/เฉลี่ย)</li>
        <li>GC stats merge</li>
        <li>Non-comparable on failure</li>
      </ul>
    </div>
    <div class="mbox purple">
      <h4>Soak &amp; Trend Tests</h4>
      <ul>
        <li>RAM slope calculation (ตรวจ memory leak)</li>
        <li>Latency degradation detection (ตรวจการช้าลงเรื่อย ๆ)</li>
        <li>Threshold comparison</li>
        <li>Not-applicable when n &lt; 2</li>
      </ul>
    </div>
  </div>
</div>"""
