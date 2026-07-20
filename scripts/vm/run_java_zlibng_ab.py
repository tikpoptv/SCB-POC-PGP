#!/usr/bin/env python3
"""
run_java_zlibng_ab.py — POC: Java comeback ด้วย zlib-ng ได้แค่ไหน?

เทียบ 3 ทางบน VM: java (libz ระบบ) vs java-zlibng (LD_PRELOAD zlib-ng) vs
go-klauspost (เป้าที่ Java ต้องไล่) — ไม่แก้โค้ด Java เลย เพราะ Deflater ของ JDK
link กับ libz.so แบบ dynamic → LD_PRELOAD สลับ implementation ได้ทั้งก้อน
(zlib-ng โหมด ZLIB_COMPAT ให้ zlib stream มาตรฐาน → PGP ที่ได้ gpg ถอดได้ปกติ)

คัดลอกโครงจาก run_klauspost_ab.py (a913595) แบบตั้งใจ — แยกไฟล์เพื่อ:
  - ผลออกไฟล์ใหม่ results_java_zlibng_ab.json (ไม่ทับผล FULL run เดิม)
  - ไม่ export .prom (กันทับ pgp_bench.prom ของ FULL run บน Grafana)
  - scenario ชุดเล็ก (~30–60 นาที) ไม่ใช่ matrix เต็ม

เตรียมบน VM ก่อน (ครั้งเดียว):
  sudo apt install -y cmake build-essential
  git clone --depth 1 https://github.com/zlib-ng/zlib-ng ~/zlib-ng
  cd ~/zlib-ng && cmake -B build -DZLIB_COMPAT=ON . && cmake --build build -j
  # ได้ ~/zlib-ng/build/libz.so.1

รัน:  ZLIBNG_LIB=$HOME/zlib-ng/build/libz.so.1 \
      POC_CORPUS=$HOME/corpus-zlibng ROUNDS=5 WARMUP=3 \
      python3 scripts/vm/run_java_zlibng_ab.py
ผลออกที่: report/results_java_zlibng_ab.json  (+ ตารางสรุปบน stdout)
"""
import json, os, subprocess, statistics, pathlib, hashlib, random, sys, shutil
from datetime import datetime, timezone

# ── ค้น repo root จาก git (ไม่ผูกกับชื่อโฟลเดอร์) ────────────────────────────
REPO = pathlib.Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    cwd=pathlib.Path(__file__).parent, capture_output=True, text=True
).stdout.strip())

KEYS    = REPO / "keys"
GO_DIR  = REPO / "runners/go"
JAR     = REPO / "runners/java/target/java-runner-0.1.0.jar"
OUT_JSON = REPO / "report/results_java_zlibng_ab.json"

GO_KP = GO_DIR / "go-runner-klauspost"

ROUNDS = int(os.getenv("ROUNDS", "5"))
WARMUP = int(os.getenv("WARMUP", "3"))

# zlib-ng shared lib (build ด้วย -DZLIB_COMPAT=ON)
ZLIBNG_LIB = os.getenv("ZLIBNG_LIB", str(pathlib.Path.home() / "zlib-ng/build/libz.so.1"))

# corpus: ใช้ tmpfs ถ้าเขียนได้ ไม่งั้น fallback ในบ้าน
def pick_corpus_dir():
    env = os.getenv("POC_CORPUS")
    if env:
        p = pathlib.Path(env); p.mkdir(parents=True, exist_ok=True)
        return p
    for cand in ("/mnt/corpus", "/tmp/corpus-zlibng"):
        try:
            p = pathlib.Path(cand); p.mkdir(parents=True, exist_ok=True)
            (p / ".w").write_text("x"); (p / ".w").unlink()
            return p
        except Exception:
            continue
    p = pathlib.Path.home() / "corpus-zlibng"; p.mkdir(parents=True, exist_ok=True)
    return p

CORPUS = pick_corpus_dir()

# ขนาด size gradient (KB) — subset ที่ gap ชัด: 1MB / 16MB / 128MB
SIZEGRAD_STEPS_KB = [int(x) for x in os.getenv("SIZEGRAD_STEPS_KB", "1024,16384,131072").split(",") if x.strip()]
INMEM_CAP_MB = int(os.getenv("INMEM_CAP_MB", "256"))

# แยก variant เป็น in-memory vs streaming เพื่อ gate ตามขนาดไฟล์
GO_INMEM     = ["go-inmem-single"]
GO_STREAM    = ["go-stream-parallel"]
JAVA_INMEM   = ["java-inmem-single"]
JAVA_STREAM  = ["java-stream-parallel"]
GO_VARIANTS   = GO_INMEM + GO_STREAM
JAVA_VARIANTS = JAVA_INMEM + JAVA_STREAM

