#!/usr/bin/env bash
set -euo pipefail

# สร้างกุญแจ PGP สำหรับใช้ใน POC:
#   - RSA-2048, RSA-4096 (บังคับ ตาม Req 31.1)
#   - Curve25519 ECC (เพื่อรองรับ key-type coverage ตาม Req 14.1)
# ใช้ GNUPGHOME ชั่วคราว เพื่อไม่ยุ่งกับ keyring ของเครื่อง
# กุญแจ "ไม่มี passphrase" (เพื่อความง่ายของ POC — ห้ามนำ key ชุดนี้ไปใช้งานจริง)
# กุญแจถูก export เป็น OpenPGP ASCII-armored ที่ทั้ง go-crypto และ Bouncy Castle อ่านได้
#
# สคริปต์นี้ idempotent: ถ้ามีไฟล์ public+private ของ spec ใดอยู่แล้ว จะข้ามการสร้างใหม่
# เพื่อไม่ให้ fingerprint ที่บันทึกไว้ใน KEYINFO.md เปลี่ยน เว้นแต่ตั้ง FORCE=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYS_DIR="$ROOT/keys"
TMP_HOME="$(mktemp -d)"
export GNUPGHOME="$TMP_HOME"
chmod 700 "$TMP_HOME"
FORCE="${FORCE:-0}"

mkdir -p "$KEYS_DIR"

# จะข้ามการสร้างถ้ามีไฟล์อยู่แล้ว (ยกเว้น FORCE=1)
should_skip() {
  local name="$1"
  if [[ "$FORCE" == "1" ]]; then
    return 1
  fi
  if [[ -f "$KEYS_DIR/${name}-public.asc" && -f "$KEYS_DIR/${name}-private.asc" ]]; then
    echo "skip ${name}: มีไฟล์อยู่แล้ว (ตั้ง FORCE=1 เพื่อสร้างใหม่)"
    return 0
  fi
  return 1
}

export_pair() {
  local name="$1"
  local email="$2"
  gpg --armor --export "$email" > "$KEYS_DIR/${name}-public.asc"
  gpg --armor --export-secret-keys "$email" > "$KEYS_DIR/${name}-private.asc"
  local fpr
  fpr="$(gpg --with-colons --fingerprint "$email" | awk -F: '/^fpr:/{print $10; exit}')"
  echo "${name} fingerprint: ${fpr}"
}

gen_rsa() {
  local bits="$1"
  local name="rsa${bits}"
  local email="poc-rsa${bits}@example.com"
  should_skip "$name" && return 0

  cat > "$TMP_HOME/keyparams-${name}" <<EOF
%no-protection
Key-Type: RSA
Key-Length: ${bits}
Subkey-Type: RSA
Subkey-Length: ${bits}
Name-Real: poc-rsa${bits}
Name-Email: ${email}
Expire-Date: 0
%commit
EOF

  gpg --batch --gen-key "$TMP_HOME/keyparams-${name}"
  export_pair "$name" "$email"
}

gen_ecc_cv25519() {
  local name="cv25519"
  local email="poc-cv25519@example.com"
  should_skip "$name" && return 0

  # primary = EdDSA (ed25519) สำหรับ sign/cert, subkey = ECDH (cv25519) สำหรับ encrypt
  cat > "$TMP_HOME/keyparams-${name}" <<EOF
%no-protection
Key-Type: EDDSA
Key-Curve: ed25519
Subkey-Type: ECDH
Subkey-Curve: cv25519
Name-Real: poc-cv25519
Name-Email: ${email}
Expire-Date: 0
%commit
EOF

  gpg --batch --gen-key "$TMP_HOME/keyparams-${name}"
  export_pair "$name" "$email"
}

gen_rsa 2048
gen_rsa 4096
gen_ecc_cv25519

# ลบโฮมชั่วคราวทิ้ง
rm -rf "$TMP_HOME"
echo "DONE. keys written to $KEYS_DIR"
ls -la "$KEYS_DIR"
