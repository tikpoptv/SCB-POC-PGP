"""pages/results.py — Tab 2: กราฟผลทดสอบ (CSS bars)"""


def _bar(go_val: float, java_val: float, max_val: float, label: str) -> str:
    gp  = min(go_val   / max_val * 100, 100) if max_val > 0 else 0
    jp  = min(java_val / max_val * 100, 100) if max_val > 0 else 0
    go_wins = go_val < java_val
    ratio = max(go_val,java_val) / min(go_val,java_val) if min(go_val,java_val) > 0 else 1
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


def build(rows: list, conc: dict) -> str:

    # chart 1: file types RSA-2048
    ft_rsa2 = {r["sc_id"].replace("ft-","").replace("-rsa2048",""): r
               for r in rows if "ft-" in r["sc_id"] and "rsa2048" in r["sc_id"]}
    max1 = max(max(r["go_p50"],r["java_p50"]) for r in ft_rsa2.values()) * 1.15 if ft_rsa2 else 1
    chart1 = "".join(_bar(r["go_p50"], r["java_p50"], max1, ft.upper())
                     for ft, r in ft_rsa2.items())

    # chart 2: file types Curve25519
    ft_ec  = {r["sc_id"].replace("ft-","").replace("-curve25519",""): r
              for r in rows if "ft-" in r["sc_id"] and "curve25519" in r["sc_id"]}
    max2 = max(max(r["go_p50"],r["java_p50"]) for r in ft_ec.values()) * 1.15 if ft_ec else 1
    chart2 = "".join(_bar(r["go_p50"], r["java_p50"], max2, ft.upper())
                     for ft, r in ft_ec.items())

    # chart 3: key type on .txt
    txt_rows = [r for r in rows if r["sc_id"].startswith("ft-txt-")]
    max3 = max(max(r["go_p50"],r["java_p50"]) for r in txt_rows) * 1.15 if txt_rows else 1
    chart3 = "".join(_bar(r["go_p50"], r["java_p50"], max3, r["pub_alg"])
                     for r in txt_rows)

    # chart 4: many-small
    small_rows = [r for r in rows if "many-" in r["sc_id"]]
    max4 = max(max(r["go_p50"],r["java_p50"]) for r in small_rows) * 1.15 if small_rows else 1
    chart4 = "".join(_bar(r["go_p50"], r["java_p50"], max4,
                          r["sc_id"].replace("many-",""))
                     for r in small_rows)

    # chart 5: concurrent throughput (MB/s — higher is better, flip bar logic)
    conc_html = ""
    if conc:
        max_thr = max(
            v.get("go-stream-parallel",{}).get("throughput_mean_mbs",0)
            for v in conc.values()
        ) * 1.15 or 100
        for cl in ["1","2","4","8"]:
            cl_data = conc.get(cl, {})
            g = cl_data.get("go-stream-parallel",{}).get("throughput_mean_mbs",0)
            j = cl_data.get("java-stream-parallel",{}).get("throughput_mean_mbs",0)
            gp = min(g/max_thr*100,100)
            jp = min(j/max_thr*100,100)
            ratio = g/j if j > 0 else 1
            conc_html += f"""
<div class="bar-row">
  <div class="bar-lbl">{cl} client{"s" if int(cl)>1 else ""} พร้อมกัน</div>
  <div class="bar-wrap">
    <span class="bar-name" style="color:#00ADE8">Go</span>
    <div class="bar-bg" style="background:#e8f4fd">
      <div class="bar-fill" style="width:{gp:.1f}%;background:#00ADE8">
        <span>{g:.0f} MB/s</span>
      </div>
    </div>
  </div>
  <div class="bar-wrap">
    <span class="bar-name" style="color:#F89820">Java</span>
    <div class="bar-bg" style="background:#fef3e2">
      <div class="bar-fill" style="width:{jp:.1f}%;background:#F89820">
        <span>{j:.0f} MB/s</span>
      </div>
    </div>
  </div>
  <div class="bar-note" style="color:#00ADE8">Go เร็วกว่า {ratio:.1f}×</div>
</div>"""

    return f"""
<div class="grid2">
  <div class="card">
    <h2>📄 ชนิดไฟล์ vs RSA-2048</h2>
    <p style="font-size:12px;color:#888;margin-bottom:12px">
      p50 round-trip ms · 15 files × 512KB · ยิ่งน้อยยิ่งดี</p>
    {chart1}
    <div class="info" style="font-size:12px;margin-top:10px">
      Go ชนะ binary (.pdf/.xlsx/.zip/.dat) · Java ชนะ text (.txt/.csv)
    </div>
  </div>

  <div class="card">
    <h2>🔑 ชนิดไฟล์ vs Curve25519</h2>
    <p style="font-size:12px;color:#888;margin-bottom:12px">
      p50 round-trip ms · 15 files × 512KB · ยิ่งน้อยยิ่งดี</p>
    {chart2}
    <div class="info" style="font-size:12px;margin-top:10px">
      Pattern เดิม: Go ชนะ binary · Java ชนะ text
    </div>
  </div>

  <div class="card">
    <h2>📝 Key Algorithm Effect (.txt)</h2>
    <p style="font-size:12px;color:#888;margin-bottom:12px">
      p50 ms ต่อไฟล์ · Java ชนะ .txt ทุก key type (ZLIB path เร็วกว่า)</p>
    {chart3}
  </div>

  <div class="card">
    <h2>📦 Many-Small Files</h2>
    <p style="font-size:12px;color:#888;margin-bottom:12px">
      p50 ms ต่อ operation · Go ชนะไฟล์เล็กมาก (1KB,10KB) · 100KB Java ชนะ (ZLIB คุ้มขึ้น)</p>
    {chart4}
  </div>
</div>

<div class="card">
  <h2>⚡ Concurrent Load — ยิ่งเยอะ clients Go ยิ่งได้เปรียบ</h2>
  <p style="font-size:12px;color:#888;margin-bottom:12px">
    Throughput MB/s รวม (ยิ่งมากยิ่งดี) · RSA-2048 · parallel variant</p>
  {conc_html if conc_html else "<p>ไม่มีข้อมูล concurrent</p>"}
  <div class="hi" style="margin-top:12px;font-size:12px">
    Go scale ได้ดีกว่าเมื่อ load สูงขึ้น
    Java throughput ตกมากกว่าเมื่อ concurrent เพิ่ม
  </div>
</div>"""
