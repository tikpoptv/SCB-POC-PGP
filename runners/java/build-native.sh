#!/usr/bin/env bash
# build-native.sh — Build the java-native-stream-parallel GraalVM Native Image
# variant (task 11.3, Req 22.1, 22.3, 22.5).
#
# USAGE:
#   ./build-native.sh [--skip-jar]
#
# EXIT CODES:
#   0  — native binary built successfully at target/java-native-runner
#   0  — native-image not found; variant SKIPPED (non-fatal, Req 22.5)
#   1  — native build attempted but failed (log written, variant excluded)
#
# Req 22.3: prints GraalVM version to stdout so the harness can persist it in
#           results.json → versions.graalvm.
# Req 22.5: if native-image is absent, writes a skip marker file and exits 0
#           so the benchmark suite continues without this variant.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${SCRIPT_DIR}/target"
SKIP_MARKER="${TARGET_DIR}/native-build-skipped.txt"
FAIL_MARKER="${TARGET_DIR}/native-build-failed.txt"
BINARY="${TARGET_DIR}/java-native-runner"

# ----- 1. Check for native-image ------------------------------------------ #
if ! command -v native-image >/dev/null 2>&1; then
    echo "[build-native] SKIP: 'native-image' not found on PATH." >&2
    echo "  To build the native variant, install GraalVM for JDK 21 (or later)" >&2
    echo "  and ensure 'native-image' is on your PATH, or use SDKMAN:" >&2
    echo "    sdk install java 21.0.x-graalce  &&  gu install native-image" >&2
    mkdir -p "${TARGET_DIR}"
    {
        echo "SKIPPED: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "REASON: native-image binary not found on PATH"
        echo "VARIANT: java-native-stream-parallel"
    } > "${SKIP_MARKER}"
    echo "[build-native] Skip marker written to ${SKIP_MARKER}" >&2
    # Exit 0: Req 22.5 — native build failure / absence skips THIS variant only.
    exit 0
fi

# ----- 2. Print GraalVM version (Req 22.3) --------------------------------- #
GRAALVM_VERSION="$(native-image --version 2>&1 | head -1 || true)"
echo "[build-native] GraalVM version: ${GRAALVM_VERSION}"

# ----- 3. Build the fat JAR first (unless --skip-jar passed) --------------- #
if [[ "${1-}" != "--skip-jar" ]]; then
    echo "[build-native] Building JAR with: ./mvnw -q -DskipTests package" >&2
    "${SCRIPT_DIR}/mvnw" -q -DskipTests package -f "${SCRIPT_DIR}/pom.xml"
fi

# ----- 4. Run the Maven native profile ------------------------------------- #
echo "[build-native] Compiling native image (this may take several minutes)…" >&2
rm -f "${SKIP_MARKER}" "${FAIL_MARKER}"

set +e
"${SCRIPT_DIR}/mvnw" -q -Pnative -DskipTests package \
    -f "${SCRIPT_DIR}/pom.xml" 2>&1
BUILD_EXIT=$?
set -e

if [[ ${BUILD_EXIT} -ne 0 ]]; then
    echo "[build-native] FAILED: native-image compilation exited ${BUILD_EXIT}." >&2
    mkdir -p "${TARGET_DIR}"
    {
        echo "FAILED: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "EXIT_CODE: ${BUILD_EXIT}"
        echo "GRAALVM_VERSION: ${GRAALVM_VERSION}"
        echo "VARIANT: java-native-stream-parallel"
        echo "NOTE: This variant is excluded from Best_Variant selection (Req 22.5)."
        echo "      The benchmark suite continues with remaining variants."
    } > "${FAIL_MARKER}"
    echo "[build-native] Failure details written to ${FAIL_MARKER}" >&2
    # Exit 1: harness reads this to mark the variant non-comparable (Req 22.5).
    exit 1
fi

# ----- 5. Verify the binary exists ---------------------------------------- #
if [[ ! -f "${BINARY}" ]]; then
    echo "[build-native] FAILED: expected binary not found at ${BINARY}" >&2
    {
        echo "FAILED: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "REASON: binary not found at ${BINARY} after build"
        echo "GRAALVM_VERSION: ${GRAALVM_VERSION}"
        echo "VARIANT: java-native-stream-parallel"
    } > "${FAIL_MARKER}"
    exit 1
fi

echo "[build-native] SUCCESS: ${BINARY}"
echo "[build-native] GraalVM version: ${GRAALVM_VERSION}"
