"""charts.py — สร้าง Chart.js HTML snippet (ไม่ต้องติดตั้ง library)"""
import json, statistics

def build(rows: list[dict]) -> str:
    # รองรับทั้ง extended rows (sc_id+pub_alg) และ original rows (scenario+pub_alg)
    def _pub_alg(r): return r.get("pub_alg", r.get("pub_alg", "RSA-2048"))
    def _lbl(r):     return r.get("sc_label", r.get("sc_id", r.get("scenario", "")))[:20]

    pub_algs = list(dict.fromkeys(_pub_alg(r) for r in rows))

    # Chart 1 — Go vs Java per scenario (RSA-2048, max 10)
    r2048   = [r for r in rows if _pub_alg(r) == "RSA-2048"][:10]
    c1_lbl  = [_lbl(r) for r in r2048]
    c1_go   = [r["go_p50"]   for r in r2048]
    c1_java = [r["java_p50"] for r in r2048]

    # Chart 2 — Speedup diverging bar (max 15)
    rows15  = rows[:15]
    c2_lbl    = [_lbl(r)[:12]+"/"+_pub_alg(r)[:8] for r in rows15]
    c2_vals   = [r["speedup"] if r["winner"]=="GO" else
                 -r["speedup"] if r["winner"]=="JAVA" else 0 for r in rows15]
    c2_colors = ['"#00ADE8"' if r["winner"]=="GO" else
                 '"#F89820"' if r["winner"]=="JAVA" else '"#95a5a6"' for r in rows15]

    # Chart 3 — by key type
    c3_go, c3_java = [], []
    for alg in pub_algs:
        ar = [r for r in rows if r["pub_alg"] == alg]
        c3_go.append(round(statistics.mean([r["go_p50"]   for r in ar]), 3))
        c3_java.append(round(statistics.mean([r["java_p50"] for r in ar]), 3))

    # Chart 4 — Pie/Doughnut
    go_w   = sum(1 for r in rows if r["winner"] == "GO")
    java_w = sum(1 for r in rows if r["winner"] == "JAVA")
    tie_w  = sum(1 for r in rows if r["winner"] == "TIE")
    total  = len(rows)

    return f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">

  <div class="chart-box">
    <div class="chart-title">① Go vs Java ต่อ Scenario (RSA-2048)
      <div class="chart-sub">p50 round-trip ms — ยิ่งน้อยยิ่งดี</div></div>
    <canvas id="c1"></canvas>
  </div>

  <div class="chart-box">
    <div class="chart-title">② Speedup ทุก Test Case
      <div class="chart-sub">บวก = Go เร็วกว่า / ลบ = Java เร็วกว่า</div></div>
    <canvas id="c2"></canvas>
  </div>

  <div class="chart-box">
    <div class="chart-title">③ เปรียบเทียบตามชนิดกุญแจ
      <div class="chart-sub">ค่าเฉลี่ย latency รวมทุก scenario</div></div>
    <canvas id="c3"></canvas>
  </div>

  <div class="chart-box">
    <div class="chart-title">④ สรุปผล — ชนะกี่ Test Cases
      <div class="chart-sub">จาก {total} test cases ทั้งหมด</div></div>
    <canvas id="c4"></canvas>
  </div>
</div>

<script>
const B="#00ADE8", O="#F89820", G="#95a5a6";
const opts = (ylabel) => ({{
  responsive:true,
  plugins:{{legend:{{position:"top"}},tooltip:{{callbacks:{{label:c=>c.dataset.label+": "+c.parsed.y.toFixed(3)+" ms"}}}}}},
  scales:{{y:{{title:{{display:true,text:ylabel}},grid:{{color:"#f5f5f5"}}}},x:{{grid:{{display:false}}}}}}
}});

new Chart(document.getElementById("c1"),{{type:"bar",
  data:{{labels:{json.dumps(c1_lbl)},
    datasets:[
      {{label:"Go",  data:{json.dumps(c1_go)},  backgroundColor:B,borderRadius:4}},
      {{label:"Java",data:{json.dumps(c1_java)},backgroundColor:O,borderRadius:4}}
    ]}},options:opts("Latency (ms)")}});

new Chart(document.getElementById("c2"),{{type:"bar",
  data:{{labels:{json.dumps(c2_lbl)},
    datasets:[{{label:"Speedup",data:{json.dumps(c2_vals)},
      backgroundColor:[{",".join(c2_colors)}],borderRadius:3}}]}},
  options:{{responsive:true,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>(c.parsed.y>0?"Go ":"Java ")+Math.abs(c.parsed.y).toFixed(1)+"x faster"}}}}}},
    scales:{{y:{{title:{{display:true,text:"Speedup (x)"}},grid:{{color:"#f5f5f5"}}}},
             x:{{ticks:{{maxRotation:45,font:{{size:9}}}},grid:{{display:false}}}}}}}}}});

new Chart(document.getElementById("c3"),{{type:"bar",
  data:{{labels:{json.dumps(pub_algs)},
    datasets:[
      {{label:"Go",  data:{json.dumps(c3_go)},  backgroundColor:B,borderRadius:4}},
      {{label:"Java",data:{json.dumps(c3_java)},backgroundColor:O,borderRadius:4}}
    ]}},options:opts("Avg Latency (ms)")}});

new Chart(document.getElementById("c4"),{{type:"doughnut",
  data:{{labels:["Go ชนะ ({go_w})","Java ชนะ ({java_w})","เสมอ ({tie_w})"],
    datasets:[{{data:[{go_w},{java_w},{tie_w}],backgroundColor:[B,O,G],borderWidth:3,borderColor:"white"}}]}},
  options:{{responsive:true,plugins:{{legend:{{position:"bottom"}}}}}}}});
</script>"""
