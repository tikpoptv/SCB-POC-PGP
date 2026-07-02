#!/usr/bin/env bash
# run_full_benchmark_v3.sh — รัน full benchmark หลัง reboot VM
# VM: Ubuntu 24.04, 8 vCPU, 14 GB RAM
# สั่งรัน: bash ~/POC-Encryption/scripts/run_full_benchmark_v3.sh
set -euo pipefail

BASE="$HOME/POC-Encryption"
RESULTS_DIR="$HOME/bench-results-v3"
TMPFS_DIR="/tmp/bench-corpus-v3"
KEYS_DIR="$BASE/keys"
GO_BIN="$BASE/runners/go/go-runner"
JAVA_JAR="$BASE/runners/java/target/java-runner-0.1.0.jar"
ROUNDS=5
WARMUP=5

echo "============================================================"
echo "  PGP Benchmark v3 — Full Run (post-reboot cold start)"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo "  VM: $(uname -n) | $(nproc) vCPU | $(free -h | awk '/Mem/{print $2}') RAM"
echo "  Go:   $GO_BIN"
echo "  Java: $JAVA_JAR"
echo ""

# ── prereq check ──────────────────────────────────────────────────────────
for f in "$GO_BIN" "$JAVA_JAR" "$KEYS_DIR/rsa2048-public.asc"; do
  [[ -f "$f" ]] || { echo "❌ ไม่พบ: $f"; exit 1; }
done
java -version 2>&1 | head -1
"$GO_BIN" 2>/dev/null || true  # ping binary

# ── setup tmpfs corpus ────────────────────────────────────────────────────
mkdir -p "$TMPFS_DIR" "$RESULTS_DIR"
echo "📁 สร้าง corpus บน tmpfs..."
python3 - <<'PYEOF'
import pathlib, random, os

base = pathlib.Path("/tmp/bench-corpus-v3")

def gen_text(path, n, size_kb):
    path.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    words = "hello world data encrypt pgp benchmark test performance go java crypto secure".split()
    for i in range(n):
        content = " ".join(rng.choice(words) for _ in range(size_kb * 80)) + "\n"
        (path / f"file{i:04d}.txt").write_text(content)

def gen_binary(path, n, size_kb):
    path.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    for i in range(n):
        data = bytes(rng.randint(0,255) for _ in range(size_kb * 1024))
        (path / f"file{i:04d}.dat").write_bytes(data)

# file-type scenarios (15 files × 512KB each)
for ft in ["txt", "csv", "pdf", "xlsx", "zip", "dat"]:
    gen_text(base / f"filetypes/{ft}", 15, 512) if ft in ["txt","csv"] else gen_binary(base / f"filetypes/{ft}", 15, 512)

# many-small (100 files × 1KB, 10KB, 100KB)
gen_text(base / "manysmall/1kb",   100, 1)
gen_text(base / "manysmall/10kb",  100, 10)
gen_text(base / "manysmall/100kb", 100, 100)

# size gradient: 1KB → 1MB (compressible) — 20 files with increasing sizes
sg_path = base / "sizegradient/comp"
sg_path.mkdir(parents=True, exist_ok=True)
rng = random.Random(42)
sizes = [1, 2, 5, 10, 20, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1024, 2048, 4096, 8192, 20480]
words = "hello world data encrypt pgp benchmark performance".split()
for i, kb in enumerate(sizes):
    content = " ".join(rng.choice(words) for _ in range(kb * 80)) + "\n"
    (sg_path / f"file{i:04d}_{kb}kb.txt").write_text(content)

# concurrent test corpus (100 files × 1MB)
gen_binary(base / "concurrent", 100, 1024)

print(f"✓ corpus ready at {base}")
PYEOF
echo "  ✓ corpus สร้างแล้ว"

# ── python helper: checksum + run_runner ─────────────────────────────────
cat > /tmp/bench_helper.py <<'PYEOF'
import hashlib, json, subprocess, pathlib, os, tempfile, statistics, time, sys

def key_checksum(key_dir):
    lines = []
    for f in sorted(pathlib.Path(key_dir).iterdir()):
        if f.name.endswith("-public.asc") or f.name.endswith("-private.asc"):
            h = hashlib.sha256(); h.update(f.read_bytes())
            lines.append(f.name + ":sha256:" + h.hexdigest())
    lines.sort()
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()

