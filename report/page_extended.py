"""page_extended.py — Full Coverage Benchmark Results"""
import pathlib, json, statistics
import data_loader

RESULTS_PATH = pathlib.Path(__file__).parent / "results_extended.json"

FILE_TYPES = ["txt", "csv", "pdf", "xlsx", "zip", "dat"]
KEY_ALGS   = ["RSA-2048", "RSA-4096", "Curve25519"]
FILE_ICONS = {"txt":"📄","csv":"📊","pdf":"📕","xlsx":"📗","zip":"🗜","dat":"💾"}
FILE_DESC  = {
    "txt":  ".txt — ข้อความ (บีบอัดได้สูง ~80%)",
    "csv":  ".csv — ตาราง CSV (บีบอัดได้สูง)",
    "pdf":  ".pdf — PDF binary (บีบอัดได้ต่ำ ~5%)",
    "xlsx": ".xlsx — Excel ZIP-based (binary)",
    "zip":  ".gz — ไฟล์บีบอัดแล้ว (บีบไม่ได้เพิ่ม)",
    "dat":  ".dat — Random binary (บีบไม่ได้เลย)",
}

def _badge(w, speedup):
    if w == "GO":   return f'<span class="badge bg">🔵 Go +{speedup:.1f}×</span>'
    if w == "JAVA": return f'<span class="badge bj">🟠 Java +{speedup:.1f}×</span>'
    return '<span class="badge bt">⚪ เสมอ</span>'

def _cell_bg(w):
    if w == "GO":   return "#dbeafe"
    if w == "JAVA": return "#fef3c7"
    return "#f3f4f6"

def _build_coverage_matrix(lookup: dict) -> str:
    """สร้าง heatmap matrix: rows=file type, cols=key alg"""
    html = """
<div style="overflow-x:auto">
<table style="width:auto;min-width:700px">
<thead>
  <tr>
    <th style="min-width:200px">ชนิดไฟล์</th>
    <th style="text-align:center;min-width:150px">RSA-2048<br><small>มาตรฐาน</small></th>
    <th style="text-align:center;min-width:150px">RSA-4096<br><small>ความปลอดภัยสูง</small></th>
    <th style="text-align:center;min-width:150px">Curve25519<br><small>ยุคใหม่</small></th>
  </tr>
</thead>
<tbody>"""

    for ft in FILE_TYPES:
        icon = FILE_ICONS.get(ft,"📄")
        desc = FILE_DESC.get(ft, ft)
        html += f"<tr><td><strong>{icon} {desc}</strong></td>"
        for alg in KEY_ALGS:
            sc_id = f"ft-{ft}-{alg.lower().replace('-','')}"
            r = lookup.get(sc_id)
            if not r:
                html += '<td style="text-align:center;color:#aaa">—</td>'
                continue
            bg = _cell_bg(r["winner"])
            if r["winner"] == "GO":
                winner_text = f"🔵 Go<br><strong>{r['go_p50']:.1f}</strong> vs {r['java_p50']:.1f} ms"
                spd_text = f"+{r['speedup']:.1f}×"
            elif r["winner"] == "JAVA":
                winner_text = f"🟠 Java<br>{r['go_p50']:.1f} vs <strong>{r['java_p50']:.1f}</strong> ms"
                spd_text = f"+{r['speedup']:.1f}×"
            else:
                winner_text = f"⚪ เสมอ<br>{r['go_p50']:.1f} vs {r['java_p50']:.1f} ms"
                spd_text = f"~{r['diff_pct']:.0f}%"
            html += f'<td style="text-align:center;background:{bg};padding:8px">'
            html += f'{winner_text}<br><small style="color:#666">{spd_text}</small></td>'
        html += "</tr>"
    html += "</tbody></table></div>"
    return html


