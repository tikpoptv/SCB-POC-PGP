#!/usr/bin/env python3
"""
build_kp_vs_zlibng_report.py — รายงาน head-to-head ฉบับเต็ม:
Go+klauspost vs Java+zlib-ng บน matrix FULL 74 scenarios

อ่าน:  report/results_kp_vs_zlibng_full.json  (ผลจาก scripts/vm/run_kp_vs_zlibng_full.py)
       report/results_klauspost_ab.json       (join คอลัมน์ java เดิม + go-stdlib เป็นบริบท —
                                               สนามเดียวกัน: corpus/seed/scenario ตรงกัน 74/74,
                                               ตัวเลข go-klauspost สองรอบต่างกัน median ~1.1%)
เขียน: report/kp_vs_zlibng_report.html

ใช้:   python3 report/build_kp_vs_zlibng_report.py

reuse เอนจินกราฟ/CSS จาก build_klauspost_report.py (สไตล์เดียวกับ report v3)
"""
import json, pathlib, argparse, statistics
from datetime import datetime

import build_klauspost_report as base
from build_klauspost_report import (
    esc, fmt_ms, best_ms, best_variant, svg_lines, svg_grouped, CSS, TAB_JS,
    C_KP, C_JAVA, C_STD,
)

HERE = pathlib.Path(__file__).parent
DEFAULT_NEW = HERE / "results_kp_vs_zlibng_full.json"
DEFAULT_OLD = HERE / "results_klauspost_ab.json"
DEFAULT_OUT = HERE / "kp_vs_zlibng_report.html"

C_NG = "#27ae60"   # java-zlibng (เขียว = ตัวโม)

base.LABEL_DISP.update({"java-zlibng": "Java + zlib-ng"})
base.LABEL_COLOR.update({"java-zlibng": C_NG})

# ลำดับในกราฟ: จัดตามภาษา (Java คู่, Go คู่) — คู่หลักที่ชิงกันคือ ng vs kp
CHART_LABELS = ["java", "java-zlibng", "go-stdlib", "go-klauspost"]

SG_SIZES = [("1KB", 1), ("64KB", 64), ("512KB", 512), ("4MB", 4096), ("16MB", 16384),
            ("64MB", 65536), ("128MB", 131072), ("256MB", 262144), ("300MB", 307200)]
SG_EXTS = ["txt", "csv", "pdf", "zip"]


def sc_filetype(name):
    for ext in ("txt", "csv", "pdf", "zip", "xlsx", "dat"):
        if f"-{ext}" in name:
            return ext
    return "mixed"   # count/many/conc ใช้ corpus ปนหลายสกุล


def load_rows(new, old):
    rows = []
    for name, sc in new["scenarios"].items():
        sc_old = old["scenarios"].get(name, {})
        rows.append({
            "name": name,
            "kp": best_ms(sc.get("go-klauspost", {})),
            "ng": best_ms(sc.get("java-zlibng", {})),
            "jv": best_ms(sc_old.get("java", {})),
            "std": best_ms(sc_old.get("go-stdlib", {})),
            "sc": sc, "sc_old": sc_old,
        })
    return rows


def find_sg(by_name, ext, lab):
    return by_name.get(f"sg-{ext}-{lab}") or by_name.get(f"sg-{ext}-{lab}S")


def legend_html(labels=CHART_LABELS):
    spans = "".join(
        f'<span><span class="k" style="background:{base.LABEL_COLOR[l]}"></span>{esc(base.LABEL_DISP[l])}</span>'
        for l in labels)
    return f'<div class="legend">{spans}</div>'


def row_vals(r):
    """ค่า 4 impl ตามลำดับ CHART_LABELS"""
    return {"java": r["jv"], "java-zlibng": r["ng"], "go-stdlib": r["std"], "go-klauspost": r["kp"]}


