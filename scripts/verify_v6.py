#!/usr/bin/env python3
"""verify_v6.py — ตรวจว่า runner process ไฟล์จริง ไม่ skip (กันพลาดแบบ v2)"""
import json, subprocess, hashlib, pathlib, os, tempfile

KEYS = pathlib.Path("/home/tikxd/POC-Encryption/keys")
GO   = str(pathlib.Path("/home/tikxd/POC-Encryption/runners/go/go-runner"))
JAR  = "/home/tikxd/POC-Encryption/runners/java/target/java-runner-0.1.0.jar"


def kcs():
    lines = []
    for f in sorted(KEYS.iterdir()):
        if f.name.endswith("-public.asc") or f.name.endswith("-private.asc"):
            h = hashlib.sha256(); h.update(f.read_bytes())
            lines.append(f.name + ":sha256:" + h.hexdigest())
    lines.sort()
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def ccs(p):
    e = []
    for f in sorted(p.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(p)).replace(os.sep, "/")
            h = hashlib.sha256(); h.update(f.read_bytes())
            e.append((rel, h.hexdigest()))
    e.sort()
    hh = hashlib.sha256()
    for rel, hx in e:
        hh.update(rel.encode()); hh.update(b"\x00"); hh.update(hx.encode()); hh.update(b"\n")
    return "sha256:" + hh.hexdigest()


def check(corpus_path, variant, runner_cmd):
    p = pathlib.Path(corpus_path)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = {
            "command": "run", "variantId": variant,
            "mode": "steady_state", "warmupIterations": 1, "concurrency": 1,
            "cryptoProfile": {"pubAlg": "RSA-2048", "cipher": "AES-256",
                              "compression": "ZLIB", "hash": "SHA-256"},
            "outputEncoding": "binary",
            "keySetPath": str(KEYS), "keySetChecksum": kcs(),
            "corpusPath": str(p), "corpusChecksum": ccs(p),
            "outputDir": tmp, "operation": "roundtrip"
        }
        r = subprocess.run(runner_cmd, input=json.dumps(cmd).encode(),
                           capture_output=True, timeout=120)
        out = json.loads(r.stdout)
        ops = out.get("operations", [])
        total = len(ops)
        skipped = sum(1 for o in ops if o.get("skipped"))
        rt_ok = sum(1 for o in ops if o.get("roundTripOk"))
        o0 = ops[0] if ops else {}
        enc = o0.get("encryptMs")
        dec = o0.get("decryptMs")
        byts = o0.get("originalBytes")
        ok = o0.get("roundTripOk")
        print("  {} on {}: total={} skipped={} roundTripOk={}".format(
            variant, p.name, total, skipped, rt_ok))
        print("    sample: enc={} dec={} bytes={} ok={}".format(enc, dec, byts, ok))


GO_CMD = [GO]
JAVA_CMD = ["java", "-jar", JAR]

print("=== Go ===")
check("/mnt/corpus-v6/filetypes/txt", "go-inmem-single", GO_CMD)
check("/mnt/corpus-v6/filetypes/pdf", "go-inmem-single", GO_CMD)
print("=== Java ===")
check("/mnt/corpus-v6/filetypes/txt", "java-inmem-single", JAVA_CMD)
check("/mnt/corpus-v6/filetypes/pdf", "java-inmem-single", JAVA_CMD)