def _build_size_gradient_table(rows_by_id: dict) -> str:
    """ตาราง size gradient × 3 key types สำหรับ compressible"""
    alg_rows = []
    for alg in KEY_ALGS:
        sc_id = f"sizegrad-comp-{alg.lower().replace('-','')}"
        r = rows_by_id.get(sc_id)
        if r:
            alg_rows.append((alg, r))

    if not alg_rows:
        return "<p>ไม่มีข้อมูล</p>"

    html = "<table><thead><tr>"
    html += "<th>Key Algorithm</th>"
    html += "<th>Best Go Variant</th><th style='text-align:center'>Go p50 ms</th>"
    html += "<th>Best Java Variant</th><th style='text-align:center'>Java p50 ms</th>"
    html += "<th>Winner</th><th>Throughput Go</th><th>Throughput Java</th></tr></thead><tbody>"

    for alg, r in alg_rows:
        bg = _cell_bg(r["winner"])
        gvs = r["go_variant"].replace("go-","").replace("-single","").replace("-parallel","⚡")
        jvs = r["java_variant"].replace("java-","").replace("-single","").replace("-parallel","⚡")
        tg = f"{r['go_thr']:.1f} MB/s" if r.get("go_thr") else "—"
        tj = f"{r['java_thr']:.1f} MB/s" if r.get("java_thr") else "—"
        html += f'<tr style="background:{bg}">'
        html += f'<td><strong>{alg}</strong></td>'
        html += f'<td style="color:#00ADE8">{gvs}</td>'
        html += f'<td style="text-align:center;font-weight:600">{r["go_p50"]:.3f}</td>'
        html += f'<td style="color:#F89820">{jvs}</td>'
        html += f'<td style="text-align:center;font-weight:600">{r["java_p50"]:.3f}</td>'
        html += f'<td>{_badge(r["winner"], r["speedup"])}</td>'
        html += f'<td>{tg}</td><td>{tj}</td></tr>'

    html += "</tbody></table>"
    return html