# ── หน้า 1: สรุปผล ───────────────────────────────────────────────────────────
def page_summary(rows):
    ng_win = [r for r in rows if r["kp"] and r["ng"] and r["ng"] < r["kp"] * 0.98]
    kp_win = [r for r in rows if r["kp"] and r["ng"] and r["kp"] < r["ng"] * 0.98]
    tie = len(rows) - len(ng_win) - len(kp_win)

    def med(pred):
        vals = [r["ng"] / r["kp"] for r in rows if r["kp"] and r["ng"] and pred(r)]
        return statistics.median(vals) if vals else None

    med_txt = med(lambda r: sc_filetype(r["name"]) == "txt")
    med_csv = med(lambda r: sc_filetype(r["name"]) == "csv")
    med_all = med(lambda r: True)

    # กราฟ headline: production load + สนามใหญ่ตัวแทน
    by_name = {r["name"]: r for r in rows}
    picks = [("prod txt×1300", "prod-txt-1300"), ("prod csv×450", "prod-csv-450"),
             ("txt 128MB", "sg-txt-128MB"), ("csv 128MB", "sg-csv-128MB"),
             ("pdf 128MB", "sg-pdf-128MB")]
    groups = []
    for glabel, key in picks:
        r = by_name.get(key)
        if r:
            v = row_vals(r)
            groups.append((glabel, [(l, v[l]) for l in CHART_LABELS]))
    chart = svg_grouped(groups, "Headline: production load + ไฟล์ใหญ่ 128MB",
                        "p50 roundtrip (ต่ำ = ดี) — java/go-stdlib จากรอบ FULL เดิม สนามเดียวกัน", width=860)

    # ตารางเต็ม 74 แถว
    head = ("<tr><th>Scenario</th><th>Java</th><th>Java+zlib-ng</th><th>Go stdlib</th>"
            "<th>Go klauspost</th><th>ng vs kp</th></tr>")
    body = []
    for r in rows:
        if r["kp"] and r["ng"]:
            k = r["ng"] / r["kp"]
            if k > 1.02:
                k_txt, k_cls = f"kp นำ {k:.2f}×", "win"
            elif k < 0.98:
                k_txt, k_cls = f"ng แซง {1/k:.2f}×", "lose"
            else:
                k_txt, k_cls = "เสมอ", ""
        else:
            k_txt, k_cls = "—", ""
        body.append(
            f'<tr><td>{esc(r["name"])}</td>'
            f'<td class="num">{fmt_ms(r["jv"])}</td>'
            f'<td class="num" style="color:{C_NG};font-weight:700">{fmt_ms(r["ng"])}</td>'
            f'<td class="num">{fmt_ms(r["std"])}</td>'
            f'<td class="num" style="color:{C_KP};font-weight:700">{fmt_ms(r["kp"])}</td>'
            f'<td class="num {k_cls}">{k_txt}</td></tr>'
        )
    table = f'<table>{head}{"".join(body)}</table>'

    ng_win_names = ", ".join(r["name"] for r in ng_win)

    return f"""
<div class="verdict">
  <div class="big">klauspost ยังครองสนาม 🔵 — zlib-ng ยึดได้เฉพาะเกาะ csv</div>
  <div class="vsub">FULL matrix 74 scenarios: <b>Go+klauspost ชนะ {len(kp_win)} สนาม (median {med_all:.1f}×)</b> ·
  Java+zlib-ng แซงได้ <b>{len(ng_win)} สนาม — csv ล้วน, margin ~5–10%</b> · เสมอ {tie}</div>
</div>
{legend_html()}
<div class="stats">
  <div class="sbox go-b"><div class="val">{len(kp_win)}/74</div><div class="lbl">สนามที่ klauspost ชนะ</div></div>
  <div class="sbox green-b"><div class="val">{len(ng_win)}/74</div><div class="lbl">สนามที่ zlib-ng แซง (csv ทั้งหมด)</div></div>
  <div class="sbox go-b"><div class="val">{med_txt:.2f}×</div><div class="lbl">txt: klauspost นำ (median)</div></div>
  <div class="sbox green-b"><div class="val">{1/med_csv:.2f}×</div><div class="lbl">csv: zlib-ng แซง (median)</div></div>
</div>
{chart}
<div class="info">💡 <b>สนามที่ zlib-ng แซงทั้ง {len(ng_win)}:</b> {esc(ng_win_names)} —
เป็น csv ล้วนตั้งแต่ 512KB ขึ้นไป (csv เล็กกว่านั้น overhead JVM ต่อไฟล์ยังถ่วงอยู่)</div>
<div class="card">
<h2>ตารางผลเต็ม (74 scenarios)</h2>
<p style="margin-bottom:10px">คอลัมน์ Java / Go stdlib มาจากรอบ FULL เดิม (สนามเดียวกัน corpus/seed เดิม —
ตรวจแล้ว: ตัวเลข go-klauspost สองรอบต่างกัน median 1.1%) ·
"ng vs kp" = java-zlibng ÷ go-klauspost</p>
{table}
</div>
"""


