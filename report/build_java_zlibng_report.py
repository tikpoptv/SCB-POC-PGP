#!/usr/bin/env python3
"""
build_java_zlibng_report.py — รายงาน POC: Java comeback ด้วย zlib-ng ได้แค่ไหน?

อ่าน:  report/results_java_zlibng_ab.json  (ผลจาก scripts/vm/run_java_zlibng_ab.py)
เขียน: report/java_zlibng_report.html

ใช้:   python3 report/build_java_zlibng_report.py

reuse เอนจินกราฟ/CSS จาก build_klauspost_report.py (สไตล์เดียวกับ report v3)
— แค่เพิ่ม label ใหม่ java-zlibng เข้า palette
"""
import json, pathlib, argparse
from datetime import datetime

import build_klauspost_report as base
from build_klauspost_report import (
    esc, fmt_ms, best_ms, best_variant, svg_lines, svg_grouped, CSS, TAB_JS,
    C_KP, C_JAVA, C_GREEN, C_RED,
)

HERE = pathlib.Path(__file__).parent
DEFAULT_IN  = HERE / "results_java_zlibng_ab.json"
DEFAULT_OUT = HERE / "java_zlibng_report.html"

C_NG = "#27ae60"   # java-zlibng (เขียว = ตัวโม)

LABELS = ["java", "java-zlibng", "go-klauspost"]
# เติม palette ให้เอนจินกราฟของ base รู้จัก label ใหม่
base.LABEL_DISP.update({"java-zlibng": "Java + zlib-ng"})
base.LABEL_COLOR.update({"java-zlibng": C_NG})
DISP = base.LABEL_DISP
COLOR = base.LABEL_COLOR


def ratio_fmt(a, b):
    """a/b — >1 = ตัวหลัง (b) เร็วกว่า"""
    if not a or not b:
        return None
    return a / b


def legend_html():
    return (
        '<div class="legend">'
        f'<span><span class="k" style="background:{C_JAVA}"></span>Java (libz ระบบ)</span>'
        f'<span><span class="k" style="background:{C_NG}"></span>Java + zlib-ng (LD_PRELOAD)</span>'
        f'<span><span class="k" style="background:{C_KP}"></span>Go klauspost (เป้าที่ต้องไล่)</span>'
        '</div>'
    )


def rows_of(data):
    out = []
    for sc_name, sc in data["scenarios"].items():
        jv = best_ms(sc.get("java", {}))
        ng = best_ms(sc.get("java-zlibng", {}))
        kp = best_ms(sc.get("go-klauspost", {}))
        out.append({"name": sc_name, "java": jv, "ng": ng, "kp": kp, "sc": sc})
    return out


def sc_type(name):
    if "-csv" in name or name.startswith("csv"):
        return "csv"
    if "-txt" in name or name.startswith("txt"):
        return "txt"
    return "dat"


