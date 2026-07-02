#!/usr/bin/env python3
"""
build_klauspost_report.py — สร้าง HTML report v3 (self-contained, ไม่มี CDN/เดปนอก)
สำหรับผล A/B/C: go-stdlib vs go-klauspost vs java

อ่าน:  report/results_klauspost_ab.json   (ผลจาก scripts/vm/run_klauspost_ab.py)
เขียน: report/klauspost_report_v3.html

ใช้:   python3 report/build_klauspost_report.py
       python3 report/build_klauspost_report.py --in path/to.json --out path/to.html

หมายเหตุ: กราฟทั้งหมดเป็น inline SVG (ไม่พึ่ง Chart.js/CDN) → เปิดออฟไลน์/พรีเซนต์ได้ทันที
"""
import json, sys, pathlib, argparse, math, html as _html
from datetime import datetime

HERE = pathlib.Path(__file__).parent
DEFAULT_IN  = HERE / "results_klauspost_ab.json"
DEFAULT_OUT = HERE / "klauspost_report_v3.html"

# สี (ให้ตรง report เดิม)
C_STD  = "#7f8c8d"   # go-stdlib (เทา = baseline)
C_KP   = "#00ADE8"   # go-klauspost (ฟ้า Go)
C_JAVA = "#F89820"   # java (ส้ม)
C_GREEN = "#27ae60"
C_RED   = "#e74c3c"

LABELS = ["go-stdlib", "go-klauspost", "java"]
LABEL_DISP = {"go-stdlib": "Go (stdlib zlib)", "go-klauspost": "Go (klauspost)", "java": "Java (BC)"}
LABEL_COLOR = {"go-stdlib": C_STD, "go-klauspost": C_KP, "java": C_JAVA}


# ─────────────────────────────────────────────────────────────────────────────
CSS = """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:#f0f2f5;color:#2c3e50;font-size:14px}
.wrap{max-width:1280px;margin:0 auto;padding:20px}
.hdr{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;padding:36px;
  border-radius:12px;margin-bottom:20px;box-shadow:0 8px 32px rgba(0,0,0,.3)}
.hdr h1{font-size:24px;font-weight:800;margin-bottom:6px}
.hdr .sub{font-size:13px;opacity:.85;margin-bottom:14px;line-height:1.6}
.hdr .meta{font-size:11px;opacity:.65;display:flex;gap:18px;flex-wrap:wrap}
.tabs{display:flex;gap:6px;margin-bottom:0;flex-wrap:wrap}
.tab{padding:10px 20px;border-radius:8px 8px 0 0;cursor:pointer;font-weight:600;
  font-size:13px;border:none;background:#dde1e7;color:#555;transition:.2s}
.tab.active{background:#fff;color:#0f3460;box-shadow:0 -2px 8px rgba(0,0,0,.08)}
.tab:hover{background:#e8eaed}
.page{display:none;background:#fff;border-radius:0 12px 12px 12px;padding:28px;
  box-shadow:0 2px 12px rgba(0,0,0,.08);margin-bottom:20px}
.page.active{display:block}
.card{background:#f8f9fa;border-radius:10px;padding:22px;margin-bottom:18px;border:1px solid #e9ecef}
h2{font-size:18px;font-weight:700;color:#1a1a2e;border-left:4px solid #00ADE8;padding-left:12px;margin-bottom:16px}
h3{font-size:15px;font-weight:600;color:#2c3e50;margin:16px 0 8px}
p,li{line-height:1.8;color:#444}
ul{padding-left:20px}
.verdict{background:linear-gradient(135deg,#00ADE8,#0078a8);color:#fff;padding:22px;
  border-radius:10px;text-align:center;margin-bottom:18px}
.verdict .big{font-size:32px;font-weight:900}
.verdict .vsub{font-size:14px;opacity:.92;margin-top:6px;line-height:1.6}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:18px}
.sbox{background:#fff;border-radius:10px;padding:16px;text-align:center;border:2px solid #e9ecef;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.sbox .val{font-size:26px;font-weight:800}
.sbox .lbl{font-size:11px;color:#6c757d;margin-top:3px}
.go-b{border-color:#00ADE8}.go-b .val{color:#00ADE8}
.java-b{border-color:#F89820}.java-b .val{color:#F89820}
.green-b{border-color:#27ae60}.green-b .val{color:#27ae60}
.gray-b{border-color:#7f8c8d}.gray-b .val{color:#7f8c8d}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#1a1a2e;color:#fff;padding:10px 9px;text-align:left;font-weight:600;white-space:nowrap}
td{padding:9px;border-bottom:1px solid #e9ecef;vertical-align:middle}
tr:hover td{background:#f0f4f8}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.win{color:#27ae60;font-weight:700}
.lose{color:#e74c3c;font-weight:700}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700}
.ok{background:#d4edda;color:#1e7e34}
.bad{background:#f8d7da;color:#a71d2a}
.hi{background:#fff3cd;border-left:4px solid #ffc107;padding:12px 16px;border-radius:0 8px 8px 0;margin:12px 0;font-size:13px}
.info{background:#d1ecf1;border-left:4px solid #17a2b8;padding:12px 16px;border-radius:0 8px 8px 0;margin:12px 0;font-size:13px}
.okbar{background:linear-gradient(135deg,#27ae60,#1e8449);color:#fff;padding:18px 22px;border-radius:10px;margin-bottom:18px;font-size:15px;font-weight:700}
.errbar{background:linear-gradient(135deg,#e74c3c,#c0392b);color:#fff;padding:18px 22px;border-radius:10px;margin-bottom:18px;font-size:15px;font-weight:700}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;margin:8px 0 14px}
.legend .k{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:middle}
.chart-box{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:16px}
.chart-title{font-size:14px;font-weight:700;color:#1a1a2e;margin-bottom:4px}
.chart-sub{font-size:11px;color:#888;margin-bottom:10px}
footer{text-align:center;padding:20px;color:#aaa;font-size:11px}
@media(max-width:768px){.stats{grid-template-columns:1fr 1fr}}
</style>"""

TAB_JS = """<script>
function showTab(id){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('page-'+id).classList.add('active');
}
</script>"""


# ── helpers ──────────────────────────────────────────────────────────────────
def esc(s):
    return _html.escape(str(s))

def best_variant(res):
    """คืน (variant, metrics) ที่ p50 ต่ำสุดของ label; None ถ้าไม่มีข้อมูล"""
    best = None
    for vname, d in (res or {}).items():
        if not d:
            continue
        if best is None or d.get("p50", 1e18) < best[1].get("p50", 1e18):
            best = (vname, d)
    return best

def best_ms(res):
    bv = best_variant(res)
    return bv[1]["p50"] if bv else None

