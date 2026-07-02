#!/usr/bin/env python3
"""
run_klauspost_ab.py — เทียบ 3 ทางบน VM: go-stdlib vs go-klauspost vs java

เป้าหมาย: วัดผลจริงว่าการสลับ zlib เป็น klauspost ช่วยปิดช่องว่างที่ Go แพ้ Java
บนข้อมูล compressible (txt/csv) ได้แค่ไหน — และไม่ทำให้ incompressible แย่ลง

ต้อง build ก่อน:  bash scripts/vm/build_klauspost_ab.sh
รัน:              python3 scripts/vm/run_klauspost_ab.py

ปรับได้ผ่าน env:
  ROUNDS (default 5), WARMUP (default 3), POC_CORPUS (default อัตโนมัติ)
ผลออกที่: report/results_klauspost_ab.json  (+ ตารางสรุปบน stdout)
"""
import json, os, subprocess, statistics, pathlib, hashlib, random, sys, time, shutil
from datetime import datetime, timezone

# ── ค้น repo root จาก git (ไม่ผูกกับชื่อโฟลเดอร์) ────────────────────────────
REPO = pathlib.Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    cwd=pathlib.Path(__file__).parent, capture_output=True, text=True
).stdout.strip())

KEYS    = REPO / "keys"
GO_DIR  = REPO / "runners/go"
JAR     = REPO / "runners/java/target/java-runner-0.1.0.jar"
OUT_JSON = REPO / "report/results_klauspost_ab.json"

GO_KP  = GO_DIR / "go-runner-klauspost"
GO_STD = GO_DIR / "go-runner-stdlib"

ROUNDS = int(os.getenv("ROUNDS", "5"))
WARMUP = int(os.getenv("WARMUP", "3"))

# BIG = โหมด production-scale (จำนวนไฟล์จริงของระบบเดิม + เผื่อเล็กน้อย, รวม ~300MB)
#   ระบบเดิม: txt 1200 / pdf 300 / csv 400 / zip 20  → เทสสูงกว่าเล็กน้อยเพื่อความปลอดภัย
#   เปิดด้วย: BIG=1 python3 scripts/vm/run_klauspost_ab.py
BIG = os.getenv("BIG", "0") not in ("0", "", "false", "no")
# จำนวนไฟล์ (ปรับได้ผ่าน env) — ดีฟอลต์สูงกว่าระบบเดิมเล็กน้อย
PROD_TXT_N = int(os.getenv("PROD_TXT_N", "1300"))   # เดิม 1200
PROD_CSV_N = int(os.getenv("PROD_CSV_N", "450"))    # เดิม 400
PROD_PDF_N = int(os.getenv("PROD_PDF_N", "350"))    # เดิม 300
PROD_ZIP_N = int(os.getenv("PROD_ZIP_N", "30"))     # เดิม 20
# ขนาดต่อไฟล์ (KB) — เลือกให้รวมทุกสกุล ≈ 300MB
PROD_TXT_KB = int(os.getenv("PROD_TXT_KB", "128"))  # 1300×128KB ≈ 166MB
PROD_CSV_KB = int(os.getenv("PROD_CSV_KB", "128"))  # 450×128KB  ≈ 58MB
PROD_PDF_KB = int(os.getenv("PROD_PDF_KB", "192"))  # 350×192KB  ≈ 70MB
PROD_ZIP_KB = int(os.getenv("PROD_ZIP_KB", "256"))  # 30×256KB   ≈ 8MB
# รวม ≈ 302MB

# corpus: ใช้ tmpfs ถ้าเขียนได้ ไม่งั้น fallback ในบ้าน
def pick_corpus_dir():
    env = os.getenv("POC_CORPUS")
    if env:
        p = pathlib.Path(env); p.mkdir(parents=True, exist_ok=True)
        return p
    for cand in ("/mnt/corpus", "/tmp/corpus-klauspost"):
        try:
            p = pathlib.Path(cand); p.mkdir(parents=True, exist_ok=True)
            (p / ".w").write_text("x"); (p / ".w").unlink()
            return p
        except Exception:
            continue
    p = pathlib.Path.home() / "corpus-klauspost"; p.mkdir(parents=True, exist_ok=True)
    return p

CORPUS = pick_corpus_dir()