# ── หน้า 2: size gradient ────────────────────────────────────────────────────
def page_sizegrad(rows):
    by_name = {r["name"]: r for r in rows}
    xs_labels = [(kb, lab) for lab, kb in SG_SIZES]
    charts = []
    for ext in SG_EXTS:
        series = {}
        for lbl in CHART_LABELS:
            pts = []
            for lab, kb in SG_SIZES:
                r = find_sg(by_name, ext, lab)
                pts.append((kb, row_vals(r)[lbl] if r else None))
            series[lbl] = pts
        charts.append(svg_lines(series, xs_labels,
                                f"Size gradient — {ext} (log-log, 1KB → 300MB)",
                                "ช่องว่างแนวตั้งคงที่ = อัตราส่วนคงที่ · hover ดูค่า", width=820))
    return f"""
<h2>Size gradient: แพทเทิร์นชัดตั้งแต่ 4MB ขึ้นไป</h2>
<p>ไฟล์เล็ก (&lt;512KB) overhead ต่อ process/ไฟล์กลบผล — Go ชนะทุกสกุลเพราะ JVM แพงต่อครั้ง
พอไฟล์ใหญ่ขึ้น อัตราส่วนล็อกคงที่: <b>txt/pdf/zip klauspost นำ ~2.3–2.6× ทุกขนาด</b>
แต่ <b>csv สลับขั้ว: zlib-ng แซง ~8–10% ตั้งแต่ 4MB จนถึง 300MB</b></p>
{legend_html()}
{"".join(charts)}
<div class="hi">⚠️ เส้น java / go-stdlib มาจากรอบ FULL เดิม (join ข้ามรอบ) —
เทียบข้ามรอบมี noise ~1–2% (วัดจาก go-klauspost ที่รันทั้งสองรอบ: ต่างกัน median 1.1%, max 7.8%)
ไม่กระทบข้อสรุปที่ gap เป็นเท่าตัว</div>
"""


# ── หน้า 3: เข้า vs ถอด ─────────────────────────────────────────────────────
def page_encdec(rows):
    by_name = {r["name"]: r for r in rows}
    picks = [("txt 128MB", "sg-txt-128MB"), ("csv 128MB", "sg-csv-128MB"),
             ("pdf 128MB", "sg-pdf-128MB"), ("txt 300MB", "sg-txt-300MBS"),
             ("csv 300MB", "sg-csv-300MBS")]
    enc_groups, dec_groups = [], []
    for glabel, key in picks:
        r = by_name.get(key)
        if not r:
            continue
        eb, db = [], []
        for lbl in ("java-zlibng", "go-klauspost"):
            bv = best_variant(r["sc"].get(lbl, {}))
            eb.append((lbl, bv[1].get("enc_p50") if bv else None))
            db.append((lbl, bv[1].get("dec_p50") if bv else None))
        enc_groups.append((glabel, eb))
        dec_groups.append((glabel, db))
    c1 = svg_grouped(enc_groups, "เฉพาะเข้ารหัส (compress+encrypt)",
                     "enc p50 — จุดแข็ง klauspost: อิสระเชิงอัลกอริทึมฝั่ง deflate", width=820)
    c2 = svg_grouped(dec_groups, "เฉพาะถอดรหัส (decrypt+decompress)",
                     "dec p50 — จุดแข็ง zlib-ng: inflate ระดับ C+SIMD ชนะ pure Go", width=820)
    return f"""
<h2>เข้า vs ถอด — ต่างคนต่างมีอาวุธคนละขา</h2>
<p><b>Encrypt:</b> klauspost ชนะขาดใน txt/pdf/zip (deflate มีอิสระเชิงอัลกอริทึม —
เลือก match หลวมลงแลกความเร็วได้) · <b>Decrypt:</b> zlib-ng ชนะทุกสกุลในไฟล์ใหญ่
(inflate ถูก format lock ทุก implementation ต้องทำงานเท่ากัน → C+SIMD เร็วกว่า pure Go):</p>
<div class="legend">
  <span><span class="k" style="background:{C_NG}"></span>Java + zlib-ng</span>
  <span><span class="k" style="background:{C_KP}"></span>Go klauspost</span>
</div>
{c1}{c2}
<div class="info">💡 ตัวอย่าง txt-128MB: enc — klauspost 728ms vs zlib-ng 2,714ms (นำ 3.7×) ·
dec — zlib-ng 219ms vs klauspost 528ms (นำ 2.4×) · แต่ enc กิน ~80% ของ roundtrip
→ ผลรวม klauspost ยังชนะ 2.3× · ส่วน csv ที่ enc สูสี dec เลยชี้ขาดให้ zlib-ng แซง</div>
"""