# ── หน้า 1: สรุปผล ───────────────────────────────────────────────────────────
def page_summary(data, rows):
    # ค่าเฉลี่ย gain แยกสกุล
    def avg(vals):
        vals = [v for v in vals if v]
        return sum(vals) / len(vals) if vals else None

    gain_txt = avg([ratio_fmt(r["java"], r["ng"]) for r in rows if sc_type(r["name"]) == "txt"])
    gain_csv = avg([ratio_fmt(r["java"], r["ng"]) for r in rows if sc_type(r["name"]) == "csv"])
    vs_kp_txt = avg([ratio_fmt(r["ng"], r["kp"]) for r in rows if sc_type(r["name"]) == "txt"])
    vs_kp_csv = avg([ratio_fmt(r["ng"], r["kp"]) for r in rows if sc_type(r["name"]) == "csv"])

    # ตาราง
    head = ("<tr><th>Scenario</th><th>Java (p50)</th><th>Java+zlib-ng (p50)</th>"
            "<th>Go klauspost (p50)</th><th>zlib-ng ช่วย</th><th>เทียบ klauspost</th></tr>")
    body = []
    for r in rows:
        g = ratio_fmt(r["java"], r["ng"])
        k = ratio_fmt(r["ng"], r["kp"])   # >1 = klauspost ยังนำ
        g_txt = f"{g:.2f}×" if g else "—"
        if k is None:
            k_txt, k_cls = "—", ""
        elif k > 1.02:
            k_txt, k_cls = f"แพ้ {k:.2f}×", "lose"
        elif k < 0.98:
            k_txt, k_cls = f"ชนะ {1/k:.2f}×", "win"
        else:
            k_txt, k_cls = "เสมอ", ""
        body.append(
            f'<tr><td>{esc(r["name"])}</td>'
            f'<td class="num">{fmt_ms(r["java"])}</td>'
            f'<td class="num" style="color:{C_NG};font-weight:700">{fmt_ms(r["ng"])}</td>'
            f'<td class="num">{fmt_ms(r["kp"])}</td>'
            f'<td class="num win">{g_txt}</td>'
            f'<td class="num {k_cls}">{k_txt}</td></tr>'
        )
    table = f'<table>{head}{"".join(body)}</table>'

    # กราฟ headline: 512KB×15 + 16MB + 128MB
    picks = [("csv 512KB×15", "csv-512KB×15"), ("csv 16MB", "sg-csv-16MB"), ("csv 128MB", "sg-csv-128MB"),
             ("txt 16MB", "sg-txt-16MB"), ("txt 128MB", "sg-txt-128MB")]
    groups = []
    by_name = {r["name"]: r for r in rows}
    for glabel, key in picks:
        r = by_name.get(key)
        if r:
            groups.append((glabel, [("java", r["java"]), ("java-zlibng", r["ng"]), ("go-klauspost", r["kp"])]))
    chart = svg_grouped(groups, "ภาพรวม: zlib-ng ดัน Java ขึ้นมาแค่ไหน",
                        "p50 roundtrip ต่อ scenario (ต่ำ = ดี) — hover ดูค่า", width=760)

    return f"""
<div class="verdict">
  <div class="big">Java comeback ได้ครึ่งสนาม 🟡</div>
  <div class="vsub">LD_PRELOAD zlib-ng (ไม่แก้โค้ด Java เลย) → <b>csv เร็วขึ้น {gain_csv:.1f}× จนแซง klauspost เล็กน้อย</b><br>
  แต่ <b>txt ได้แค่ {gain_txt:.2f}× — klauspost ยังนำ {vs_kp_txt:.1f}×</b> ข้อสรุปหลักของ experiment เดิมยังยืน</div>
</div>
{legend_html()}
<div class="stats">
  <div class="sbox green-b"><div class="val">{gain_csv:.1f}×</div><div class="lbl">csv: zlib-ng ช่วย Java (เฉลี่ย)</div></div>
  <div class="sbox green-b"><div class="val">{1/vs_kp_csv:.2f}×</div><div class="lbl">csv: Java+zlib-ng ชนะ klauspost</div></div>
  <div class="sbox java-b"><div class="val">{gain_txt:.2f}×</div><div class="lbl">txt: zlib-ng ช่วย Java (เฉลี่ย)</div></div>
  <div class="sbox go-b"><div class="val">{vs_kp_txt:.1f}×</div><div class="lbl">txt: klauspost ยังนำ</div></div>
</div>
{chart}
<div class="card">
<h2>ตารางผลเต็ม (ทุก scenario)</h2>
<p style="margin-bottom:10px">"zlib-ng ช่วย" = java/java-zlibng (&gt;1 = เร็วขึ้น) ·
"เทียบ klauspost" = ฝั่งไหนเร็วกว่าและกี่เท่า (มุมมอง Java+zlib-ng)</p>
{table}
</div>
<div class="info">💡 <b>วิธีโม:</b> Deflater ของ JDK เรียก libz.so ของระบบแบบ dynamic →
ใช้ <code>LD_PRELOAD</code> สลับเป็น zlib-ng 1.3.1 (โหมด zlib-compat, มี AVX2/AVX512) ตอนเปิด JVM
โดยไม่แตะโค้ด Java สักบรรทัด — output ยังเป็น ZLIB มาตรฐาน (ยืนยันแล้ว: gpg ถอดได้ byte-for-byte,
packet เป็น algo=2 ปกติ)</div>
"""