# SIZEGRAD = โหมด size gradient: วัด "ขนาดไฟล์มีผลแค่ไหน" ต่อสกุลไฟล์
#   ไฟล์เดียวต่อขนาด ไล่ 1KB → SIZEGRAD_MAX (ดีฟอลต์ 300MB) ครบทุกสกุล
#   in-memory variant ถูกจำกัดที่ INMEM_CAP_MB (256MB ตาม ENVIRONMENT.md);
#   ขนาดใหญ่กว่านั้นวัดเฉพาะ streaming variant (Req 15.4)
#   เปิดด้วย: SIZEGRAD=1 python3 scripts/vm/run_klauspost_ab.py
# FULL = ครอบทุกมิติเท่า run_v5 (6 สกุล × 3 key alg + count gradient + many-small
#        + concurrent) เทียบ 3 ทาง + รวม size gradient ถึง 300MB
#   เปิดด้วย: FULL=1 python3 scripts/vm/run_klauspost_ab.py
FULL = os.getenv("FULL", "0") not in ("0", "", "false", "no")
# key algorithms (ต้องมี key ใน keys/ : rsa2048, rsa4096, cv25519)
FULL_KEY_ALGS = [a.strip() for a in os.getenv("FULL_KEY_ALGS", "RSA-2048,RSA-4096,Curve25519").split(",") if a.strip()]
FULL_FILETYPES = [t.strip() for t in os.getenv("FULL_FILETYPES", "txt,csv,pdf,xlsx,zip,dat").split(",") if t.strip()]
FULL_COUNTS = [int(x) for x in os.getenv("FULL_COUNTS", "1,5,10,25,50,100,200,500,1000").split(",") if x.strip()]
FULL_CONC = [int(x) for x in os.getenv("FULL_CONC", "1,2,4,8").split(",") if x.strip()]

SIZEGRAD = (os.getenv("SIZEGRAD", "0") not in ("0", "", "false", "no")) or FULL
INMEM_CAP_MB = int(os.getenv("INMEM_CAP_MB", "256"))

# FULL ครอบทั้ง size gradient (SIZEGRAD) และ เทสจำนวนไฟล์ตามระบบเดิม (BIG)
# → FULL=1 ครบทั้ง 2 เงื่อนไข: (1) ทุกสกุลถึง 300MB  (2) จำนวนไฟล์ txt/csv/pdf/zip
BIG = BIG or FULL
# สเต็ปขนาด (KB) ปรับได้ผ่าน env SIZEGRAD_STEPS_KB (คั่นด้วย comma)
_DEFAULT_STEPS = "1,64,512,4096,16384,65536,131072,262144,307200"  # 1KB..300MB
SIZEGRAD_STEPS_KB = [int(x) for x in os.getenv("SIZEGRAD_STEPS_KB", _DEFAULT_STEPS).split(",") if x.strip()]
# สกุลไฟล์ที่ทดสอบใน size gradient (txt/csv=compressible, pdf/zip=incompressible)
SIZEGRAD_TYPES = [t.strip() for t in os.getenv("SIZEGRAD_TYPES", "txt,csv,pdf,zip").split(",") if t.strip()]

# แยก variant เป็น in-memory vs streaming เพื่อ gate ตามขนาดไฟล์
GO_INMEM     = ["go-inmem-single"]
GO_STREAM    = ["go-stream-parallel"]
JAVA_INMEM   = ["java-inmem-single"]
JAVA_STREAM  = ["java-stream-parallel"]
GO_VARIANTS   = GO_INMEM + GO_STREAM
JAVA_VARIANTS = JAVA_INMEM + JAVA_STREAM
RUNNERS = {
    "go-stdlib":    ([str(GO_STD)], GO_VARIANTS),
    "go-klauspost": ([str(GO_KP)],  GO_VARIANTS),
    "java":         (["java", "-Xmx3g", "-jar", str(JAR)], JAVA_VARIANTS),
}
# variant เฉพาะ streaming (ใช้เมื่อไฟล์ > INMEM_CAP_MB)
RUNNERS_STREAM_ONLY = {
    "go-stdlib":    ([str(GO_STD)], GO_STREAM),
    "go-klauspost": ([str(GO_KP)],  GO_STREAM),
    "java":         (["java", "-Xmx3g", "-jar", str(JAR)], JAVA_STREAM),
}

# ── checksum helpers (เหมือน harness) ───────────────────────────────────────
def key_cs():
    lines = []
    for f in sorted(KEYS.iterdir()):
        if f.name.endswith(("-public.asc", "-private.asc")):
            lines.append(f.name + ":sha256:" + hashlib.sha256(f.read_bytes()).hexdigest())
    lines.sort()
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()