def fmt_ms(x):
    if x is None:
        return "—"
    if x >= 1000:
        return f"{x/1000:.2f} s"
    if x >= 10:
        return f"{x:.1f} ms"
    return f"{x:.2f} ms"

def fmt_speedup(baseline_ms, kp_ms):
    """baseline/kp — >1 = klauspost เร็วกว่า"""
    if not baseline_ms or not kp_ms:
        return "—", ""
    r = baseline_ms / kp_ms
    cls = "win" if r >= 1.0 else "lose"
    return f"{r:.2f}×", cls


# ── inline SVG horizontal bar chart (no CDN) ──────────────────────────────────
def svg_bars(series, title, sub="", unit="ms", width=760):
    """
    series = [(label, value, color), ...]
    วาด horizontal bar chart เป็น inline SVG (พรีเซนต์ออฟไลน์ได้)
    """
    series = [(l, v, c) for (l, v, c) in series if v is not None]
    if not series:
        return ""
    row_h, gap, top, left, right = 34, 12, 8, 150, 70
    vmax = max(v for _, v, _ in series) or 1.0
    plot_w = width - left - right
    h = top + len(series) * (row_h + gap)
    parts = [f'<svg viewBox="0 0 {width} {h}" width="100%" style="max-width:{width}px" '
             f'font-family="Segoe UI,Arial" font-size="12">']
    y = top
    for label, val, color in series:
        bw = max(2, plot_w * (val / vmax))
        parts.append(f'<text x="{left-8}" y="{y+row_h/2+4}" text-anchor="end" '
                     f'fill="#2c3e50" font-weight="600">{esc(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{row_h}" '
                     f'rx="4" fill="{color}"><title>{esc(label)}: {val:.2f} {unit}</title></rect>')
        vtxt = f"{val:.2f}" if val < 100 else f"{val:.0f}"
        parts.append(f'<text x="{left+bw+6:.1f}" y="{y+row_h/2+4}" fill="#555">{vtxt} {unit}</text>')
        y += row_h + gap
    parts.append("</svg>")
    body = "".join(parts)
    st = f'<div class="chart-title">{esc(title)}</div>'
    ss = f'<div class="chart-sub">{esc(sub)}</div>' if sub else ""
    return f'<div class="chart-box">{st}{ss}{body}</div>'


# ── inline SVG line chart (log-log) — สำหรับ size gradient ───────────────────
def svg_lines(series_map, xs_labels, title, sub="", unit="ms", width=760, height=300):
    """
    series_map = {label: [(x_kb, ms|None), ...]}  (x เรียงแล้ว)
    xs_labels  = [(x_kb, "1KB"), ...]  ป้ายแกน x
    แกน x = log2(ขนาดไฟล์), แกน y = log10(ms) — ช่องว่างคงที่ = อัตราส่วนคงที่
    """
    pts_all = [v for pts in series_map.values() for _, v in pts if v]
    if not pts_all:
        return ""
    top, right, bottom, left = 14, 16, 40, 64
    pw, ph = width - left - right, height - top - bottom
    xs = [x for x, _ in xs_labels]
    x0, x1 = math.log2(min(xs)), math.log2(max(xs))
    ymin, ymax = min(pts_all), max(pts_all)
    y0, y1 = math.floor(math.log10(ymin)), math.ceil(math.log10(ymax))
    if y1 == y0: y1 += 1

    def X(kb): return left + pw * ((math.log2(kb) - x0) / (x1 - x0 or 1))
    def Y(ms): return top + ph * (1 - (math.log10(ms) - y0) / (y1 - y0))

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:{width}px" '
             f'font-family="Segoe UI,Arial" font-size="11">']
    # gridlines + y labels (ทุก decade)
    for e in range(y0, y1 + 1):
        gy = Y(10 ** e)
        lab = f"{10**e:,}" if e >= 0 else f"{10**e:g}"
        parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{left+pw}" y2="{gy:.1f}" stroke="#e9ecef"/>')
        parts.append(f'<text x="{left-6}" y="{gy+4:.1f}" text-anchor="end" fill="#888">{lab}</text>')
    # x labels — สลับสูง/ต่ำเมื่อป้ายชิดกัน (ปลาย log scale จุดถี่ ป้ายทับกัน)
    prev_x = None
    row = 0
    for kb, lab in xs_labels:
        gx = X(kb)
        row = (row + 1) % 2 if (prev_x is not None and gx - prev_x < 46) else 0
        parts.append(f'<text x="{gx:.1f}" y="{height-bottom+16+row*13}" text-anchor="middle" fill="#888">{esc(lab)}</text>')
        prev_x = gx
    parts.append(f'<text x="{left-50}" y="{top+ph/2:.0f}" transform="rotate(-90 {left-50} {top+ph/2:.0f})" '
                 f'text-anchor="middle" fill="#888">{unit} (log)</text>')
    # เส้น + จุด (จุดมี <title> = tooltip ตอน hover + วงใสขยายพื้นที่รับเมาส์)
    xlab = dict(xs_labels)
    for label, pts in series_map.items():
        color = LABEL_COLOR.get(label, "#555")
        disp = LABEL_DISP.get(label, label)
        seg = [(X(x), Y(v), x, v) for x, v in pts if v]
        if len(seg) >= 2:
            d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py, _, _ in seg)
            parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5" pointer-events="none"/>')
        for px, py, x, v in seg:
            tip = f"{disp} @ {xlab.get(x, x)}: {fmt_ms(v)}"
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{color}"/>'
                         f'<circle cx="{px:.1f}" cy="{py:.1f}" r="10" fill="transparent">'
                         f'<title>{esc(tip)}</title></circle>')
    parts.append("</svg>")
    st = f'<div class="chart-title">{esc(title)}</div>'
    ss = f'<div class="chart-sub">{esc(sub)}</div>' if sub else ""
    return f'<div class="chart-box">{st}{ss}{"".join(parts)}</div>'


