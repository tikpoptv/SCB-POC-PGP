#!/usr/bin/env python3
"""
run_benchmark_extended.py — Benchmark รอบ 2 ด้วย corpus ขยาย

USAGE (รันบน VM หลังจากรัน gen_corpus_extended.py แล้ว):
    export PATH=$PATH:/usr/local/go/bin
    export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
    python3 run_benchmark_extended.py

OUTPUT:
    /tmp/bench-ext/results_extended.json
"""
import json, os, subprocess, time, statistics, pathlib, sys
from datetime import datetime, timezone

POC_DIR   = pathlib.Path("/home/tikxd/POC-Encryption")
KEYS_DIR  = POC_DIR / "keys"
CORPUS    = pathlib.Path("/mnt/corpus-ext")
OUT_DIR   = pathlib.Path("/tmp/bench-ext")
JAVA_JAR  = POC_DIR / "runners/java/target/java-runner-0.1.0.jar"
GO_BIN    = POC_DIR / "runners/go/go-runner"
CMDGEN_CP = f"/tmp/cmdgen-build:{JAVA_JAR}"

# Best variants only (from round 1 — reduces runtime while keeping insight)
VARIANTS = {
    "go":   ["go-inmem-single", "go-stream-single", "go-stream-parallel"],
    "java": ["java-inmem-single", "java-stream-single", "java-stream-parallel"],
}

# ─── Scenarios definition ─────────────────────────────────────────────────────

# Tier A: file types (เฉพาะ RSA-2048 เพื่อเปรียบชนิดไฟล์ล้วนๆ)
TIER_A_SCENARIOS = [
    ("filetypes/txt",  "RSA-2048", "txt-files"),
    ("filetypes/csv",  "RSA-2048", "csv-files"),
    ("filetypes/pdf",  "RSA-2048", "pdf-files"),
    ("filetypes/xlsx", "RSA-2048", "xlsx-files"),
    ("filetypes/zip",  "RSA-2048", "zip-gz-files"),
    ("filetypes/dat",  "RSA-2048", "dat-binary-files"),
]

# Tier B: size gradient × 3 key types
SIZE_LABELS = ["1KB","10KB","100KB","500KB","1MB","5MB","10MB","20MB","50MB"]
TIER_B_SCENARIOS_COMP   = [("sizegradient",       alg, f"sizegrad-comp-{alg.lower()}")   for alg in ["RSA-2048","RSA-4096","Curve25519"]]
TIER_B_SCENARIOS_INCOMP = [("sizegradient-incomp", alg, f"sizegrad-incomp-{alg.lower()}") for alg in ["RSA-2048","Curve25519"]]

# Tier C: many small
TIER_C_SCENARIOS = [
    ("manysmall-1kb",  "RSA-2048", "many-1kb"),
    ("manysmall-10kb", "RSA-2048", "many-10kb"),
    ("manysmall-50kb", "RSA-2048", "many-50kb"),
]

ALL_SCENARIOS = TIER_A_SCENARIOS + TIER_B_SCENARIOS_COMP + TIER_B_SCENARIOS_INCOMP + TIER_C_SCENARIOS

ROUNDS  = 3   # ลดรอบเพราะ scenarios เยอะขึ้น
WARMUP  = 1

# ─── helpers (เหมือน run_benchmark.py เดิม) ───────────────────────────────────

def make_cmd(keys, corpus, out, variant, pub_alg):
    result = subprocess.run(
        ["java", "-cp", CMDGEN_CP, "CmdGen",
         str(keys), str(corpus), str(out), pub_alg, "roundtrip"],
        capture_output=True, text=True, timeout=20
    )
    if not result.stdout.strip():
        raise RuntimeError(f"CmdGen failed: {result.stderr[:200]}")
    cmd = json.loads(result.stdout)
    cmd["variantId"] = variant
    cmd["mode"] = "steady_state"
    cmd["warmupIterations"] = WARMUP
    cmd["concurrency"] = 4 if "parallel" in variant else 1
    return json.dumps(cmd)

def run_variant(variant, cmd_json):
    is_java = variant.startswith("java")
    proc = ["java", "-Xmx3g", "-jar", str(JAVA_JAR)] if is_java else [str(GO_BIN)]
    try:
        r = subprocess.run(proc, input=cmd_json, capture_output=True,
                           text=True, timeout=300)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except Exception as e:
        print(f"  ERROR {variant}: {e}", file=sys.stderr)
    return None