_CORPUS_CS_CACHE = {}
def corpus_cs(path):
    # cache ต่อ path: corpus ไม่เปลี่ยนระหว่างรัน → ไม่ต้อง hash ซ้ำทุก invocation
    # (สำคัญมากในโหมด BIG ที่ corpus ใหญ่ ~300MB)
    key = str(path)
    if key in _CORPUS_CS_CACHE:
        return _CORPUS_CS_CACHE[key]
    e = []
    for f in sorted(pathlib.Path(path).rglob("*")):
        if f.is_file():
            rel = f.relative_to(path).as_posix()
            e.append((rel, hashlib.sha256(f.read_bytes()).hexdigest()))
    e.sort()
    hh = hashlib.sha256()
    for rel, hx in e:
        hh.update(rel.encode()); hh.update(b"\x00"); hh.update(hx.encode()); hh.update(b"\n")
    val = "sha256:" + hh.hexdigest()
    _CORPUS_CS_CACHE[key] = val
    return val

_KCS = None
def kcs():
    global _KCS
    if _KCS is None:
        _KCS = key_cs()
    return _KCS

# ── corpus generators ──────────────────────────────────────────────────────
# เขียนไฟล์เป็น chunk เพื่อ (1) รองรับไฟล์ใหญ่ 300MB (2) คุม memory
# (3) เลี่ยง rng.randbytes ก้อนใหญ่ที่ overflow C int limit ของ getrandbits)
_GEN_CHUNK = 8 * 1024 * 1024   # 8MB

def gen_text(dest, n, size_kb):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    vocab = "the quick brown fox jumps over lazy dog data encrypt secure file process network request response service application".split()
    nbytes = size_kb * 1024
    for i in range(n):
        with open(dest / f"file{i:04d}.txt", "wb") as f:
            written = 0
            while written < nbytes:
                block, blen = [], 0
                # สร้างทีละบล็อก ~256KB (คำสุ่มสดทุกบรรทัด → compressibility สมจริง)
                while blen < 256 * 1024 and written + blen < nbytes:
                    line = " ".join(rng.choices(vocab, k=rng.randint(8, 20))) + "\n"
                    block.append(line); blen += len(line)
                data = "".join(block).encode("ascii", "replace")
                if written + len(data) > nbytes:
                    data = data[:nbytes - written]
                f.write(data); written += len(data)

def gen_csv(dest, n, size_kb):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    nbytes = size_kb * 1024
    for i in range(n):
        with open(dest / f"file{i:04d}.csv", "wb") as f:
            written = 0
            while written < nbytes:
                block, blen = [], 0
                while blen < 256 * 1024 and written + blen < nbytes:
                    row = f"{rng.randint(0,99999)},{rng.randint(0,999)},{rng.randint(0,1)},{rng.random()*1000:.2f}\n"
                    block.append(row); blen += len(row)
                data = "".join(block).encode("ascii", "replace")
                if written + len(data) > nbytes:
                    data = data[:nbytes - written]
                f.write(data); written += len(data)

def gen_binary(dest, n, size_kb, ext="dat"):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    nbytes = size_kb * 1024
    for i in range(n):
        with open(dest / f"file{i:04d}.{ext}", "wb") as f:
            remaining = nbytes
            while remaining > 0:
                c = min(_GEN_CHUNK, remaining)   # 8MB/chunk → getrandbits ไม่ overflow
                f.write(rng.randbytes(c))
                remaining -= c

def setup_corpus():
    print(f"📁 corpus @ {CORPUS}")
    gen_text(CORPUS / "ft/txt", n=15, size_kb=512);  print("  ✓ txt  15×512KB (compressible)")
    gen_csv(CORPUS / "ft/csv", n=15, size_kb=512);   print("  ✓ csv  15×512KB (compressible)")
    gen_binary(CORPUS / "ft/dat", n=15, size_kb=512); print("  ✓ dat  15×512KB (incompressible)")
    # size gradient (compressible text) — จุดที่ Go เคยแพ้ชัด
    for kb in (10, 100, 512, 1024):
        gen_text(CORPUS / f"size/txt-{kb}kb", n=1, size_kb=kb)
    print("  ✓ size gradient text 10/100/512/1024 KB")

def gen_filetype(dest, ext, n, size_kb):
    """สร้าง n ไฟล์ตามสกุล: txt/csv=บีบได้, pdf/xlsx/zip/dat=บีบไม่ได้"""
    if ext == "txt":
        gen_text(dest, n=n, size_kb=size_kb)
    elif ext == "csv":
        gen_csv(dest, n=n, size_kb=size_kb)
    else:
        gen_binary(dest, n=n, size_kb=size_kb, ext=ext)