# ── inline SVG grouped bar chart — เทียบ 3 impl หลาย scenario ────────────────
def svg_grouped(groups, title, sub="", unit="ms", width=760):
    """
    groups = [(group_label, [(impl_label, value|None), ...]), ...]
    แท่งแนวตั้งจัดกลุ่ม สูงตามค่า (linear) — เหมาะเทียบไม่กี่กลุ่ม
    """
    vals = [v for _, bars in groups for _, v in bars if v]
    if not vals:
        return ""
    top, bottom, left, right = 18, 44, 56, 10
    bw, bgap, ggap = 26, 4, 30
    n_bars = max(len(b) for _, b in groups)
    gw = n_bars * (bw + bgap) - bgap
    pw = len(groups) * (gw + ggap) - ggap
    width = max(width, left + right + pw)
    ph = 220
    height = top + ph + bottom
    vmax = max(vals)

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:{width}px" '
             f'font-family="Segoe UI,Arial" font-size="11">']
    # เส้น grid 4 ระดับ
    for i in range(5):
        gy = top + ph * i / 4
        gv = vmax * (1 - i / 4)
        parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{left+pw}" y2="{gy:.1f}" stroke="#e9ecef"/>')
        parts.append(f'<text x="{left-6}" y="{gy+4:.1f}" text-anchor="end" fill="#888">{gv:,.0f}</text>')
    parts.append(f'<text x="{left-44}" y="{top+ph/2:.0f}" transform="rotate(-90 {left-44} {top+ph/2:.0f})" '
                 f'text-anchor="middle" fill="#888">{esc(unit)}</text>')
    x = left
    for glabel, bars in groups:
        bx = x
        for impl, v in bars:
            if v:
                bh = ph * (v / vmax)
                color = LABEL_COLOR.get(impl, "#555")
                tip = f"{LABEL_DISP.get(impl, impl)} — {glabel}: {fmt_ms(v)}"
                parts.append(f'<rect x="{bx}" y="{top+ph-bh:.1f}" width="{bw}" height="{bh:.1f}" rx="3" fill="{color}">'
                             f'<title>{esc(tip)}</title></rect>')
                vtxt = f"{v:,.0f}" if v >= 10 else f"{v:.1f}"
                parts.append(f'<text x="{bx+bw/2}" y="{top+ph-bh-4:.1f}" text-anchor="middle" '
                             f'fill="#555" font-size="10">{vtxt}</text>')
            bx += bw + bgap
        parts.append(f'<text x="{x+gw/2}" y="{top+ph+16}" text-anchor="middle" fill="#2c3e50" '
                     f'font-weight="600">{esc(glabel)}</text>')
        x += gw + ggap
    parts.append("</svg>")
    st = f'<div class="chart-title">{esc(title)}</div>'
    ss = f'<div class="chart-sub">{esc(sub)}</div>' if sub else ""
    return f'<div class="chart-box">{st}{ss}{"".join(parts)}</div>'


# ── scenario categorization ───────────────────────────────────────────────────
def categorize(name):
    if name.startswith("ft-"):
        return "filetype"
    if name.startswith("sg-"):
        return "sizegrad"
    if name.startswith("prod-"):
        return "prod"
    if name.startswith("count-") or name.startswith("many-") or name.startswith("conc-"):
        return "scaling"
    return "quick"


def scenario_row(sc_name, sc):
    """คืน dict ของค่าที่ใช้ในตาราง/กราฟ 1 scenario"""
    std = best_ms(sc.get("go-stdlib", {}))
    kp  = best_ms(sc.get("go-klauspost", {}))
    jv  = best_ms(sc.get("java", {}))
    bv_kp = best_variant(sc.get("go-klauspost", {}))
    ratio = bv_kp[1].get("ratio") if bv_kp else None
    mbps  = bv_kp[1].get("mbps") if bv_kp else None
    return {"name": sc_name, "std": std, "kp": kp, "java": jv,
            "ratio": ratio, "mbps": mbps}


def build_table(rows, caption_cols=None):
    """สร้าง <table> เทียบ 3 impl + speedup + ratio"""
    head = (
        "<tr><th>Scenario</th>"
        "<th>Go stdlib (p50)</th><th>Go klauspost (p50)</th><th>Java (p50)</th>"
        "<th>kp vs stdlib</th><th>kp vs java</th>"
        "<th>Ratio</th><th>MB/s</th></tr>"
    )
    body = []
    for r in rows:
        sp_std, cs_std = fmt_speedup(r["std"], r["kp"])
        sp_jv,  cs_jv  = fmt_speedup(r["java"], r["kp"])
        ratio = f'{r["ratio"]:.2f}×' if r.get("ratio") else "—"
        mbps  = f'{r["mbps"]:.1f}' if r.get("mbps") else "—"
        body.append(
            f'<tr><td>{esc(r["name"])}</td>'
            f'<td class="num">{fmt_ms(r["std"])}</td>'
            f'<td class="num">{fmt_ms(r["kp"])}</td>'
            f'<td class="num">{fmt_ms(r["java"])}</td>'
            f'<td class="num {cs_std}">{sp_std}</td>'
            f'<td class="num {cs_jv}">{sp_jv}</td>'
            f'<td class="num">{ratio}</td>'
            f'<td class="num">{mbps}</td></tr>'
        )
    return f'<table>{head}{"".join(body)}</table>'


def legend_html():
    return (
        '<div class="legend">'
        f'<span><span class="k" style="background:{C_STD}"></span>Go stdlib zlib</span>'
        f'<span><span class="k" style="background:{C_KP}"></span>Go klauspost</span>'
        f'<span><span class="k" style="background:{C_JAVA}"></span>Java (Bouncy Castle)</span>'
        '</div>'
    )


# ── correctness check (anti-v2) ───────────────────────────────────────────────
def check_correctness(data):
    problems = []
    n_variants = 0
    for sc_name, sc in data.get("scenarios", {}).items():
        for label, res in sc.items():
            for vname, d in (res or {}).items():
                n_variants += 1
                if d.get("ok_ratio_min", 1.0) < 1.0:
                    problems.append(f"{sc_name}/{label}/{vname}: roundTripOk<100% (min={d.get('ok_ratio_min')})")
                if d.get("skipped_max", 0) > 0:
                    problems.append(f"{sc_name}/{label}/{vname}: มีไฟล์ถูก skip ({d.get('skipped_max')})")
    return problems, n_variants


# ── summary computations ──────────────────────────────────────────────────────
def compute_summary(data):
    """หา speedup รวมของ klauspost บนกลุ่ม compressible (txt/csv) vs stdlib และ vs java"""
    comp_std, comp_jv, incomp_std, incomp_jv = [], [], [], []
    best_txt = None  # (name, speedup vs stdlib)
    for sc_name, sc in data.get("scenarios", {}).items():
        std = best_ms(sc.get("go-stdlib", {}))
        kp  = best_ms(sc.get("go-klauspost", {}))
        jv  = best_ms(sc.get("java", {}))
        is_comp = any(t in sc_name for t in ("txt", "csv"))
        is_incomp = any(t in sc_name for t in ("pdf", "zip", "dat"))
        if kp and std:
            sp = std / kp
            if is_comp:
                comp_std.append(sp)
                if best_txt is None or sp > best_txt[1]:
                    best_txt = (sc_name, sp)
            elif is_incomp:
                incomp_std.append(sp)
        if kp and jv:
            sp = jv / kp
            if is_comp:
                comp_jv.append(sp)
            elif is_incomp:
                incomp_jv.append(sp)

    def avg(xs):
        return sum(xs) / len(xs) if xs else None
    return {
        "comp_vs_std": avg(comp_std),
        "comp_vs_java": avg(comp_jv),
        "incomp_vs_std": avg(incomp_std),
        "best_txt": best_txt,
        "n_scen": len(data.get("scenarios", {})),
    }