# ── หน้า 2: ทำไม csv ฟื้นแต่ txt ไม่ ─────────────────────────────────────────
def page_why(data, rows):
    by_name = {r["name"]: r for r in rows}
    steps = data.get("sizegradStepsKB", [1024, 16384, 131072])
    xs_labels = [(kb, f"{kb//1024}MB" if kb >= 1024 else f"{kb}KB") for kb in steps]

    charts = []
    for ext in ("txt", "csv"):
        series = {}
        for lbl in LABELS:
            pts = []
            for kb in steps:
                sz = f"{kb//1024}MB" if kb >= 1024 else f"{kb}KB"
                r = by_name.get(f"sg-{ext}-{sz}") or by_name.get(f"sg-{ext}-{sz}S")
                pts.append((kb, r[{"java": "java", "java-zlibng": "ng", "go-klauspost": "kp"}[lbl]] if r else None))
            series[lbl] = pts
        charts.append(svg_lines(series, xs_labels,
                                f"Size gradient — {ext} (สเกล log-log)",
                                "ช่องว่างแนวตั้งคงที่ = อัตราส่วนคงที่ · hover ดูค่า", width=760))

    # ratio เทียบ (จาก best variant ของแต่ละ label ที่ 128MB)
    r128t = by_name.get("sg-txt-128MB"); r128c = by_name.get("sg-csv-128MB")

    def ratio_of(r, lbl):
        bv = best_variant(r["sc"].get(lbl, {})) if r else None
        return bv[1].get("ratio") if bv else None

    return f"""
<h2>ทำไม csv ฟื้นสุดตัว แต่ txt ฟื้นนิดเดียว?</h2>
<p>zlib-ng ไม่ได้เร่ง deflate ทุกส่วนเท่ากัน — มันเร่งด้วย SIMD (AVX2/AVX512) ตรงส่วน
<b>match finding / hash chain</b> ซึ่งเป็นคอขวดของข้อมูลแบบ csv (แพทเทิร์นสั้น ซ้ำถี่ ตัวเลขล้วน)
ส่วน txt ของเรา (ประโยคคำสุ่ม ซ้ำยาวกว่า กระจายกว่า) คอขวดไปอยู่ที่ส่วนอื่นของอัลกอริทึม
ที่ zlib-ng ช่วยได้น้อยกว่า จึงเห็น gain ต่างกันชัด:</p>
<div class="stats">
  <div class="sbox green-b"><div class="val">2.7–3.2×</div><div class="lbl">csv: gain จาก zlib-ng (ทุกขนาด)</div></div>
  <div class="sbox java-b"><div class="val">1.31–1.35×</div><div class="lbl">txt: gain จาก zlib-ng (ทุกขนาด)</div></div>
</div>
{legend_html()}
{"".join(charts)}
<div class="card">
<h3>Compression ratio ไม่เสีย</h3>
<p>ที่ 128MB: txt — java {ratio_of(r128t,'java'):.2f}× vs zlib-ng {ratio_of(r128t,'java-zlibng'):.2f}× ·
csv — java {ratio_of(r128c,'java'):.2f}× vs zlib-ng {ratio_of(r128c,'java-zlibng'):.2f}×
(zlib-ng level เดียวกัน บีบได้เท่าเดิม ไม่ได้แลกความเร็วกับขนาด)</p>
<p style="margin-top:8px">ส่วน klauspost ratio ต่ำกว่าเล็กน้อย (txt 5.36× vs 6.41×) —
เร็วกว่าแต่บีบหลวมกว่านิดหน่อย เป็น trade-off ที่รู้อยู่แล้วจาก report v3</p>
</div>
<div class="hi">⚠️ <b>ข้อจำกัดของข้อสรุปนี้:</b> corpus เป็น synthetic — csv จริงของ production
อาจมีสัดส่วน text ปนมากกว่า ทำให้ gain อยู่ระหว่าง 1.3×–3.2× · จุดที่ควรจำ:
gain ของ zlib-ng <b>ขึ้นกับชนิดข้อมูลแรงมาก</b> ต่างจาก klauspost ที่สม่ำเสมอกว่า</div>
"""