def setup_corpus_full():
    """corpus ครบเท่า run_v5: filetypes / count-gradient / many-small / concurrent"""
    print("🗂️  FULL corpus (เท่า run_v5) — สร้างสักครู่")
    # 1) filetype matrix: 6 สกุล × 15 ไฟล์ × 512KB
    for ft in FULL_FILETYPES:
        gen_filetype(CORPUS / f"ft/{ft}", ft, n=15, size_kb=512)
    print(f"  ✓ filetypes: {','.join(FULL_FILETYPES)} (15×512KB)")
    # 2) count gradient: 100KB binary, จำนวนต่างๆ
    for c in FULL_COUNTS:
        gen_binary(CORPUS / f"count/{c}", n=c, size_kb=100, ext="dat")
    print(f"  ✓ count gradient: {FULL_COUNTS} × 100KB")
    # 3) many-small: text
    for name, n, kb in [("1kb", 200, 1), ("10kb", 200, 10), ("100kb", 100, 100)]:
        gen_text(CORPUS / f"many/{name}", n=n, size_kb=kb)
    print("  ✓ many-small: 1kb×200, 10kb×200, 100kb×100")
    # 4) concurrent: 100 × 1MB binary
    gen_binary(CORPUS / "conc", n=100, size_kb=1024, ext="dat")
    print("  ✓ concurrent corpus: 100×1MB")

def gen_one(dest, ext, size_kb):
    """สร้างไฟล์เดียวขนาด size_kb ตามสกุล (txt/csv=บีบได้, pdf/zip/dat=บีบไม่ได้)"""
    if ext == "txt":
        gen_text(dest, n=1, size_kb=size_kb)
    elif ext == "csv":
        gen_csv(dest, n=1, size_kb=size_kb)
    else:  # pdf, zip, dat → incompressible
        gen_binary(dest, n=1, size_kb=size_kb, ext=ext)

def setup_corpus_sizegrad():
    """size gradient: ไฟล์เดียวต่อขนาด ไล่ตาม SIZEGRAD_STEPS_KB ครบทุกสกุล"""
    mx = max(SIZEGRAD_STEPS_KB) / 1024
    print(f"📏 SIZEGRAD corpus @ {CORPUS}/sizegrad  (max {mx:.0f} MB/ไฟล์, สกุล: {','.join(SIZEGRAD_TYPES)})")
    for ext in SIZEGRAD_TYPES:
        for kb in SIZEGRAD_STEPS_KB:
            gen_one(CORPUS / f"sizegrad/{ext}/{kb}kb", ext, kb)
    print(f"  ✓ {len(SIZEGRAD_TYPES)}สกุล × {len(SIZEGRAD_STEPS_KB)}ขนาด ({SIZEGRAD_STEPS_KB[0]}KB..{SIZEGRAD_STEPS_KB[-1]}KB)")

def setup_corpus_prod():
    """corpus ระดับ production จริง (BIG) — จำนวนไฟล์ตามระบบเดิม+เผื่อ, รวม ~300MB"""
    total_mb = (PROD_TXT_N*PROD_TXT_KB + PROD_CSV_N*PROD_CSV_KB
                + PROD_PDF_N*PROD_PDF_KB + PROD_ZIP_N*PROD_ZIP_KB) / 1024
    print(f"📦 PROD corpus @ {CORPUS}/prod  (รวม ≈ {total_mb:.0f} MB) — อาจใช้เวลาสร้างสักครู่")
    gen_text(CORPUS / "prod/txt", n=PROD_TXT_N, size_kb=PROD_TXT_KB)
    print(f"  ✓ txt  {PROD_TXT_N}×{PROD_TXT_KB}KB (compressible)")
    gen_csv(CORPUS / "prod/csv", n=PROD_CSV_N, size_kb=PROD_CSV_KB)
    print(f"  ✓ csv  {PROD_CSV_N}×{PROD_CSV_KB}KB (compressible)")
    gen_binary(CORPUS / "prod/pdf", n=PROD_PDF_N, size_kb=PROD_PDF_KB, ext="pdf")
    print(f"  ✓ pdf  {PROD_PDF_N}×{PROD_PDF_KB}KB (incompressible)")
    gen_binary(CORPUS / "prod/zip", n=PROD_ZIP_N, size_kb=PROD_ZIP_KB, ext="zip")
    print(f"  ✓ zip  {PROD_ZIP_N}×{PROD_ZIP_KB}KB (incompressible)")

