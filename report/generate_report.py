#!/usr/bin/env python3
"""
generate_report.py — entry point หลัก

ใช้ results_extended.json (full benchmark 26 scenarios) เป็น primary data
ถ้าไม่มีจึง fallback ไป results.json (original 15 scenarios)

USAGE:
    python3 generate_report.py                     # auto-find
    python3 generate_report.py /path/results.json  # explicit
"""
import sys, pathlib
import data_loader, charts, html_builder

REPORT_DIR = pathlib.Path(__file__).parent


def main():
    # ── หา results หลัก (extended ก่อน, fallback ไป original) ─────────────
    if len(sys.argv) > 1:
        primary_path = sys.argv[1]
    else:
        # ลำดับความสำคัญ: extended > original > /tmp
        candidates = [
            REPORT_DIR / "results_extended.json",    # full benchmark
            REPORT_DIR / "results.json",              # original
            pathlib.Path("/tmp/bench_results_extended.json"),
            pathlib.Path("/tmp/bench-full/results_full.json"),
            pathlib.Path("/tmp/bench_results.json"),
        ]
        primary_path = None
        for c in candidates:
            if c.exists():
                primary_path = str(c)
                break
        if not primary_path:
            print("❌ ไม่พบไฟล์ results")
            sys.exit(1)

    print(f"\n🔍 โหลดข้อมูลจาก: {primary_path}")
    data = data_loader.load(primary_path)

    # ── ตรวจว่าเป็น extended format (มี pub_alg ใน scenario) หรือ original ──
    first_sc = list(data.get("scenarios", {}).values())[:1]
    is_extended = (first_sc and isinstance(first_sc[0], dict)
                   and "pub_alg" in first_sc[0])

    if is_extended:
        print("  ✓ Extended format (full benchmark 26 scenarios)")
        rows = data_loader.extract_extended_rows(data)
    else:
        print("  ✓ Original format (15 scenarios)")
        rows = data_loader.extract_rows(data)

    print(f"  ✓ {len(rows)} test scenarios")

    out_html = str(REPORT_DIR / "pgp_benchmark_report.html")

    print("\n📊 สร้างกราฟ Chart.js...")
    chart_html = charts.build(rows)

    print("📝 สร้าง HTML report...")
    html_builder.build(data, rows, chart_html, out_html)

    print(f"""
╔══════════════════════════════════════════════════╗
║  ✅ รายงานพร้อมแล้ว                              ║
║                                                  ║
║  เปิดไฟล์นี้ด้วย browser ได้เลย:               ║
║  {out_html[-48:]:48}║
╚══════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