def corpus_checksum(root):
    entries = []
    for f in sorted(pathlib.Path(root).rglob("*")):
        if f.is_file():
            rel = f.relative_to(root).as_posix()
            h = hashlib.sha256(); h.update(f.read_bytes())
            entries.append((rel, h.hexdigest()))
    entries.sort()
    hh = hashlib.sha256()
    for rel, hx in entries:
        hh.update(rel.encode()); hh.update(b"\x00"); hh.update(hx.encode()); hh.update(b"\n")
    return "sha256:" + hh.hexdigest()

def run_once(binary_cmd, variant, warmup, pub_alg, key_dir, corpus_dir, out_dir):
    cmd = {
        "command": "run", "variantId": variant,
        "mode": "cold_start" if warmup == 0 else "steady_state",
        "warmupIterations": warmup, "concurrency": 1,
        "cryptoProfile": {"pubAlg": pub_alg, "cipher": "AES-256", "compression": "ZLIB", "hash": "SHA-256"},
        "outputEncoding": "binary",
        "keySetPath": str(key_dir), "keySetChecksum": key_checksum(key_dir),
        "corpusPath": str(corpus_dir), "corpusChecksum": corpus_checksum(corpus_dir),
        "outputDir": str(out_dir), "operation": "roundtrip"
    }
    t0 = time.perf_counter()
    r = subprocess.run(binary_cmd, input=json.dumps(cmd).encode(), capture_output=True, timeout=300)
    elapsed = (time.perf_counter() - t0) * 1000
    if r.returncode not in (0, 2):
        return None, elapsed
    try:
        out = json.loads(r.stdout)
        ops = [o for o in out.get("operations", []) if not o.get("skipped")]
        times = [(o.get("encryptMs") or 0) + (o.get("decryptMs") or 0) for o in ops if (o.get("encryptMs") or 0) + (o.get("decryptMs") or 0) > 0]
        if times:
            return {"p50": statistics.median(times), "p95": statistics.quantiles(times, n=20)[18] if len(times) >= 20 else max(times),
                    "min": min(times), "max": max(times), "mean": statistics.mean(times),
                    "n": len(times), "throughput_mbs": out.get("throughputMbSec")}, elapsed
    except: pass
    n = len(list(pathlib.Path(corpus_dir).iterdir()))
    return {"p50": elapsed/max(n,1), "n": n, "wall_ms": elapsed}, elapsed

PYEOF
echo "  ✓ helper script ready"

# ── main benchmark runner (python) ───────────────────────────────────────
python3 - <<PYEOF
import sys, json, statistics, pathlib, tempfile, time
sys.path.insert(0, "/tmp")
from bench_helper import run_once, key_checksum, corpus_checksum

HOME = pathlib.Path.home()
GO_BIN   = str(HOME / "POC-Encryption/runners/go/go-runner")
JAVA_JAR = str(HOME / "POC-Encryption/runners/java/target/java-runner-0.1.0.jar")
KEY_DIR  = HOME / "POC-Encryption/keys"
CORPUS   = pathlib.Path("/tmp/bench-corpus-v3")
OUT_DIR  = HOME / "bench-results-v3"
OUT_DIR.mkdir(exist_ok=True)

ROUNDS  = $ROUNDS
WARMUP  = $WARMUP

GO_VARIANTS   = ["go-inmem-single", "go-stream-single", "go-stream-parallel"]
JAVA_VARIANTS = ["java-inmem-single", "java-stream-single", "java-stream-parallel"]

go_cmd   = [GO_BIN]
java_cmd = ["java", "-Xmx4g", "-jar", JAVA_JAR]

started_at = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

SCENARIOS = [
    # (sc_id, pub_alg, corpus_subpath)
    ("ft-txt-rsa2048",    "RSA-2048",    "filetypes/txt"),
    ("ft-txt-rsa4096",    "RSA-4096",    "filetypes/txt"),
    ("ft-txt-curve25519", "Curve25519",  "filetypes/txt"),
    ("ft-csv-rsa2048",    "RSA-2048",    "filetypes/csv"),
    ("ft-csv-rsa4096",    "RSA-4096",    "filetypes/csv"),
    ("ft-csv-curve25519", "Curve25519",  "filetypes/csv"),
    ("ft-pdf-rsa2048",    "RSA-2048",    "filetypes/pdf"),
    ("ft-pdf-rsa4096",    "RSA-4096",    "filetypes/pdf"),
    ("ft-pdf-curve25519", "Curve25519",  "filetypes/pdf"),
    ("ft-xlsx-rsa2048",   "RSA-2048",    "filetypes/xlsx"),
    ("ft-xlsx-rsa4096",   "RSA-4096",    "filetypes/xlsx"),
    ("ft-xlsx-curve25519","Curve25519",  "filetypes/xlsx"),
    ("ft-zip-rsa2048",    "RSA-2048",    "filetypes/zip"),
    ("ft-zip-rsa4096",    "RSA-4096",    "filetypes/zip"),
    ("ft-zip-curve25519", "Curve25519",  "filetypes/zip"),
    ("ft-dat-rsa2048",    "RSA-2048",    "filetypes/dat"),
    ("ft-dat-rsa4096",    "RSA-4096",    "filetypes/dat"),
    ("ft-dat-curve25519", "Curve25519",  "filetypes/dat"),
    ("sizegrad-comp-rsa2048",    "RSA-2048",   "sizegradient/comp"),
    ("sizegrad-comp-rsa4096",    "RSA-4096",   "sizegradient/comp"),
    ("sizegrad-comp-curve25519", "Curve25519", "sizegradient/comp"),
    ("many-1kb",   "RSA-2048", "manysmall/1kb"),
    ("many-10kb",  "RSA-2048", "manysmall/10kb"),
    ("many-100kb", "RSA-2048", "manysmall/100kb"),
]