def _build_charts(rows: list, lookup: dict) -> str:
    """CSS-only bar charts — ไม่พึ่ง JS เลย ทำงานได้ทันที"""

    def css_bar_pair(go_val, java_val, max_val, label):
        go_pct   = min(go_val   / max_val * 100, 100) if max_val > 0 else 0
        java_pct = min(java_val / max_val * 100, 100) if max_val > 0 else 0
        go_winner = go_val < java_val
        return f"""
        <div style="margin-bottom:14px">
          <div style="font-size:12px;font-weight:600;color:#444;margin-bottom:4px">{label}</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
            <span style="width:40px;font-size:11px;color:#00ADE8">Go</span>
            <div style="flex:1;background:#e8f4fd;border-radius:4px;height:22px;position:relative">
              <div style="width:{go_pct:.1f}%;background:{'#00ADE8' if go_winner else '#93c5fd'};height:100%;border-radius:4px;display:flex;align-items:center;padding-left:6px">
                <span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{go_val:.1f} ms</span>
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="width:40px;font-size:11px;color:#F89820">Java</span>
            <div style="flex:1;background:#fef3e2;border-radius:4px;height:22px;position:relative">
              <div style="width:{java_pct:.1f}%;background:{'#F89820' if not go_winner else '#fcd34d'};height:100%;border-radius:4px;display:flex;align-items:center;padding-left:6px">
                <span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{java_val:.1f} ms</span>
              </div>
            </div>
          </div>
        </div>"""

    # Chart 1: File types × RSA-2048
    chart1_rows = ""
    vals1 = []
    for ft in FILE_TYPES:
        r = lookup.get(f"ft-{ft}-rsa2048")
        if r: vals1.extend([r["go_p50"], r["java_p50"]])
    max1 = max(vals1) * 1.1 if vals1 else 1
    for ft in FILE_TYPES:
        r = lookup.get(f"ft-{ft}-rsa2048")
        if r:
            chart1_rows += css_bar_pair(r["go_p50"], r["java_p50"], max1,
                                         FILE_ICONS.get(ft,"") + " " + ft.upper())

    # Chart 2: File types × Curve25519
    chart2_rows = ""
    vals2 = []
    for ft in FILE_TYPES:
        r = lookup.get(f"ft-{ft}-curve25519")
        if r: vals2.extend([r["go_p50"], r["java_p50"]])
    max2 = max(vals2) * 1.1 if vals2 else 1
    for ft in FILE_TYPES:
        r = lookup.get(f"ft-{ft}-curve25519")
        if r:
            chart2_rows += css_bar_pair(r["go_p50"], r["java_p50"], max2,
                                         FILE_ICONS.get(ft,"") + " " + ft.upper())

    # Chart 3: Size gradient × key types
    chart3_rows = ""
    vals3 = []
    for alg in KEY_ALGS:
        r = lookup.get(f"sizegrad-comp-{alg.lower().replace('-','')}")
        if r: vals3.extend([r["go_p50"], r["java_p50"]])
    max3 = max(vals3) * 1.1 if vals3 else 1
    for alg in KEY_ALGS:
        r = lookup.get(f"sizegrad-comp-{alg.lower().replace('-','')}")
        if r:
            chart3_rows += css_bar_pair(r["go_p50"], r["java_p50"], max3, alg)

    # Chart 4: Win count stacked (simple table)
    win_rows = ""
    for ft in FILE_TYPES:
        go_w, java_w, tie_w = 0, 0, 0
        for alg in KEY_ALGS:
            r = lookup.get(f"ft-{ft}-{alg.lower().replace('-','')}")
            if r:
                if r["winner"] == "GO":   go_w += 1
                elif r["winner"] == "JAVA": java_w += 1
                else: tie_w += 1
        total = go_w + java_w + tie_w
        if total == 0: continue
        go_pct   = go_w   / total * 100
        java_pct = java_w / total * 100
        win_rows += f"""
        <div style="margin-bottom:10px">
          <div style="font-size:12px;font-weight:600;color:#444;margin-bottom:4px">
            {FILE_ICONS.get(ft,"")} {ft.upper()} — {total} key types ทดสอบ</div>
          <div style="display:flex;height:24px;border-radius:4px;overflow:hidden">
            <div style="width:{go_pct:.0f}%;background:#00ADE8;display:flex;align-items:center;justify-content:center">
              {"<span style='font-size:11px;color:white;font-weight:700'>Go×" + str(go_w) + "</span>" if go_w > 0 else ""}
            </div>
            <div style="width:{java_pct:.0f}%;background:#F89820;display:flex;align-items:center;justify-content:center">
              {"<span style='font-size:11px;color:white;font-weight:700'>Java×" + str(java_w) + "</span>" if java_w > 0 else ""}
            </div>
            <div style="flex:1;background:#e5e7eb;display:flex;align-items:center;justify-content:center">
              {"<span style='font-size:11px;color:#666;font-weight:700'>เสมอ×" + str(tie_w) + "</span>" if tie_w > 0 else ""}
            </div>
          </div>
        </div>"""

    return f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
  <div class="chart-box">
    <div class="chart-title">① แต่ละชนิดไฟล์ vs RSA-2048 (20 files × 512KB)
      <div class="chart-sub">p50 round-trip ms — ยิ่งน้อยยิ่งดี | สีเข้ม = ผู้ชนะ</div></div>
    {chart1_rows}
  </div>
  <div class="chart-box">
    <div class="chart-title">② แต่ละชนิดไฟล์ vs Curve25519 (20 files × 512KB)
      <div class="chart-sub">Curve25519 ผลต่างชัดที่สุด</div></div>
    {chart2_rows}
  </div>
  <div class="chart-box">
    <div class="chart-title">③ Size Gradient (compressible .txt) ทุก Key Algorithm
      <div class="chart-sub">p50 ms รวมทั้งชุด corpus</div></div>
    {chart3_rows}
  </div>
  <div class="chart-box">
    <div class="chart-title">④ Go/Java ชนะกี่ Key Algorithm ต่อชนิดไฟล์
      <div class="chart-sub">🔵 = Go ชนะ | 🟠 = Java ชนะ | เทา = เสมอ</div></div>
    {win_rows}
  </div>
