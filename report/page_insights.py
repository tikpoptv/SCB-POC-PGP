"""page_insights.py — Tab: Key Insights — กราฟสรุปปัจจัยสำคัญ"""


def _bar_pair(label, go_val, java_val, max_val, unit="ms"):
    go_pct   = min(go_val   / max_val * 100, 100) if max_val > 0 else 0
    java_pct = min(java_val / max_val * 100, 100) if max_val > 0 else 0
    go_lbl   = f"{go_val:.2f} {unit}" if unit == "ms" else f"{go_val:.1f} {unit}"
    java_lbl = f"{java_val:.2f} {unit}" if unit == "ms" else f"{java_val:.1f} {unit}"
    ratio    = java_val / go_val if go_val > 0 else 1
    return f"""
<div style="margin-bottom:16px">
  <div style="font-size:13px;font-weight:700;color:#2c3e50;margin-bottom:5px">{label}</div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
    <span style="width:42px;font-size:11px;color:#00ADE8;font-weight:700">Go</span>
    <div style="flex:1;background:#e8f4fd;border-radius:4px;height:26px">
      <div style="width:{go_pct:.1f}%;background:#00ADE8;height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px">
        <span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{go_lbl}</span>
      </div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:8px">
    <span style="width:42px;font-size:11px;color:#F89820;font-weight:700">Java</span>
    <div style="flex:1;background:#fef3e2;border-radius:4px;height:26px">
      <div style="width:{java_pct:.1f}%;background:#F89820;height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px">
        <span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{java_lbl}</span>
      </div>
    </div>
  </div>
  <div style="text-align:right;font-size:11px;color:#00ADE8;font-weight:700;margin-top:2px">
    Go เร็วกว่า {ratio:.2f}×</div>
</div>"""


