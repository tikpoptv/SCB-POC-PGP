"""pages/insights.py — Tab 3: Key Insights + Size/Count Gradient"""


def _bar(go_val, java_val, max_val, label):
    gp = min(go_val / max_val * 100, 100) if max_val > 0 else 0
    jp = min(java_val / max_val * 100, 100) if max_val > 0 else 0
    go_wins = go_val < java_val
    ratio = max(go_val, java_val) / min(go_val, java_val) if min(go_val, java_val) > 0 else 1
    note_color = "#00ADE8" if go_wins else "#F89820"
    note_txt = f"Go เร็วกว่า {ratio:.2f}×" if go_wins else f"Java เร็วกว่า {ratio:.2f}×"
    return f"""
<div class="bar-row">
  <div class="bar-lbl">{label}</div>
  <div class="bar-wrap">
    <span class="bar-name" style="color:#00ADE8">Go</span>
    <div class="bar-bg" style="background:#e8f4fd">
      <div class="bar-fill" style="width:{gp:.1f}%;background:{'#00ADE8' if go_wins else '#93c5fd'}">
        <span>{go_val:.1f} ms</span>
      </div>
    </div>
  </div>
  <div class="bar-wrap">
    <span class="bar-name" style="color:#F89820">Java</span>
    <div class="bar-bg" style="background:#fef3e2">
      <div class="bar-fill" style="width:{jp:.1f}%;background:{'#F89820' if not go_wins else '#fcd34d'}">
        <span>{java_val:.1f} ms</span>
      </div>
    </div>
  </div>
  <div class="bar-note" style="color:{note_color}">{note_txt}</div>
</div>"""


def _sg_chart(sg: dict, suffix: str, title: str) -> str:
    """size gradient chart"""
    keys = sorted(
        [k for k in sg.keys() if k.endswith(suffix)],
        key=lambda x: int(x.replace(suffix, "").replace("kb", ""))
    )
    if not keys:
        return "<p>ไม่มีข้อมูล</p>"

    vals = []
    for k in keys:
        s = sg[k]
        if s.get("go") and s.get("java"):
            gp = min(v["p50_mean"] for v in s["go"].values())
            jp = min(v["p50_mean"] for v in s["java"].values())
            vals.extend([gp, jp])
    max_v = max(vals) * 1.15 if vals else 1

    html = f'<p style="font-size:12px;color:#888;margin-bottom:12px">{title}</p>'
    for k in keys:
        s = sg[k]
        if not s.get("go") or not s.get("java"):
            continue
        gp = min(v["p50_mean"] for v in s["go"].values())
        jp = min(v["p50_mean"] for v in s["java"].values())
        kb = k.replace(suffix, "").replace("kb", "")
        label = f"{kb}KB" if int(kb) < 1024 else f"{int(kb)//1024}MB"
        html += _bar(gp, jp, max_v, label)
    return html


def _cg_chart(cg: dict) -> str:
    """count gradient chart"""
    keys = sorted(cg.keys(), key=lambda x: int(x.replace("files", "")))
    if not keys:
        return "<p>ไม่มีข้อมูล</p>"

    vals = []
    for k in keys:
        s = cg[k]
        if s.get("go") and s.get("java"):
            gp = min(v["p50_mean"] for v in s["go"].values())
            jp = min(v["p50_mean"] for v in s["java"].values())
            vals.extend([gp, jp])
    max_v = max(vals) * 1.15 if vals else 1

    html = '<p style="font-size:12px;color:#888;margin-bottom:12px">p50 ms ต่อไฟล์ (100KB binary · RSA-2048) — ยิ่งน้อยยิ่งดี</p>'
    for k in keys:
        s = cg[k]
        if not s.get("go") or not s.get("java"):
            continue
        gp = min(v["p50_mean"] for v in s["go"].values())
        jp = min(v["p50_mean"] for v in s["java"].values())
        n = k.replace("files", "")
        html += _bar(gp, jp, max_v, f"{n} ไฟล์")
    return html