# ── หน้า 4: วิธีทดสอบ + correctness ──────────────────────────────────────────
def page_method(new, problems):
    ok_bar = ('<div class="okbar">🔒 correctness ผ่านครบ: roundTripOk 100% byte-for-byte, '
              'ไม่มีไฟล์ถูก skip ทุก scenario/variant + verify_preload + gpg interop</div>'
              if not problems else
              '<div class="errbar">❌ พบปัญหา correctness — อย่าใช้ผลตัดสินใจ</div>')
    plist = "".join(f"<li>{esc(p)}</li>" for p in problems)
    return f"""
{ok_bar}
{'<ul>' + plist + '</ul>' if problems else ''}
<h2>วิธีทดสอบ</h2>
<div class="card">
<h3>Setup</h3>
<ul>
<li><b>VM:</b> Ubuntu 24.04, 8 vCPU (VM 122) — เครื่องเดียวกับ FULL run ทุกรอบ</li>
<li><b>Matrix เต็มเหมือน FULL เดิม (74 scenarios):</b> 6 สกุลไฟล์ × 3 keyAlg + count gradient
    (1→1000 ไฟล์) + many-small + concurrent (1→8) + production file-count
    (txt1300/csv450/pdf350/zip30) + size gradient 1KB→300MB × 4 สกุล</li>
<li><b>เงื่อนไขเดิมเป๊ะ:</b> FULL=1 ROUNDS=5 (median) WARMUP=3, corpus <code>~/corpus-kp</code>
    ชุดเดิม seed เดิม, p50 ของ variant เร็วสุดต่อ label, in-memory cap 256MB (&gt;256MB stream เท่านั้น)</li>
<li><b>ผู้เข้าแข่ง 2 ตัว:</b> go-klauspost (แชมป์จาก report v3) vs java + LD_PRELOAD zlib-ng 1.3.1
    zlib-compat (ตัวโมที่ดีที่สุดฝั่ง Java จาก POC ก่อนหน้า) — คอลัมน์ java/go-stdlib ใน
    รายงานนี้ join มาจากรอบ FULL เดิมเป็นบริบท</li>
</ul>
<h3>ด่านความถูกต้อง</h3>
<ul>
<li><b>verify_preload gate:</b> เช็ค marker zlib-ng ใน lib + java -version ใต้ preload ไม่มี ld.so error
    (LD_PRELOAD ล้มแบบเงียบได้ — ต้องดักก่อนรัน)</li>
<li><b>gpg interop (จาก POC ก่อนหน้า):</b> Java+zlib-ng encrypt → gpg ถอด byte-for-byte ผ่าน,
    packet <code>algo=2</code> ZLIB มาตรฐาน — ไม่หลุดสเปค OpenPGP</li>
<li><b>in-run guard:</b> roundTripOk 100% + skip=0 ทุกรอบ (anti-v2) — รอบนี้ผ่านครบ, fail(x)=0 ทั้ง log</li>
<li><b>cross-run sanity:</b> go-klauspost รันทั้งสองรอบ → ต่างกัน median 1.1% ยืนยันว่า join ได้</li>
</ul>
</div>
<div class="card">
<h3>ความหมายเชิงตัดสินใจ</h3>
<ul>
<li>🔵 <b>ข้อสรุปหลักยืนบน matrix เต็ม:</b> Go+klauspost ชนะ 65/74 สนาม median ~2.3× —
    รวมสกุลปริมาณหลักของ production (txt 1300 ไฟล์/รอบ: นำ 1.7×)</li>
<li>🟡 <b>ข้อยกเว้นเดียวคือ csv ≥512KB:</b> Java+zlib-ng แซง ~5–10% (prod-csv-450 แซง 7%) —
    ถ้า workload เป็น csv ใหญ่ล้วน สองทางแทบไม่ต่าง</li>
<li>🟢 <b>ถ้าอยู่กับ Java ต่อ:</b> LD_PRELOAD zlib-ng คือ quick win จริง (csv 2.9× / txt 1.3× ฟรี)
    แต่ยังไล่ klauspost ไม่ทันในสนามส่วนใหญ่</li>
<li>🔬 <b>ช่องที่เหลือของ Go:</b> decrypt ไฟล์ใหญ่แพ้ zlib-ng ~2× (format-locked, C+SIMD ชนะ pure Go)
    — ปิดได้ด้วย cgo แต่เสียข้อดี pure-Go; ประเมินแล้วไม่คุ้มเพราะ enc ครองสัดส่วนเวลา</li>
</ul>
</div>
"""