</div>"""

    # ── new CSS chart function ends above ──────────────────────────────────────


def build() -> str:
    if not RESULTS_PATH.exists():
        return """<div class="card">
          <h2>⏳ Full Benchmark ยังไม่พร้อม</h2>
          <p>รัน <code>python3 run_benchmark_full.py</code> บน VM
          แล้ว copy <code>results_full.json</code> มาใส่เป็น <code>report/results_extended.json</code></p></div>"""

    with open(RESULTS_PATH, encoding="utf-8") as f:
        ext_data = json.load(f)

    rows   = data_loader.extract_extended_rows(ext_data)
    lookup = {r["sc_id"]: r for r in rows}

    if not rows:
        return "<div class='card'><p>ไม่มีข้อมูล</p></div>"

    started  = ext_data.get("startedAt", "—")[:19].replace("T", " ")
    finished = ext_data.get("finishedAt", "—")[:19].replace("T", " ")
    total_sc = ext_data.get("totalScenarios", len(rows))

    go_wins  = sum(1 for r in rows if r["winner"] == "GO")
    java_wins = sum(1 for r in rows if r["winner"] == "JAVA")
    tie_wins  = sum(1 for r in rows if r["winner"] == "TIE")

    # Tier splits
    tier_a_ids  = [f"ft-{ft}-{alg.lower().replace('-','')}" for ft in FILE_TYPES for alg in KEY_ALGS]
    tier_b_ids  = [f"sizegrad-comp-{alg.lower().replace('-','')}" for alg in KEY_ALGS] + \
                  [f"sizegrad-incomp-{alg.lower().replace('-','')}" for alg in ["RSA-2048","Curve25519"]]
    tier_c_ids  = [r["sc_id"] for r in rows if "many-" in r["sc_id"]]

    rows_a = [r for r in rows if r["sc_id"] in tier_a_ids]
    rows_b = [r for r in rows if r["sc_id"] in tier_b_ids]
    rows_c = [r for r in rows if r["sc_id"] in tier_c_ids]

    # Many-small table
    def many_small_rows():
        out = ""
        for r in rows_c:
            bg = _cell_bg(r["winner"])
            gvs = r["go_variant"].replace("go-","").replace("-single","").replace("-parallel","⚡")
            jvs = r["java_variant"].replace("java-","").replace("-single","").replace("-parallel","⚡")
            tg = f"{r['go_thr']:.1f}" if r.get("go_thr") else "—"
            tj = f"{r['java_thr']:.1f}" if r.get("java_thr") else "—"
            out += f"""<tr style="background:{bg}">
              <td><strong>{r['sc_id']}</strong><br><small style="color:#aaa">{r['pub_alg']}</small></td>
              <td style="color:#00ADE8;font-weight:600">{r['go_p50']:.3f} ms<br>
                  <small style="color:#aaa">{gvs} · {tg} MB/s</small></td>
              <td style="color:#F89820;font-weight:600">{r['java_p50']:.3f} ms<br>
                  <small style="color:#aaa">{jvs} · {tj} MB/s</small></td>
              <td>{_badge(r['winner'], r['speedup'])}</td></tr>"""
        return out

    charts_html = _build_charts(rows, lookup)
    matrix_html = _build_coverage_matrix(lookup)
    sizegrad_html = _build_size_gradient_table(lookup)

    # ── Concurrent Load section ───────────────────────────────────────────────
    conc_data = ext_data.get("concurrent", {})
    if conc_data:
        def conc_bar(val, max_val, color):
            pct = min(val/max_val*100, 100) if max_val > 0 else 0
            return f'<div style="width:{pct:.0f}%;background:{color};height:22px;border-radius:4px;display:flex;align-items:center;padding-left:6px"><span style="font-size:11px;color:white;font-weight:700;white-space:nowrap">{val:.0f} MB/s</span></div>'

        conc_rows = ""
        all_thr = []
        for cl in ["1","2","4","8"]:
            cl_data = conc_data.get(cl, {})
            g = cl_data.get("go-stream-parallel", {})
            j = cl_data.get("java-stream-parallel", {})
            g_thr = g.get("throughputMbSec") or g.get("throughput_mean_mbs")
            j_thr = j.get("throughputMbSec") or j.get("throughput_mean_mbs")
            g_p50 = g.get("roundTrip", {}).get("p50") or "—"
            j_p50 = j.get("roundTrip", {}).get("p50") or "—"
            if g_thr: all_thr.append(g_thr)
            if j_thr: all_thr.append(j_thr)
            conc_rows += f"""<tr>
              <td style="font-weight:700">{cl} client{"s" if int(cl)>1 else ""}</td>
              <td style="color:#00ADE8;font-weight:600">{g_thr or "—"} MB/s<br><small style="color:#aaa">p50={g_p50}ms</small></td>
              <td style="color:#F89820;font-weight:600">{j_thr or "—"} MB/s<br><small style="color:#aaa">p50={j_p50}ms</small></td>
              <td>{"🔵 Go ดีกว่า" if g_thr and j_thr and g_thr>j_thr else ("🟠 Java ดีกว่า" if j_thr and g_thr and j_thr>g_thr else "—")}</td></tr>"""

        max_thr = max(all_thr) * 1.1 if all_thr else 300
        conc_bars = ""
        for cl in ["1","2","4","8"]:
            cl_data = conc_data.get(cl, {})
            g = cl_data.get("go-stream-parallel", {})
            j = cl_data.get("java-stream-parallel", {})
            g_thr = g.get("throughputMbSec") or g.get("throughput_mean_mbs") or 0
            j_thr = j.get("throughputMbSec") or j.get("throughput_mean_mbs") or 0
            conc_bars += f"""<div style="margin-bottom:16px">
              <div style="font-size:13px;font-weight:700;color:#444;margin-bottom:6px">
                {cl} client{"s" if int(cl)>1 else ""} พร้อมกัน</div>
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <span style="width:45px;font-size:12px;color:#00ADE8">Go</span>
                <div style="flex:1;background:#e8f4fd;border-radius:4px;height:22px">
                  {conc_bar(g_thr, max_thr, "#00ADE8") if g_thr else '<div style="padding-left:6px;font-size:11px;color:#aaa">—</div>'}
                </div>
              </div>
              <div style="display:flex;align-items:center;gap:8px">
                <span style="width:45px;font-size:12px;color:#F89820">Java</span>
                <div style="flex:1;background:#fef3e2;border-radius:4px;height:22px">
                  {conc_bar(j_thr, max_thr, "#F89820") if j_thr else '<div style="padding-left:6px;font-size:11px;color:#aaa">—</div>'}
                </div>
              </div>
            </div>"""

        concurrent_section = f"""
