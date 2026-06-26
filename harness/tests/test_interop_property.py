"""Property-based test for Property 2: Cross-language / standard-tool interoperability."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness.interop import (
    GO,
    GPG,
    JAVA,
    GoRunnerInterop,
    GpgInterop,
    InteropOutcome,
    InteropPair,
    InteroperabilityChecker,
    pending_endpoint,
)

# Relaxed iteration cap for the real-subprocess interop gate (see module docstring).
REAL_INTEROP_MAX_EXAMPLES = 30

# Largest generated payload. Kept modest so real crypto per example stays cheap
# while still covering small/medium binary inputs across the chosen examples.
MAX_PAYLOAD_BYTES = 4096


# Repo layout helpers
def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "keys").is_dir() and (parent / "runners" / "go").is_dir():
            return parent
    raise RuntimeError("could not locate repo root")


@pytest.fixture(scope="module")
def keys_dir() -> Path:
    return _repo_root() / "keys"


@pytest.fixture(scope="module")
def go_binary() -> Path:
    """The real Go_Runner binary, built on demand if it is not present yet."""
    root = _repo_root()
    go_dir = root / "runners" / "go"
    binary = go_dir / "go-runner"
    if not binary.exists():
        go = shutil.which("go")
        if go is None:
            pytest.skip("go-runner binary not built and the 'go' toolchain is unavailable")
        proc = subprocess.run(
            [go, "build", "-o", "go-runner", "."],
            cwd=go_dir,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not binary.exists():
            pytest.skip(f"failed to build go-runner: {proc.stderr.strip()}")
    return binary


@pytest.fixture(scope="module")
def interop_checker(go_binary: Path, keys_dir: Path):
    """An :class:`InteroperabilityChecker` wired to the *real* Go_Runner and gpg.

    Built once for the whole module (key import / GNUPGHOME setup is expensive)
    and reused across every generated example. ``gpg`` is exposed as both a
    producer and consumer so the ``gpg -> go`` direction can be checked; the
    Java endpoint is registered *pending* (Task 11-12).
    """
    if shutil.which("gpg") is None:
        pytest.skip("gpg executable not available (Req 25.3 interop check requires it)")

    go = GoRunnerInterop(go_binary, keys_dir, pub_alg="RSA-2048")
    gpg = GpgInterop(keys_dir, pub_alg="RSA-2048")
    gpg.__enter__()
    try:
        checker = InteroperabilityChecker(
            {
                GO: go.as_endpoint(),
                # decrypt_only=False so gpg is also a producer (gpg -> go pair).
                GPG: gpg.as_endpoint(decrypt_only=False),
                JAVA: pending_endpoint(JAVA, "Java_Runner arrives in Task 11-12"),
            },
            pairs=[
                InteropPair(GO, GPG),   # active now
                InteropPair(GPG, GO),   # active now
                InteropPair(GO, JAVA),  # pending until Task 11-12
                InteropPair(JAVA, GO),  # pending until Task 11-12
                InteropPair(JAVA, GPG), # pending (java side)
            ],
        )
        yield checker
    finally:
        gpg.close()


# Feature: pgp-encryption-benchmark-go-java, Property 2: Cross-language / standard-tool interoperability
@settings(
    max_examples=REAL_INTEROP_MAX_EXAMPLES,
    deadline=None,  # real subprocess crypto timing is not what we assert
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ],
)
@given(payload=st.binary(min_size=0, max_size=MAX_PAYLOAD_BYTES))
def test_property2_real_interop_go_gpg_round_trip(payload: bytes, interop_checker):
    with tempfile.TemporaryDirectory(prefix="prop2-interop-") as d:
        plaintext = Path(d) / "payload.bin"
        plaintext.write_bytes(payload)
        summary = interop_checker.check(plaintext)

    by_dir = {(c.producer, c.consumer): c for c in summary.checks}

    # active now: real Go <-> real gpg must round-trip byte-for-byte
    go_gpg = by_dir[(GO, GPG)]
    assert go_gpg.result is InteropOutcome.PASS, (
        f"go -> gpg interop failed for {len(payload)}-byte payload: {go_gpg.reason}"
    )
    gpg_go = by_dir[(GPG, GO)]
    assert gpg_go.result is InteropOutcome.PASS, (
        f"gpg -> go interop failed for {len(payload)}-byte payload: {gpg_go.reason}"
    )

    assert by_dir[(GO, JAVA)].result is InteropOutcome.PENDING
    assert by_dir[(JAVA, GO)].result is InteropOutcome.PENDING
    assert by_dir[(JAVA, GPG)].result is InteropOutcome.PENDING

    assert summary.comparable is True, summary.non_comparable_reasons()