JAVA_CMD = ["java", "-Xmx3g", "-jar", str(JAR)]
# LD_PRELOAD ผ่าน env prefix → run_one/bench ใช้ subprocess เดิมได้ไม่ต้องแก้
JAVA_ZLIBNG_CMD = ["env", f"LD_PRELOAD={ZLIBNG_LIB}"] + JAVA_CMD

RUNNERS = {
    "java":         (JAVA_CMD,        JAVA_VARIANTS),
    "java-zlibng":  (JAVA_ZLIBNG_CMD, JAVA_VARIANTS),
    "go-klauspost": ([str(GO_KP)],    GO_VARIANTS),
}
# variant เฉพาะ streaming (ใช้เมื่อไฟล์ > INMEM_CAP_MB)
RUNNERS_STREAM_ONLY = {
    "java":         (JAVA_CMD,        JAVA_STREAM),
    "java-zlibng":  (JAVA_ZLIBNG_CMD, JAVA_STREAM),
    "go-klauspost": ([str(GO_KP)],    GO_STREAM),
}
LABELS = ["java", "java-zlibng", "go-klauspost"]

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

# ── corpus generators (chunked เหมือนตัวเต็ม — รองรับไฟล์ใหญ่) ───────────────
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
                c = min(_GEN_CHUNK, remaining)
                f.write(rng.randbytes(c))
                remaining -= c

def setup_corpus():
    print(f"📁 corpus @ {CORPUS}")
    gen_text(CORPUS / "ft/txt", n=15, size_kb=512);   print("  ✓ txt  15×512KB (compressible — สนามหลัก)")
    gen_csv(CORPUS / "ft/csv", n=15, size_kb=512);    print("  ✓ csv  15×512KB (compressible)")
    gen_binary(CORPUS / "ft/dat", n=15, size_kb=512); print("  ✓ dat  15×512KB (incompressible — control)")
    for kb in SIZEGRAD_STEPS_KB:
        gen_text(CORPUS / f"sg/txt-{kb}kb", n=1, size_kb=kb)
        gen_csv(CORPUS / f"sg/csv-{kb}kb", n=1, size_kb=kb)
    steps = ",".join(f"{kb//1024}MB" if kb >= 1024 else f"{kb}KB" for kb in SIZEGRAD_STEPS_KB)
    print(f"  ✓ size gradient txt+csv: {steps}")

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
    if not xs:
        return 0.0
    s = sorted(xs)
    idx = max(0, min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1)))))
    return s[idx]

def _median(xs):
    return round(statistics.median(xs), 3) if xs else 0.0

def bench(label, corpus_path, out_root, runners_map, pub_alg="RSA-2048", concurrency=1):
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
            shutil.rmtree(od, ignore_errors=True)
        if rounds:
            agg = {k: _median([r[k] for r in rounds])
                   for k in ("p50", "p95", "enc_p50", "dec_p50", "mbps", "ratio", "ok_ratio")}
            agg["n"] = rounds[0]["n"]
            agg["rounds"] = len(rounds)
            agg["ok_ratio_min"] = min(r["ok_ratio"] for r in rounds)
            agg["skipped_max"] = max(r.get("skipped", 0) for r in rounds)
            best[v] = agg
    return best

def scenario_best_variant(res):
    best = None
    for vname, d in res.items():
        if not d:
            continue
        if best is None or d["p50"] < best[1]["p50"]:
            best = (vname, d)
    return best

def scenario_best_ms(res):
    bv = scenario_best_variant(res)
    return bv[1]["p50"] if bv else None

# ── preload sanity gate ─────────────────────────────────────────────────────
def verify_preload():
    """LD_PRELOAD ล้มแบบเงียบ (แค่ warning บน stderr แล้วรันต่อด้วย libz เดิม)
    → ตัวเลขจะออกมาเท่า java เดิมโดยไม่มี error ต้องดักก่อนรันจริง"""
    lib = pathlib.Path(ZLIBNG_LIB)
    if not lib.exists():
        print(f"❌ ไม่พบ zlib-ng ที่ {lib} — build ก่อน (ดู docstring) หรือตั้ง env ZLIBNG_LIB")
        sys.exit(1)
    r = subprocess.run(["env", f"LD_PRELOAD={lib}", "java", "-version"],
                       capture_output=True, text=True, timeout=60)
    err = r.stderr or ""
    if "cannot be preloaded" in err or "ERROR: ld.so" in err:
        print(f"❌ LD_PRELOAD ล้มเหลว:\n{err.strip()}")
        sys.exit(1)
    # zlib-ng รายงานเวอร์ชันรูปแบบ "1.x.y.zlib-ng" ผ่าน zlibVersion() —
    # เช็คผ่าน strings ของ lib ว่ามี marker จริง (กันหยิบ libz ปกติมาผิดไฟล์)
    s = subprocess.run(["strings", str(lib)], capture_output=True, text=True)
    if "zlib-ng" not in (s.stdout or ""):
        print(f"⚠ {lib} ไม่มี marker 'zlib-ng' ข้างใน — แน่ใจนะว่า build จาก zlib-ng (ZLIB_COMPAT)?")
        sys.exit(1)
    print(f"🔗 preload OK: {lib} (java -version รันผ่าน, พบ marker zlib-ng)")