<div class="card">
  <h2><span class="sn">⚡</span>Concurrent Load Test — ส่งไฟล์พร้อมกันหลาย client</h2>
  <p style="margin-bottom:14px">
    วัด throughput รวม (MB/วินาที) เมื่อมีการส่งไฟล์พร้อมกันหลาย client
    ใช้ไฟล์ 1MB × 100 ไฟล์ · RSA-2048 · parallel variant ของแต่ละภาษา
  </p>
  <div class="grid2">
    <div class="chart-box">{conc_bars}</div>
    <div>
      <table>
        <thead><tr>
          <th>จำนวน client</th>
          <th>🔵 Go (MB/s)</th><th>🟠 Java (MB/s)</th><th>ผล</th>
        </tr></thead>
        <tbody>{conc_rows}</tbody>
      </table>
    </div>
  </div>
  <div class="hi" style="margin-top:14px">
    <strong>Key Insight — Concurrent:</strong><br>
    • <strong>1 client:</strong> Go 263 MB/s vs Java 207 MB/s — Go เร็วกว่า 1.3×<br>
    • <strong>8 clients พร้อมกัน:</strong> Go 163 MB/s vs Java 90 MB/s — Go เร็วกว่า <strong>1.8×</strong><br>
    • Java throughput ตกมากกว่าเมื่อ load สูงขึ้น — Go scale ได้ดีกว่าอย่างชัดเจน<br>
    • <strong>สรุป:</strong> ถ้าระบบต้องรับ request พร้อมกันเยอะ Go เป็นตัวเลือกที่ดีกว่ามาก
  </div>
</div>"""
    else:
        concurrent_section = ""

    return f"""