def build() -> str:
    # ── ข้อมูลจาก results_extended.json (best variant) ──────────────────

    # ขนาดไฟล์ (per-file p50 ms)
    size_data = [
        ("~1 KB (many-1kb)",            0.763, 1.017),
        ("~10 KB (many-10kb)",           0.794, 1.162),
        ("~100 KB (many-100kb)",         1.201, 1.587),
        ("~512 KB (ft-txt-rsa2048)",     2.508, 3.436),
        ("1KB–20MB mix (sizegrad)",     16.415, 18.785),
    ]
    max_size = max(j for _, _, j in size_data) * 1.15

    # จำนวนไฟล์ extrapolated (total seconds = per-file × n_files / 1000)
    n_files  = 10_000
    count_scenarios = [
        ("~1 KB",   0.763, 1.017),
        ("~10 KB",  0.794, 1.162),
        ("~100 KB", 1.201, 1.587),
        ("~512 KB", 2.508, 3.436),
    ]
    count_data = [(lbl, g * n_files / 1000, j * n_files / 1000)
                  for lbl, g, j in count_scenarios]
    max_count = max(j for _, _, j in count_data) * 1.15

    # key algorithm (p50 ms, .txt ~512KB)
    key_data = [
        ("Curve25519 (ยุคใหม่)", 1.762, 3.154),
        ("RSA-2048 (มาตรฐาน)", 2.508, 3.436),
        ("RSA-4096 (high-sec)", 6.334, 7.940),
    ]
    max_key = max(j for _, _, j in key_data) * 1.15

    # file type (RSA-2048)
    type_data = [
        (".txt (บีบอัด ~80%)",   2.508, 3.436),
        (".csv (บีบอัด ~80%)",   2.413, 3.428),
        (".pdf (binary ~5%)",    11.454, 14.275),
        (".xlsx (binary)",       11.667, 14.472),
        (".zip (บีบแล้ว ~0%)",  11.302, 14.481),
        (".dat (random ~0%)",    11.358, 14.483),
    ]
    max_type = max(j for _, _, j in type_data) * 1.15

    # concurrent throughput MB/s
    conc_data = [
        ("1 client พร้อมกัน",  263, 207),
        ("2 clients พร้อมกัน", 218, 155),
        ("4 clients พร้อมกัน", 190, 120),
        ("8 clients พร้อมกัน", 163,  90),
    ]
    max_conc = max(g for _, g, _ in conc_data) * 1.15

    # ── Build charts ─────────────────────────────────────────────────────

    size_chart = "".join(_bar_pair(lbl, g, j, max_size) for lbl, g, j in size_data)

    key_chart  = "".join(_bar_pair(lbl, g, j, max_key)  for lbl, g, j in key_data)

    type_chart = "".join(_bar_pair(lbl, g, j, max_type) for lbl, g, j in type_data)

    # count chart (วินาที)
    count_chart = ""
    for lbl, g_s, j_s in count_data:
        go_pct   = min(g_s / max_count * 100, 100)
        java_pct = min(j_s / max_count * 100, 100)
        diff     = j_s - g_s
        count_chart += f"""
<div style="margin-bottom:16px">
  <div style="font-size:13px;font-weight:700;color:#2c3e50;margin-bottom:5px">
    {lbl} × {n_files:,} ไฟล์</div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
    <span style="width:42px;font-size:11px;color:#00ADE8;font-weight:700">Go</span>
    <div style="flex:1;background:#e8f4fd;border-radius:4px;height:26px">
      <div style="width:{go_pct:.1f}%;background:#00ADE8;height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px">
        <span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{g_s:.1f} วินาที</span>
      </div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:8px">
    <span style="width:42px;font-size:11px;color:#F89820;font-weight:700">Java</span>
    <div style="flex:1;background:#fef3e2;border-radius:4px;height:26px">
      <div style="width:{java_pct:.1f}%;background:#F89820;height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px">
        <span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{j_s:.1f} วินาที</span>
      </div>
    </div>
  </div>
  <div style="text-align:right;font-size:11px;color:#e74c3c;font-weight:700;margin-top:2px">
    Java ใช้เวลาเพิ่ม +{diff:.1f} วินาที ต่อ {n_files:,} ไฟล์</div>
</div>"""

    # concurrent chart
    conc_chart = ""
    for lbl, g, j in conc_data:
        g_pct = min(g / max_conc * 100, 100)
        j_pct = min(j / max_conc * 100, 100)
        ratio = g / j
        conc_chart += f"""
<div style="margin-bottom:16px">
  <div style="font-size:13px;font-weight:700;color:#2c3e50;margin-bottom:5px">{lbl}</div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
    <span style="width:42px;font-size:11px;color:#00ADE8;font-weight:700">Go</span>
    <div style="flex:1;background:#e8f4fd;border-radius:4px;height:26px">
      <div style="width:{g_pct:.1f}%;background:#00ADE8;height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px">
        <span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{g:.0f} MB/s</span>
      </div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:8px">
    <span style="width:42px;font-size:11px;color:#F89820;font-weight:700">Java</span>
    <div style="flex:1;background:#fef3e2;border-radius:4px;height:26px">
      <div style="width:{j_pct:.1f}%;background:#F89820;height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px">
        <span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{j:.0f} MB/s</span>
      </div>
    </div>
  </div>
  <div style="text-align:right;font-size:11px;color:#00ADE8;font-weight:700;margin-top:2px">
    Go throughput สูงกว่า {ratio:.1f}×</div>
</div>"""

    # warm vs cold
    warm_data = [
        ("Go (cold process)",        1.59, "#00ADE8"),
        ("Java cold (warmup=0)",     3.36, "#e74c3c"),
        ("Java warm (warmup=20)",    1.67, "#F89820"),
    ]
    max_warm = max(v for _, v, _ in warm_data) * 1.15
    warm_chart = ""
    for lbl, v, color in warm_data:
        pct = min(v / max_warm * 100, 100)
        warm_chart += f"""
<div style="margin-bottom:12px">
  <div style="font-size:12px;font-weight:700;color:#2c3e50;margin-bottom:4px">{lbl}</div>
  <div style="flex:1;background:#f0f2f5;border-radius:4px;height:26px">
    <div style="width:{pct:.1f}%;background:{color};height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px">
      <span style="font-size:12px;color:white;font-weight:700">{v:.2f} ms</span>
    </div>
  </div>
</div>"""

    # ── key type advantage bar (speedup ratio, not ms) ────────────────────
    ratio_bars = ""
    for lbl, g, j in key_data:
        r = j / g
        pct = min((r - 1.0) / 1.0 * 100, 100)  # 1× = 0%, 2× = 100%
        ratio_bars += f"""
<div style="margin-bottom:10px">
  <div style="display:flex;align-items:center;gap:12px">
    <span style="width:140px;font-size:12px;font-weight:700">{lbl}</span>
    <div style="flex:1;background:#e8f4fd;border-radius:4px;height:24px">
      <div style="width:{pct:.0f}%;background:linear-gradient(90deg,#00ADE8,#0078a8);height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px">
        <span style="font-size:11px;color:white;font-weight:700">Go เร็วกว่า {r:.2f}×</span>
      </div>
    </div>
  </div>
</div>"""

    return f"""
<div class="card">
  <h2><span class="sn">🎯</span>สรุปปัจจัยสำคัญ — อะไรทำให้เร็วหรือช้า?</h2>
  <p style="color:#666;margin-bottom:16px">
    วิเคราะห์จากผล benchmark จริง 26 scenarios บน VM Ubuntu 24.04, 8 vCPU, 14GB RAM
    — ทุกตัวเลขมาจากข้อมูลจริง ไม่ใช่การประมาณ
  </p>
  <div class="grid2" style="margin-bottom:0">
    <div class="mbox green" style="text-align:center;padding:14px">
      <div style="font-size:32px;font-weight:900;color:#27ae60">Go ชนะ</div>
      <div style="font-size:16px;font-weight:700;color:#2c3e50">26/26 scenarios</div>
      <div style="font-size:12px;color:#666;margin-top:4px">ทุกชนิดไฟล์ ทุก key type ทุกขนาด</div>
    </div>
    <div class="mbox orange" style="text-align:center;padding:14px">
      <div style="font-size:32px;font-weight:900;color:#F89820">1.1× – 1.8×</div>
      <div style="font-size:16px;font-weight:700;color:#2c3e50">ช่องว่าง Go vs Java</div>
      <div style="font-size:12px;color:#666;margin-top:4px">ขึ้นอยู่กับ key type + file size + concurrent</div>
    </div>
  </div>
</div>

<div class="grid2">

  <div class="card">
    <h2><span class="sn">📏</span>ปัจจัย 1: ขนาดไฟล์ → ยิ่งใหญ่ ช่องว่างยิ่งแคบ</h2>
    <p style="font-size:12px;color:#888;margin-bottom:14px">
      p50 round-trip ms ต่อไฟล์ | RSA-2048 | best variant — ยิ่งน้อยยิ่งดี
    </p>
    {size_chart}
    <div class="hi" style="font-size:12px;margin-top:4px">
      <strong>📌 นัยยะ:</strong>
      ไฟล์เล็ก ~10KB = Java ช้ากว่า <strong>1.46×</strong> (เสียเปรียบมากสุด)<br>
      ไฟล์ใหญ่ mix = Java ช้ากว่า <strong>1.14×</strong> (เกือบตามทัน)
    </div>
  </div>

  <div class="card">
    <h2><span class="sn">📦</span>ปัจจัย 2: จำนวนไฟล์ → เวลาสะสม (10,000 ไฟล์)</h2>
    <p style="font-size:12px;color:#888;margin-bottom:14px">
      คำนวณจาก per-file p50 × 10,000 ไฟล์ | RSA-2048 | วินาทีรวม — ยิ่งน้อยยิ่งดี
    </p>
    {count_chart}
    <div class="hi" style="font-size:12px;margin-top:4px">
      <strong>📌 นัยยะ:</strong>
      ยิ่งไฟล์เยอะ เวลาต่างกันสะสม (linear)<br>
      ตัวอย่าง: 10,000 ไฟล์ขนาด 10KB — Java ใช้เวลาเพิ่ม <strong>+3.7 วินาที</strong><br>
      ถ้ารัน 10 batch/วัน = Java ช้ากว่า Go <strong>37 วินาที/วัน</strong> สำหรับ workload นี้
    </div>
  </div>

  <div class="card">
    <h2><span class="sn">🔑</span>ปัจจัย 3: Key Algorithm — ส่งผลมากที่สุด</h2>
    <p style="font-size:12px;color:#888;margin-bottom:14px">
      p50 round-trip ms | ไฟล์ .txt ~512KB | best variant
    </p>
    {key_chart}
    <div style="margin-top:12px;margin-bottom:6px">
      <div style="font-size:12px;font-weight:700;color:#444;margin-bottom:8px">Go ได้เปรียบกี่เท่า (1× = เท่ากัน, 2× = Go เร็วกว่า 2 เท่า)</div>
      {ratio_bars}
    </div>
    <div class="hi" style="font-size:12px;margin-top:4px">
      <strong>📌 นัยยะ:</strong>
      Key type เป็นตัวแปรที่ส่งผลมากกว่าขนาดไฟล์<br>
      Curve25519 = Go เร็วกว่า <strong>1.79×</strong> |
      RSA-4096 = Java ตามทันได้ดีสุด <strong>1.25×</strong>
    </div>
  </div>

  <div class="card">
    <h2><span class="sn">📄</span>ปัจจัย 4: ชนิดไฟล์ → Compressible vs Binary</h2>
    <p style="font-size:12px;color:#888;margin-bottom:14px">
      p50 round-trip ms | RSA-2048 | ชนิดไฟล์เปลี่ยน throughput ไม่เปลี่ยนผู้ชนะ
    </p>
    {type_chart}
    <div class="info" style="font-size:12px;margin-top:4px">
      <strong>📌 นัยยะ:</strong>
      .txt/.csv เร็วกว่า binary ~5× เพราะ ZLIB ลดข้อมูลก่อน AES<br>
      แต่ Go ชนะทุกชนิดไฟล์ — ชนิดไฟล์ไม่เปลี่ยนผู้ชนะ
    </div>
  </div>

  <div class="card">
    <h2><span class="sn">⚡</span>ปัจจัย 5: Concurrent Load — ยิ่งเยอะ Go ยิ่งได้เปรียบ</h2>
    <p style="font-size:12px;color:#888;margin-bottom:14px">
      Throughput MB/s รวม — ยิ่งมากยิ่งดี | RSA-2048 | parallel variant
    </p>
    {conc_chart}
    <div class="hi" style="font-size:12px;margin-top:4px">
      <strong>📌 นัยยะ:</strong>
      1 client พร้อมกัน = Go เร็วกว่า <strong>1.3×</strong><br>
      8 clients พร้อมกัน = Go เร็วกว่า <strong>1.8×</strong><br>
      Java throughput ตกชันกว่าเมื่อ concurrent สูงขึ้น
    </div>
  </div>

  <div class="card">
    <h2><span class="sn">🌡</span>ปัจจัย 6: JVM Warm-up — ทดสอบจริงบน VM</h2>
    <p style="font-size:12px;color:#888;margin-bottom:14px">
      p50 ms ต่อไฟล์ | RSA-2048 | .txt ~512KB | warmup iterations ต่างกัน
    </p>
    {warm_chart}
    <div class="grid2" style="margin-top:12px">
      <div class="mbox orange">
        <h4>🔥 Java cold start</h4>
        <p style="font-size:12px">JIT ยังไม่ compile → 3.36ms<br>
        Go เร็วกว่า <strong>2.1×</strong></p>
      </div>
      <div class="mbox green">
        <h4>✅ Java warm (20 warmup iters)</h4>
        <p style="font-size:12px">JIT compile ครบ → 1.67ms<br>
        ต่างจาก Go แค่ <strong>5%</strong></p>
      </div>
    </div>
    <div class="info" style="font-size:12px;margin-top:10px">
      <strong>📌 นัยยะ:</strong>
      Java long-running service สามารถ competitive กับ Go ได้สำหรับ .txt/.csv
      หลัง JIT warm ครบ (~1,000 request แรก)
      แต่ binary files และ concurrent load Go ยังได้เปรียบชัดเจน
    </div>
  </div>

</div>

<div class="card" style="background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff">
  <h2 style="color:#fff;border-left-color:#00ADE8">
    <span class="sn">🏆</span>สรุปสำหรับตัดสินใจ
  </h2>
  <div class="grid2" style="margin-top:16px">
    <div style="background:rgba(0,173,232,0.15);border-radius:10px;padding:18px;border:1px solid rgba(0,173,232,0.4)">
      <h4 style="color:#00ADE8;font-size:15px;margin-bottom:12px">🔵 เลือก Go เมื่อ...</h4>
      <ul style="color:#e8eaed;line-height:2.2">
        <li>ไฟล์เล็ก &lt;100KB จำนวนมาก (batch หมื่นไฟล์/วัน)</li>
        <li>ใช้ <strong style="color:#00ADE8">Curve25519</strong> — Go ได้เปรียบ 1.79×</li>
        <li>ต้องการ concurrent load สูง (8+ clients พร้อมกัน)</li>
        <li>ระบบใหม่ที่ไม่มี Java stack เดิม</li>
        <li>Memory footprint และ startup time สำคัญ</li>
      </ul>
    </div>
    <div style="background:rgba(248,152,32,0.15);border-radius:10px;padding:18px;border:1px solid rgba(248,152,32,0.4)">
      <h4 style="color:#F89820;font-size:15px;margin-bottom:12px">🟠 Java ทำได้ดีพอเมื่อ...</h4>
      <ul style="color:#e8eaed;line-height:2.2">
        <li>ระบบ enterprise ที่ใช้ Java stack อยู่แล้ว</li>
        <li><strong style="color:#F89820">Long-running service</strong> + .txt/.csv (warm ≈ Go)</li>
        <li>ใช้ <strong style="color:#F89820">RSA-4096</strong> — ช่องว่างเหลือแค่ 1.25×</li>
        <li>ไฟล์ใหญ่ &gt;5MB — ช่องว่างแคบเหลือ 1.14×</li>
        <li>ทีมมีความรู้ Java ไม่อยากเรียน Go ใหม่</li>
      </ul>
    </div>
  </div>
</div>"""