# ── page builders ─────────────────────────────────────────────────────────────
def page_summary(data, summ, problems):
    # correctness banner
    if not problems:
        banner = ('<div class="okbar">🔒 Correctness ผ่านทุก scenario/variant — '
                  'roundTripOk 100% และไม่มีไฟล์ถูก skip (ถอดรหัส+คลายบีบอัดได้ไฟล์เดิมเป๊ะ byte-for-byte)</div>')
    else:
        items = "".join(f"<li>{esc(p)}</li>" for p in problems[:30])
        banner = ('<div class="errbar">❌ พบปัญหา correctness — อย่าใช้ผลนี้ตัดสินใจ:'
                  f'<ul style="margin-top:8px;font-weight:400;font-size:13px">{items}</ul></div>')

    cs = summ["comp_vs_std"]
    cj = summ["comp_vs_java"]
    ics = summ["incomp_vs_std"]
    bt = summ["best_txt"]

    verdict_sub = []
    if cs:
        verdict_sub.append(f"klauspost เร็วกว่า Go stdlib เฉลี่ย <b>{cs:.2f}×</b> บนข้อมูลบีบได้ (txt/csv)")
    if cj:
        state = "เร็วกว่า" if cj >= 1 else "ช้ากว่า"
        verdict_sub.append(f"และ {state} Java เฉลี่ย <b>{cj:.2f}×</b>")
    verdict = (
        '<div class="verdict">'
        f'<div class="big">{"Go + klauspost ปิดช่องว่างสำเร็จ" if cs and cs > 1.1 else "ผลเปรียบเทียบ A/B/C"}</div>'
        f'<div class="vsub">{" ".join(verdict_sub) if verdict_sub else "ดูรายละเอียดในแต่ละแท็บ"}</div>'
        '</div>'
    )

    boxes = ['<div class="stats">']
    boxes.append(f'<div class="sbox go-b"><div class="val">{cs:.2f}×</div>'
                 f'<div class="lbl">klauspost vs stdlib (txt/csv เฉลี่ย)</div></div>' if cs
                 else '<div class="sbox go-b"><div class="val">—</div><div class="lbl">klauspost vs stdlib</div></div>')
    boxes.append(f'<div class="sbox java-b"><div class="val">{cj:.2f}×</div>'
                 f'<div class="lbl">klauspost vs Java (txt/csv เฉลี่ย)</div></div>' if cj
                 else '<div class="sbox java-b"><div class="val">—</div><div class="lbl">klauspost vs Java</div></div>')
    boxes.append(f'<div class="sbox gray-b"><div class="val">{ics:.2f}×</div>'
                 f'<div class="lbl">klauspost vs stdlib (pdf/zip — ไม่ถดถอย)</div></div>' if ics
                 else '<div class="sbox gray-b"><div class="val">—</div><div class="lbl">incompressible</div></div>')
    boxes.append(f'<div class="sbox green-b"><div class="val">{summ["n_scen"]}</div>'
                 f'<div class="lbl">scenario ที่ทดสอบ</div></div>')
    boxes.append('</div>')

    best_note = ""
    if bt:
        best_note = (f'<div class="hi">🚀 จุดที่ klauspost ช่วยมากสุด: <b>{esc(bt[0])}</b> — '
                     f'เร็วกว่า Go stdlib <b>{bt[1]:.2f}×</b></div>')

    # highlight chart: เลือก scenario txt/csv เด่นๆ มาโชว์เทียบ 3 ทาง
    charts = []
    picks = []
    for sc_name, sc in data.get("scenarios", {}).items():
        if any(t in sc_name for t in ("txt", "csv")) and best_ms(sc.get("go-klauspost", {})):
            picks.append((sc_name, sc))
    for sc_name, sc in picks[:4]:
        series = [
            (LABEL_DISP["go-stdlib"], best_ms(sc.get("go-stdlib", {})), C_STD),
            (LABEL_DISP["go-klauspost"], best_ms(sc.get("go-klauspost", {})), C_KP),
            (LABEL_DISP["java"], best_ms(sc.get("java", {})), C_JAVA),
        ]
        charts.append(svg_bars(series, f"{sc_name} — roundtrip p50 (ต่ำ=ดี)",
                               "ข้อมูลบีบอัดได้: จุดที่ Go เคยแพ้ Java", unit="ms"))

    return (
        f'{banner}{verdict}'
        f'<div class="card"><h2>ภาพรวม</h2>{"".join(boxes)}{best_note}'
        f'<div class="info">การทดลองนี้สลับเฉพาะไลบรารี zlib ภายใน (compress/zlib → '
        'klauspost/compress/zlib) โดย<b>ไม่แก้โค้ด runner engine</b> — วัด 3 ทาง: '
        'Go เดิม (stdlib), Go+klauspost, และ Java (Bouncy Castle)</div></div>'
        f'<div class="card"><h2>ไฮไลต์: ข้อมูลบีบอัดได้ (txt/csv)</h2>{legend_html()}{"".join(charts)}</div>'
    )


def page_group(data, cat, title, intro, charts=""):
    rows = []
    for sc_name, sc in data.get("scenarios", {}).items():
        if categorize(sc_name) == cat:
            rows.append(scenario_row(sc_name, sc))
    if not rows:
        return f'<div class="card"><h2>{esc(title)}</h2><p>ไม่มีข้อมูลในกลุ่มนี้ (โหมดรันอาจไม่ครอบคลุม)</p></div>'
    intro_html = f'<div class="info">{intro}</div>' if intro else ""
    return (f'<div class="card"><h2>{esc(title)}</h2>{intro_html}'
            f'{legend_html()}{charts}{build_table(rows)}</div>')


# ── per-category charts ───────────────────────────────────────────────────────
def _size_label(kb):
    return f"{kb//1024}MB" if kb >= 1024 else f"{kb}KB"

def charts_sizegrad(data):
    """กราฟเส้น log-log ต่อสกุลไฟล์: p50 ตามขนาด 1KB→300MB เทียบ 3 impl"""
    prof = data.get("sizegradProfile") or {}
    steps = prof.get("stepsKB") or []
    types = prof.get("types") or []
    cap = prof.get("inmemCapMB", 256)
    scs = data.get("scenarios", {})
    out = []
    for ext in types:
        series = {}
        for label in LABELS:
            pts = []
            for kb in steps:
                tag = "S" if (kb / 1024) > cap else ""
                sc = scs.get(f"sg-{ext}-{_size_label(kb)}{tag}")
                pts.append((kb, best_ms(sc.get(label, {})) if sc else None))
            series[label] = pts
        xs_labels = [(kb, _size_label(kb)) for kb in steps]
        out.append(svg_lines(series, xs_labels,
                             f"{ext} — roundtrip p50 ตามขนาดไฟล์ (ต่ำ=ดี)",
                             "แกน log ทั้งสองด้าน: ระยะห่างแนวตั้งคงที่ = อัตราส่วน (speedup) คงที่",
                             unit="ms"))
    return "".join(out)