<div class="card">
  <h2><span class="sn">🔬</span>Full Coverage Benchmark — ครบทุก combination</h2>
  <div class="grid3" style="margin-bottom:16px">
    <div class="mbox">
      <h4>📐 Coverage</h4>
      <ul>
        <li>6 ชนิดไฟล์ × 3 key algorithms = 18 scenarios</li>
        <li>Size gradient × 3+2 key algs = 5 scenarios</li>
        <li>Many-small × RSA-2048 = 3 scenarios</li>
        <li>รวม <strong>{total_sc} scenarios</strong></li>
        <li>3 rounds × 6 variants = 468 runs</li>
      </ul>
    </div>
    <div class="mbox">
      <h4>📅 ข้อมูล</h4>
      <ul>
        <li>เริ่ม: {started}</li>
        <li>สิ้นสุด: {finished}</li>
        <li>VM: Ubuntu 24.04, 8 vCPU, <strong>14 GB RAM (อัพเกรดใหม่)</strong></li>
        <li>Corpus: RAM disk (tmpfs 4 GB)</li>
        <li>15 files × 512 KB ต่อ file-type scenario</li>
      </ul>
    </div>
    <div class="mbox">
      <h4>🏆 ผลรวม</h4>
      <div class="stats" style="margin:0">
        <div class="sbox go-b" style="padding:10px"><div class="val" style="font-size:22px">{go_wins}</div><div class="lbl">Go ชนะ (/{len(rows)})</div></div>
        <div class="sbox" style="border-color:#F89820;padding:10px"><div class="val" style="font-size:22px;color:#F89820">{java_wins}</div><div class="lbl">Java ชนะ (/{len(rows)})</div></div>
        <div class="sbox" style="padding:10px"><div class="val" style="font-size:22px;color:#6c757d">{tie_wins}</div><div class="lbl">เสมอ</div></div>
      </div>
    </div>
  </div>
</div>

<div class="card">
  <h2><span class="sn">📈</span>กราฟ Interactive</h2>
  {charts_html}
</div>

<div class="card">
  <h2><span class="sn">🗺</span>Coverage Matrix — ชนิดไฟล์ × Key Algorithm</h2>
  <p style="font-size:12px;color:#888;margin-bottom:12px">
    แต่ละช่อง = Best Go variant vs Best Java variant |
    🔵 = Go เร็วกว่า | 🟠 = Java เร็วกว่า | ⚪ = เสมอ (±5%) |
    ตัวเลข = p50 round-trip ms (ยิ่งน้อยยิ่งดี)
  </p>
  {matrix_html}
  <div class="hi" style="margin-top:14px">
    <strong>Key Insights จาก Matrix:</strong><br>
    • <strong>Binary files (.pdf, .xlsx, .gz, .dat)</strong>: Go ชนะทุก key algorithm — AES hardware path ของ Go runtime มีประสิทธิภาพสูงกว่า<br>
    • <strong>Text files (.txt, .csv)</strong>: Java ชนะหรือสูสี — JVM ZLIB path (zlib JNI) เร็วกว่า Go ZLIB สำหรับข้อมูลบีบอัดได้สูง<br>
    • <strong>Curve25519</strong>: Go ได้เปรียบมากที่สุดในทุกชนิดไฟล์ — Go crypto library ECC path เร็วกว่า Bouncy Castle มาก
  </div>
</div>

<div class="card">
  <h2><span class="sn">📐</span>Size Gradient — Compressible (.txt) ทุก Key Algorithm</h2>
  <p style="font-size:12px;color:#888;margin-bottom:12px">
    วัดเวลารวมของ corpus (1KB → 20MB ใน 1 run) — p50 round-trip ms
  </p>
  {sizegrad_html}
  <div class="info" style="margin-top:12px">
    <strong>Key Insight:</strong> Curve25519 Go เร็วที่สุดอย่างชัดเจน (เร็วกว่า RSA-2048 เพราะ ECC key exchange เร็วกว่า RSA มาก)
    ส่วน Java กับทุก key type ให้ค่าใกล้เคียงกัน — Java overhead ต่อ operation คงที่กว่า
  </div>
</div>

<div class="card">
  <h2><span class="sn">📦</span>Many-Small Files — วัด Per-File Overhead</h2>
  <p style="font-size:12px;color:#888;margin-bottom:12px">
    วัด p50 round-trip time ต่อ operation (ms) สำหรับไฟล์เล็กจำนวนมาก
  </p>
  <table>
    <thead><tr>
      <th>Scenario</th><th>🔵 Go Best</th><th>🟠 Java Best</th><th>Winner</th>
    </tr></thead>
    <tbody>{many_small_rows()}</tbody>
  </table>
  <div class="info" style="margin-top:12px">
    <strong>Key Insight:</strong> Go p50 per-file ต่ำกว่า Java ~1.2–1.7× —
    JVM overhead ต่อ PGP operation (key wrap, packet structure) สูงกว่า Go runtime
    สำคัญสำหรับ batch processing หลายพัน-หมื่นไฟล์ต่อวัน
  </div>
</div>

{concurrent_section}"""
