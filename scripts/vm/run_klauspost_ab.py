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
import json, os, subprocess, statistics, pathlib, hashlib, random, sys, time
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
        return pathlib.Path(env)
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
SIZEGRAD = os.getenv("SIZEGRAD", "0") not in ("0", "", "false", "no")
INMEM_CAP_MB = int(os.getenv("INMEM_CAP_MB", "256"))
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
def gen_text(dest, n, size_kb):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    vocab = "the quick brown fox jumps over lazy dog data encrypt secure file process network request response service application".split()
    for i in range(n):
        target = size_kb * 1024
        buf, total = [], 0
        while total < target:
            line = " ".join(rng.choices(vocab, k=rng.randint(8, 20))) + "\n"
            buf.append(line); total += len(line)
        content = ("".join(buf)[:target]).ljust(target)
        (dest / f"file{i:04d}.txt").write_bytes(content.encode("ascii", "replace"))

def gen_csv(dest, n, size_kb):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    for i in range(n):
        target = size_kb * 1024
        buf, total = [], 0
        while total < target:
            row = f"{rng.randint(0,99999)},{rng.randint(0,999)},{rng.randint(0,1)},{rng.random()*1000:.2f}\n"
            buf.append(row); total += len(row)
        content = ("".join(buf)[:target]).ljust(target)
        (dest / f"file{i:04d}.csv").write_bytes(content.encode("ascii", "replace"))

def gen_binary(dest, n, size_kb, ext="dat"):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    nbytes = size_kb * 1024
    for i in range(n):
        # randbytes (Py3.9+) เร็วกว่าการสุ่มทีละไบต์มาก — สำคัญตอน corpus ใหญ่
        (dest / f"file{i:04d}.{ext}").write_bytes(rng.randbytes(nbytes))

def setup_corpus():
    print(f"📁 corpus @ {CORPUS}")
    gen_text(CORPUS / "ft/txt", n=15, size_kb=512);  print("  ✓ txt  15×512KB (compressible)")
    gen_csv(CORPUS / "ft/csv", n=15, size_kb=512);   print("  ✓ csv  15×512KB (compressible)")
    gen_binary(CORPUS / "ft/dat", n=15, size_kb=512); print("  ✓ dat  15×512KB (incompressible)")
    # size gradient (compressible text) — จุดที่ Go เคยแพ้ชัด
    for kb in (10, 100, 512, 1024):
        gen_text(CORPUS / f"size/txt-{kb}kb", n=1, size_kb=kb)
    print("  ✓ size gradient text 10/100/512/1024 KB")

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
def run_one(binary_cmd, variant, corpus_path, out_dir):
    cmd = {
        "command": "run", "variantId": variant,
        "mode": "steady_state", "warmupIterations": WARMUP, "concurrency": 1,
        "cryptoProfile": {"pubAlg": "RSA-2048", "cipher": "AES-256", "compression": "ZLIB", "hash": "SHA-256"},
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
        ops = [o for o in out.get("operations", []) if not o.get("skipped")]
        times = [(o.get("encryptMs", 0) or 0) + (o.get("decryptMs", 0) or 0) for o in ops]
        times = [t for t in times if t > 0]
        if not times:
            return None
        return round(statistics.median(times), 3)
    except Exception as e:
        sys.stderr.write(f"    ERR {variant}: {e}\n")
        return None

def bench(label, corpus_path, out_root, runners_map=RUNNERS):
    binary_cmd, variants = runners_map[label]
    best = {}
    for v in variants:
        samples = []
        for rnd in range(ROUNDS):
            od = out_root / label / v / f"r{rnd}"; od.mkdir(parents=True, exist_ok=True)
            p50 = run_one(binary_cmd, v, corpus_path, od)
            if p50 is not None:
                samples.append(p50); sys.stdout.write(".")
            else:
                sys.stdout.write("x")
            sys.stdout.flush()
        if samples:
            best[v] = {"p50_median": round(statistics.median(samples), 3),
                       "p50_min": round(min(samples), 3),
                       "p50_max": round(max(samples), 3),
                       "rounds": len(samples)}
    return best

def scenario_best_ms(res):
    """เอา variant ที่เร็วสุดของ label นั้นมาเป็นตัวแทน (p50_median ต่ำสุด)"""
    vals = [d["p50_median"] for d in res.values() if d]
    return min(vals) if vals else None

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
          f"BIG={'on (file-count load)' if BIG else 'off'} "
          f"SIZEGRAD={'on (1KB→%dMB/file, inmem cap %dMB)' % (max(SIZEGRAD_STEPS_KB)//1024, INMEM_CAP_MB) if SIZEGRAD else 'off'}")
    print("=" * 64)
    os.system("nproc >/dev/null 2>&1 && echo -n 'cores: ' && nproc || true")

    setup_corpus()
    out_root = CORPUS / "_out"; out_root.mkdir(exist_ok=True)

    # แต่ละ scenario = (ชื่อ, path, runners_map)
    scenarios = [
        ("txt-512KB×15", CORPUS / "ft/txt", RUNNERS),
        ("csv-512KB×15", CORPUS / "ft/csv", RUNNERS),
        ("dat-512KB×15", CORPUS / "ft/dat", RUNNERS),
        ("txt-10KB",     CORPUS / "size/txt-10kb", RUNNERS),
        ("txt-100KB",    CORPUS / "size/txt-100kb", RUNNERS),
        ("txt-512KB",    CORPUS / "size/txt-512kb", RUNNERS),
        ("txt-1MB",      CORPUS / "size/txt-1024kb", RUNNERS),
    ]

    if BIG:
        setup_corpus_prod()
        scenarios += [
            (f"prod-txt-{PROD_TXT_N}", CORPUS / "prod/txt", RUNNERS),
            (f"prod-csv-{PROD_CSV_N}", CORPUS / "prod/csv", RUNNERS),
            (f"prod-pdf-{PROD_PDF_N}", CORPUS / "prod/pdf", RUNNERS),
            (f"prod-zip-{PROD_ZIP_N}", CORPUS / "prod/zip", RUNNERS),
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
                    (f"sg-{ext}-{label_sz}{tag}", CORPUS / f"sizegrad/{ext}/{kb}kb", rmap)
                )
    labels = ["go-stdlib", "go-klauspost"] + (["java"] if have_java else [])

    results = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "rounds": ROUNDS, "warmup": WARMUP, "big": BIG, "sizegrad": SIZEGRAD,
        "prodProfile": ({"txt": [PROD_TXT_N, PROD_TXT_KB], "csv": [PROD_CSV_N, PROD_CSV_KB],
                          "pdf": [PROD_PDF_N, PROD_PDF_KB], "zip": [PROD_ZIP_N, PROD_ZIP_KB]} if BIG else None),
        "sizegradProfile": ({"stepsKB": SIZEGRAD_STEPS_KB, "types": SIZEGRAD_TYPES,
                              "inmemCapMB": INMEM_CAP_MB} if SIZEGRAD else None),
        "branch": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 cwd=REPO, capture_output=True, text=True).stdout.strip(),
        "scenarios": {},
    }

    for sc_name, corpus_path, rmap in scenarios:
        print(f"\n[{sc_name}]  ({len(list(pathlib.Path(corpus_path).iterdir()))} files)")
        sc = {}
        for label in labels:
            print(f"  {label:14s} ", end="")
            sc[label] = bench(label, corpus_path, out_root, runners_map=rmap)
            print()
        results["scenarios"][sc_name] = sc

    results["finishedAt"] = datetime.now(timezone.utc).isoformat()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2))

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

if __name__ == "__main__":
    main()