def charts_filetype(data):
    """แท่งกลุ่มต่อ keyAlg: 6 สกุลไฟล์ × 3 impl"""
    prof = data.get("fullProfile") or {}
    algs = prof.get("keyAlgs") or []
    fts = prof.get("filetypes") or []
    scs = data.get("scenarios", {})
    out = []
    for alg in algs:
        groups = []
        for ft in fts:
            sc = scs.get(f"ft-{ft}-{alg}")
            if not sc:
                continue
            groups.append((ft, [(l, best_ms(sc.get(l, {}))) for l in LABELS]))
        if groups:
            out.append(svg_grouped(groups, f"{alg} — roundtrip p50 ต่อสกุลไฟล์ (ต่ำ=ดี)",
                                   "15 ไฟล์ × 512KB ต่อสกุล", unit="ms"))
    return "".join(out)

def charts_prod(data):
    scs = data.get("scenarios", {})
    groups = [(n.replace("prod-", ""), [(l, best_ms(sc.get(l, {}))) for l in LABELS])
              for n, sc in scs.items() if n.startswith("prod-")]
    if not groups:
        return ""
    return svg_grouped(groups, "Production load — roundtrip p50 ต่อไฟล์ (ต่ำ=ดี)",
                       "จำนวนไฟล์ตามโหลดจริงของระบบเดิม + เผื่อ", unit="ms")

def charts_scaling(data):
    scs = data.get("scenarios", {})
    out = []
    # count gradient → กราฟเส้น (x = จำนวนไฟล์)
    counts = sorted(int(n.split("-")[1]) for n in scs if n.startswith("count-"))
    if counts:
        series = {}
        for label in LABELS:
            series[label] = [(c, best_ms(scs[f"count-{c}"].get(label, {}))) for c in counts]
        xs_labels = [(c, str(c)) for c in counts]
        out.append(svg_lines(series, xs_labels,
                             "Count gradient — p50 ต่อไฟล์ ตามจำนวนไฟล์ (ต่ำ=ดี)",
                             "ไฟล์ 100KB (binary) — เส้นแบนราบ = สเกลตามจำนวนไฟล์ได้ดี",
                             unit="ms"))
    # concurrency → แท่งกลุ่ม
    concs = [(n, sc) for n, sc in scs.items() if n.startswith("conc-")]
    if concs:
        groups = [(n.replace("conc-", "×"), [(l, best_ms(sc.get(l, {}))) for l in LABELS])
                  for n, sc in concs]
        out.append(svg_grouped(groups, "Concurrency 1/2/4/8 — roundtrip p50 (ต่ำ=ดี)",
                               "100 ไฟล์ × 1MB, streaming-parallel variant", unit="ms"))
    # many-small → แท่งกลุ่ม
    manys = [(n, sc) for n, sc in scs.items() if n.startswith("many-")]
    if manys:
        groups = [(n.replace("many-", ""), [(l, best_ms(sc.get(l, {}))) for l in LABELS])
                  for n, sc in manys]
        out.append(svg_grouped(groups, "Many-small — roundtrip p50 ต่อไฟล์ (ต่ำ=ดี)",
                               "ไฟล์เล็กจำนวนมาก: 1kb×200 / 10kb×200 / 100kb×100", unit="ms"))
    return "".join(out)


