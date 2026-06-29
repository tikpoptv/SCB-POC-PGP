# Java PGP Runner

The Java side of the PGP benchmark. This module is the **shared CLI shell**
(task 11.1): a Spring Boot `CommandLineRunner` that speaks the language-neutral
Runner CLI contract in `contract/` exactly like the Go runner.

Spring Boot is used **only** as the application/runtime shell — there is no web,
data, actuator, or networking starter (out-of-scope guard, Req 1.2). Bouncy
Castle (`bcpg`/`bcprov`) is the OpenPGP provider; Jackson parses the Command JSON
and serialises the RunnerOutput JSON.

## Contract behaviour
- Reads **one** Command JSON object from **stdin**.
- Writes **one** RunnerOutput JSON object to **stdout** (and nothing else).
- All logs/diagnostics go to **stderr** (`logback.xml` targets `System.err`).
- Exit codes (`contract/exit-codes.json`): `0` success, `2` checksum/version
  mismatch, `3` config error, `4` unsupported crypto-profile, other `>0`
  operation failure.
- Verifies the Key_Set + Test_Corpus checksums (byte-for-byte parity with the Go
  runner and Python harness) before any crypto, and times **only** the crypto
  call with `System.nanoTime()` (Req 1.1, 4.6, 24.1).

## Scaffold layout
```
src/main/java/com/poc/pgp/
  JavaRunnerApplication.java     # Spring Boot entry point + bean wiring
  Checksum.java                  # Key_Set / Corpus aggregate checksums (Go/Python parity)
  KeySet.java                    # armored key loading via Bouncy Castle (untimed)
  Classifier.java                # file-type / output-naming rules (Req 32; 11.4 owns property tests)
  cli/
    CliRunner.java               # CommandLineRunner + ExitCodeGenerator
    RunnerShell.java             # runtime-neutral orchestration (mirrors Go runner.go)
    CommandParser.java           # Command JSON parse + validation -> exit 3
    Command-/ExitCodes/RunnerException
  contract/                      # Command, CryptoProfile, RunnerOutput, OperationSample, GcStats
  crypto/
    CryptoEngine.java            # design.md interface; variants plug in here
    Timing.java                  # record Timing(totalNanos, asymNanos, symNanos, hardwareAccel)
    EngineRegistry.java          # variantId -> engine (ServiceLoader-discovered)
    CryptoException / UnsupportedProfileException
```

Concrete variants come next: `java-stream-parallel` (task 11.2) and the
GraalVM native variant (11.3); น้อง's `java-inmem-single` / `java-stream-single`
are integrated onto `CryptoEngine` in task 12.2. A variant registers itself via
`META-INF/services/com.poc.pgp.crypto.CryptoEngine`.

## Build & Run
```
cd runners/java
./mvnw -q -DskipTests package
./mvnw test

echo '{"command":"run","variantId":"java-stream-parallel","mode":"steady_state","warmupIterations":1,"concurrency":4,"cryptoProfile":{"pubAlg":"RSA-2048","cipher":"AES-256","compression":"ZLIB","hash":"SHA-256"},"outputEncoding":"binary","keySetPath":"../../keys","keySetChecksum":"sha256:...","corpusPath":"../../corpus","corpusChecksum":"sha256:...","outputDir":"./out","operation":"roundtrip"}' \
  | java -jar target/java-runner-0.1.0.jar
```
(The example needs a registered variant; until task 11.2 lands, the shell exits 3
on an unknown `variantId`.)

## Building the GraalVM Native Image variant (`java-native-stream-parallel`)

The native variant is an optional extra that competes with `java-stream-parallel`
in Best_Variant selection (Req 22.1, 22.5). A dedicated helper script handles
everything including graceful skip when `native-image` is not on PATH:

```bash
cd runners/java
./build-native.sh        # builds JAR first, then native image
./build-native.sh --skip-jar  # skips JAR step (if already built)
```

**Exit codes:**
- `0` — native binary built at `target/java-native-runner` **OR** `native-image`
  not found (soft skip, Req 22.5): a `target/native-build-skipped.txt` marker
  file is written so the Harness knows to exclude this variant from selection.
- `1` — `native-image` was found but compilation failed: `target/native-build-failed.txt`
  marker written (Req 22.5): only this variant is excluded; the suite continues.

**GraalVM version (Req 22.3):** The script prints the detected GraalVM version
string to stdout. At runtime the native binary itself stamps `java.vm.version`
into every `RunnerOutput` JSON it emits (field `graalvmVersion`), so the Harness
can persist it in `results.json → versions.graalvm`.

**Prerequisites:**
```bash
# Install GraalVM JDK (e.g. via SDKMAN — use the same major as java.version in pom.xml)
sdk install java 21.0.x-graalce
gu install native-image     # install the native-image component
```

**Running the native binary directly:**
```bash
# Smoke-test the crypto path (no corpus needed):
./target/java-native-runner selftest ../../keys

# Full run with a Command JSON (same contract as the JVM runner):
echo '{"command":"run","variantId":"java-native-stream-parallel",...}' \
  | ./target/java-native-runner
```

**Metadata capture (when hints need refreshing):**
```bash
# Run under the GraalVM tracing agent to regenerate reachability-metadata.json:
./mvnw -q -DskipTests package
java -agentlib:native-image-agent=config-output-dir=src/main/resources/META-INF/native-image \
     -cp target/java-runner-0.1.0.jar \
     com.poc.pgp.AgentExercise
# Commit the updated files in META-INF/native-image/ before rebuilding.
```
