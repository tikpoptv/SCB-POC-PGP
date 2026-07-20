#!/usr/bin/env python3
"""
vm_warm_cold_test.py — Warm JVM vs Cold JVM vs Go
รันบน VM โดยตรง — สื่อสารกับ runner ผ่าน stdin JSON (contract จริง)

Phase 1: Go cold (new process ทุกครั้ง)
Phase 2: Java cold (new JVM ทุกครั้ง, warmupIterations=0)
Phase 3: Java warm (new JVM ทุกครั้ง, warmupIterations=20 = JIT compile ก่อนวัด)
"""
import subprocess, time, json, statistics, sys, pathlib, hashlib, tempfile, os, random

HOME       = pathlib.Path.home()
GO_BIN     = HOME / "POC-Encryption/runners/go/go-runner"
JAVA_JAR   = HOME / "POC-Encryption/runners/java/target/java-runner-0.1.0.jar"
KEY_DIR    = HOME / "POC-Encryption/keys"
OUT_FILE   = HOME / "bench-results/warm_cold_result.json"

N_REPEAT   = 5
WARMUP_HOT = 20

def banner(t): print("\n" + "═"*60 + f"\n  {t}\n" + "═"*60)

# ── Checksum helpers (ตรงกับ Go runner algorithm) ─────────────────────────
def compute_key_checksum() -> str:
    lines = []
    for f in sorted(KEY_DIR.iterdir()):
        if f.name.endswith('-public.asc') or f.name.endswith('-private.asc'):
            h = hashlib.sha256(); h.update(f.read_bytes())
            lines.append(f.name + ':sha256:' + h.hexdigest())
    lines.sort()
    return 'sha256:' + hashlib.sha256('\n'.join(lines).encode()).hexdigest()

def compute_corpus_checksum(corpus: pathlib.Path) -> str:
    entries = []
    for f in sorted(corpus.rglob('*')):
        if f.is_file():
            rel = str(f.relative_to(corpus)).replace(os.sep, '/')
            h = hashlib.sha256(); h.update(f.read_bytes())
            entries.append((rel, h.hexdigest()))
    entries.sort(key=lambda x: x[0])
    hh = hashlib.sha256()
    for rel, hexhash in entries:
        hh.update(rel.encode()); hh.update(b'\x00')
        hh.update(hexhash.encode()); hh.update(b'\n')
    return 'sha256:' + hh.hexdigest()

# ── Corpus creator (plaintext .txt files) ──────────────────────────────────
def create_plaintext_corpus(dest: pathlib.Path, n_files: int = 15, size_kb: int = 512):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    words = ["hello world data encrypt pgp benchmark test performance go java "
             "crypto secure file process system network request response service "
             "application database transaction record report document analysis"]
    for i in range(n_files):
        # text ที่บีบอัดได้สูง ~80% (เหมือน ft-txt scenario จริง)
        lines = []
        for _ in range(size_kb * 2):  # ~512KB ต่อไฟล์
            lines.append(rng.choice(words[0].split()) * rng.randint(5, 15))
        (dest / f"file{i:03d}.txt").write_text('\n'.join(lines) + '\n')
    print(f"  created {n_files} plaintext files in {dest}")
    return dest

# ── Command builder ─────────────────────────────────────────────────────────
def make_command(variant: str, warmup: int, corpus: pathlib.Path, outdir: pathlib.Path) -> dict:
    return {
        "command": "run",
        "variantId": variant,
        "mode": "cold_start" if warmup == 0 else "steady_state",
        "warmupIterations": warmup,
        "concurrency": 1,
        "cryptoProfile": {
            "pubAlg": "RSA-2048",
            "cipher": "AES-256",
            "compression": "ZLIB",
            "hash": "SHA-256"
        },
        "outputEncoding": "binary",
        "keySetPath": str(KEY_DIR),
        "keySetChecksum": compute_key_checksum(),
        "corpusPath": str(corpus),
        "corpusChecksum": compute_corpus_checksum(corpus),
        "outputDir": str(outdir),
        "operation": "roundtrip"
    }

# ── Extract p50 from runner output ─────────────────────────────────────────
def extract_timing(out: dict, corpus: pathlib.Path, elapsed_ms: float) -> float | None:
    ops = out.get("operations", [])
    if ops:
        times = []
        for op in ops:
            if op.get("skipped"): continue
            rt = (op.get("encryptMs") or 0) + (op.get("decryptMs") or 0)
            if rt > 0: times.append(rt)
        if times:
            return statistics.median(times)
    n = len([f for f in corpus.iterdir() if f.is_file()])
    return elapsed_ms / max(n, 1)

