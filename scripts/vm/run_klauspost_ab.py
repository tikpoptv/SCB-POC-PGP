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

# runner ต่อ label: (binary_cmd, variants)
GO_VARIANTS   = ["go-inmem-single", "go-stream-parallel"]
JAVA_VARIANTS = ["java-inmem-single", "java-stream-parallel"]
RUNNERS = {
    "go-stdlib":    ([str(GO_STD)], GO_VARIANTS),
    "go-klauspost": ([str(GO_KP)],  GO_VARIANTS),
    "java":         (["java", "-Xmx3g", "-jar", str(JAR)], JAVA_VARIANTS),
}

# ── checksum helpers (เหมือน harness) ───────────────────────────────────────
def key_cs():
    lines = []
    for f in sorted(KEYS.iterdir()):
        if f.name.endswith(("-public.asc", "-private.asc")):
            lines.append(f.name + ":sha256:" + hashlib.sha256(f.read_bytes()).hexdigest())
    lines.sort()
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()

def corpus_cs(path):
    e = []
    for f in sorted(pathlib.Path(path).rglob("*")):
        if f.is_file():
            rel = f.relative_to(path).as_posix()
            e.append((rel, hashlib.sha256(f.read_bytes()).hexdigest()))
    e.sort()
    hh = hashlib.sha256()
    for rel, hx in e:
        hh.update(rel.encode()); hh.update(b"\x00"); hh.update(hx.encode()); hh.update(b"\n")
    return "sha256:" + hh.hexdigest()

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

def gen_binary(dest, n, size_kb):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    for i in range(n):
        (dest / f"file{i:04d}.dat").write_bytes(bytes(rng.getrandbits(8) for _ in range(size_kb * 1024)))

def setup_corpus():
    print(f"📁 corpus @ {CORPUS}")
    gen_text(CORPUS / "ft/txt", n=15, size_kb=512);  print("  ✓ txt  15×512KB (compressible)")
    gen_csv(CORPUS / "ft/csv", n=15, size_kb=512);   print("  ✓ csv  15×512KB (compressible)")
    gen_binary(CORPUS / "ft/dat", n=15, size_kb=512); print("  ✓ dat  15×512KB (incompressible)")
    # size gradient (compressible text) — จุดที่ Go เคยแพ้ชัด
    for kb in (10, 100, 512, 1024):
        gen_text(CORPUS / f"size/txt-{kb}kb", n=1, size_kb=kb)
    print("  ✓ size gradient text 10/100/512/1024 KB")

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

def bench(label, corpus_path, out_root):
    binary_cmd, variants = RUNNERS[label]
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
    print(f"ROUNDS={ROUNDS} WARMUP={WARMUP}")
    print("=" * 64)
    os.system("nproc >/dev/null 2>&1 && echo -n 'cores: ' && nproc || true")

    setup_corpus()
    out_root = CORPUS / "_out"; out_root.mkdir(exist_ok=True)

    scenarios = [
        ("txt-512KB×15", CORPUS / "ft/txt"),
        ("csv-512KB×15", CORPUS / "ft/csv"),
        ("dat-512KB×15", CORPUS / "ft/dat"),
        ("txt-10KB",     CORPUS / "size/txt-10kb"),
        ("txt-100KB",    CORPUS / "size/txt-100kb"),
        ("txt-512KB",    CORPUS / "size/txt-512kb"),
        ("txt-1MB",      CORPUS / "size/txt-1024kb"),
    ]
    labels = ["go-stdlib", "go-klauspost"] + (["java"] if have_java else [])

    results = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "rounds": ROUNDS, "warmup": WARMUP,
        "branch": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 cwd=REPO, capture_output=True, text=True).stdout.strip(),
        "scenarios": {},
    }

    for sc_name, corpus_path in scenarios:
        print(f"\n[{sc_name}]  ({len(list(pathlib.Path(corpus_path).iterdir()))} files)")
        sc = {}
        for label in labels:
            print(f"  {label:14s} ", end="")
            sc[label] = bench(label, corpus_path, out_root)
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