def summarize(ops):
    enc = [o["encryptMs"] for o in ops if o.get("encryptMs") and not o.get("skipped")]
    dec = [o["decryptMs"] for o in ops if o.get("decryptMs") and not o.get("skipped")]
    rt  = [e + d for e, d in zip(enc, dec)]
    ok  = sum(1 for o in ops if o.get("roundTripOk") and not o.get("skipped"))
    total_bytes = sum(o.get("originalBytes", 0) for o in ops if not o.get("skipped"))
    def stat(xs):
        if not xs: return {}
        xs_s = sorted(xs)
        n = len(xs_s)
        return {
            "n": n, "mean": round(statistics.mean(xs), 3),
            "p50": round(xs_s[n//2], 3),
            "p95": round(xs_s[min(int(n*0.95), n-1)], 3),
            "min": round(xs_s[0], 3), "max": round(xs_s[-1], 3),
        }
    throughput_mbs = None
    if rt:
        total_rt_s = sum(rt) / 1000.0
        if total_rt_s > 0:
            throughput_mbs = round((total_bytes / 1_048_576) / total_rt_s, 2)
    return {
        "encrypt": stat(enc), "decrypt": stat(dec), "roundTrip": stat(rt),
        "roundTripOk": ok, "total": len(enc),
        "totalBytes": total_bytes, "throughputMbSec": throughput_mbs,
    }

def agg(rounds_list):
    if not rounds_list: return {}
    p50s = [r["roundTrip"].get("p50") for r in rounds_list if r.get("roundTrip", {}).get("p50")]
    thr  = [r.get("throughputMbSec") for r in rounds_list if r.get("throughputMbSec")]
    if not p50s: return {}
    return {
        "p50_mean": round(statistics.mean(p50s), 3),
        "p50_min":  round(min(p50s), 3),
        "p50_max":  round(max(p50s), 3),
        "rounds":   len(p50s),
        "throughput_mean_mbs": round(statistics.mean(thr), 2) if thr else None,
    }

# ─── main ─────────────────────────────────────────────────────────────────────

OUT_DIR.mkdir(parents=True, exist_ok=True)
results = {
    "startedAt": datetime.now(timezone.utc).isoformat(),
    "note": "Extended benchmark — file types + size gradient",
    "scenarios": {}
}

print(f"=== Extended PGP Benchmark ({results['startedAt'][:19]}) ===")
print(f"  {len(ALL_SCENARIOS)} scenarios × {len(VARIANTS['go'])+len(VARIANTS['java'])} variants × {ROUNDS} rounds\n")

total_scenarios = len(ALL_SCENARIOS)
for sc_idx, (corpus_subdir, pub_alg, sc_id) in enumerate(ALL_SCENARIOS, 1):
    corpus_path = CORPUS / corpus_subdir
    if not corpus_path.exists():
        print(f"  SKIP {sc_id} — corpus not found at {corpus_path}")
        continue

    n_files = len(list(corpus_path.iterdir()))
    print(f"\n[{sc_idx}/{total_scenarios}] {sc_id}  ({n_files} files, {pub_alg})")
    results["scenarios"][sc_id] = {}

    round_results = {"go": {v: [] for v in VARIANTS["go"]},
                     "java": {v: [] for v in VARIANTS["java"]}}

    for rnd in range(ROUNDS):
        order = (["go", "java"] if rnd % 2 == 0 else ["java", "go"])
        for lang in order:
            for variant in VARIANTS[lang]:
                out_path = OUT_DIR / sc_id / pub_alg / variant / f"r{rnd}"
                out_path.mkdir(parents=True, exist_ok=True)
                try:
                    cmd_json = make_cmd(KEYS_DIR, corpus_path, out_path, variant, pub_alg)
                    t0 = time.monotonic()
                    output = run_variant(variant, cmd_json)
                    elapsed = time.monotonic() - t0
                    if output:
                        s = summarize(output["operations"])
                        round_results[lang][variant].append(s)
                        rt_p50 = s["roundTrip"].get("p50", "?")
                        thr    = s.get("throughputMbSec", "?")
                        print(f"  [{lang}] {variant:<30} p50={rt_p50}ms "
                              f"thr={thr}MB/s ok={s['roundTripOk']}/{s['total']} ({elapsed:.1f}s)")
                    else:
                        print(f"  [{lang}] {variant:<30} FAILED")
                except Exception as e:
                    print(f"  [{lang}] {variant}: ERROR {e}")

    for lang in ["go", "java"]:
        results["scenarios"][sc_id][lang] = {
            v: agg(round_results[lang][v]) for v in VARIANTS[lang]
        }

results["finishedAt"] = datetime.now(timezone.utc).isoformat()
out_file = OUT_DIR / "results_extended.json"
out_file.write_text(json.dumps(results, indent=2))
print(f"\n\n✓ Results saved → {out_file}")
print("=== DONE ===")