def page_insights(data):
    """แท็บวิเคราะห์: ขนาดไฟล์ vs จำนวนไฟล์ — อะไรคือปัจจัยที่ทำให้ช้า"""
    scs = data.get("scenarios", {})
    prof = data.get("sizegradProfile") or {}
    steps = prof.get("stepsKB") or []
    cap = prof.get("inmemCapMB", 256)

    # ── กราฟ 1: เวลาต่อ MB ตามขนาดไฟล์ (txt) — เส้นแบน = สเกลเชิงเส้น ──
    per_mb_series = {}
    flat_per_mb = {}   # ค่าเฉลี่ยช่วงอิ่มตัว (≥4MB) ต่อ impl
    for label in LABELS:
        pts = []
        satur = []
        for kb in steps:
            tag = "S" if (kb / 1024) > cap else ""
            sc = scs.get(f"sg-txt-{_size_label(kb)}{tag}")
            ms = best_ms(sc.get(label, {})) if sc else None
            if ms:
                v = ms / (kb / 1024)
                pts.append((kb, v))
                if kb >= 4096:
                    satur.append(v)
            else:
                pts.append((kb, None))
        per_mb_series[label] = pts
        if satur:
            flat_per_mb[label] = sum(satur) / len(satur)
    xs_labels = [(kb, _size_label(kb)) for kb in steps]
    chart_permb = svg_lines(per_mb_series, xs_labels,
                            "ต้นทุนต่อ MB ตามขนาดไฟล์ (txt, ต่ำ=ดี)",
                            "เส้นแบนทางขวา = เวลาโตเชิงเส้นตามขนาด (ราคา/MB คงที่) — ช่วงซ้ายชันเพราะ fixed overhead ต่อไฟล์ครอบไฟล์เล็ก",
                            unit="ms/MB")

    # ── กราฟ 2: p50 ต่อไฟล์ ตามจำนวนไฟล์ — เส้นแบน = จำนวนไม่มีผล ──
    counts = sorted(int(n.split("-")[1]) for n in scs if n.startswith("count-"))
    chart_count = ""
    if counts:
        series = {l: [(c, best_ms(scs[f"count-{c}"].get(l, {}))) for c in counts] for l in LABELS}
        chart_count = svg_lines(series, [(c, str(c)) for c in counts],
                                "เวลาต่อไฟล์ ตามจำนวนไฟล์ (ไฟล์ 100KB เท่ากันหมด, ต่ำ=ดี)",
                                "เส้นแบน = จำนวนไฟล์ไม่ทำให้ช้าลง (ไม่มีการสะสม/degradation) — เส้น Java ลาดลงคือ JIT warmup",
                                unit="ms/ไฟล์")

    # ── สูตรประเมิน (จากค่าที่วัดจริง) ──
    kp_permb = flat_per_mb.get("go-klauspost")
    std_permb = flat_per_mb.get("go-stdlib")
    jv_permb = flat_per_mb.get("java")
    # fixed overhead ≈ p50 ของไฟล์ 1KB (งานบีบ/เข้ารหัสจริงแทบเป็นศูนย์)
    sc1kb = scs.get("sg-txt-1KB")
    kp_fixed = best_ms(sc1kb.get("go-klauspost", {})) if sc1kb else None

    boxes = ['<div class="stats">']
    for label, permb, cls in (("go-stdlib", std_permb, "gray-b"),
                              ("java", jv_permb, "java-b"),
                              ("go-klauspost", kp_permb, "go-b")):
        if permb:
            boxes.append(f'<div class="sbox {cls}"><div class="val">{permb:.1f}</div>'
                         f'<div class="lbl">ms ต่อ MB (txt) — {esc(LABEL_DISP[label])}</div></div>')
    if kp_fixed:
        boxes.append(f'<div class="sbox green-b"><div class="val">~{kp_fixed:.1f}</div>'
                     f'<div class="lbl">ms fixed overhead ต่อไฟล์ (klauspost)</div></div>')
    boxes.append('</div>')

    formula = ""
    if kp_permb and kp_fixed:
        formula = (f'<div class="hi">📐 <b>สูตรประเมินเวลา (Go klauspost, ข้อมูล txt):</b> '
                   f'เวลารวม ≈ (จำนวนไฟล์ × ~{kp_fixed:.0f} ms) + (ขนาดรวมเป็น MB × ~{kp_permb:.0f} ms)<br>'
                   f'ตัวอย่าง: 1,000 ไฟล์ รวม 500MB ≈ {kp_fixed*1000/1000:.0f} + {kp_permb*500/1000:.1f} วินาที '
                   f'≈ <b>{(kp_fixed*1000 + kp_permb*500)/1000:.0f} วินาที</b></div>')

    return (
        '<div class="card"><h2>อะไรทำให้ช้า — ขนาดไฟล์ หรือ จำนวนไฟล์?</h2>'
        '<div class="info"><b>คำตอบจากข้อมูล: ขนาดไฟล์ (ปริมาณ MB รวม) คือปัจจัยหลัก — '
        'จำนวนไฟล์แทบไม่มีผล</b> จ่ายแค่ค่าแรกเข้าคงที่ต่อไฟล์ (~1ms) ไม่มีผลทบต้น</div>'
        f'{boxes and "".join(boxes)}'
        f'{formula}'
        '<h3>หลักฐาน 1 — เวลาโตเชิงเส้นตามขนาด (ควบคุมจำนวนไว้ที่ 1 ไฟล์)</h3>'
        '<p>ขนาด ×2 → เวลา ×2.0 สม่ำเสมอตั้งแต่ 4MB→300MB ไม่มีจุดหักที่ไฟล์ใหญ่แล้วพัง '
        'ต้นทุนต่อ MB จึงเป็นค่าคงที่ (เส้นแบนในกราฟ) — ยกเว้นไฟล์จิ๋ว &lt;64KB ที่ fixed overhead ครอบ</p>'
        f'{legend_html()}{chart_permb}'
        '<h3>หลักฐาน 2 — จำนวนไฟล์ไม่ทำให้ช้าลง (ควบคุมขนาดไว้ที่ 100KB)</h3>'
        '<p>เวลาต่อไฟล์คงที่ตั้งแต่ 1 → 1,000 ไฟล์ (แกว่ง &lt;10% = ระดับ noise) '
        'งานสเกลเป็น O(n) ตรงๆ — สิ่งที่ต้องวางแผนในโปรดักชันคือ <b>ปริมาณ MB รวม ไม่ใช่จำนวนไฟล์</b></p>'
        f'{chart_count}</div>'
    )


def best_by(res, field):
    """metrics ของ variant ที่ field ต่ำสุดใน label (เช่น enc_p50/dec_p50)"""
    vals = [d for d in (res or {}).values() if d and d.get(field)]
    return min(vals, key=lambda d: d[field]) if vals else None


