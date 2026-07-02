#!/usr/bin/env python3
"""build.py — entry point: python3 build.py → pgp_report.html"""
import json, pathlib, sys
from datetime import datetime

DATA = pathlib.Path(__file__).parent.parent / "report" / "results_extended.json"
OUT  = pathlib.Path(__file__).parent / "pgp_report.html"

import pages.summary  as p_summary
import pages.results  as p_results
import pages.insights as p_insights
import pages.method   as p_method


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    sc   = data["scenarios"]
    conc = data.get("concurrent", {})
    sg   = data.get("size_gradient", {})
    cg   = data.get("count_gradient", {})

    rows = _extract(sc)
    print(f"  loaded {len(rows)} scenarios | size_gradient={len(sg)} count_gradient={len(cg)}")

    tabs = [
        ("summary",  "📊 สรุปผล",          p_summary.build(data, rows, conc)),
        ("results",  "📈 ผลทดสอบ",         p_results.build(rows, conc)),
        ("insights", "🎯 Key Insights",     p_insights.build(rows, conc, sg, cg)),
        ("method",   "🔬 วิธีการทดสอบ",    p_method.build()),
    ]

    html = _assemble(data, tabs)
    OUT.write_text(html, encoding="utf-8")
    print(f"  ✅  {OUT}")


def _extract(sc: dict) -> list[dict]:
    rows = []
    for sc_id, s in sc.items():
        if not s.get("go") or not s.get("java"):
            continue
        go_best   = min(s["go"].values(),   key=lambda v: v["p50_mean"])
        java_best = min(s["java"].values(), key=lambda v: v["p50_mean"])
        gv = min(s["go"],   key=lambda k: s["go"][k]["p50_mean"])
        jv = min(s["java"], key=lambda k: s["java"][k]["p50_mean"])
        gp, jp = go_best["p50_mean"], java_best["p50_mean"]
        diff = abs(gp - jp) / ((gp + jp) / 2) * 100
        winner = "TIE" if diff <= 5 else ("GO" if gp < jp else "JAVA")
        speedup = round(max(gp, jp) / min(gp, jp), 2) if min(gp, jp) > 0 else 1
        rows.append({
            "sc_id": sc_id,
            "pub_alg": s.get("pub_alg", "RSA-2048"),
            "corpus": s.get("corpus", ""),
            "go_variant": gv, "java_variant": jv,
            "go_p50": round(gp, 3), "java_p50": round(jp, 3),
            "go_thr":   go_best.get("throughput_mean_mbs"),
            "java_thr": java_best.get("throughput_mean_mbs"),
            "winner": winner, "speedup": speedup, "diff_pct": round(diff, 1),
        })
    return rows


def _assemble(data: dict, tabs: list) -> str:
    started  = data.get("startedAt", "")[:19].replace("T", " ")
    finished = data.get("finishedAt", "")[:19].replace("T", " ")

    tabs_html = "".join(
        f'<button class="tab{" active" if i == 0 else ""}" '
        f'onclick="showTab(\'{pid}\')" id="tab-{pid}">{label}</button>'
        for i, (pid, label, _) in enumerate(tabs)
    )
    pages_html = "".join(
        f'<div class="page{" active" if i == 0 else ""}" id="page-{pid}">{content}</div>'
        for i, (pid, _, content) in enumerate(tabs)
    )

    return f"""<!DOCTYPE html><html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>POC Report — PGP Benchmark: Go vs Java (v5 cold start)</title>
{_css()}
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>📊 รายงาน POC: เปรียบเทียบประสิทธิภาพการเข้ารหัส PGP</h1>
    <div class="sub">Go (ProtonMail/go-crypto) vs Java (Bouncy Castle)
      — Ubuntu 24.04 · 8 vCPU · 14 GB RAM · <strong>Cold Start (post-reboot)</strong></div>
    <div class="meta">
      <span>📅 {started}</span>
      <span>✅ {finished}</span>
      <span>🔒 AES-256 + ZLIB</span>
      <span>🧪 21 scenarios + size/count gradient</span>
      <span>🔄 3 rounds · warmup=1</span>
    </div>
  </div>
  <div class="tabs">{tabs_html}</div>
  {pages_html}
  <footer>สร้างอัตโนมัติ {datetime.now().strftime("%Y-%m-%d %H:%M")} · v5 cold start</footer>
</div>
<script>
function showTab(id){{
  document.querySelectorAll('.tab,.page').forEach(e=>e.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('page-'+id).classList.add('active');
}}
</script>
</body></html>"""