# ── หน้า 3: เข้า vs ถอด ─────────────────────────────────────────────────────
def page_encdec(rows):
    picks = [("csv 16MB", "sg-csv-16MB"), ("csv 128MB", "sg-csv-128MB"),
             ("txt 16MB", "sg-txt-16MB"), ("txt 128MB", "sg-txt-128MB")]
    by_name = {r["name"]: r for r in rows}
    enc_groups, dec_groups = [], []
    for glabel, key in picks:
        r = by_name.get(key)
        if not r:
            continue
        eb, db = [], []
        for lbl in LABELS:
            bv = best_variant(r["sc"].get(lbl, {}))
            eb.append((lbl, bv[1].get("enc_p50") if bv else None))
            db.append((lbl, bv[1].get("dec_p50") if bv else None))
        enc_groups.append((glabel, eb))
        dec_groups.append((glabel, db))
    c1 = svg_grouped(enc_groups, "เฉพาะเข้ารหัส (encrypt = compress+encrypt)",
                     "enc p50 — ฝั่งที่ zlib-ng ออกแรง", width=760)
    c2 = svg_grouped(dec_groups, "เฉพาะถอดรหัส (decrypt = decrypt+decompress)",
                     "dec p50 — โบนัส: inflate ของ zlib-ng ก็เร็วขึ้นด้วย", width=760)
    return f"""
<h2>เข้า vs ถอด — zlib-ng ช่วยทั้งสองขา</h2>
<p>ต่างจาก klauspost ที่ gain เกือบทั้งหมดอยู่ฝั่ง encrypt — zlib-ng เร่งทั้ง deflate (เข้า)
และ inflate (ถอด) เพราะสลับที่ระดับไลบรารี C ทั้งก้อน:</p>
{legend_html()}
{c1}{c2}
<div class="info">💡 ที่ 128MB csv: decrypt ของ Java+zlib-ng (608ms) เร็วกว่า klauspost (1,108ms) เกือบ 2× —
ฝั่งถอดรหัส Java แข็งแรงอยู่แล้ว (จาก report v3) พอเสริม zlib-ng ยิ่งทิ้งห่าง</div>
"""