def main():
    if not GO_KP.exists():
        print(f"❌ ไม่พบ {GO_KP} — รัน build_klauspost_ab.sh ก่อน"); sys.exit(1)
    if not JAR.exists():
        print(f"❌ ไม่พบ {JAR} — POC นี้เทียบ Java เป็นหลัก ขาดไม่ได้"); sys.exit(1)
    verify_preload()

    print("=" * 64)
    print("Java zlib-ng A/B  (java vs java+LD_PRELOAD zlib-ng vs go-klauspost)")
    print(f"ROUNDS={ROUNDS} WARMUP={WARMUP} steps={SIZEGRAD_STEPS_KB}KB inmem_cap={INMEM_CAP_MB}MB")
    print("=" * 64)

    out_root = CORPUS / "_out"; out_root.mkdir(parents=True, exist_ok=True)
    setup_corpus()

    def SC(name, path, rmap=RUNNERS):
        return (name, path, rmap)

    scenarios = [
        SC("txt-512KB×15", CORPUS / "ft/txt"),
        SC("csv-512KB×15", CORPUS / "ft/csv"),
        SC("dat-512KB×15", CORPUS / "ft/dat"),
    ]
    for kb in SIZEGRAD_STEPS_KB:
        rmap = RUNNERS_STREAM_ONLY if (kb / 1024) > INMEM_CAP_MB else RUNNERS
        tag = "S" if rmap is RUNNERS_STREAM_ONLY else ""
        label_sz = f"{kb//1024}MB" if kb >= 1024 else f"{kb}KB"
        scenarios.append(SC(f"sg-txt-{label_sz}{tag}", CORPUS / f"sg/txt-{kb}kb", rmap))
        scenarios.append(SC(f"sg-csv-{label_sz}{tag}", CORPUS / f"sg/csv-{kb}kb", rmap))

    results = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "rounds": ROUNDS, "warmup": WARMUP,
        "zlibngLib": ZLIBNG_LIB,
        "sizegradStepsKB": SIZEGRAD_STEPS_KB,
        "branch": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 cwd=REPO, capture_output=True, text=True).stdout.strip(),
        "scenarios": {},
    }

    for sc_name, corpus_path, rmap in scenarios:
        nfiles = len(list(pathlib.Path(corpus_path).iterdir()))
        print(f"\n[{sc_name}]  ({nfiles} files)")
        sc = {}
        for label in LABELS:
            print(f"  {label:14s} ", end="")
            sc[label] = bench(label, corpus_path, out_root, runners_map=rmap)
            print()
        results["scenarios"][sc_name] = sc

    results["finishedAt"] = datetime.now(timezone.utc).isoformat()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2))

    # ── ตารางสรุป: zlib-ng ช่วย Java กี่เท่า และไล่ klauspost ทันมั้ย ──────────
    print("\n" + "=" * 78)
    print("สรุป (p50 ms, ใช้ variant เร็วสุดของแต่ละ label)")
    print("=" * 78)
    hdr = (f"{'scenario':14s} | {'java':>10s} | {'java-zlibng':>11s} | {'go-kp':>10s}"
           f" | {'ng vs java':>10s} | {'kp vs ng':>9s}")
    print(hdr); print("-" * len(hdr))
    for sc_name, sc in results["scenarios"].items():
        jv = scenario_best_ms(sc.get("java", {}))
        ng = scenario_best_ms(sc.get("java-zlibng", {}))
        kp = scenario_best_ms(sc.get("go-klauspost", {}))
        def f(x, w=10): return f"{x:{w}.3f}" if x is not None else f"{'-':>{w}s}"
        sp_ng = f"{jv/ng:9.2f}x" if (jv and ng) else f"{'-':>10s}"
        sp_kp = f"{ng/kp:8.2f}x" if (ng and kp) else f"{'-':>9s}"
        print(f"{sc_name:14s} | {f(jv)} | {f(ng, 11)} | {f(kp)} | {sp_ng:>10s} | {sp_kp:>9s}")
    print(f"\n✅ ผลบันทึกที่: {OUT_JSON}")
    print("   (ng vs java = java/java-zlibng, >1 = zlib-ng ช่วย ; kp vs ng = java-zlibng/go-kp, >1 = klauspost ยังนำ)")

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
