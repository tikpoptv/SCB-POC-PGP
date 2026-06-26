#!/usr/bin/env bash
set -euo pipefail

# สร้างกุญแจ PGP (RSA-2048 และ RSA-4096) สำหรับใช้ใน POC
# ใช้ GNUPGHOME ชั่วคราว เพื่อไม่ยุ่งกับ keyring ของเครื่อง
# กุญแจ "ไม่มี passphrase" (เพื่อความง่ายของ POC — ห้ามนำ key ชุดนี้ไปใช้งานจริง)

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYS_DIR="$ROOT/keys"
TMP_HOME="$(mktemp -d)"
export GNUPGHOME="$TMP_HOME"
chmod 700 "$TMP_HOME"

mkdir -p "$KEYS_DIR"

gen_and_export() {
  local bits="$1"
  local uid="poc-rsa${bits} <poc-rsa${bits}@example.com>"

  cat > "$TMP_HOME/keyparams-${bits}" <<EOF
%no-protection
Key-Type: RSA
Key-Length: ${bits}
Subkey-Type: RSA
Subkey-Length: ${bits}
Name-Real: poc-rsa${bits}
Name-Email: poc-rsa${bits}@example.com
Expire-Date: 0
%commit
EOF

  gpg --batch --gen-key "$TMP_HOME/keyparams-${bits}"

  gpg --armor --export "poc-rsa${bits}@example.com" > "$KEYS_DIR/rsa${bits}-public.asc"
  gpg --armor --export-secret-keys "poc-rsa${bits}@example.com" > "$KEYS_DIR/rsa${bits}-private.asc"

  local fpr
  fpr="$(gpg --with-colons --fingerprint "poc-rsa${bits}@example.com" | awk -F: '/^fpr:/{print $10; exit}')"
  echo "rsa${bits} fingerprint: ${fpr}"
}

gen_and_export 2048
gen_and_export 4096

# ลบโฮมชั่วคราวทิ้ง
rm -rf "$TMP_HOME"
echo "DONE. keys written to $KEYS_DIR"
ls -la "$KEYS_DIR"