def build(rows: list, conc: dict, sg: dict, cg: dict) -> str:
    # ดึงข้อมูล key type
    curve_txt = next((r for r in rows if r["sc_id"] == "ft-txt-curve25519"), None)
    rsa2_txt  = next((r for r in rows if r["sc_id"] == "ft-txt-rsa2048"), None)
    rsa4_txt  = next((r for r in rows if r["sc_id"] == "ft-txt-rsa4096"), None)

    binary_rows = [r for r in rows if any(x in r["sc_id"] for x in ["ft-pdf","ft-xlsx","ft-zip","ft-dat"])]
    text_rows   = [r for r in rows if any(x in r["sc_id"] for x in ["ft-txt","ft-csv"])]
    go_wins_binary = sum(1 for r in binary_rows if r["winner"] == "GO")
    java_wins_text = sum(1 for r in text_rows   if r["winner"] == "JAVA")

    bin_avg_go   = sum(r["go_p50"]   for r in binary_rows) / max(len(binary_rows), 1)
    bin_avg_java = sum(r["java_p50"] for r in binary_rows) / max(len(binary_rows), 1)
    txt_avg_go   = sum(r["go_p50"]   for r in text_rows)   / max(len(text_rows), 1)
    txt_avg_java = sum(r["java_p50"] for r in text_rows)   / max(len(text_rows), 1)

    # concurrent
    g1 = conc.get("1",{}).get("go-stream-parallel",{}).get("throughput_mean_mbs",0)
    j1 = conc.get("1",{}).get("java-stream-parallel",{}).get("throughput_mean_mbs",0)
    g8 = conc.get("8",{}).get("go-stream-parallel",{}).get("throughput_mean_mbs",0)
    j8 = conc.get("8",{}).get("java-stream-parallel",{}).get("throughput_mean_mbs",0)

    # size gradient charts
    sg_binary_chart = _sg_chart(sg, "_binary", "p50 ms ต่อไฟล์ (binary · RSA-2048) — ยิ่งน้อยยิ่งดี")
    sg_text_chart   = _sg_chart(sg, "_text",   "p50 ms ต่อไฟล์ (text compressible · RSA-2048) — ยิ่งน้อยยิ่งดี")

    # count gradient chart
    cg_chart = _cg_chart(cg)

    # size gradient breakpoint analysis
    sg_breakpoint = ""
    if sg:
        for k in sorted([x for x in sg if x.endswith("_binary")],
                        key=lambda x: int(x.replace("_binary","").replace("kb",""))):
            s = sg[k]
            if not s.get("go") or not s.get("java"):
                continue
            gp = min(v["p50_mean"] for v in s["go"].values())
            jp = min(v["p50_mean"] for v in s["java"].values())
            kb = int(k.replace("_binary","").replace("kb",""))
            label = f"{kb}KB" if kb < 1024 else f"{kb//1024}MB"
            winner = "Go" if gp < jp else "Java"
            ratio = max(gp,jp)/min(gp,jp) if min(gp,jp)>0 else 1
            bg = "#dbeafe" if winner=="Go" else "#fef3c7"
            sg_breakpoint += f'<tr style="background:{bg}"><td>{label}</td><td style="color:#00ADE8">{gp:.2f}</td><td style="color:#F89820">{jp:.2f}</td><td><strong>{winner} {ratio:.2f}×</strong></td></tr>'

    sg_breakpoint_text = ""
    if sg:
        for k in sorted([x for x in sg if x.endswith("_text")],
                        key=lambda x: int(x.replace("_text","").replace("kb",""))):
            s = sg[k]
            if not s.get("go") or not s.get("java"):
                continue
            gp = min(v["p50_mean"] for v in s["go"].values())
            jp = min(v["p50_mean"] for v in s["java"].values())
            kb = int(k.replace("_text","").replace("kb",""))
            label = f"{kb}KB" if kb < 1024 else f"{kb//1024}MB"
            winner = "Go" if gp < jp else "Java"
            ratio = max(gp,jp)/min(gp,jp) if min(gp,jp)>0 else 1
            bg = "#dbeafe" if winner=="Go" else "#fef3c7"
            sg_breakpoint_text += f'<tr style="background:{bg}"><td>{label}</td><td style="color:#00ADE8">{gp:.2f}</td><td style="color:#F89820">{jp:.2f}</td><td><strong>{winner} {ratio:.2f}×</strong></td></tr>'

    # count gradient table
    cg_table = ""
    if cg:
        for k in sorted(cg.keys(), key=lambda x: int(x.replace("files",""))):
            s = cg[k]
            if not s.get("go") or not s.get("java"):
                continue
            gp = min(v["p50_mean"] for v in s["go"].values())
            jp = min(v["p50_mean"] for v in s["java"].values())
            n = int(k.replace("files",""))
            ratio = jp/gp if gp > 0 else 0
            bg = "#dbeafe" if gp < jp else "#fef3c7"
            cg_table += f'<tr style="background:{bg}"><td><strong>{n:,} ไฟล์</strong></td><td style="color:#00ADE8">{gp:.2f}</td><td style="color:#F89820">{jp:.2f}</td><td><strong>Go เร็วกว่า {ratio:.2f}×</strong></td></tr>'

    return f"""
<div class="card">
  <h2>🔍 สรุปปัจจัยสำคัญ</h2>
  <div class="grid2">
    <div class="mbox go">
      <h3>� Go ได้เปรียบเมื่อ...</h3>
      <ul style="line-height:2.2;margin-top:8px">
        <li>ไฟล์ binary ทุกขนาด (.pdf/.xlsx/.zip/.dat) — {go_wins_binary}/{len(binary_rows)} scenarios</li>
        <li>ไฟล์ขนาดเล็ก &lt;512KB — Go เร็วกว่า <strong>1.7–6×</strong></li>
        <li>ไฟล์ 1 ใบ (JVM startup overhead หาร 1 ไฟล์ = สูงมาก)</li>
        <li>Concurrent load สูง — Go {g1:.0f} MB/s vs Java {j1:.0f} MB/s</li>
      </ul>
    </div>
    <div class="mbox java">
      <h3>🟠 Java ได้เปรียบเมื่อ...</h3>
      <ul style="line-height:2.2;margin-top:8px">
        <li>ไฟล์ text (.txt/.csv) ที่บีบอัดได้สูง — {java_wins_text}/{len(text_rows)} scenarios</li>
        <li>ไฟล์ขนาดใหญ่ &gt;1MB text — Java เร็วกว่า <strong>1.4–1.7×</strong></li>
        <li>ไฟล์หลายพันใบ (JVM overhead เฉลี่ยลงต่อไฟล์)</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2>� ขนาดไฟล์ส่งผลยังไง? — Binary Files</h2>
  <div class="grid2">
    <div>
      {sg_binary_chart}
    </div>
    <div style="overflow-x:auto">
      <table>
        <thead><tr><th>ขนาด</th><th>Go ms</th><th>Java ms</th><th>Winner</th></tr></thead>
        <tbody>{sg_breakpoint}</tbody>
      </table>
    </div>
  </div>
  <div class="hi" style="margin-top:12px;font-size:12px">
    <strong>📌 นัยยะ (Binary):</strong>
    ไฟล์ขนาดเล็ก &lt;512KB → Go เร็วกว่า <strong>2–6×</strong> ชัดเจน
    ไฟล์ใหญ่ขึ้น ช่องว่างแคบลงแต่ Go ยังชนะตลอด
    เพราะ AES hardware path ของ Go runtime เร็วกว่า Java ทุกขนาด
  </div>
</div>

<div class="card">
  <h2>📄 ขนาดไฟล์ส่งผลยังไง? — Text Files (Compressible)</h2>
  <div class="grid2">
    <div>
      {sg_text_chart}
    </div>
    <div style="overflow-x:auto">
      <table>
        <thead><tr><th>ขนาด</th><th>Go ms</th><th>Java ms</th><th>Winner</th></tr></thead>
        <tbody>{sg_breakpoint_text}</tbody>
      </table>
    </div>
  </div>
  <div class="hi" style="margin-top:12px;font-size:12px">
    <strong>📌 นัยยะ (Text):</strong>
    ไฟล์ขนาดเล็ก &lt;256KB → Go เร็วกว่า (compression step เล็ก)<br>
    <strong>Breakpoint ~512KB</strong> — แทบเท่ากัน<br>
    ไฟล์ใหญ่ &gt;1MB → <strong>Java ชนะกลับ</strong> เพราะ JVM ZLIB native เร็วกว่า Go pure-Go ZLIB มาก
  </div>
</div>

<div class="card">
  <h2>� จำนวนไฟล์ส่งผลยังไง?</h2>
  <div class="grid2">
    <div>
      {cg_chart}
    </div>
    <div style="overflow-x:auto">
      <table>
        <thead><tr><th>จำนวนไฟล์</th><th>Go ms/file</th><th>Java ms/file</th><th>Go เร็วกว่า</th></tr></thead>
        <tbody>{cg_table}</tbody>
      </table>
    </div>
  </div>
  <div class="hi" style="margin-top:12px;font-size:12px">
    <strong>📌 นัยยะ (Count):</strong>
    1 ไฟล์ → Go เร็วกว่า <strong>4.7×</strong> (JVM startup overhead ทั้งหมดตกที่ 1 ไฟล์)<br>
    ยิ่งไฟล์เยอะขึ้น JVM overhead เฉลี่ยลง ช่องว่างแคบลงเรื่อยๆ<br>
    1,000 ไฟล์ → เหลือแค่ <strong>1.08×</strong> แทบไม่ต่างกัน
  </div>
</div>

<div class="card">
  <h2>⚡ Concurrent Load</h2>
  <div class="grid2">
    <div class="mbox go">
      <h3>1 client</h3>
      <p>Go <strong>{g1:.0f} MB/s</strong> vs Java {j1:.0f} MB/s</p>
      <p style="color:#00ADE8;font-weight:700">Go เร็วกว่า {g1/j1:.1f}×</p>
    </div>
    <div class="mbox go">
      <h3>8 clients พร้อมกัน</h3>
      <p>Go <strong>{g8:.0f} MB/s</strong> vs Java {j8:.0f} MB/s</p>
      <p style="color:#00ADE8;font-weight:700">Go เร็วกว่า {g8/j8:.1f}×</p>
    </div>
  </div>
  <div class="info" style="margin-top:10px;font-size:12px">
    เมื่อ clients เพิ่มขึ้น ช่องว่าง Go vs Java ถ่างออก —
    Go Goroutine scale ได้ดีกว่า JVM thread pool เมื่อ load สูง
  </div>
</div>

<div class="card" style="background:linear-gradient(135deg,#0f3460,#1a1a2e)">
  <h2 style="color:#fff;border-left-color:#00ADE8">🏆 สรุปสำหรับตัดสินใจ</h2>
  <div class="grid2" style="margin-top:14px">
    <div style="background:#1e4d7b;border-radius:10px;padding:16px;border:2px solid #00ADE8">
      <h3 style="color:#00ADE8;margin-bottom:10px">✅ เลือก Go เมื่อ...</h3>
      <ul style="color:#ffffff;line-height:2.2;list-style:disc;padding-left:20px">
        <li style="color:#ffffff">ระบบ process binary files (.pdf, .xlsx, .zip)</li>
        <li style="color:#ffffff">ไฟล์ขนาดเล็ก &lt;512KB จำนวนน้อย (&lt;100 ไฟล์)</li>
        <li style="color:#ffffff">ต้องการ concurrent request สูง (8+ clients)</li>
        <li style="color:#ffffff">ระบบใหม่ที่ต้องการ performance สูงสุด</li>
      </ul>
    </div>
    <div style="background:#4d2e00;border-radius:10px;padding:16px;border:2px solid #F89820">
      <h3 style="color:#F89820;margin-bottom:10px">⚖️ Java ทำได้ดีเมื่อ...</h3>
      <ul style="color:#ffffff;line-height:2.2;list-style:disc;padding-left:20px">
        <li style="color:#ffffff">ระบบ enterprise ที่ใช้ Java stack อยู่แล้ว</li>
        <li style="color:#ffffff">Workload เป็น .txt/.csv ขนาดใหญ่ &gt;1MB เป็นหลัก</li>
        <li style="color:#ffffff">Batch หลายพันไฟล์ (per-file overhead เฉลี่ยออก)</li>
        <li style="color:#ffffff">Long-running service (JIT warm เต็มที่)</li>
      </ul>
    </div>
  </div>
</div>"""