# ── run one (binary,variant) → p50 ms ──────────────────────────────────────
def run_one(binary_cmd, variant, corpus_path, out_dir, pub_alg="RSA-2048", concurrency=1):
    cmd = {
        "command": "run", "variantId": variant,
        "mode": "steady_state", "warmupIterations": WARMUP, "concurrency": concurrency,
        "cryptoProfile": {"pubAlg": pub_alg, "cipher": "AES-256", "compression": "ZLIB", "hash": "SHA-256"},
        "outputEncoding": "binary",
        "keySetPath": str(KEYS), "keySetChecksum": kcs(),
        "corpusPath": str(corpus_path), "corpusChecksum": corpus_cs(corpus_path),
        "outputDir": str(out_dir), "operation": "roundtrip",
    }
    try:
        r = subprocess.run(binary_cmd, input=json.dumps(cmd).encode(),
                           capture_output=True, timeout=600)
        if r.returncode not in (0, 2):
            return None
        out = json.loads(r.stdout)
        ops_all = out.get("operations", [])
        ops = [o for o in ops_all if not o.get("skipped")]
        n_skipped = sum(1 for o in ops_all if o.get("skipped"))
        enc = [o.get("encryptMs") or 0 for o in ops]
        dec = [o.get("decryptMs") or 0 for o in ops]
        tot = [e + d for e, d in zip(enc, dec)]
        tot_nz = [t for t in tot if t > 0]
        if not tot_nz:
            return None
        orig = sum(o.get("originalBytes", 0) or 0 for o in ops)
        ct = sum((o.get("ciphertextBytes") or 0) for o in ops)
        ok = sum(1 for o in ops if o.get("roundTripOk"))
        total_s = sum(tot) / 1000.0
        return {
            "p50": round(_pct(tot_nz, 50), 3),
            "p95": round(_pct(tot_nz, 95), 3),
            "enc_p50": round(_pct([e for e in enc if e > 0] or [0], 50), 3),
            "dec_p50": round(_pct([d for d in dec if d > 0] or [0], 50), 3),
            "mbps": round((orig / 1048576) / total_s, 2) if total_s > 0 else 0.0,
            "ratio": round(orig / ct, 3) if ct > 0 else 0.0,
            "ok_ratio": round(ok / len(ops), 4) if ops else 0.0,
            "n": len(ops),
            "skipped": n_skipped,
        }
    except Exception as e:
        sys.stderr.write(f"    ERR {variant}: {e}\n")
        return None

def _pct(xs, q):
    """quantile แบบง่าย (nearest-rank) — q เป็นเปอร์เซ็นต์ 0..100"""
    if not xs:
        return 0.0
    s = sorted(xs)
    idx = max(0, min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1)))))
    return s[idx]

def _median(xs):
    return round(statistics.median(xs), 3) if xs else 0.0

def bench(label, corpus_path, out_root, runners_map=RUNNERS, pub_alg="RSA-2048", concurrency=1):
    binary_cmd, variants = runners_map[label]
    best = {}
    for v in variants:
        rounds = []
        for rnd in range(ROUNDS):
            od = out_root / label / v / f"r{rnd}"; od.mkdir(parents=True, exist_ok=True)
            m = run_one(binary_cmd, v, corpus_path, od, pub_alg=pub_alg, concurrency=concurrency)
            if m is not None:
                rounds.append(m); sys.stdout.write(".")
            else:
                sys.stdout.write("x")
            sys.stdout.flush()
            # ลบ output ciphertext ทันที (เราเก็บแค่ timing จาก stdout) — กัน disk เต็ม
            # ตอนรันไฟล์ใหญ่ 300MB ที่เขียน output สะสมได้มหาศาล
            shutil.rmtree(od, ignore_errors=True)
        if rounds:
            # aggregate = median ข้ามรอบ ของแต่ละ metric
            agg = {k: _median([r[k] for r in rounds])
                   for k in ("p50", "p95", "enc_p50", "dec_p50", "mbps", "ratio", "ok_ratio")}
            agg["n"] = rounds[0]["n"]
            agg["rounds"] = len(rounds)
            # correctness guard (anti-v2): worst-case ข้ามรอบ
            agg["ok_ratio_min"] = min(r["ok_ratio"] for r in rounds)
            agg["skipped_max"] = max(r.get("skipped", 0) for r in rounds)
            best[v] = agg
    return best

def scenario_best_variant(res):
    """คืน (ชื่อ variant, metrics) ของ variant ที่ p50 ต่ำสุดใน label นั้น"""
    best = None
    for vname, d in res.items():
        if not d:
            continue
        if best is None or d["p50"] < best[1]["p50"]:
            best = (vname, d)
    return best

def scenario_best_ms(res):
    """p50 ของ variant เร็วสุดใน 1 label"""
    bv = scenario_best_variant(res)
    return bv[1]["p50"] if bv else None

