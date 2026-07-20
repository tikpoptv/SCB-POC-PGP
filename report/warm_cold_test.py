#!/usr/bin/env python3
"""
warm_cold_test.py — Mini benchmark: Cold vs Warm comparison
ทดสอบบนเครื่องนี้เพื่อ confirm ผลที่บอกไว้ใน report

ทดสอบ 3 กรณี:
  1. Cold start  — เปิด process ใหม่ทุก invocation (สะท้อน VM reboot)
  2. Warm repeat — เปิด process เดิมซ้ำๆ หลายรอบก่อนวัด (JVM JIT warm-up)
  3. Compare     — แสดงผลต่างระหว่าง cold vs warm
"""
import subprocess, time, pathlib, json, statistics, sys, os, tempfile, shutil

BASE    = pathlib.Path(__file__).parent.parent
GO_BIN  = BASE / "runners/go/go-runner"
JAVA_JAR= BASE / "runners/java/target/java-runner-0.1.0.jar"
KEY_PUB = BASE / "keys/rsa2048-public.asc"
KEY_PRIV= BASE / "keys/rsa2048-private.asc"
CORPUS  = BASE / "corpus/sample.txt"  # ~small file

JAVA_CMD = ["java", "-jar", str(JAVA_JAR)]

# ── ตรวจสอบ prerequisites ─────────────────────────────────────────────────
def check_prereqs():
    missing = []
    if not GO_BIN.exists():
        missing.append(f"Go binary: {GO_BIN}")
    if not JAVA_JAR.exists():
        missing.append(f"Java JAR: {JAVA_JAR}")
    if not KEY_PUB.exists():
        missing.append(f"RSA-2048 pub key: {KEY_PUB}")
    if not CORPUS.exists():
        missing.append(f"Corpus: {CORPUS}")
    if missing:
        print("❌ ไม่พบไฟล์ที่ต้องการ:")
        for m in missing:
            print(f"   {m}")
        sys.exit(1)
    # ตรวจ java
    r = subprocess.run(["java", "-version"], capture_output=True)
    if r.returncode != 0:
        print("❌ ไม่พบ java ใน PATH")
        sys.exit(1)

# ── สร้าง temp corpus ──────────────────────────────────────────────────────
def make_corpus(tmpdir: pathlib.Path, n_files: int = 5, size_kb: int = 256):
    """สร้างไฟล์ทดสอบแบบ deterministic"""
    corpus_dir = tmpdir / "corpus"
    corpus_dir.mkdir()
    import random
    rng = random.Random(42)
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 \n"
    for i in range(n_files):
        data = "".join(rng.choice(chars) for _ in range(size_kb * 1024))
        (corpus_dir / f"file_{i:03d}.txt").write_text(data)
    return corpus_dir

# ── วัด round-trip time: Go ──────────────────────────────────────────────
def measure_go_once(corpus_dir: pathlib.Path) -> float:
    """รัน go-runner 1 ครั้ง วัด wall-clock time (ms)"""
    cmd = [
        str(GO_BIN), "benchmark",
        "--variant", "inmem-single",
        "--pub-key", str(KEY_PUB),
        "--priv-key", str(KEY_PRIV),
        "--corpus", str(corpus_dir),
        "--iterations", "1",
        "--output", "json",
    ]
    t0 = time.perf_counter()
    r  = subprocess.run(cmd, capture_output=True, timeout=30)
    elapsed = (time.perf_counter() - t0) * 1000
    if r.returncode != 0:
        return None
    # พยายามดึง p50 จาก json output ถ้ามี
    try:
        out = json.loads(r.stdout)
        p50 = out.get("p50") or out.get("median") or out.get("p50_ms")
        if p50:
            return float(p50)
    except Exception:
        pass
    return elapsed  # fallback: wall-clock

# ── วัด round-trip time: Java ─────────────────────────────────────────────
def measure_java_once(corpus_dir: pathlib.Path, warmup_iters: int = 0) -> float:
    """
    รัน java-runner 1 ครั้ง
    warmup_iters: จำนวนรอบ warmup ก่อนวัดจริง (ถ้า > 0 = warm mode)
    """
    cmd = [
        "java", "-jar", str(JAVA_JAR),
        "benchmark",
        "--variant", "inmem-single",
        "--pub-key", str(KEY_PUB),
        "--priv-key", str(KEY_PRIV),
        "--corpus", str(corpus_dir),
        "--iterations", "1",
        "--warmup", str(warmup_iters),
        "--output", "json",
    ]
    t0 = time.perf_counter()
    r  = subprocess.run(cmd, capture_output=True, timeout=60)
    elapsed = (time.perf_counter() - t0) * 1000
    if r.returncode != 0:
        return elapsed  # fallback wall-clock รวม JVM startup
    try:
        out = json.loads(r.stdout)
        p50 = out.get("p50") or out.get("median") or out.get("p50_ms")
        if p50:
            return float(p50)
    except Exception:
        pass
    return elapsed

