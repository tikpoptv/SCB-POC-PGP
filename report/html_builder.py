"""html_builder.py — CSS, shared JS, และ build() ที่ประกอบทุก page เข้าด้วยกัน"""
from datetime import datetime
import page_summary
import page_methodology
import page_testdata
import page_tests
import page_integrity


# ─────────────────────────────────────────────────────────────────────────────
CSS = """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:#f0f2f5;color:#2c3e50;font-size:14px}
.wrap{max-width:1280px;margin:0 auto;padding:20px}
/* HEADER */
.hdr{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;padding:36px;
  border-radius:12px;margin-bottom:20px;box-shadow:0 8px 32px rgba(0,0,0,.3)}
.hdr h1{font-size:24px;font-weight:800;margin-bottom:6px}
.hdr .sub{font-size:13px;opacity:.8;margin-bottom:14px}
.hdr .meta{font-size:11px;opacity:.6;display:flex;gap:20px;flex-wrap:wrap}
/* TABS */
.tabs{display:flex;gap:6px;margin-bottom:0;flex-wrap:wrap}
.tab{padding:10px 20px;border-radius:8px 8px 0 0;cursor:pointer;font-weight:600;
  font-size:13px;border:none;background:#dde1e7;color:#555;transition:.2s}
.tab.active{background:#fff;color:#0f3460;box-shadow:0 -2px 8px rgba(0,0,0,.08)}
.tab:hover{background:#e8eaed}
/* PAGE */
.page{display:none;background:#fff;border-radius:0 12px 12px 12px;padding:28px;
  box-shadow:0 2px 12px rgba(0,0,0,.08);margin-bottom:20px}
.page.active{display:block}
/* CARD inside page */
.card{background:#f8f9fa;border-radius:10px;padding:22px;margin-bottom:18px;
  border:1px solid #e9ecef}
h2{font-size:18px;font-weight:700;color:#1a1a2e;border-left:4px solid #00ADE8;
  padding-left:12px;margin-bottom:16px}
h3{font-size:15px;font-weight:600;color:#2c3e50;margin:16px 0 8px}
h4{font-size:13px;font-weight:700;color:#1a1a2e;margin-bottom:8px}
p,li{line-height:1.8;color:#444}
ul{padding-left:20px}
/* VERDICT */
.verdict{background:linear-gradient(135deg,#00ADE8,#0078a8);color:#fff;
  padding:22px;border-radius:10px;text-align:center;margin-bottom:18px}
.verdict .big{font-size:36px;font-weight:900}
.verdict .vsub{font-size:14px;opacity:.9;margin-top:4px}
/* STATS GRID */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:18px}
.sbox{background:#fff;border-radius:10px;padding:16px;text-align:center;
  border:2px solid #e9ecef;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.sbox .val{font-size:28px;font-weight:800}
.sbox .lbl{font-size:11px;color:#6c757d;margin-top:3px}
.go-b{border-color:#00ADE8}.go-b .val{color:#00ADE8}
.java-b{border-color:#F89820}.java-b .val{color:#F89820}
.green-b{border-color:#27ae60}.green-b .val{color:#27ae60}
/* TABLE */
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#1a1a2e;color:#fff;padding:10px 9px;text-align:left;font-weight:600}
td{padding:9px;border-bottom:1px solid #e9ecef;vertical-align:middle}
tr:hover td{background:#f0f4f8}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700}
.bg{background:#cce9f6;color:#0078a8}
.bj{background:#fde9c8;color:#b96800}
.bt{background:#e9ecef;color:#6c757d}
.sg{color:#00ADE8;font-weight:700}
.sj{color:#F89820;font-weight:700}
/* GRID 2/3/4 cols */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
/* METHOD BOX */
.mbox{background:#fff;border-radius:10px;padding:18px;border-left:4px solid #00ADE8;
  box-shadow:0 1px 4px rgba(0,0,0,.06)}
.mbox.green{border-left-color:#27ae60}
.mbox.orange{border-left-color:#F89820}
.mbox.purple{border-left-color:#9b59b6}
.mbox.red{border-left-color:#e74c3c}
/* TIMELINE */
.timeline{list-style:none;padding-left:0}
.timeline li{position:relative;padding:12px 12px 12px 44px;margin-bottom:10px;
  background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.timeline li::before{content:attr(data-n);position:absolute;left:10px;top:12px;
  background:#00ADE8;color:#fff;width:24px;height:24px;border-radius:50%;
  text-align:center;line-height:24px;font-weight:700;font-size:12px}
.tl-title{font-weight:700;font-size:13px;color:#1a1a2e;margin-bottom:3px}
/* CODE BLOCK */
.code{background:#1a1a2e;color:#e8eaed;padding:16px;border-radius:8px;
  font-family:monospace;font-size:12px;line-height:1.7;overflow-x:auto;margin:10px 0}
.code .c{color:#6a9fb5}.code .k{color:#cc99cd}.code .s{color:#7ec699}
/* HIGHLIGHT */
.hi{background:#fff3cd;border-left:4px solid #ffc107;padding:12px 16px;
  border-radius:0 8px 8px 0;margin:12px 0;font-size:13px}
.info{background:#d1ecf1;border-left:4px solid #17a2b8;padding:12px 16px;
  border-radius:0 8px 8px 0;margin:12px 0;font-size:13px}
/* CHART */
.chart-box{background:#fff;border-radius:10px;padding:16px;
  box-shadow:0 1px 4px rgba(0,0,0,.06)}
.chart-title{font-size:13px;font-weight:700;color:#1a1a2e;margin-bottom:8px}
.chart-sub{font-size:11px;font-weight:400;color:#888;margin-top:2px}
/* SECTION NUM */
.sn{display:inline-block;background:#00ADE8;color:#fff;width:24px;height:24px;
  border-radius:50%;text-align:center;line-height:24px;font-weight:700;
  font-size:12px;margin-right:8px;flex-shrink:0}
footer{text-align:center;padding:20px;color:#aaa;font-size:11px}
@media(max-width:768px){.grid2,.grid3{grid-template-columns:1fr}}
</style>"""

