# Benchmark Harness

Neutral Python orchestrator (`Benchmark_Harness`) for the Go vs Java PGP
encrypt/decrypt benchmark POC. The harness performs **no crypto itself** — it
spawns the Go and Java Runners as subprocesses, samples CPU/RAM, runs the
verification gate, computes statistics, and generates reports.

- Python: 3.12+
- Dependencies: `numpy`, `scipy`, `psutil` (runtime); `hypothesis`, `pytest` (test)

## Scope guard (Req 1.2, 1.3, 1.5)
No database, no REST/HTTP API, no network clients. The harness reads local
input files and writes local output files only, and compares exactly two
languages: Go and Java.

## Layout
```
harness/
  pyproject.toml
  requirements.txt
  src/harness/        # package source
  tests/              # unit + property-based tests (hypothesis)
```

## Setup
```bash
cd harness
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
pytest
```
