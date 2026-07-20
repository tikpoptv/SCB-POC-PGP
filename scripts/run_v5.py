#!/usr/bin/env python3
"""
run_v5.py — Full benchmark v5 (post-reboot cold start)
เพิ่ม scenarios สำหรับตอบ:
  1. ขนาดไฟล์ส่งผลยังไง (size gradient: 1KB → 10MB, fixed 1 file)
  2. จำนวนไฟล์ส่งผลยังไง (count gradient: 1→1000 files, fixed 100KB each)
  3. Full matrix: 6 file types × 3 key algs (เหมือนเดิม)
  4. Concurrent: 1,2,4,8 clients

ผล → ~/bench-results-v5/results_v5.json
"""
import json, os, subprocess, time, statistics, pathlib, hashlib, random
from datetime import datetime, timezone

POC    = pathlib.Path("/home/tikxd/POC-Encryption")
KEYS   = POC / "keys"
CORPUS = pathlib.Path("/mnt/corpus-v5")  # tmpfs
OUT    = pathlib.Path("/home/tikxd/bench-results-v5")
JAR    = POC / "runners/java/target/java-runner-0.1.0.jar"
GO_BIN = POC / "runners/go/go-runner"

GO_VARIANTS   = ["go-inmem-single","go-stream-single","go-stream-parallel"]
JAVA_VARIANTS = ["java-inmem-single","java-stream-single","java-stream-parallel"]
ALL_VARIANTS  = GO_VARIANTS + JAVA_VARIANTS
ROUNDS = 3
WARMUP = 1

# ── checksum helpers ──────────────────────────────────────────────────────
def key_cs():
    lines = []
    for f in sorted(KEYS.iterdir()):
        if f.name.endswith("-public.asc") or f.name.endswith("-private.asc"):
            h = hashlib.sha256(); h.update(f.read_bytes())
            lines.append(f.name + ":sha256:" + h.hexdigest())
    lines.sort()
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()

def corpus_cs(path):
    entries = []
    for f in sorted(path.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(path)).replace(os.sep, "/")
            h = hashlib.sha256(); h.update(f.read_bytes())
            entries.append((rel, h.hexdigest()))
    entries.sort()
    hh = hashlib.sha256()
    for rel, hx in entries:
        hh.update(rel.encode()); hh.update(b"\x00"); hh.update(hx.encode()); hh.update(b"\n")
    return "sha256:" + hh.hexdigest()

KEY_CS_CACHED = None
def get_key_cs():
    global KEY_CS_CACHED
    if not KEY_CS_CACHED:
        KEY_CS_CACHED = key_cs()
        print(f"  key checksum: {KEY_CS_CACHED[:24]}...")
    return KEY_CS_CACHED

# ── corpus generators ─────────────────────────────────────────────────────
def gen_text(dest, n=15, size_kb=512):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    vocab = "the quick brown fox jumps over lazy dog data encrypt secure file process network request response service application".split()
    for i in range(n):
        target = size_kb * 1024
        buf, total = [], 0
        while total < target:
            line = " ".join(rng.choices(vocab, k=rng.randint(8,20))) + "\n"
            buf.append(line); total += len(line)
        content = "".join(buf)[:target]
        content = content + " " * (target - len(content))
        (dest / f"file{i:04d}.txt").write_bytes(content.encode("ascii", "replace"))

def gen_binary(dest, n=15, size_kb=512):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    for i in range(n):
        (dest / f"file{i:04d}.dat").write_bytes(bytes(rng.getrandbits(8) for _ in range(size_kb*1024)))