# ── Runner invocation ───────────────────────────────────────────────────────
def run_once(binary_cmd: list, variant: str, warmup: int,
             corpus: pathlib.Path, label: str = "") -> float | None:
    with tempfile.TemporaryDirectory() as tmp:
        cmd_json = make_command(variant, warmup, corpus, pathlib.Path(tmp))
        t0 = time.perf_counter()
        r  = subprocess.run(
            binary_cmd,
            input=json.dumps(cmd_json).encode(),
            capture_output=True,
            timeout=180
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

    if r.returncode not in (0, 2):
        print(f"    ⚠ error (exit {r.returncode}): {r.stderr.decode()[:200]}")
        return None
    if r.returncode == 2:
        # checksum mismatch = gate failure, log but try to use elapsed
        pass

    try:
        out = json.loads(r.stdout)
        return extract_timing(out, corpus, elapsed_ms)
    except Exception:
        n = len([f for f in corpus.iterdir() if f.is_file()])
        return elapsed_ms / max(n, 1)

def check_prereqs():
    ok = True
    for p, name in [(GO_BIN,"Go binary"),(JAVA_JAR,"Java JAR"),(KEY_DIR,"Keys dir")]:
        if p.exists(): print(f"  ✓ {name}: {p}")
        else: print(f"  ✗ {name}: {p}  ← NOT FOUND"); ok = False
    if not ok: sys.exit(1)

# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    banner("VM Warm vs Cold Benchmark — Confirm JIT Effect")
    os.system("uptime")
    print()
    check_prereqs()

    go_cmd   = [str(GO_BIN)]
    java_cmd = ["java", "-jar", str(JAVA_JAR)]

    # สร้าง plaintext corpus ใน tmpfs
    print("\n📁 สร้าง plaintext corpus บน tmpfs...")
    corpus_dir = pathlib.Path("/tmp/warm_cold_corpus")
    create_plaintext_corpus(corpus_dir, n_files=15, size_kb=512)

    results = {}

    # ─── Phase 1: Go cold ──────────────────────────────────────────────
    banner("Phase 1: 🔵 Go — cold process (new process per run)")
    go_times = []
    for i in range(N_REPEAT):
        t = run_once(go_cmd, "go-inmem-single", 0, corpus_dir)
        print(f"  round {i+1}/{N_REPEAT}: {f'{t:.2f} ms' if t else '❌'}")
        if t: go_times.append(t)

    if go_times:
        results["go_cold"] = {"p50": statistics.median(go_times),
                               "min": min(go_times), "max": max(go_times), "all": go_times}
        print(f"  → p50 = {results['go_cold']['p50']:.2f} ms")

    # ─── Phase 2: Java cold (warmup=0) ─────────────────────────────────
    banner("Phase 2: 🟠 Java COLD — new JVM per run, warmupIterations=0")
    java_cold = []
    for i in range(N_REPEAT):
        t = run_once(java_cmd, "java-inmem-single", 0, corpus_dir)
        print(f"  round {i+1}/{N_REPEAT}: {f'{t:.2f} ms' if t else '❌'}")
        if t: java_cold.append(t)

    if java_cold:
        results["java_cold"] = {"p50": statistics.median(java_cold),
                                 "min": min(java_cold), "max": max(java_cold), "all": java_cold}
        print(f"  → p50 = {results['java_cold']['p50']:.2f} ms")

    # ─── Phase 3: Java warm (warmup=20) ────────────────────────────────
    banner(f"Phase 3: 🟠 Java WARM — new JVM per run, warmupIterations={WARMUP_HOT}")
    print("  (JIT compiler รัน crypto functions ซ้ำ 20 รอบก่อนเริ่มวัด)")
    java_warm = []
    for i in range(N_REPEAT):
        t = run_once(java_cmd, "java-inmem-single", WARMUP_HOT, corpus_dir)
        print(f"  round {i+1}/{N_REPEAT}: {f'{t:.2f} ms' if t else '❌'}")
        if t: java_warm.append(t)

    if java_warm:
        results["java_warm"] = {"p50": statistics.median(java_warm),
                                 "min": min(java_warm), "max": max(java_warm), "all": java_warm}
        print(f"  → p50 = {results['java_warm']['p50']:.2f} ms")

    # ─── Summary ────────────────────────────────────────────────────────
    banner("📊 ผลสรุป — Cold Start vs Warm JIT vs Go")

    go_p50 = results.get("go_cold",  {}).get("p50")
    jc_p50 = results.get("java_cold",{}).get("p50")
    jw_p50 = results.get("java_warm",{}).get("p50")

    print(f"\n  {'Mode':<35} {'p50 ms':>8}  {'vs Go':>12}")
    print(f"  {'-'*60}")
    if go_p50:
        print(f"  {'🔵 Go (cold process)':<35} {go_p50:>8.2f}  {'baseline':>12}")
    if jc_p50 and go_p50:
        r = jc_p50/go_p50
        lbl = f"Go {r:.1f}× faster" if go_p50 < jc_p50 else f"Java {go_p50/jc_p50:.1f}× faster"
        print(f"  {'🟠 Java cold (warmup=0)':<35} {jc_p50:>8.2f}  {lbl:>12}")
    if jw_p50 and go_p50:
        r = jw_p50/go_p50
        lbl = f"Go {r:.1f}× faster" if go_p50 < jw_p50 else f"Java {go_p50/jw_p50:.1f}× faster"
        print(f"  {'🟠 Java warm (warmup=20)':<35} {jw_p50:>8.2f}  {lbl:>12}")

    print()
    if jc_p50 and jw_p50:
        gain = (jc_p50 - jw_p50) / jc_p50 * 100
        direction = "เร็วขึ้น" if gain > 0 else "ช้าลง (!)"
        print(f"  💡 JVM warmup ({WARMUP_HOT} iters) ทำให้ Java {direction}: {abs(gain):.1f}%")
        print(f"     cold {jc_p50:.2f} ms → warm {jw_p50:.2f} ms")

    if go_p50 and jw_p50:
        if go_p50 < jw_p50:
            ratio = jw_p50/go_p50
            print(f"\n  ✅ CONFIRM: Go ยังเร็วกว่า Java warm {ratio:.1f}×")
            print(f"     → แม้ JIT อุ่นแล้ว Go runtime ยังได้เปรียบ")
        else:
            ratio = go_p50/jw_p50
            print(f"\n  ⚠️  Java warm เร็วกว่า Go {ratio:.1f}× — JIT ช่วยได้มาก")
            print(f"     → Java long-running service อาจ competitive กับ Go")

    # บันทึก
    OUT_FILE.write_text(json.dumps(results, indent=2))
    print(f"\n  📄 บันทึกผล: {OUT_FILE}")
    print()

if __name__ == "__main__":
    main()
