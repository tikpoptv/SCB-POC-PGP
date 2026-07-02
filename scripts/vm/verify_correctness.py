#!/usr/bin/env python3
"""
verify_correctness.py — ด่านสุดท้ายก่อนรันจริง (กันพลาดแบบ v2)

พิสูจน์ว่า: บีบอัด → เข้ารหัส → ถอดรหัส → คลายบีบอัด แล้วได้ไฟล์ "เป๊ะ byte-for-byte"
กับ binary จริงที่จะใช้รัน benchmark (go-klauspost / go-stdlib / java) ครบทุกสกุล
(txt/csv/pdf/zip) × ทุก key alg (RSA-2048/RSA-4096/Curve25519) × ทุก variant.

เงื่อนไข PASS ที่เข้มงวด (ต่างจาก v2 ที่วัดผิดเพราะไฟล์ถูก skip เงียบๆ):
  - total == จำนวนไฟล์ที่คาดไว้         (ไม่มีไฟล์หาย)
  - skipped == 0                        (ไม่มีไฟล์ถูกข้าม)
  - roundTripOk == total                (ถอดแล้วตรงต้นฉบับทุกไฟล์)
  - encryptMs>0 และ decryptMs>0 ทุกไฟล์ (วัดจริง ไม่ใช่ 0/None)
  - ciphertextBytes>0 และ ciphertext != plaintext

รัน:  python3 scripts/vm/verify_correctness.py
exit 0 = ผ่านหมด, exit 1 = มีอะไรพัง (อย่ารัน benchmark ต่อ)
"""
import json, os, subprocess, pathlib, hashlib, random, sys

REPO = pathlib.Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    cwd=pathlib.Path(__file__).parent, capture_output=True, text=True).stdout.strip())
KEYS = REPO / "keys"
GO_KP = REPO / "runners/go/go-runner-klauspost"
GO_STD = REPO / "runners/go/go-runner-stdlib"
JAR = REPO / "runners/java/target/java-runner-0.1.0.jar"
CORPUS = pathlib.Path(os.getenv("POC_CORPUS", "/tmp/verify-corpus"))

KEY_ALGS = [a.strip() for a in os.getenv("VERIFY_KEY_ALGS", "RSA-2048,RSA-4096,Curve25519").split(",") if a.strip()]

# runner + variants (in-memory + streaming ต้องถูกต้องทั้งคู่)
RUNNERS = {
    "go-klauspost": ([str(GO_KP)], ["go-inmem-single", "go-stream-single", "go-stream-parallel"]),
    "go-stdlib":    ([str(GO_STD)], ["go-inmem-single", "go-stream-single", "go-stream-parallel"]),
    "java":         (["java", "-jar", str(JAR)], ["java-inmem-single", "java-stream-single", "java-stream-parallel"]),
}


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
            e.append((f.relative_to(path).as_posix(), hashlib.sha256(f.read_bytes()).hexdigest()))
    e.sort()
    hh = hashlib.sha256()
    for rel, hx in e:
        hh.update(rel.encode()); hh.update(b"\x00"); hh.update(hx.encode()); hh.update(b"\n")
    return "sha256:" + hh.hexdigest()


def make_corpus():
    """สร้างไฟล์ครบ 4 สกุล × หลายลักษณะ (เล็ก/ใหญ่/ว่าง/ไบต์ขอบเขต) เพื่อกด edge case"""
    CORPUS.mkdir(parents=True, exist_ok=True)
    for f in CORPUS.glob("*"):
        f.unlink()
    rng = random.Random(1234)
    # compressible text/csv
    def text(n):
        vocab = "the quick brown fox data encrypt secure benchmark compression".split()
        b = []
        while sum(len(x) for x in b) < n:
            b.append(" ".join(rng.choices(vocab, k=12)) + "\n")
        return ("".join(b)[:n]).encode()
    def csv(n):
        b = []
        while sum(len(x) for x in b) < n:
            b.append(f"{rng.randint(0,99999)},{rng.randint(0,9)},{rng.random():.3f}\n")
        return ("".join(b)[:n]).encode()
    files = {
        # เล็ก
        "small.txt": text(64 * 1024),
        "small.csv": csv(64 * 1024),
        "small.pdf": rng.randbytes(64 * 1024),
        "small.zip": rng.randbytes(64 * 1024),
        # ใหญ่ (กด streaming path > buffer)
        "big.txt": text(4 * 1024 * 1024),
        "big.pdf": rng.randbytes(4 * 1024 * 1024),
        # edge: ไฟล์ว่าง + ไบต์พิเศษ (lone CR / null / high bytes)
        "empty.txt": b"",
        "edge.txt": b"a\rb\r\nc\x00\x01\xff\xfe binary-ish \n",
    }
    for name, data in files.items():
        (CORPUS / name).write_bytes(data)
    return files