# ── runner ────────────────────────────────────────────────────────────────
def run_one(variant, corpus_path, alg, out_dir):
    cmd = {
        "command": "run", "variantId": variant,
        "mode": "steady_state", "warmupIterations": WARMUP, "concurrency": 1,
        "cryptoProfile": {"pubAlg": alg, "cipher": "AES-256", "compression": "ZLIB", "hash": "SHA-256"},
        "outputEncoding": "binary",
        "keySetPath": str(KEYS), "keySetChecksum": get_key_cs(),
        "corpusPath": str(corpus_path), "corpusChecksum": corpus_cs(corpus_path),
        "outputDir": str(out_dir), "operation": "roundtrip"
    }
    runner = ["java", "-Xmx4g", "-jar", str(JAR)] if variant.startswith("java") else [str(GO_BIN)]
    try:
        r = subprocess.run(runner, input=json.dumps(cmd).encode(), capture_output=True, timeout=300)
        if r.returncode not in (0, 2):
            return None
        out = json.loads(r.stdout)
        ops = [op for op in out.get("operations", []) if not op.get("skipped")]
        times = [(op.get("encryptMs",0) or 0)+(op.get("decryptMs",0) or 0) for op in ops]
        times = [t for t in times if t > 0]
        if not times: return None
        total_bytes = sum(op.get("originalBytes",0) or 0 for op in ops)
        total_s = sum(times)/1000
        return {
            "p50_mean": round(statistics.median(times), 3),
            "p50_min":  round(min(times), 3),
            "p50_max":  round(max(times), 3),
            "p95_mean": round(sorted(times)[max(0,int(len(times)*0.95)-1)], 3),
            "rounds":   1,
            "throughput_mean_mbs": round(total_bytes/1048576/total_s, 2) if total_s > 0 else 0,
            "n_files":  len(times),
        }
    except Exception as e:
        print(f"    ERROR: {e}")
        return None

def run_scenario(sc_id, pub_alg, corpus_dir, results):
    print(f"\n  [{sc_id}] {pub_alg}")
    sc = {"pub_alg": pub_alg, "corpus": str(corpus_dir.relative_to(CORPUS)), "go": {}, "java": {}}

    for rnd in range(ROUNDS):
        order = ALL_VARIANTS if rnd % 2 == 0 else (JAVA_VARIANTS + GO_VARIANTS)
        for variant in order:
            od = OUT / sc_id / alg_short(pub_alg) / variant / f"r{rnd}"
            od.mkdir(parents=True, exist_ok=True)
            res = run_one(variant, corpus_dir, pub_alg, od)
            if res is None:
                sys.stdout.write("x"); sys.stdout.flush(); continue
            sys.stdout.write("."); sys.stdout.flush()
            lang = "go" if variant.startswith("go") else "java"
            if variant not in sc[lang]:
                sc[lang][variant] = {"_s": []}
            sc[lang][variant]["_s"].append(res["p50_mean"])

    # aggregate
    for lang in ["go", "java"]:
        for v, d in sc[lang].items():
            s = d.pop("_s", [])
            if s:
                d["p50_mean"] = round(statistics.median(s), 3)
                d["p50_min"]  = round(min(s), 3)
                d["p50_max"]  = round(max(s), 3)
                d["rounds"]   = len(s)

    results["scenarios"][sc_id] = sc
    print()

def alg_short(alg):
    return alg.lower().replace("-","").replace(" ","")

import sys

# ── setup corpus ──────────────────────────────────────────────────────────
def setup_corpus():
    print("\n📁 สร้าง corpus บน tmpfs...")

    # 1. file types (6 × 512KB × 15 files)
    for ft in ["txt","csv"]:
        gen_text(CORPUS/f"filetypes/{ft}", n=15, size_kb=512)
    for ft in ["pdf","xlsx","zip","dat"]:
        gen_binary(CORPUS/f"filetypes/{ft}", n=15, size_kb=512)
    print("  ✓ filetypes (6 types × 15 files × 512KB)")

    # 2. SIZE gradient: 1 file per size, binary (ไม่มี compress effect)
    sg_path = CORPUS / "size-gradient-binary"
    sg_path.mkdir(parents=True, exist_ok=True)
    sizes_kb = [1, 4, 16, 64, 128, 256, 512, 1024, 2048, 5120, 10240]
    rng = random.Random(42)
    for kb in sizes_kb:
        (sg_path / f"file_{kb}kb.dat").write_bytes(bytes(rng.getrandbits(8) for _ in range(kb*1024)))
    print(f"  ✓ size-gradient-binary ({len(sizes_kb)} sizes: 1KB→10MB)")

    # 3. SIZE gradient: compressible text
    sg_txt_path = CORPUS / "size-gradient-text"
    sg_txt_path.mkdir(parents=True, exist_ok=True)
    vocab = "the quick brown fox data encrypt process network request response".split()
    for kb in sizes_kb:
        target = kb * 1024
        rng2 = random.Random(42)
        buf, total = [], 0
        while total < target:
            line = " ".join(rng2.choices(vocab, k=rng2.randint(8,20))) + "\n"
            buf.append(line); total += len(line)
        content = "".join(buf)[:target]
        content += " " * (target - len(content))
        (sg_txt_path / f"file_{kb}kb.txt").write_bytes(content.encode("ascii","replace"))
    print(f"  ✓ size-gradient-text ({len(sizes_kb)} sizes: 1KB→10MB)")

    # 4. COUNT gradient: fixed 100KB binary, 1/5/10/25/50/100/200/500/1000 files
    for count in [1, 5, 10, 25, 50, 100, 200, 500, 1000]:
        p = CORPUS / f"count-gradient/{count}files"
        p.mkdir(parents=True, exist_ok=True)
        rng3 = random.Random(42)
        for i in range(count):
            (p / f"file{i:04d}.dat").write_bytes(bytes(rng3.getrandbits(8) for _ in range(100*1024)))
    print("  ✓ count-gradient (1→1000 files × 100KB binary)")

    # 5. many-small (existing)
    for name, kb, n in [("1kb",1,200),("10kb",10,200),("100kb",100,100)]:
        gen_text(CORPUS/f"manysmall/{name}", n=n, size_kb=kb)
    print("  ✓ manysmall")

    # 6. concurrent
    gen_binary(CORPUS/"concurrent", n=100, size_mb_each=1)
    print("  ✓ concurrent (100 × 1MB)")
    print(f"  corpus ready at {CORPUS}")