# ─────────────────────────────────────────────────────────────────────────────
TAB_JS = """<script>
function showTab(id){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('page-'+id).classList.add('active');
}
</script>"""


# ─────────────────────────────────────────────────────────────────────────────
def build(data: dict, rows: list, chart_html: str, out_path: str):
    started  = data.get("startedAt", "—")[:19].replace("T", " ")
    finished = data.get("finishedAt", "—")[:19].replace("T", " ")

    pages = [
        ("summary",   "📊 สรุปผล",              page_summary.build(data, rows)),
        ("charts",    "📈 กราฟ",                 f'<div class="card"><h2><span class="sn">📈</span>กราฟเปรียบเทียบ (Interactive)</h2>{chart_html}</div>'),
        ("method",    "🔬 วิธีการทดสอบ",        page_methodology.build()),
        ("testdata",  "📁 ข้อมูลและ Variants",   page_testdata.build()),
        ("tests",     "🧪 721 Tests",             page_tests.build()),
        ("integrity", "🛡 ความน่าเชื่อถือ",     page_integrity.build()),
    ]

    tabs_html = "".join(
        f'<button class="tab{" active" if i == 0 else ""}" id="tab-{pid}" onclick="showTab(\'{pid}\')">{label}</button>'
        for i, (pid, label, _) in enumerate(pages)
    )
    pages_html = "".join(
        f'<div class="page{" active" if i == 0 else ""}" id="page-{pid}">{content}</div>'
        for i, (pid, _, content) in enumerate(pages)
    )

    html = f"""<!DOCTYPE html><html lang="th">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>POC Report — PGP Benchmark: Go vs Java</title>
{CSS}
</head>
<body>
<div class="wrap">

<div class="hdr">
  <h1>📊 รายงาน POC: เปรียบเทียบประสิทธิภาพการเข้ารหัส PGP</h1>
  <div class="sub">Go (ProtonMail/go-crypto) เทียบกับ Java (Spring Boot + Bouncy Castle)
    — ผลการทดสอบจริงบน VM Ubuntu 24.04 LTS, 8 vCPU, 8 GB RAM</div>
  <div class="meta">
    <span>📅 เริ่มทดสอบ: {started}</span>
    <span>✅ สิ้นสุด: {finished}</span>
    <span>🖥 VM: Ubuntu 24.04, 8 vCPU, 8 GB RAM</span>
    <span>🔒 AES-256 + ZLIB + SHA-256</span>
    <span>🧪 721 tests ผ่านทั้งหมด</span>
  </div>
</div>

<div class="tabs">{tabs_html}</div>
{pages_html}

<footer>รายงานสร้างโดยอัตโนมัติ | POC: PGP Benchmark Go vs Java | {datetime.now().strftime("%Y-%m-%d %H:%M")}</footer>
</div>
{TAB_JS}
</body></html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✓ HTML → {out_path}")
