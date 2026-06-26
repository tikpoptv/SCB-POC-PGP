# Shared Runner CLI Contract

This directory is the **single source of truth** for the interface between the
`Benchmark_Harness` (Python) and the two Runners (`Go_Runner`, `Java_Runner`).
It is intentionally language-neutral so all three codebases reference the same
artifacts and the harness can treat both Runners identically (the core
anti-bias property — see design.md, "Runner CLI Contract").

## Invocation model

The harness spawns a Runner process and:

1. Writes **one** `Command` JSON object to the Runner's **stdin**.
2. Reads **one** `RunnerOutput` JSON object from the Runner's **stdout**.
3. Treats everything on **stderr** as logs/diagnostics only.
4. Interprets the process **exit code** per `exit-codes.json`.

## Artifacts

| File | Purpose |
|---|---|
| `command.schema.json` | JSON Schema (draft 2020-12) for the Command JSON sent on stdin. |
| `runner-output.schema.json` | JSON Schema (draft 2020-12) for the RunnerOutput JSON written to stdout. |
| `exit-codes.json` | Canonical Runner process exit codes. |

## Exit codes

| Code | Name | Meaning |
|---|---|---|
| `0` | `SUCCESS` | Success (recorded per-file correctness failures still exit 0). |
| `2` | `CHECKSUM_OR_VERSION_MISMATCH` | Input checksum or version mismatch — results excluded from statistics (Req 4.6, 2.5). |
| `3` | `CONFIG_ERROR` | Invalid config/command JSON (Req 19.6). |
| `4` | `UNSUPPORTED_CRYPTO_PROFILE` | Crypto-profile not supported by this Runner (Req 4.4, 18.5). |
| `>0` (other) | `OPERATION_FAILURE` | Any other non-zero code is a generic operation failure (Req 5.3). |

## `outputEncoding`

Both the `Command` and `RunnerOutput` carry `outputEncoding ∈ {binary, armored}`.
All Runners within a Scenario must use the **same** encoding so ciphertext
sizes and interoperability are comparable and fair (Req 4.7).

## Consumers

- **Python harness** — `harness/src/harness/contract/` provides typed
  dataclasses, parsers, exit-code constants, and schema validation that load
  these files directly (no duplicated definitions).
- **Go_Runner** — `runners/go` mirrors the exit codes in `main.go` and
  (re)serializes the same JSON shapes.
- **Java_Runner** — `runners/java` mirrors the exit codes and JSON shapes.

When the contract changes, update the schema/exit-code files here first, then
update the language mirrors. The Python tests assert the mirrored constants
match `exit-codes.json`.
