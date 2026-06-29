#!/usr/bin/env python3
"""
generate_report.py — entry point หลัก

โครงสร้าง:
  data_loader.py  — โหลด results.json → rows[]
  charts.py       — สร้าง Chart.js HTML snippet (ไม่ต้องติดตั้งอะไร)
  html_builder.py — ประกอบ HTML รายงานเต็ม
  generate_report.py (ไฟล์นี้) — รันทั้งหมด

USAGE:
  python3 generate_report.py                    # หา results.json อัตโนมัติ
  python3 generate_report.py /path/results.json
"""
import sys, pathlib
import data_loader, charts, html_builder


def main():
    # หา results.json
    if len(sys.argv) > 1:
        results_path = sys.argv[1]
    else:
        results_path = data_loader.find_results_json()
        if not results_path:
            print("❌ ไม่พบ results.json")
            print("   usage: python3 generate_report.py /path/to/results.json")
            sys.exit(1)

    print(f"\n🔍 โหลดข้อมูลจาก: {results_path}")
    data = data_loader.load(results_path)
    rows = data_loader.extract_rows(data)
    print(f"  ✓ {len(rows)} test cases")

    out_dir  = pathlib.Path(__file__).parent
    out_html = str(out_dir / "pgp_benchmark_report.html")

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