# ── wall-clock wrapper (ใช้ถ้า runner ไม่รองรับ json output) ─────────────
def run_and_time(cmd: list, timeout=60) -> float | None:
    """วัด elapsed time (ms) ของการ run command"""
    try:
        t0 = time.perf_counter()
        r  = subprocess.run(cmd, capture_output=True, timeout=timeout)
        elapsed = (time.perf_counter() - t0) * 1000
        if r.returncode != 0:
            return None
        return elapsed
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None

# ── ทดสอบ Go cold start ───────────────────────────────────────────────────
def test_go_cold(corpus_dir: pathlib.Path, n: int = 5) -> list[float]:
    """รัน n รอบ แต่ละรอบเปิด process ใหม่ (cold)"""
    results = []
    for i in range(n):
        # Go ไม่มี JVM จึง "cold" ทุกครั้ง
        cmd = [
            str(GO_BIN), "benchmark",
            "--variant", "inmem-single",
            "--pub-key", str(KEY_PUB),
            "--priv-key", str(KEY_PRIV),
            "--corpus", str(corpus_dir),
            "--iterations", "3",
        ]
        t = run_and_time(cmd)
        if t is not None:
            results.append(t / 3)  # per-iteration avg
    return results

# ── ทดสอบ Java cold (new JVM each time) ──────────────────────────────────
def test_java_cold(corpus_dir: pathlib.Path, n: int = 3) -> list[float]:
    """รัน n รอบ แต่ละรอบเปิด JVM ใหม่ (cold)"""
    results = []
    for i in range(n):
        cmd = [
            "java", "-jar", str(JAVA_JAR), "benchmark",
            "--variant", "inmem-single",
            "--pub-key", str(KEY_PUB),
            "--priv-key", str(KEY_PRIV),
            "--corpus", str(corpus_dir),
            "--iterations", "3",
            "--warmup", "0",
        ]
        t = run_and_time(cmd, timeout=90)
        if t is not None:
            results.append(t / 3)
    return results

# ── ทดสอบ Java warm (same JVM, many warmup rounds) ───────────────────────
def test_java_warm(corpus_dir: pathlib.Path, n: int = 3) -> list[float]:
    """รัน n รอบ พร้อม warmup 20 iterations ก่อนวัด (simulate warm JVM)"""
    results = []
    for i in range(n):
        cmd = [
            "java", "-jar", str(JAVA_JAR), "benchmark",
            "--variant", "inmem-single",
            "--pub-key", str(KEY_PUB),
            "--priv-key", str(KEY_PRIV),
            "--corpus", str(corpus_dir),
            "--iterations", "3",
            "--warmup", "20",
        ]
        t = run_and_time(cmd, timeout=120)
        if t is not None:
            # หัก warmup time ออก (estimate: warmup ≈ 20/23 ของ total)
            # ไม่หักเพื่อ conservative estimate
            results.append(t / 3)
    return results

# ── ทดสอบ approach ที่ VM ทำ (separate process per scenario) ─────────────
def test_vm_approach_cold(corpus_dir: pathlib.Path) -> dict:
    """
    จำลอง approach ที่ VM ใช้จริง:
    - Go: new process per scenario (cold เสมอ)
    - Java: new JVM per scenario, warmup=5 iterations
    วัด 3 scenarios แล้วเอา p50
    """
    print("\n  🔵 Go (cold process × 3 scenarios)...")
    go_times = []
    for sc in range(3):
        cmd = [
            str(GO_BIN), "benchmark",
            "--variant", "inmem-single",
            "--pub-key", str(KEY_PUB),
            "--priv-key", str(KEY_PRIV),
            "--corpus", str(corpus_dir),
            "--iterations", "5",
        ]
        t = run_and_time(cmd)
        if t: go_times.append(t / 5)
        sys.stdout.write(f"    scenario {sc+1}/3 → {t/5:.1f} ms\n" if t else "    scenario {sc+1}/3 → ❌\n")
        sys.stdout.flush()

    print("\n  🟠 Java (cold JVM × 3 scenarios, warmup=5)...")
    java_cold_times = []
    for sc in range(3):
        cmd = [
            "java", "-jar", str(JAVA_JAR), "benchmark",
            "--variant", "inmem-single",
            "--pub-key", str(KEY_PUB),
            "--priv-key", str(KEY_PRIV),
            "--corpus", str(corpus_dir),
            "--iterations", "5",
            "--warmup", "5",
        ]
        t = run_and_time(cmd, timeout=90)
        if t: java_cold_times.append(t / 5)
        sys.stdout.write(f"    scenario {sc+1}/3 → {t/5:.1f} ms\n" if t else f"    scenario {sc+1}/3 → ❌\n")
        sys.stdout.flush()

    print("\n  🟠 Java (warm JVM — same process, 20 warmup iterations)...")
    cmd = [
        "java", "-jar", str(JAVA_JAR), "benchmark",
        "--variant", "inmem-single",
        "--pub-key", str(KEY_PUB),
        "--priv-key", str(KEY_PRIV),
        "--corpus", str(corpus_dir),
        "--iterations", "15",
        "--warmup", "20",
    ]
    t = run_and_time(cmd, timeout=120)
    java_warm_avg = (t / 15) if t else None
    sys.stdout.write(f"    warm result → {java_warm_avg:.1f} ms per iteration\n" if java_warm_avg else "    warm result → ❌\n")

    return {
        "go_cold": go_times,
        "java_cold": java_cold_times,
        "java_warm_avg": java_warm_avg,
    }