def run(binary_cmd, variant, pub_alg, out_dir):
    cmd = {
        "command": "run", "variantId": variant, "mode": "steady_state",
        "warmupIterations": 0, "concurrency": 1,
        "cryptoProfile": {"pubAlg": pub_alg, "cipher": "AES-256", "compression": "ZLIB", "hash": "SHA-256"},
        "outputEncoding": "binary",
        "keySetPath": str(KEYS), "keySetChecksum": key_cs(),
        "corpusPath": str(CORPUS), "corpusChecksum": corpus_cs(CORPUS),
        "outputDir": str(out_dir), "operation": "roundtrip",
    }
    r = subprocess.run(binary_cmd, input=json.dumps(cmd).encode(), capture_output=True, timeout=600)
    return r


def check(ops, expected_n):
    """คืน (ok: bool, reason: str)"""
    if len(ops) != expected_n:
        return False, f"operation count {len(ops)} != expected {expected_n}"
    skipped = [o for o in ops if o.get("skipped")]
    if skipped:
        return False, f"{len(skipped)} file(s) skipped: {[o.get('fileName') for o in skipped][:5]}"
    bad_rt = [o["fileName"] for o in ops if not o.get("roundTripOk")]
    if bad_rt:
        return False, f"roundTripOk FALSE (ไม่ตรงต้นฉบับ!): {bad_rt[:5]}"
    # empty file: encrypt/decrypt อาจ ~0ms ยอมได้ แต่ non-empty ต้อง >0 และ ciphertext>0
    for o in ops:
        if (o.get("originalBytes") or 0) > 0:
            if not (o.get("ciphertextBytes") or 0) > 0:
                return False, f"{o['fileName']}: ciphertextBytes ว่าง"
            enc, dec = o.get("encryptMs"), o.get("decryptMs")
            if enc is None or dec is None or enc < 0 or dec < 0:
                return False, f"{o['fileName']}: enc/dec time ไม่ถูกต้อง ({enc}/{dec})"
    return True, "ok"


def main():
    for b in (GO_KP, GO_STD):
        if not b.exists():
            print(f"❌ ไม่พบ {b} — build ก่อน"); sys.exit(1)
    have_java = JAR.exists()

    files = make_corpus()
    expected_n = len(files)
    out_root = CORPUS / "_verify_out"; out_root.mkdir(exist_ok=True)
    print(f"corpus: {expected_n} ไฟล์ (txt/csv/pdf/zip + empty + edge) @ {CORPUS}")
    print(f"key algs: {KEY_ALGS}\n")

    import shutil
    all_pass = True
    hdr = f"{'impl':13s} {'variant':22s} {'keyAlg':11s} {'total':>5s} {'skip':>4s} {'ok':>4s}  result"
    print(hdr); print("-" * len(hdr))
    for label, (cmd, variants) in RUNNERS.items():
        if label == "java" and not have_java:
            print(f"{label}: ข้าม (ไม่พบ jar)"); continue
        for variant in variants:
            for alg in KEY_ALGS:
                od = out_root / label / variant / alg; od.mkdir(parents=True, exist_ok=True)
                try:
                    r = run(cmd, variant, alg, od)
                except Exception as e:
                    print(f"{label:13s} {variant:22s} {alg:11s}  ERROR: {e}"); all_pass = False; continue
                finally:
                    pass
                if r.returncode not in (0, 2):
                    print(f"{label:13s} {variant:22s} {alg:11s}  exit={r.returncode} FAIL: {r.stderr.decode()[:120]}")
                    all_pass = False
                    shutil.rmtree(od, ignore_errors=True); continue
                try:
                    out = json.loads(r.stdout)
                except Exception as e:
                    print(f"{label:13s} {variant:22s} {alg:11s}  bad JSON: {e}"); all_pass = False
                    shutil.rmtree(od, ignore_errors=True); continue
                ops = out.get("operations", [])
                ok, reason = check(ops, expected_n)
                nskip = sum(1 for o in ops if o.get("skipped"))
                nok = sum(1 for o in ops if o.get("roundTripOk"))
                status = "PASS ✅" if ok else f"FAIL ❌ ({reason})"
                print(f"{label:13s} {variant:22s} {alg:11s} {len(ops):>5d} {nskip:>4d} {nok:>4d}  {status}")
                if not ok:
                    all_pass = False
                shutil.rmtree(od, ignore_errors=True)

    print()
    if all_pass:
        print("=" * 60)
        print("✅✅ ผ่านทั้งหมด — roundtrip byte-for-byte ถูกต้องทุก impl/variant/สกุล/keyAlg")
        print("    ปลอดภัยที่จะรัน benchmark จริง")
        print("=" * 60)
        sys.exit(0)
    else:
        print("=" * 60)
        print("❌❌ มีเคสพัง — อย่ารัน benchmark จนกว่าจะแก้ (กันวัดผลผิดแบบ v2)")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