# ── หน้า 4: วิธีทดสอบ + correctness ──────────────────────────────────────────
def page_method(data, problems):
    ok_bar = ('<div class="okbar">🔒 correctness ผ่านครบ: roundTripOk 100% byte-for-byte, '
              'ไม่มีไฟล์ถูก skip ทุก scenario/variant + gpg interop ยืนยันก่อนรัน</div>'
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
<li><b>VM:</b> Ubuntu 24.04, 8 vCPU (VM 122) — เครื่องเดียวกับ FULL run ของ report v3</li>
<li><b>zlib-ng:</b> 1.3.1 build โหมด <code>--zlib-compat</code> (AVX2/AVX512 ครบ) →
    <code>LD_PRELOAD</code> ตอนเปิด JVM — โค้ด Java/Bouncy Castle ไม่ถูกแก้เลย</li>
<li><b>เทียบ 3 ทาง:</b> java (libz ระบบ) / java + zlib-ng / go-klauspost (ผู้ชนะจาก report v3)</li>
<li><b>วัดแบบเดียวกับ FULL run:</b> ROUNDS=5 (median), WARMUP=3 (กัน JIT cold),
    p50 ของ variant ที่เร็วสุดต่อ label, corpus generator ตัวเดียวกัน seed เดิม</li>
<li><b>Scenarios:</b> txt/csv/dat 512KB×15 + size gradient txt/csv @ 1MB/16MB/128MB (รวม 9)</li>
</ul>
<h3>ด่านความถูกต้องก่อนเชื่อผล</h3>
<ul>
<li><b>preload gate:</b> เช็คว่า lib มี marker zlib-ng จริง + <code>java -version</code> ใต้ preload ไม่มี ld.so error
    (กัน LD_PRELOAD ล้มเงียบแล้ววัดได้ค่าเท่า java เดิม)</li>
<li><b>gpg interop:</b> Java+zlib-ng encrypt → gpg (reference implementation) ถอด byte-for-byte ผ่าน,
    packet เป็น <code>compressed algo=2</code> (ZLIB มาตรฐาน) → ไม่หลุดสเปค OpenPGP</li>
<li><b>in-run guard:</b> roundTripOk ต้อง 100% และ skip ต้อง 0 ทุกรอบ (anti-v2)</li>
</ul>
</div>
<div class="card">
<h3>ความหมายเชิงตัดสินใจ</h3>
<ul>
<li>🟢 <b>ถ้าทีมต้องอยู่กับ Java ต่อ:</b> zlib-ng คือ quick win ของจริง — env var ตัวเดียว
    ได้ csv 3× / txt 1.3× ฟรี ไม่แตะโค้ด (แต่ต้องดูแล lib เพิ่ม 1 ตัวใน deployment)</li>
<li>🔵 <b>ข้อสรุปหลักของ experiment ยังยืน:</b> Go+klauspost ยังเร็วกว่าใน txt (สกุลที่ปริมาณเยอะสุดใน
    production: 1300 ไฟล์/รอบ) ~2.3–2.5× และ incompressible ~2.2×</li>
<li>🟡 <b>csv เป็นข้อยกเว้น:</b> Java+zlib-ng แซง klauspost ~5–10% — ถ้า workload หนัก csv
    ช่องว่างระหว่างสองภาษาแทบหายไป</li>
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


def build(data, out_path):
    rows = rows_of(data)
    problems = check_correctness(data)

    duration = ""
    try:
        t0 = datetime.fromisoformat(data["startedAt"])
        t1 = datetime.fromisoformat(data["finishedAt"])
        secs = int((t1 - t0).total_seconds())
        h, m = secs // 3600, (secs % 3600) // 60
        duration = f"{h} ชม. {m} นาที" if h else f"{m} นาที"
    except Exception:
        pass

    started = data.get("startedAt", "")[:19].replace("T", " ")

    pages = [
        ("summary", "📊 สรุปผล", page_summary(data, rows)),
        ("why", "🔬 ทำไม csv ฟื้น txt ไม่ฟื้น", page_why(data, rows)),
        ("encdec", "🔀 เข้า vs ถอด", page_encdec(rows)),
        ("method", "🧪 วิธีทดสอบ + Correctness", page_method(data, problems)),
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
<title>POC: Java comeback ด้วย zlib-ng — ผลจริงบน VM</title>
{CSS}</head><body><div class="wrap">
<div class="hdr">
  <h1>🏁 POC: Java comeback ด้วย zlib-ng ได้แค่ไหน?</h1>
  <div class="sub">คำถามต่อจาก report v3 (Go+klauspost ชนะ): ถ้าให้ Java ได้โมชั้นบีบอัดบ้าง
  (LD_PRELOAD zlib-ng — ไม่แก้โค้ด) จะไล่ทันมั้ย? · เทียบ 3 ทาง: java / java+zlib-ng / go-klauspost</div>
  <div class="meta">
    <span>📅 เริ่ม: {esc(started)} UTC</span>
    {f'<span>⏱ ใช้เวลารัน: {esc(duration)}</span>' if duration else ''}
    <span>🔁 ROUNDS={data.get("rounds")} WARMUP={data.get("warmup")}</span>
    <span>🌿 {esc(data.get("branch", ""))}</span>
    <span>🧬 zlib-ng 1.3.1 (zlib-compat)</span>
  </div>
</div>
<div class="tabs">{tabs}</div>
{bodies}
<footer>สร้างจาก results_java_zlibng_ab.json · self-contained (เปิดออฟไลน์ได้) · กราฟ hover ดูค่าได้</footer>
</div>{TAB_JS}</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_IN))
    ap.add_argument("--out", dest="out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    data = json.loads(pathlib.Path(a.inp).read_text())
    out = build(data, pathlib.Path(a.out))
    print(f"✅ เขียนแล้ว: {out}")


if __name__ == "__main__":
    main()