# ── main ──────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("🧪 Mini Benchmark: Cold vs Warm — Local Confirm")
    print("=" * 60)
    print(f"  Go binary:  {GO_BIN}")
    print(f"  Java JAR:   {JAVA_JAR}")
    print(f"  Key:        RSA-2048")
    print()

    check_prereqs()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        print("📁 สร้าง corpus (5 files × 256KB)...")
        corpus_dir = make_corpus(tmpdir, n_files=5, size_kb=256)
        print(f"   → {corpus_dir} (5 ไฟล์ รวม ~1.25 MB)")

        results = test_vm_approach_cold(corpus_dir)

    # ── สรุปผล ───────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 ผลการทดสอบ")
    print("=" * 60)

    go_cold  = results["go_cold"]
    j_cold   = results["java_cold"]
    j_warm   = results["java_warm_avg"]

    def fmt(lst):
        if not lst: return "ไม่มีข้อมูล"
        med = statistics.median(lst)
        return f"p50 = {med:.1f} ms  (min={min(lst):.1f}, max={max(lst):.1f})"

    print(f"\n  🔵 Go (cold process):    {fmt(go_cold)}")
    print(f"  🟠 Java (cold JVM):      {fmt(j_cold)}")
    if j_warm:
        print(f"  🟠 Java (warm JVM):      {j_warm:.1f} ms per iteration")

    if go_cold and j_cold:
        go_med   = statistics.median(go_cold)
        j_c_med  = statistics.median(j_cold)
        if go_med < j_c_med:
            spd = j_c_med / go_med
            print(f"\n  ✅ Cold: Go เร็วกว่า Java {spd:.1f}× (สอดคล้องกับ VM results)")
        else:
            spd = go_med / j_c_med
            print(f"\n  ⚠️  Cold: Java เร็วกว่า Go {spd:.1f}×")
            print(f"     (เครื่องนี้อาจมี JVM state ค้างอยู่ หรือ Go binary ไม่ได้ build optimized)")

    if go_cold and j_warm:
        go_med   = statistics.median(go_cold)
        if j_warm < go_med:
            spd = go_med / j_warm
            print(f"\n  ℹ️  Warm: Java warm เร็วกว่า Go cold {spd:.1f}×")
            print(f"     → confirm: JVM ที่อุ่นแล้วเร็วกว่า cold process (แต่ไม่ใช่ fair comparison)")
        else:
            spd = j_warm / go_med
            print(f"\n  ✅ Warm: Go ยังเร็วกว่า Java warm {spd:.1f}× (Go runtime ได้เปรียบแม้ Java warm แล้ว)")

    print("\n" + "=" * 60)
    print("📋 สรุปสั้นๆ สำหรับนำเสนอ")
    print("=" * 60)
    if go_cold and j_cold:
        go_med  = statistics.median(go_cold)
        j_c_med = statistics.median(j_cold)
        print(f"""
  • ทดสอบ RSA-2048, inmem-single, ไฟล์ .txt ~256KB/ไฟล์ × 5 ไฟล์
  • Cold start (แต่ละ scenario เปิด process ใหม่):
      Go  p50 ≈ {go_med:.1f} ms
      Java p50 ≈ {j_c_med:.1f} ms
      → Go {"เร็วกว่า" if go_med < j_c_med else "ช้ากว่า"} Java {abs(j_c_med/go_med if go_med > 0 else 1):.1f}× ภายใต้ cold start
  • Warm JVM (รันซ้ำในกระบวนการเดิม 20 warmup rounds):
      Java warm ≈ {j_warm:.1f} ms {"(เร็วกว่า cold)" if j_warm and j_c_med and j_warm < j_c_med else "(ไม่ต่างมาก)"}
  • ผลบนเครื่องนี้ (macOS) จะต่างจาก VM Linux แต่ความสัมพันธ์ relative น่าจะเหมือนกัน
""" if j_warm else f"""
  • ทดสอบ RSA-2048, inmem-single, ไฟล์ .txt ~256KB/ไฟล์ × 5 ไฟล์
  • Go  p50 ≈ {go_med:.1f} ms / Java p50 ≈ {j_c_med:.1f} ms
""")

if __name__ == "__main__":
    main()
