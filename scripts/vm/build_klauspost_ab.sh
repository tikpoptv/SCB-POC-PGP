#!/usr/bin/env bash
# build_klauspost_ab.sh — สร้าง binary สำหรับเทียบ 3 ทางบน VM
#   1) go-runner-klauspost : Go runner ที่ใช้ go-crypto fork (klauspost zlib)  [replace เปิด]
#   2) go-runner-stdlib    : Go runner baseline ที่ใช้ stdlib compress/zlib     [replace ปิด]
#   3) java-runner jar     : Java runner (BouncyCastle / native zlib)
#
# รันบน VM (Ubuntu 24.04, GNU sed):  bash scripts/vm/build_klauspost_ab.sh
# ต้องอยู่บน branch: experiment/go-klauspost-compression
set -euo pipefail

# repo root = โฟลเดอร์บนสุดของ git (ไม่ผูกกับชื่อโฟลเดอร์ ใช้ได้ทั้ง POC-Encryption / อื่น ๆ)
REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
GO_DIR="$REPO/runners/go"
JAVA_DIR="$REPO/runners/java"
OUT="$GO_DIR"   # วาง binary ไว้ข้าง go-runner เดิม

echo "== repo: $REPO"
echo "== branch: $(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
echo "== go: $(go version) | java: $(java -version 2>&1 | head -1)"

cd "$GO_DIR"

# --- 1) klauspost build (replace เปิดตาม commit) ---------------------------
echo ""
echo "[1/3] build go-runner-klauspost (fork + klauspost zlib)"
grep -q '^replace github.com/ProtonMail/go-crypto' go.mod \
  || { echo "❌ ไม่พบ replace directive — ต้องอยู่บน branch experiment/go-klauspost-compression"; exit 1; }
go build -trimpath -o "$OUT/go-runner-klauspost" .
echo "  ✓ $OUT/go-runner-klauspost"

# --- 2) stdlib baseline build (ปิด replace ชั่วคราว แล้ว restore ด้วย git) ---
echo ""
echo "[2/3] build go-runner-stdlib (baseline stdlib zlib)"
restore_gomod() {
  git -C "$REPO" checkout -- runners/go/go.mod runners/go/go.sum 2>/dev/null || true
}
trap restore_gomod EXIT
# ลบบรรทัด replace ออกชั่วคราว แล้ว tidy (ต้องมีเน็ตเพื่อดึง hash go-crypto v1.4.1 upstream)
sed -i '/^replace github.com\/ProtonMail\/go-crypto/d' go.mod
go mod tidy
go build -trimpath -o "$OUT/go-runner-stdlib" .
restore_gomod
go mod tidy   # คืน state ให้ตรง (replace เปิดอีกครั้ง)
trap - EXIT
echo "  ✓ $OUT/go-runner-stdlib"

# verify ว่า binary klauspost มี symbol ของ klauspost จริง (stdlib ต้องไม่มี)
# ใช้ grep -c (อ่านครบทั้ง stream ไม่ early-exit) กัน SIGPIPE ตอน pipefail
echo ""
echo "== verify klauspost linkage =="
kp_syms=$(go tool nm "$OUT/go-runner-klauspost" 2>/dev/null | grep -c 'klauspost/compress' || true)
std_syms=$(go tool nm "$OUT/go-runner-stdlib" 2>/dev/null | grep -c 'klauspost/compress' || true)
[ "${kp_syms:-0}" -gt 0 ] \
  && echo "  ✓ go-runner-klauspost  -> มี klauspost/compress ($kp_syms symbols)" \
  || echo "  ⚠ go-runner-klauspost  -> ไม่พบ symbol klauspost (ตรวจ build)"
[ "${std_syms:-0}" -eq 0 ] \
  && echo "  ✓ go-runner-stdlib     -> ไม่มี klauspost (ใช้ stdlib)" \
  || echo "  ⚠ go-runner-stdlib     -> ไม่ควรมี klauspost แต่เจอ $std_syms symbols"

# --- 3) Java runner --------------------------------------------------------
echo ""
echo "[3/3] build java-runner jar"
cd "$JAVA_DIR"
if [ -x "./mvnw" ]; then
  ./mvnw -q -DskipTests package
  echo "  ✓ $(ls -1 "$JAVA_DIR"/target/*-runner-*.jar 2>/dev/null | head -1)"
elif command -v mvn >/dev/null 2>&1; then
  mvn -q -DskipTests package
  echo "  ✓ $(ls -1 "$JAVA_DIR"/target/*-runner-*.jar 2>/dev/null | head -1)"
else
  echo "  ⚠ ไม่พบ ./mvnw และ mvn — ข้าม build Java (ถ้ามี jar อยู่แล้วจะใช้ตัวเดิม)"
fi

echo ""
echo "== เสร็จ =="
echo "  go-runner-klauspost, go-runner-stdlib อยู่ที่ $OUT"
echo "  รันเทียบด้วย:  python3 scripts/vm/run_klauspost_ab.py"