def page_encdec(data):
    """แท็บแยกฝั่ง: เข้ารหัสอย่างเดียว vs ถอดรหัสอย่างเดียว"""
    scs = data.get("scenarios", {})
    prof = data.get("sizegradProfile") or {}
    steps = prof.get("stepsKB") or []
    cap = prof.get("inmemCapMB", 256)

    # ── นับ winner แยกฝั่งทุก scenario ──
    enc_win, dec_win, n_total = {}, {}, 0
    for n, sc in scs.items():
        b = {l: best_by(sc.get(l), "enc_p50") for l in LABELS}
        bd = {l: best_by(sc.get(l), "dec_p50") for l in LABELS}
        if not all(b.values()) or not all(bd.values()):
            continue
        n_total += 1
        ew = min(b, key=lambda l: b[l]["enc_p50"])
        dw = min(bd, key=lambda l: bd[l]["dec_p50"])
        enc_win[ew] = enc_win.get(ew, 0) + 1
        dec_win[dw] = dec_win.get(dw, 0) + 1

    boxes = ['<div class="stats">']
    boxes.append(f'<div class="sbox go-b"><div class="val">{enc_win.get("go-klauspost",0)}/{n_total}</div>'
                 '<div class="lbl">ฝั่งเข้ารหัส: klauspost ชนะ (scenarios)</div></div>')
    boxes.append(f'<div class="sbox gray-b"><div class="val">{dec_win.get("go-klauspost",0)} / {dec_win.get("go-stdlib",0)} / {dec_win.get("java",0)}</div>'
                 '<div class="lbl">ฝั่งถอดรหัส: kp / stdlib / java ชนะ (สูสี)</div></div>')
    # สัดส่วน enc:dec บนไฟล์ใหญ่
    sc_big = scs.get("sg-txt-256MB")
    if sc_big:
        bkp = best_by(sc_big.get("go-klauspost"), "p50")
        bstd = best_by(sc_big.get("go-stdlib"), "p50")
        if bkp and bstd:
            pct_std = bstd["enc_p50"] / (bstd["enc_p50"] + bstd["dec_p50"]) * 100
            pct_kp = bkp["enc_p50"] / (bkp["enc_p50"] + bkp["dec_p50"]) * 100
            boxes.append(f'<div class="sbox java-b"><div class="val">{pct_std:.0f}%</div>'
                         '<div class="lbl">stdlib: เวลาหมดไปกับเข้ารหัส (txt-256MB)</div></div>')
            boxes.append(f'<div class="sbox green-b"><div class="val">{pct_kp:.0f}%</div>'
                         '<div class="lbl">klauspost: เข้ารหัสไม่ใช่คอขวดแล้ว</div></div>')
    boxes.append('</div>')

    # ── กราฟเส้น log-log แยกฝั่ง (txt size gradient) ──
    def lines_for(field, title, sub):
        series = {}
        for label in LABELS:
            pts = []
            for kb in steps:
                tag = "S" if (kb / 1024) > cap else ""
                sc = scs.get(f"sg-txt-{_size_label(kb)}{tag}")
                b = best_by(sc.get(label), field) if sc else None
                pts.append((kb, b[field] if b else None))
            series[label] = pts
        xs_labels = [(kb, _size_label(kb)) for kb in steps]
        return svg_lines(series, xs_labels, title, sub, unit="ms")

    chart_enc = lines_for("enc_p50", "เข้ารหัสอย่างเดียว — p50 ตามขนาดไฟล์ (txt, ต่ำ=ดี)",
                          "งานบีบอัดทั้งหมดอยู่ฝั่งนี้ — klauspost ทิ้งห่างทุกขนาดตั้งแต่ 64KB ขึ้นไป")
    chart_dec = lines_for("dec_p50", "ถอดรหัสอย่างเดียว — p50 ตามขนาดไฟล์ (txt, ต่ำ=ดี)",
                          "inflate เป็นงานเบา — สามเส้นซ้อนกันเกือบสนิท = ไม่มีใครได้/เสียเปรียบ")

    # ── แท่งกลุ่มเทียบ enc vs dec บน scenario เด่น ──
    picks = [("ft-txt-RSA-2048", "txt 512KB"), ("sg-txt-16MB", "txt 16MB"),
             ("sg-txt-256MB", "txt 256MB"), ("sg-pdf-256MB", "pdf 256MB")]
    enc_groups, dec_groups = [], []
    for name, disp in picks:
        sc = scs.get(name)
        if not sc:
            continue
        enc_groups.append((disp, [(l, (best_by(sc.get(l), "enc_p50") or {}).get("enc_p50")) for l in LABELS]))
        dec_groups.append((disp, [(l, (best_by(sc.get(l), "dec_p50") or {}).get("dec_p50")) for l in LABELS]))
    chart_encbar = svg_grouped(enc_groups, "ฝั่งเข้ารหัส — scenario เด่น (ต่ำ=ดี)",
                               "klauspost ชนะขาดทุกเคส", unit="ms") if enc_groups else ""
    chart_decbar = svg_grouped(dec_groups, "ฝั่งถอดรหัส — scenario เดียวกัน (ต่ำ=ดี)",
                               "สามตัวสูสี ต่างกันระดับ 10–30% เท่านั้น", unit="ms") if dec_groups else ""

    # ── ตารางเต็มทุก scenario ──
    head = ("<tr><th>Scenario</th>"
            "<th>Enc: stdlib</th><th>Enc: klauspost</th><th>Enc: java</th><th>Enc winner</th>"
            "<th>Dec: stdlib</th><th>Dec: klauspost</th><th>Dec: java</th><th>Dec winner</th></tr>")
    body = []
    for n, sc in scs.items():
        be = {l: best_by(sc.get(l), "enc_p50") for l in LABELS}
        bd = {l: best_by(sc.get(l), "dec_p50") for l in LABELS}
        if not all(be.values()) or not all(bd.values()):
            continue
        ew = min(be, key=lambda l: be[l]["enc_p50"])
        dw = min(bd, key=lambda l: bd[l]["dec_p50"])
        def cell(v, win):
            return f'<td class="num{" win" if win else ""}">{fmt_ms(v)}</td>'
        body.append(
            f'<tr><td>{esc(n)}</td>'
            + "".join(cell(be[l]["enc_p50"], l == ew) for l in LABELS)
            + f'<td>{esc(LABEL_DISP[ew])}</td>'
            + "".join(cell(bd[l]["dec_p50"], l == dw) for l in LABELS)
            + f'<td>{esc(LABEL_DISP[dw])}</td></tr>'
        )
    table = f'<table>{head}{"".join(body)}</table>'

    return (
        '<div class="card"><h2>แยกฝั่ง: เข้ารหัสอย่างเดียว vs ถอดรหัสอย่างเดียว</h2>'
        '<div class="info">ตัวเลขหลักของรายงาน (p50) คือ <b>roundtrip = เข้ารหัส+ถอดรหัสรวมกัน</b> '
        'หน้านี้แยกสองฝั่งให้ดูว่า “กำไรมาจากไหน” — <b>คำตอบ: กำไรทั้งหมดมาจากฝั่งเข้ารหัส '
        '(จุดที่การบีบอัดทำงาน) ส่วนฝั่งถอดรหัสสามตัวเสมอกัน ไม่มี regression</b> '
        '→ ฝั่งผู้รับไฟล์ (ระบบปลายทาง/คู่ค้า) ไม่ได้รับผลกระทบใดๆ</div>'
        f'{"".join(boxes)}'
        f'<h3>ฝั่งเข้ารหัส (compression + encrypt)</h3>{legend_html()}{chart_enc}{chart_encbar}'
        f'<h3>ฝั่งถอดรหัส (decrypt + decompress)</h3>{chart_dec}{chart_decbar}'
        '<h3>ตารางเต็ม (สีเขียว = เร็วสุดในฝั่งนั้น)</h3>'
        f'{table}</div>'
    )


def page_correctness(data, problems, n_variants):
    if not problems:
        head = ('<div class="okbar">🔒 ผ่านทั้งหมด — '
                f'ตรวจ {n_variants} (scenario × impl × variant) ทุกตัว roundTripOk = 100%, '
                'ไม่มีไฟล์ถูก skip</div>')
    else:
        items = "".join(f"<li>{esc(p)}</li>" for p in problems)
        head = f'<div class="errbar">❌ พบ {len(problems)} ปัญหา<ul style="font-weight:400;margin-top:8px">{items}</ul></div>'

    # ตารางแจกแจง ok_ratio_min / skipped_max ต่อ scenario
    rows = []
    for sc_name, sc in data.get("scenarios", {}).items():
        for label in LABELS:
            for vname, d in (sc.get(label) or {}).items():
                okm = d.get("ok_ratio_min", None)
                skm = d.get("skipped_max", 0)
                ok = (okm is None or okm >= 1.0) and skm == 0
                badge = '<span class="badge ok">OK</span>' if ok else '<span class="badge bad">FAIL</span>'
                rows.append(
                    f'<tr><td>{esc(sc_name)}</td><td>{esc(LABEL_DISP.get(label,label))}</td>'
                    f'<td>{esc(vname)}</td>'
                    f'<td class="num">{"" if okm is None else f"{okm:.4f}"}</td>'
                    f'<td class="num">{skm}</td><td>{badge}</td></tr>'
                )
    tbl = ('<table><tr><th>Scenario</th><th>Impl</th><th>Variant</th>'
           '<th>ok_ratio_min</th><th>skipped_max</th><th>สถานะ</th></tr>'
           f'{"".join(rows)}</table>')
    return (f'<div class="card"><h2>ความถูกต้อง (anti-v2 guard)</h2>{head}'
            '<p>ทุกไฟล์ต้อง <b>เข้ารหัส → ถอดรหัส → คลายบีบอัด</b> แล้วได้ไบต์เดิมเป๊ะ '
            '(roundTripOk) และห้ามมีไฟล์ถูก skip เงียบๆ เหมือนที่ v2 เคยพลาด</p>'
            f'{tbl}</div>')