# ── Prometheus textfile export (ให้ node_exporter textfile collector หยิบไป) ──
# node_exporter ที่รันบน VM 122:9100 อ่านไฟล์ .prom ในโฟลเดอร์ textfile collector
# แล้ว expose ให้ Prometheus (CT200:9090) scrape → โชว์บน Grafana ได้เลย
NODE_TEXTFILE_DIR = os.getenv("NODE_EXPORTER_TEXTFILE_DIR", "/var/lib/node_exporter/textfile_collector")

def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')

def write_prometheus(results):
    """เขียน metrics เป็น .prom (atomic) ให้ node_exporter textfile collector"""
    metrics = {
        "pgp_bench_roundtrip_p50_ms": ("gauge", "median encrypt+decrypt time per file (ms)"),
        "pgp_bench_roundtrip_p95_ms": ("gauge", "p95 encrypt+decrypt time per file (ms)"),
        "pgp_bench_encrypt_p50_ms":   ("gauge", "median encrypt-only time per file (ms)"),
        "pgp_bench_decrypt_p50_ms":   ("gauge", "median decrypt-only time per file (ms)"),
        "pgp_bench_throughput_mbps":  ("gauge", "throughput MB/s (orig bytes / crypto time)"),
        "pgp_bench_compression_ratio":("gauge", "orig/ciphertext size ratio"),
        "pgp_bench_roundtrip_ok_ratio":("gauge", "fraction of files with byte-for-byte roundtrip ok"),
        "pgp_bench_files":            ("gauge", "number of files measured"),
    }
    field = {
        "pgp_bench_roundtrip_p50_ms": "p50", "pgp_bench_roundtrip_p95_ms": "p95",
        "pgp_bench_encrypt_p50_ms": "enc_p50", "pgp_bench_decrypt_p50_ms": "dec_p50",
        "pgp_bench_throughput_mbps": "mbps", "pgp_bench_compression_ratio": "ratio",
        "pgp_bench_roundtrip_ok_ratio": "ok_ratio", "pgp_bench_files": "n",
    }
    branch = results.get("branch", "")
    samples = {m: [] for m in metrics}
    speedup = []  # (labels, value)

    for sc_name, sc in results["scenarios"].items():
        for label, res in sc.items():         # label = go-stdlib/go-klauspost/java
            for vname, d in (res or {}).items():
                lbl = f'impl="{_esc(label)}",variant="{_esc(vname)}",scenario="{_esc(sc_name)}",branch="{_esc(branch)}"'
                for m, f in field.items():
                    if f in d:
                        samples[m].append((lbl, d[f]))
        # speedup: go-klauspost เทียบ stdlib / java (ใช้ variant เร็วสุดของแต่ละ label)
        kp = scenario_best_ms(sc.get("go-klauspost", {}))
        std = scenario_best_ms(sc.get("go-stdlib", {}))
        jv = scenario_best_ms(sc.get("java", {}))
        if kp and std:
            speedup.append((f'scenario="{_esc(sc_name)}",baseline="stdlib",branch="{_esc(branch)}"', round(std / kp, 3)))
        if kp and jv:
            speedup.append((f'scenario="{_esc(sc_name)}",baseline="java",branch="{_esc(branch)}"', round(jv / kp, 3)))

    lines = []
    for m, (mtype, help_) in metrics.items():
        lines.append(f"# HELP {m} {help_}")
        lines.append(f"# TYPE {m} {mtype}")
        for lbl, val in samples[m]:
            lines.append(f"{m}{{{lbl}}} {val}")
    lines.append("# HELP pgp_bench_speedup_ratio klauspost speedup vs baseline (>1 = faster)")
    lines.append("# TYPE pgp_bench_speedup_ratio gauge")
    for lbl, val in speedup:
        lines.append(f"pgp_bench_speedup_ratio{{{lbl}}} {val}")
    lines.append("")

    dest_dir = pathlib.Path(NODE_TEXTFILE_DIR)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"⚠ เขียน Prometheus textfile ไม่ได้ ({dest_dir}: {e})")
        print(f"  → ตั้ง env NODE_EXPORTER_TEXTFILE_DIR ให้ตรงกับ --collector.textfile.directory ของ node_exporter")
        return None
    dest = dest_dir / "pgp_bench.prom"
    tmp = dest_dir / "pgp_bench.prom.tmp"
    tmp.write_text("\n".join(lines))
    tmp.replace(dest)   # atomic rename (node_exporter อ่านไฟล์ครบเสมอ)
    return dest