def run_scenario(sc_id, pub_alg, corpus_sub):
    corpus_dir = CORPUS / corpus_sub
    print(f"\n  [{sc_id}] {pub_alg} corpus={corpus_sub}")
    sc_results = {"pub_alg": pub_alg, "corpus": corpus_sub, "go": {}, "java": {}}

    for variant in GO_VARIANTS:
        rounds_data = []
        for r in range(ROUNDS):
            with tempfile.TemporaryDirectory() as tmp:
                result, _ = run_once(go_cmd, variant, WARMUP, pub_alg, KEY_DIR, corpus_dir, pathlib.Path(tmp))
                if result:
                    rounds_data.append(result["p50"])
                    sys.stdout.write(".")
                else:
                    sys.stdout.write("x")
            sys.stdout.flush()
        if rounds_data:
            sc_results["go"][variant] = {
                "p50_mean": round(statistics.mean(rounds_data), 3),
                "p95_mean": round(statistics.quantiles(rounds_data, n=20)[18] if len(rounds_data)>=20 else max(rounds_data), 3),
                "p50_min": round(min(rounds_data), 3),
                "p50_max": round(max(rounds_data), 3),
                "rounds": len(rounds_data),
            }

    for variant in JAVA_VARIANTS:
        rounds_data = []
        for r in range(ROUNDS):
            with tempfile.TemporaryDirectory() as tmp:
                result, _ = run_once(java_cmd, variant, WARMUP, pub_alg, KEY_DIR, corpus_dir, pathlib.Path(tmp))
                if result:
                    rounds_data.append(result["p50"])
                    sys.stdout.write(".")
                else:
                    sys.stdout.write("x")
            sys.stdout.flush()
        if rounds_data:
            sc_results["java"][variant] = {
                "p50_mean": round(statistics.mean(rounds_data), 3),
                "p95_mean": round(statistics.quantiles(rounds_data, n=20)[18] if len(rounds_data)>=20 else max(rounds_data), 3),
                "p50_min": round(min(rounds_data), 3),
                "p50_max": round(max(rounds_data), 3),
                "rounds": len(rounds_data),
            }
    print(f" done")
    return sc_results

all_results = {"startedAt": started_at, "vm_ram_gb": 14, "rounds": ROUNDS,
               "note": "v3: post-reboot cold start, 14GB RAM, 5 rounds",
               "scenarios": {}, "concurrent": {}}

total = len(SCENARIOS)
for i, (sc_id, pub_alg, corpus_sub) in enumerate(SCENARIOS):
    print(f"\n[{i+1}/{total}] {sc_id}")
    all_results["scenarios"][sc_id] = run_scenario(sc_id, pub_alg, corpus_sub)

finished_at = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
all_results["finishedAt"] = finished_at
all_results["totalScenarios"] = len(all_results["scenarios"])

out_file = OUT_DIR / "results_v3.json"
out_file.write_text(json.dumps(all_results, indent=2))
print(f"\n\n✅ เสร็จแล้ว! ผลบันทึกที่: {out_file}")
print(f"   เวลาทั้งหมด: {started_at} → {finished_at}")
PYEOF

echo ""
echo "============================================================"
echo "  ✅ Benchmark v3 เสร็จสมบูรณ์"
echo "  ผลอยู่ที่: $RESULTS_DIR/results_v3.json"
echo "  ดาวน์โหลดด้วย:"
echo "  scp tikxd@10.110.1.42:~/bench-results-v3/results_v3.json \\"
echo "    '/Users/jedsadapornpannok/github/POC Encryption/report/results_extended.json'"
echo "============================================================"