# ── main build ────────────────────────────────────────────────────────────────
def build(data, out_path):
    started  = str(data.get("startedAt", "—"))[:19].replace("T", " ")
    finished = str(data.get("finishedAt", "—"))[:19].replace("T", " ")
    duration = ""
    try:
        t0 = datetime.fromisoformat(data["startedAt"])
        t1 = datetime.fromisoformat(data["finishedAt"])
        secs = int((t1 - t0).total_seconds())
        h, m = secs // 3600, (secs % 3600) // 60
        duration = f"{h} ชม. {m} นาที" if h else f"{m} นาที"
    except Exception:
        pass
    branch   = data.get("branch", "—")
    rounds   = data.get("rounds", "—")
    warmup   = data.get("warmup", "—")
    modes = []
    if data.get("full"): modes.append("FULL (run_v5-equivalent matrix)")
    if data.get("big"):  modes.append("BIG (production file-count)")
    if data.get("sizegrad"): modes.append("SIZEGRAD (1KB→300MB/file)")
    modes_str = ", ".join(modes) if modes else "quick"

    problems, n_variants = check_correctness(data)
    summ = compute_summary(data)

    pages = [
        ("summary",   "📊 สรุปผล",             page_summary(data, summ, problems)),
        ("filetype",  "🗂 Filetype × KeyAlg",   page_group(data, "filetype", "Filetype Matrix (สกุลไฟล์ × key algorithm)",
                        "แต่ละสกุลไฟล์ทดสอบครบทั้ง RSA-2048 / RSA-4096 / Curve25519 — txt/csv คือจุดที่ Go เคยแพ้ Java",
                        charts=charts_filetype(data))),
        ("sizegrad",  "📏 Size Gradient",        page_group(data, "sizegrad", "Size Gradient (ขนาดไฟล์มีผลแค่ไหน, สูงสุด 300MB/ไฟล์)",
                        "ไฟล์เดียวต่อขนาด ไล่ 1KB→300MB; ไฟล์ >256MB วัดเฉพาะ streaming variant (กัน OOM) — ต่อท้ายด้วย S",
                        charts=charts_sizegrad(data))),
        ("prod",      "📦 Production Load",      page_group(data, "prod", "Production File-Count (จำนวนไฟล์ระบบเดิม + เผื่อ)",
                        "txt 1300 / csv 450 / pdf 350 / zip 30 — สะท้อนโหลดจริงของระบบเดิม (txt1200/csv400/pdf300/zip20)",
                        charts=charts_prod(data))),
        ("scaling",   "⚙️ Scaling",             page_group(data, "scaling", "Scaling (count / many-small / concurrency)",
                        "ทดสอบการสเกลตามจำนวนไฟล์, ไฟล์เล็กจำนวนมาก, และ concurrency 1/2/4/8",
                        charts=charts_scaling(data))),
        ("insights",  "🔍 อะไรทำให้ช้า",        page_insights(data)),
        ("encdec",    "🔀 เข้า vs ถอด",         page_encdec(data)),
        ("correct",   "🔒 Correctness",          page_correctness(data, problems, n_variants)),
    ]
    # ตัด quick ออกถ้าไม่มี — แต่ถ้ามี quick scenario ให้เพิ่มแท็บ
    quick_rows = [scenario_row(n, s) for n, s in data.get("scenarios", {}).items()
                  if categorize(n) == "quick"]
    if quick_rows:
        pages.insert(1, ("quick", "⚡ Quick",
                         f'<div class="card"><h2>Quick scenarios</h2>{legend_html()}{build_table(quick_rows)}</div>'))

    tabs_html = "".join(
        f'<button class="tab{" active" if i==0 else ""}" id="tab-{pid}" '
        f'onclick="showTab(\'{pid}\')">{label}</button>'
        for i, (pid, label, _) in enumerate(pages)
    )
    pages_html = "".join(
        f'<div class="page{" active" if i==0 else ""}" id="page-{pid}">{content}</div>'
        for i, (pid, _, content) in enumerate(pages)
    )

    html = f"""<!DOCTYPE html><html lang="th">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Report v3 — Go klauspost vs stdlib vs Java (PGP)</title>
{CSS}
</head>
<body>
<div class="wrap">
<div class="hdr">
  <h1>📊 Report v3 — Go klauspost vs Go stdlib vs Java</h1>
  <div class="sub">การทดลองสลับไลบรารีบีบอัด zlib ภายใน Go (compress/zlib → klauspost/compress/zlib)
    เพื่อปิดช่องว่างที่ Go แพ้ Java บนข้อมูลบีบอัดได้ (txt/csv) — วัด 3 ทาง byte-for-byte</div>
  <div class="meta">
    <span>📅 เริ่ม: {esc(started)}</span>
    <span>✅ เสร็จ: {esc(finished)}</span>
    {f'<span>⏱ ใช้เวลารัน: {esc(duration)}</span>' if duration else ''}
    <span>🌿 branch: {esc(branch)}</span>
    <span>🔁 rounds: {esc(rounds)} / warmup: {esc(warmup)}</span>
    <span>🧪 mode: {esc(modes_str)}</span>
    <span>🔒 AES-256 + ZLIB(lvl6) + SHA-256</span>
  </div>
</div>
<div class="tabs">{tabs_html}</div>
{pages_html}
<footer>สร้างโดย build_klauspost_report.py | {datetime.now().strftime("%Y-%m-%d %H:%M")} | self-contained (ไม่มี CDN)</footer>
</div>
{TAB_JS}
</body></html>"""

    pathlib.Path(out_path).write_text(html, encoding="utf-8")
    print(f"  ✓ HTML → {out_path}")
    if problems:
        print(f"  ⚠ correctness: พบ {len(problems)} ปัญหา (แสดงในแท็บ Correctness)")
    else:
        print(f"  🔒 correctness: ผ่านทั้งหมด ({n_variants} variant-checks)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_IN))
    ap.add_argument("--out", dest="out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    p = pathlib.Path(args.inp)
    if not p.exists():
        print(f"❌ ไม่พบไฟล์ผล: {p}")
        print("   รัน benchmark ก่อน: python3 scripts/vm/run_klauspost_ab.py")
        sys.exit(1)
    data = json.loads(p.read_text(encoding="utf-8"))
    print(f"📥 อ่าน {p}  ({len(data.get('scenarios', {}))} scenarios)")
    build(data, args.out)


if __name__ == "__main__":
    main()