def gen_binary(dest, n=15, size_kb=512, size_mb_each=None):
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    kb = size_mb_each * 1024 if size_mb_each else size_kb
    for i in range(n):
        (dest / f"file{i:04d}.dat").write_bytes(bytes(rng.getrandbits(8) for _ in range(kb*1024)))

# ── main ──────────────────────────────────────────────────────────────────
def main():
    import sys
    OUT.mkdir(parents=True, exist_ok=True)

    print("="*60)
    print("Full Benchmark v5 — post-reboot cold start")
    print("="*60)
    os.system("uptime"); os.system("free -h")

    # mount tmpfs
    os.makedirs(str(CORPUS), exist_ok=True)
    r = subprocess.run(["mount", "-t", "tmpfs", "-o", "size=8G", "tmpfs", str(CORPUS)],
                       capture_output=True)
    if r.returncode != 0:
        print(f"  tmpfs mount failed, using regular dir: {r.stderr.decode()[:100]}")
    else:
        print(f"  ✓ tmpfs mounted at {CORPUS}")
    subprocess.run(["chown", f"{os.getenv('USER','tikxd')}:{os.getenv('USER','tikxd')}", str(CORPUS)])

    setup_corpus()

    results = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "vm_ram_gb": 14, "rounds": ROUNDS,
        "note": "v5: cold start, size+count gradient added",
        "scenarios": {}, "size_gradient": {}, "count_gradient": {}, "concurrent": {}
    }

    KEY_ALGS = ["RSA-2048", "RSA-4096", "Curve25519"]

    # ── 1. File type matrix ──────────────────────────────────────────────
    print("\n\n📊 Phase 1: File type matrix")
    for ft in ["txt","csv","pdf","xlsx","zip","dat"]:
        for alg in KEY_ALGS:
            sc_id = f"ft-{ft}-{alg_short(alg)}"
            run_scenario(sc_id, alg, CORPUS/f"filetypes/{ft}", results)

    # ── 2. Size gradient (binary — isolate size effect, no ZLIB) ─────────
    print("\n\n📐 Phase 2: Size gradient — binary (RSA-2048)")
    alg = "RSA-2048"
    # วัดทีละ 1 ไฟล์ตามขนาดต่างๆ
    sizes_kb = [1, 4, 16, 64, 128, 256, 512, 1024, 2048, 5120, 10240]
    for kb in sizes_kb:
        # สร้าง single-file corpus
        sf_path = CORPUS / f"single-binary-{kb}kb"
        sf_path.mkdir(parents=True, exist_ok=True)
        rng = random.Random(42)
        (sf_path / f"file.dat").write_bytes(bytes(rng.getrandbits(8) for _ in range(kb*1024)))

        sc_id = f"size-{kb}kb-binary"
        run_scenario(sc_id, alg, sf_path, results)
        results["size_gradient"][f"{kb}kb_binary"] = results["scenarios"].pop(sc_id, {})

    # Size gradient (text — with ZLIB)
    print("\n\n📐 Phase 2b: Size gradient — text compressible (RSA-2048)")
    for kb in sizes_kb:
        sf_path = CORPUS / f"single-text-{kb}kb"
        sf_path.mkdir(parents=True, exist_ok=True)
        vocab = "the quick brown fox data encrypt process network request response".split()
        target = kb * 1024
        rng2 = random.Random(42)
        buf, total = [], 0
        while total < target:
            line = " ".join(rng2.choices(vocab, k=rng2.randint(8,20))) + "\n"
            buf.append(line); total += len(line)
        content = "".join(buf)[:target] + " " * max(0, target - len("".join(buf)[:target]))
        (sf_path / f"file.txt").write_bytes(content.encode("ascii","replace"))

        sc_id = f"size-{kb}kb-text"
        run_scenario(sc_id, alg, sf_path, results)
        results["size_gradient"][f"{kb}kb_text"] = results["scenarios"].pop(sc_id, {})

    # ── 3. Count gradient (fixed 100KB binary, vary count) ───────────────
    print("\n\n📦 Phase 3: Count gradient — 100KB binary (RSA-2048)")
    for count in [1, 5, 10, 25, 50, 100, 200, 500, 1000]:
        sc_id = f"count-{count}files"
        run_scenario(sc_id, alg, CORPUS/f"count-gradient/{count}files", results)
        results["count_gradient"][f"{count}files"] = results["scenarios"].pop(sc_id, {})

    # ── 4. Many-small ────────────────────────────────────────────────────
    print("\n\n📦 Phase 4: Many-small files")
    for name in ["1kb","10kb","100kb"]:
        sc_id = f"many-{name}"
        run_scenario(sc_id, "RSA-2048", CORPUS/f"manysmall/{name}", results)

    # ── 5. Concurrent load ───────────────────────────────────────────────
    print("\n\n⚡ Phase 5: Concurrent load test")
    for cl in [1, 2, 4, 8]:
        results["concurrent"][str(cl)] = {}
        for v in ["go-stream-parallel","java-stream-parallel"]:
            od = OUT / "conc" / str(cl) / v
            od.mkdir(parents=True, exist_ok=True)
            cmd = {
                "command": "run", "variantId": v,
                "mode": "steady_state", "warmupIterations": 1, "concurrency": cl,
                "cryptoProfile": {"pubAlg": "RSA-2048","cipher":"AES-256","compression":"ZLIB","hash":"SHA-256"},
                "outputEncoding": "binary",
                "keySetPath": str(KEYS), "keySetChecksum": get_key_cs(),
                "corpusPath": str(CORPUS/"concurrent"),
                "corpusChecksum": corpus_cs(CORPUS/"concurrent"),
                "outputDir": str(od), "operation": "roundtrip"
            }
            runner = ["java","-Xmx4g","-jar",str(JAR)] if v.startswith("java") else [str(GO_BIN)]
            try:
                r = subprocess.run(runner, input=json.dumps(cmd).encode(), capture_output=True, timeout=300)
                if r.returncode in (0,2):
                    out = json.loads(r.stdout)
                    ops = [op for op in out.get("operations",[]) if not op.get("skipped")]
                    rt = [(op.get("encryptMs",0) or 0)+(op.get("decryptMs",0) or 0) for op in ops]
                    rt = [t for t in rt if t > 0]
                    tb = sum(op.get("originalBytes",0) or 0 for op in ops)
                    ts = sum(rt)/1000
                    results["concurrent"][str(cl)][v] = {
                        "throughput_mean_mbs": round(tb/1048576/ts,1) if ts>0 else 0,
                        "roundTrip": {"p50": round(statistics.median(rt),2) if rt else 0}
                    }
                    print(f"    {v} {cl}cl: {results['concurrent'][str(cl)][v]['throughput_mean_mbs']} MB/s")
            except Exception as e:
                print(f"    {v} SKIP: {e}")

    # save
    results["finishedAt"] = datetime.now(timezone.utc).isoformat()
    results["totalScenarios"] = len(results["scenarios"])
    out_file = OUT / "results_v5.json"
    out_file.write_text(json.dumps(results, indent=2))
    print(f"\n\n✅ เสร็จแล้ว → {out_file}")
    print(f"   scenarios: {results['totalScenarios']}")
    print(f"   size_gradient: {len(results['size_gradient'])} entries")
    print(f"   count_gradient: {len(results['count_gradient'])} entries")

if __name__ == "__main__":
    main()