def main():
    for b in (GO_KP, GO_STD):
        if not b.exists():
            print(f"❌ ไม่พบ {b} — รัน build_klauspost_ab.sh ก่อน"); sys.exit(1)
    have_java = JAR.exists()
    if not have_java:
        print(f"⚠ ไม่พบ {JAR} — จะเทียบเฉพาะ go-stdlib vs go-klauspost")

    print("=" * 64)
    print("klauspost A/B/C benchmark  (go-stdlib vs go-klauspost vs java)")
    print(f"ROUNDS={ROUNDS} WARMUP={WARMUP} "
          f"FULL={'on (run_v5-equivalent matrix)' if FULL else 'off'} "
          f"BIG={'on (file-count load)' if BIG else 'off'} "
          f"SIZEGRAD={'on (1KB→%dMB/file, inmem cap %dMB)' % (max(SIZEGRAD_STEPS_KB)//1024, INMEM_CAP_MB) if SIZEGRAD else 'off'}")
    print("=" * 64)
    os.system("nproc >/dev/null 2>&1 && echo -n 'cores: ' && nproc || true")

    out_root = CORPUS / "_out"; out_root.mkdir(parents=True, exist_ok=True)

    # แต่ละ scenario = (ชื่อ, path, runners_map, pub_alg, concurrency)
    def SC(name, path, rmap=RUNNERS, alg="RSA-2048", conc=1):
        return (name, path, rmap, alg, conc)

    scenarios = []

    if not FULL:
        # ชุด quick (ดีฟอลต์) — ข้ามเมื่อ FULL เพราะซ้ำกับ matrix ด้านล่าง
        setup_corpus()
        scenarios += [
            SC("txt-512KB×15", CORPUS / "ft/txt"),
            SC("csv-512KB×15", CORPUS / "ft/csv"),
            SC("dat-512KB×15", CORPUS / "ft/dat"),
            SC("txt-10KB",     CORPUS / "size/txt-10kb"),
            SC("txt-100KB",    CORPUS / "size/txt-100kb"),
            SC("txt-512KB",    CORPUS / "size/txt-512kb"),
            SC("txt-1MB",      CORPUS / "size/txt-1024kb"),
        ]

    if FULL:
        setup_corpus_full()
        # 1) filetype matrix: 6 สกุล × 3 key alg
        for ft in FULL_FILETYPES:
            for alg in FULL_KEY_ALGS:
                scenarios.append(SC(f"ft-{ft}-{alg}", CORPUS / f"ft/{ft}", RUNNERS, alg, 1))
        # 2) count gradient: 100KB binary, RSA-2048
        for c in FULL_COUNTS:
            scenarios.append(SC(f"count-{c}", CORPUS / f"count/{c}", RUNNERS, "RSA-2048", 1))
        # 3) many-small: text, RSA-2048
        for name in ("1kb", "10kb", "100kb"):
            scenarios.append(SC(f"many-{name}", CORPUS / f"many/{name}", RUNNERS, "RSA-2048", 1))
        # 4) concurrent: stream-parallel เท่านั้น, concurrency 1/2/4/8
        for cl in FULL_CONC:
            scenarios.append(SC(f"conc-{cl}", CORPUS / "conc", RUNNERS_STREAM_ONLY, "RSA-2048", cl))

    if BIG:
        setup_corpus_prod()
        scenarios += [
            SC(f"prod-txt-{PROD_TXT_N}", CORPUS / "prod/txt"),
            SC(f"prod-csv-{PROD_CSV_N}", CORPUS / "prod/csv"),
            SC(f"prod-pdf-{PROD_PDF_N}", CORPUS / "prod/pdf"),
            SC(f"prod-zip-{PROD_ZIP_N}", CORPUS / "prod/zip"),
        ]

    if SIZEGRAD:
        setup_corpus_sizegrad()
        for ext in SIZEGRAD_TYPES:
            for kb in SIZEGRAD_STEPS_KB:
                # ไฟล์ > INMEM_CAP_MB → วัดเฉพาะ streaming (กัน OOM in-memory)
                rmap = RUNNERS_STREAM_ONLY if (kb / 1024) > INMEM_CAP_MB else RUNNERS
                tag = "S" if rmap is RUNNERS_STREAM_ONLY else ""
                label_sz = f"{kb//1024}MB" if kb >= 1024 else f"{kb}KB"
                scenarios.append(
                    SC(f"sg-{ext}-{label_sz}{tag}", CORPUS / f"sizegrad/{ext}/{kb}kb", rmap)
                )
    labels = ["go-stdlib", "go-klauspost"] + (["java"] if have_java else [])

    results = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "rounds": ROUNDS, "warmup": WARMUP, "full": FULL, "big": BIG, "sizegrad": SIZEGRAD,
        "fullProfile": ({"keyAlgs": FULL_KEY_ALGS, "filetypes": FULL_FILETYPES,
                          "counts": FULL_COUNTS, "concurrency": FULL_CONC} if FULL else None),
        "prodProfile": ({"txt": [PROD_TXT_N, PROD_TXT_KB], "csv": [PROD_CSV_N, PROD_CSV_KB],
                          "pdf": [PROD_PDF_N, PROD_PDF_KB], "zip": [PROD_ZIP_N, PROD_ZIP_KB]} if BIG else None),
        "sizegradProfile": ({"stepsKB": SIZEGRAD_STEPS_KB, "types": SIZEGRAD_TYPES,
                              "inmemCapMB": INMEM_CAP_MB} if SIZEGRAD else None),
        "branch": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 cwd=REPO, capture_output=True, text=True).stdout.strip(),
        "scenarios": {},
    }

    for sc_name, corpus_path, rmap, alg, conc in scenarios:
        nfiles = len(list(pathlib.Path(corpus_path).iterdir()))
        extra = f" alg={alg}" + (f" conc={conc}" if conc != 1 else "")
        print(f"\n[{sc_name}]  ({nfiles} files{extra})")
        sc = {}
        for label in labels:
            print(f"  {label:14s} ", end="")
            sc[label] = bench(label, corpus_path, out_root, runners_map=rmap,
                              pub_alg=alg, concurrency=conc)
            print()
        results["scenarios"][sc_name] = sc

    results["finishedAt"] = datetime.now(timezone.utc).isoformat()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2))

    # export ให้ Grafana ผ่าน node_exporter textfile collector
    prom = write_prometheus(results)
    if prom:
        print(f"📈 Prometheus textfile: {prom}  (node_exporter จะ expose ให้ Prometheus scrape)")

    # ── ตารางสรุป (ms ต่ำสุดต่อ label + speedup) ──────────────────────────
    print("\n" + "=" * 72)
    print("สรุป (p50 ms, ใช้ variant เร็วสุดของแต่ละ label)")
    print("=" * 72)
    hdr = f"{'scenario':14s} | {'go-stdlib':>10s} | {'go-kp':>10s} | {'java':>10s} | {'kp vs std':>9s} | {'kp vs java':>10s}"
    print(hdr); print("-" * len(hdr))
    for sc_name, sc in results["scenarios"].items():
        std = scenario_best_ms(sc.get("go-stdlib", {}))
        kp  = scenario_best_ms(sc.get("go-klauspost", {}))
        jv  = scenario_best_ms(sc.get("java", {})) if have_java else None
        def f(x): return f"{x:10.3f}" if x is not None else f"{'-':>10s}"
        sp_std = f"{std/kp:8.2f}x" if (std and kp) else f"{'-':>9s}"
        sp_jv  = f"{jv/kp:9.2f}x" if (jv and kp) else f"{'-':>10s}"
        print(f"{sc_name:14s} | {f(std)} | {f(kp)} | {f(jv)} | {sp_std:>9s} | {sp_jv:>10s}")

    print(f"\n✅ ผลบันทึกที่: {OUT_JSON}")
    print("   (kp vs std = go-stdlib/go-klauspost ; kp vs java = java/go-klauspost ; >1 = klauspost เร็วกว่า)")

    # ── correctness guard (กันวัดผลผิดแบบ v2) ────────────────────────────
    problems = []
    for sc_name, sc in results["scenarios"].items():
        for label, res in sc.items():
            for vname, d in (res or {}).items():
                if d.get("ok_ratio_min", 1.0) < 1.0:
                    problems.append(f"{sc_name}/{label}/{vname}: roundTripOk<100% (min={d['ok_ratio_min']})")
                if d.get("skipped_max", 0) > 0:
                    problems.append(f"{sc_name}/{label}/{vname}: มีไฟล์ถูก skip ({d['skipped_max']})")
    if problems:
        print("\n" + "!" * 72)
        print("❌❌ พบปัญหา correctness — ผลลัพธ์อาจไม่น่าเชื่อถือ (อย่าใช้ตัดสินใจ):")
        for p in problems[:50]:
            print("   - " + p)
        print("!" * 72)
    else:
        print("🔒 correctness: roundTripOk 100% และไม่มีไฟล์ถูก skip ทุก scenario/variant")

if __name__ == "__main__":
    main()