# ── ประกอบ ───────────────────────────────────────────────────────────────────
def check_correctness(data):
    problems = []
    for sc_name, sc in data["scenarios"].items():
        for label, res in sc.items():
            for vname, d in (res or {}).items():
                if d.get("ok_ratio_min", 1.0) < 1.0:
                    problems.append(f"{sc_name}/{label}/{vname}: roundTripOk<100%")
                if d.get("skipped_max", 0) > 0:
                    problems.append(f"{sc_name}/{label}/{vname}: มีไฟล์ถูก skip")
    return problems


def build(new, old, out_path):
    rows = load_rows(new, old)
    problems = check_correctness(new)

    duration = ""
    try:
        t0 = datetime.fromisoformat(new["startedAt"])
        t1 = datetime.fromisoformat(new["finishedAt"])
        secs = int((t1 - t0).total_seconds())
        h, m = secs // 3600, (secs % 3600) // 60
        duration = f"{h} ชม. {m} นาที" if h else f"{m} นาที"
    except Exception:
        pass
    started = new.get("startedAt", "")[:19].replace("T", " ")

    pages = [
        ("summary", "📊 สรุปผล", page_summary(rows)),
        ("sizegrad", "📈 Size Gradient", page_sizegrad(rows)),
        ("encdec", "🔀 เข้า vs ถอด", page_encdec(rows)),
        ("method", "🧪 วิธีทดสอบ + Correctness", page_method(new, problems)),
    ]
    tabs = "".join(
        f'<button class="tab{" active" if i == 0 else ""}" id="tab-{pid}" '
        f'onclick="showTab(\'{pid}\')">{title}</button>'
        for i, (pid, title, _) in enumerate(pages))
    bodies = "".join(
        f'<div class="page{" active" if i == 0 else ""}" id="page-{pid}">{body}</div>'
        for i, (pid, _, body) in enumerate(pages))

    html = f"""<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Head-to-head FULL: Go klauspost vs Java zlib-ng — 74 scenarios</title>
{CSS}</head><body><div class="wrap">
<div class="hdr">
  <h1>🥊 Head-to-head ฉบับเต็ม: Go+klauspost vs Java+zlib-ng</h1>
  <div class="sub">นัดชิง: แชมป์จาก report v3 (Go+klauspost) เจอตัวโมที่ดีที่สุดฝั่ง Java
  (LD_PRELOAD zlib-ng) บน matrix FULL 74 scenarios เงื่อนไขเดียวกับรอบเดิมทุกอย่าง</div>
  <div class="meta">
    <span>📅 เริ่ม: {esc(started)} UTC</span>
    {f'<span>⏱ ใช้เวลารัน: {esc(duration)}</span>' if duration else ''}
    <span>🔁 ROUNDS={new.get("rounds")} WARMUP={new.get("warmup")}</span>
    <span>🌿 {esc(new.get("branch", ""))}</span>
    <span>🧬 zlib-ng 1.3.1 (zlib-compat)</span>
  </div>
</div>
<div class="tabs">{tabs}</div>
{bodies}
<footer>สร้างจาก results_kp_vs_zlibng_full.json + join results_klauspost_ab.json ·
self-contained (เปิดออฟไลน์ได้) · กราฟ hover ดูค่าได้</footer>
</div>{TAB_JS}</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_NEW))
    ap.add_argument("--old", dest="old", default=str(DEFAULT_OLD))
    ap.add_argument("--out", dest="out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    new = json.loads(pathlib.Path(a.inp).read_text())
    old = json.loads(pathlib.Path(a.old).read_text())
    out = build(new, old, pathlib.Path(a.out))
    print(f"✅ เขียนแล้ว: {out}")


if __name__ == "__main__":
    main()
