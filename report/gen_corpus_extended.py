#!/usr/bin/env python3
"""
gen_corpus_extended.py — สร้าง corpus ขยายบน VM สำหรับ benchmark รอบ 2
ไฟล์ครบทุกชนิด + ทุกขนาด

USAGE (รันบน VM):
    python3 gen_corpus_extended.py
"""
import os, random, struct, pathlib, hashlib, json

BASE   = pathlib.Path("/mnt/corpus-ext")
SEED   = 999888777
rng    = random.Random(SEED)

# ─── helpers ──────────────────────────────────────────────────────────────────

def fill_compressible(n: int) -> bytes:
    """ข้อความซ้ำ — บีบอัดได้สูง เหมือน .txt/.csv จริง"""
    words = ["benchmark","encryption","pgp","performance","data","file",
             "crypto","aes","rsa","curve","test","result","latency","throughput"]
    out = []
    while len(b"".join(out)) < n:
        line = " ".join(rng.choices(words, k=rng.randint(5,12))) + "\n"
        out.append(line.encode())
    return b"".join(out)[:n]

def fill_incompressible(n: int) -> bytes:
    """random bytes — บีบไม่ได้ เหมือน PDF binary / image"""
    s = SEED
    buf = bytearray(n)
    for i in range(n):
        s ^= s << 13; s &= 0xFFFFFFFFFFFFFFFF
        s ^= s >> 7;  s &= 0xFFFFFFFFFFFFFFFF
        s ^= s << 17; s &= 0xFFFFFFFFFFFFFFFF
        buf[i] = s & 0xFF
    return bytes(buf)

def fill_csv(n: int) -> bytes:
    """CSV rows — compressible"""
    header = b"id,name,value,category,timestamp\n"
    rows = []
    i = 0
    while len(header) + sum(len(r) for r in rows) < n:
        row = f"{i},item_{i},{rng.randint(1,9999)},cat_{i%10},2025-{(i%12)+1:02d}-{(i%28)+1:02d}\n"
        rows.append(row.encode())
        i += 1
    return (header + b"".join(rows))[:n]

def fill_xlsx_like(n: int) -> bytes:
    """ZIP-based binary (เลียนแบบ .xlsx) — mix compress+incompressible"""
    # .xlsx header magic
    hdr = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"
    body = fill_incompressible(n - len(hdr))
    return (hdr + body)[:n]

def fill_gz_like(n: int) -> bytes:
    """already-compressed data (.gz) — bzip2/gzip magic + random"""
    hdr = b"\x1f\x8b\x08\x00\x00\x00\x00\x00"  # gzip magic
    body = fill_incompressible(n - len(hdr))
    return (hdr + body)[:n]

def fill_pdf_like(n: int) -> bytes:
    """PDF-like binary"""
    hdr = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    body = fill_incompressible(n - len(hdr))
    return (hdr + body)[:n]

# ─── Tier A: แยกชนิดไฟล์จริง (500 KB each, 10 files each) ──────────────────

TIER_A = {
    "filetypes/txt":   [(f"doc{i:03d}.txt",  512*1024, fill_compressible)  for i in range(10)],
    "filetypes/csv":   [(f"data{i:03d}.csv", 512*1024, fill_csv)           for i in range(10)],
    "filetypes/pdf":   [(f"doc{i:03d}.pdf",  512*1024, fill_pdf_like)      for i in range(10)],
    "filetypes/xlsx":  [(f"book{i:03d}.xlsx",512*1024, fill_xlsx_like)     for i in range(10)],
    "filetypes/zip":   [(f"arch{i:03d}.gz",  512*1024, fill_gz_like)       for i in range(10)],
    "filetypes/dat":   [(f"bin{i:03d}.dat",  512*1024, fill_incompressible)for i in range(10)],
}

# ─── Tier B: Size gradient ครบทุกขนาด (.txt compressible) ────────────────────

SIZES = [
    (         1_024, "1KB"),
    (        10_240, "10KB"),
    (       102_400, "100KB"),
    (       512_000, "500KB"),
    (     1_048_576, "1MB"),
    (     5_242_880, "5MB"),
    (    10_485_760, "10MB"),
    (    20_971_520, "20MB"),
    (    52_428_800, "50MB"),
    (   104_857_600, "100MB"),
]

# ─── Tier C: Many small files (stress per-file overhead) ──────────────────────

TIER_C = {
    "manysmall-1kb":   [(f"s{i:04d}.txt",  1_024, fill_compressible) for i in range(500)],
    "manysmall-10kb":  [(f"s{i:04d}.txt", 10_240, fill_compressible) for i in range(200)],
    "manysmall-50kb":  [(f"s{i:04d}.txt", 51_200, fill_compressible) for i in range(100)],
}

# ─── main ─────────────────────────────────────────────────────────────────────

manifest = {}

BASE.mkdir(parents=True, exist_ok=True)

print("=== Generating Extended Corpus ===\n")

# Tier A
print("Tier A — File types (10 files × 6 types × 512 KB):")
for sc, files in TIER_A.items():
    d = BASE / sc
    d.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for fname, size, gen in files:
        p = d / fname
        data = gen(size)
        p.write_bytes(data)
        checksums[fname] = hashlib.sha256(data).hexdigest()
    manifest[sc] = {"files": len(files), "size_each": files[0][1], "checksums": checksums}
    print(f"  {sc}: {len(files)} files, {files[0][1]//1024} KB each")

# Tier B
print("\nTier B — Size gradient (.txt compressible):")
sc = "sizegradient"
d = BASE / sc
d.mkdir(parents=True, exist_ok=True)
checksums = {}
for size_bytes, label in SIZES:
    fname = f"file_{label}.txt"
    data = fill_compressible(size_bytes)
    (d / fname).write_bytes(data)
    checksums[fname] = hashlib.sha256(data).hexdigest()
    print(f"  {fname}: {size_bytes:>12,} bytes ({label})")
manifest[sc] = {"sizes": [s for _, s in SIZES], "checksums": checksums}

# Tier B incompressible
print("\nTier B-incomp — Size gradient (binary incompressible):")
sc = "sizegradient-incomp"
d = BASE / sc
d.mkdir(parents=True, exist_ok=True)
checksums = {}
for size_bytes, label in SIZES[:-1]:  # skip 100MB for incompressible (memory concern)
    fname = f"file_{label}.dat"
    data = fill_incompressible(size_bytes)
    (d / fname).write_bytes(data)
    checksums[fname] = hashlib.sha256(data).hexdigest()
    print(f"  {fname}: {size_bytes:>12,} bytes ({label})")
manifest[sc] = {"sizes": [s for _, s in SIZES[:-1]], "checksums": checksums}

# Tier C
print("\nTier C — Many small files:")
for sc, files in TIER_C.items():
    d = BASE / sc
    d.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for fname, size, gen in files:
        data = gen(size)
        (d / fname).write_bytes(data)
        checksums[fname] = hashlib.sha256(data).hexdigest()
    manifest[sc] = {"files": len(files), "size_each": files[0][1]}
    print(f"  {sc}: {len(files)} files, {files[0][1]//1024} KB each")

# Write manifest
manifest_path = BASE / "manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2))

total_files = sum(
    info.get("files", len(info.get("sizes", []))) for info in manifest.values()
)
print(f"\n✓ Corpus ready at {BASE}")
print(f"  Scenarios: {len(manifest)}")
print(f"  Total files: ~{total_files}")
print(f"  Manifest: {manifest_path}")