def _css() -> str:
    return """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#2c3e50;font-size:14px}
.wrap{max-width:1200px;margin:0 auto;padding:20px}
.hdr{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;padding:32px;
  border-radius:12px;margin-bottom:20px}
.hdr h1{font-size:22px;font-weight:800;margin-bottom:6px}
.hdr .sub{font-size:13px;opacity:.8;margin-bottom:10px}
.hdr .meta{font-size:11px;opacity:.6;display:flex;gap:18px;flex-wrap:wrap}
.tabs{display:flex;gap:6px;margin-bottom:0;flex-wrap:wrap}
.tab{padding:9px 18px;border-radius:8px 8px 0 0;cursor:pointer;font-weight:600;
  font-size:13px;border:none;background:#dde1e7;color:#555;transition:.15s}
.tab.active{background:#fff;color:#0f3460}
.tab:hover{background:#e8eaed}
.page{display:none;background:#fff;border-radius:0 12px 12px 12px;padding:24px;
  margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,.08)}
.page.active{display:block}
.card{background:#f8f9fa;border-radius:10px;padding:20px;margin-bottom:16px;border:1px solid #e9ecef}
h2{font-size:17px;font-weight:700;color:#1a1a2e;border-left:4px solid #00ADE8;padding-left:10px;margin-bottom:14px}
h3{font-size:14px;font-weight:700;color:#2c3e50;margin:14px 0 8px}
p,li{line-height:1.8;color:#444}
ul{padding-left:20px}
.verdict{background:linear-gradient(135deg,#00ADE8,#0078a8);color:#fff;
  padding:20px;border-radius:10px;text-align:center;margin-bottom:16px}
.verdict .big{font-size:32px;font-weight:900}
.verdict .sub{font-size:13px;opacity:.9;margin-top:4px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.sbox{background:#fff;border-radius:10px;padding:14px;text-align:center;border:2px solid #e9ecef}
.sbox .val{font-size:26px;font-weight:800}
.sbox .lbl{font-size:11px;color:#6c757d;margin-top:2px}
.go-c{border-color:#00ADE8;color:#00ADE8}
.java-c{border-color:#F89820;color:#F89820}
.green-c{border-color:#27ae60;color:#27ae60}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#1a1a2e;color:#fff;padding:9px 8px;text-align:left;font-weight:600}
td{padding:8px;border-bottom:1px solid #e9ecef;vertical-align:middle}
tr:hover td{background:#f5f7fa}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700}
.bg{background:#cce9f6;color:#0078a8}
.bj{background:#fde9c8;color:#b96800}
.bt{background:#e9ecef;color:#6c757d}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.mbox{background:#fff;border-radius:10px;padding:16px;border-left:4px solid #00ADE8}
.mbox.go{border-left-color:#00ADE8}
.mbox.java{border-left-color:#F89820}
.mbox.green{border-left-color:#27ae60}
.mbox.red{border-left-color:#e74c3c}
.hi{background:#fff3cd;border-left:4px solid #ffc107;padding:10px 14px;
  border-radius:0 8px 8px 0;margin:10px 0;font-size:13px}
.info{background:#d1ecf1;border-left:4px solid #17a2b8;padding:10px 14px;
  border-radius:0 8px 8px 0;margin:10px 0;font-size:13px}
.bar-row{margin-bottom:12px}
.bar-lbl{font-size:12px;font-weight:700;color:#2c3e50;margin-bottom:4px}
.bar-wrap{display:flex;align-items:center;gap:7px;margin-bottom:3px}
.bar-name{width:40px;font-size:11px;font-weight:700}
.bar-bg{flex:1;border-radius:4px;height:24px}
.bar-fill{height:100%;border-radius:4px;display:flex;align-items:center;padding-left:7px;min-width:40px}
.bar-fill span{font-size:11px;color:#fff;font-weight:700;white-space:nowrap}
.bar-note{text-align:right;font-size:11px;font-weight:700;margin-top:2px}
footer{text-align:center;padding:16px;color:#aaa;font-size:11px}
@media(max-width:720px){.grid2,.grid3{grid-template-columns:1fr}}
</style>"""


if __name__ == "__main__":
    main()
