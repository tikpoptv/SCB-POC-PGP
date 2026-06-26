"""Unit tests for the InteroperabilityChecker (task 7.2)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness.interop import (
    GO,
    GPG,
    JAVA,
    GoRunnerInterop,
    GpgInterop,
    InteropCheck,
    InteropEndpoint,
    InteropOutcome,
    InteropPair,
    InteropSummary,
    InteroperabilityChecker,
    default_interop_pairs,
    pending_endpoint,
)


# Fixtures / helpers
def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "keys").is_dir() and (parent / "runners" / "go").is_dir():
            return parent
    raise RuntimeError("could not locate repo root")


@pytest.fixture
def keys_dir() -> Path:
    return _repo_root() / "keys"


@pytest.fixture
def go_binary() -> Path:
    return _repo_root() / "runners" / "go" / "go-runner"


_HAS_GPG = shutil.which("gpg") is not None
_needs_gpg = pytest.mark.skipif(not _HAS_GPG, reason="gpg executable not available")


def _go_available() -> bool:
    return (_repo_root() / "runners" / "go" / "go-runner").exists()


_needs_go = pytest.mark.skipif(not _go_available(), reason="go-runner binary not built")


@pytest.fixture
def plaintext(tmp_path: Path) -> Path:
    p = tmp_path / "message.bin"
    p.write_bytes(b"interoperability matters \x00\x01\x02 " * 200)
    return p


# fake endpoints
def _copy_endpoint(name: str) -> InteropEndpoint:
    """An endpoint that 'encrypts' and 'decrypts' by copying bytes verbatim.

    A copy producer + copy consumer always round-trips, so any pair of copy
    endpoints passes — useful to verify the happy path without crypto.
    """

    def enc(src: Path, dst: Path) -> None:
        shutil.copyfile(src, dst)

    def dec(src: Path, dst: Path) -> None:
        shutil.copyfile(src, dst)

    return InteropEndpoint(name=name, encrypt=enc, decrypt=dec)


def _tamper_consumer(name: str) -> InteropEndpoint:
    """A consumer whose decrypt output differs from the input (forces a fail)."""

    def dec(src: Path, dst: Path) -> None:
        dst.write_bytes(b"WRONG")

    return InteropEndpoint(name=name, encrypt=lambda s, d: shutil.copyfile(s, d), decrypt=dec)


def _broken_consumer(name: str) -> InteropEndpoint:
    """A consumer whose decrypt raises (e.g. cannot parse the ciphertext)."""

    def dec(src: Path, dst: Path) -> None:
        raise RuntimeError("cannot parse OpenPGP packet")

    return InteropEndpoint(name=name, encrypt=lambda s, d: shutil.copyfile(s, d), decrypt=dec)


def _broken_producer(name: str) -> InteropEndpoint:
    def enc(src: Path, dst: Path) -> None:
        raise RuntimeError("encrypt blew up")

    return InteropEndpoint(name=name, encrypt=enc, decrypt=lambda s, d: shutil.copyfile(s, d))


# Value objects & default pairs
def test_default_pairs_cover_req_25():
    pairs = default_interop_pairs()
    assert InteropPair(GO, JAVA) in pairs
    assert InteropPair(JAVA, GO) in pairs
    assert InteropPair(GO, GPG) in pairs
    assert InteropPair(JAVA, GPG) in pairs
    # gpg is a consumer only in the standard set (no gpg producer pair).
    assert not any(p.producer == GPG for p in pairs)


def test_interop_pair_rejects_self_pair():
    with pytest.raises(ValueError):
        InteropPair(GO, GO)


def test_interop_check_to_dict_shapes():
    ok = InteropCheck(GO, GPG, InteropOutcome.PASS)
    assert ok.to_dict() == {"producer": "go", "consumer": "gpg", "result": "pass"}
    bad = InteropCheck(GO, JAVA, InteropOutcome.FAIL, "boom")
    assert bad.to_dict() == {
        "producer": "go",
        "consumer": "java",
        "result": "fail",
        "reason": "boom",
    }
    assert bad.direction == "go -> java"


# Framework: pass / fail / pending (fakes only)
def test_matching_endpoints_pass(plaintext: Path):
    checker = InteroperabilityChecker(
        {GO: _copy_endpoint(GO), JAVA: _copy_endpoint(JAVA)},
        pairs=[InteropPair(GO, JAVA)],
    )
    result = checker.check_pair(plaintext, InteropPair(GO, JAVA))
    assert result.result is InteropOutcome.PASS
    assert result.reason is None


def test_mismatched_output_fails_with_reason(plaintext: Path):
    checker = InteroperabilityChecker(
        {GO: _copy_endpoint(GO), JAVA: _tamper_consumer(JAVA)},
    )
    result = checker.check_pair(plaintext, InteropPair(GO, JAVA))
    assert result.result is InteropOutcome.FAIL
    assert "differs from original" in (result.reason or "")


def test_consumer_exception_is_a_fail(plaintext: Path):
    checker = InteroperabilityChecker(
        {GO: _copy_endpoint(GO), JAVA: _broken_consumer(JAVA)},
    )
    result = checker.check_pair(plaintext, InteropPair(GO, JAVA))
    assert result.result is InteropOutcome.FAIL
    assert "failed to decrypt" in (result.reason or "")
    assert "cannot parse" in (result.reason or "")


def test_producer_exception_is_a_fail(plaintext: Path):
    checker = InteroperabilityChecker(
        {GO: _broken_producer(GO), JAVA: _copy_endpoint(JAVA)},
    )
    result = checker.check_pair(plaintext, InteropPair(GO, JAVA))
    assert result.result is InteropOutcome.FAIL
    assert "failed to encrypt" in (result.reason or "")


def test_unavailable_consumer_is_pending(plaintext: Path):
    checker = InteroperabilityChecker(
        {GO: _copy_endpoint(GO), JAVA: pending_endpoint(JAVA, "Java runner lands in Task 11-12")},
    )
    result = checker.check_pair(plaintext, InteropPair(GO, JAVA))
    assert result.result is InteropOutcome.PENDING
    assert "Task 11-12" in (result.reason or "")


def test_missing_endpoint_is_pending(plaintext: Path):
    checker = InteroperabilityChecker({GO: _copy_endpoint(GO)}, pairs=[InteropPair(GO, JAVA)])
    result = checker.check_pair(plaintext, InteropPair(GO, JAVA))
    assert result.result is InteropOutcome.PENDING
    assert "not registered" in (result.reason or "")


def test_consumer_without_decrypt_is_pending(plaintext: Path):
    producer_only = InteropEndpoint(name=JAVA, encrypt=lambda s, d: shutil.copyfile(s, d))
    checker = InteroperabilityChecker({GO: _copy_endpoint(GO), JAVA: producer_only})
    result = checker.check_pair(plaintext, InteropPair(GO, JAVA))
    assert result.result is InteropOutcome.PENDING
    assert "cannot decrypt" in (result.reason or "")


def test_summary_comparable_when_no_failures():
    summary = InteropSummary(
        (
            InteropCheck(GO, GPG, InteropOutcome.PASS),
            InteropCheck(GO, JAVA, InteropOutcome.PENDING, "pending"),
        )
    )
    assert summary.comparable is True
    assert summary.non_comparable_reasons() == ()


def test_summary_non_comparable_lists_failing_pairs():
    summary = InteropSummary(
        (
            InteropCheck(GO, GPG, InteropOutcome.PASS),
            InteropCheck(JAVA, GO, InteropOutcome.FAIL, "byte mismatch"),
        )
    )
    assert summary.comparable is False
    reasons = summary.non_comparable_reasons()
    assert len(reasons) == 1
    assert "java -> go" in reasons[0]
    assert "byte mismatch" in reasons[0]


def test_summary_to_dict_matches_design_shape():
    summary = InteropSummary(
        (
            InteropCheck(GO, JAVA, InteropOutcome.PASS),
            InteropCheck(JAVA, GO, InteropOutcome.PASS),
            InteropCheck(GO, GPG, InteropOutcome.PASS),
        )
    )
    payload = summary.to_dict()
    assert payload["comparable"] is True
    assert payload["interopChecks"] == [
        {"producer": "go", "consumer": "java", "result": "pass"},
        {"producer": "java", "consumer": "go", "result": "pass"},
        {"producer": "go", "consumer": "gpg", "result": "pass"},
    ]


def test_check_runs_every_configured_pair(plaintext: Path):
    checker = InteroperabilityChecker(
        {
            GO: _copy_endpoint(GO),
            JAVA: pending_endpoint(JAVA, "pending Task 11-12"),
        }
    )
    summary = checker.check(plaintext)
    # go<->java pairs pending (java not available); go->gpg pair not configured
    # because gpg endpoint was not supplied -> filtered out of the default set.
    directions = {(c.producer, c.consumer): c.result for c in summary.checks}
    assert directions[(GO, JAVA)] is InteropOutcome.PENDING
    assert directions[(JAVA, GO)] is InteropOutcome.PENDING
    assert summary.comparable is True  # nothing failed


@_needs_go
@_needs_gpg
def test_real_go_to_gpg_passes(plaintext: Path, go_binary: Path, keys_dir: Path):
    # Go encrypts, the standard gpg tool decrypts -> proves Go emits standard
    go = GoRunnerInterop(go_binary, keys_dir, pub_alg="RSA-2048")
    with GpgInterop(keys_dir, pub_alg="RSA-2048") as gpg:
        checker = InteroperabilityChecker(
            {GO: go.as_endpoint(), GPG: gpg.as_endpoint()},
            pairs=[InteropPair(GO, GPG)],
        )
        result = checker.check_pair(plaintext, InteropPair(GO, GPG))
    assert result.result is InteropOutcome.PASS, result.reason


@_needs_go
@_needs_gpg
def test_real_gpg_to_go_passes(plaintext: Path, go_binary: Path, keys_dir: Path):
    # gpg encrypts, Go decrypts -> proves Go reads standard OpenPGP.
    go = GoRunnerInterop(go_binary, keys_dir, pub_alg="RSA-2048")
    with GpgInterop(keys_dir, pub_alg="RSA-2048") as gpg:
        checker = InteroperabilityChecker(
            {GO: go.as_endpoint(), GPG: gpg.as_endpoint(decrypt_only=False)},
            pairs=[InteropPair(GPG, GO)],
        )
        result = checker.check_pair(plaintext, InteropPair(GPG, GO))
    assert result.result is InteropOutcome.PASS, result.reason


@_needs_go
@_needs_gpg
def test_real_go_self_round_trip_passes(plaintext: Path, go_binary: Path, keys_dir: Path):
    # Go encrypt -> Go decrypt through the real CLI (sanity for the backend).
    go = GoRunnerInterop(go_binary, keys_dir, pub_alg="RSA-2048")
    ct = plaintext.parent / "ct.bin"
    rec = plaintext.parent / "rec.bin"
    go.encrypt(plaintext, ct)
    assert ct.exists() and ct.stat().st_size > 0
    go.decrypt(ct, rec)
    assert rec.read_bytes() == plaintext.read_bytes()


@_needs_go
@_needs_gpg
def test_real_standard_set_go_active_java_pending(plaintext: Path, go_binary: Path, keys_dir: Path):
    # The realistic state for task 7.2: Go + gpg are real, Java is pending.
    go = GoRunnerInterop(go_binary, keys_dir, pub_alg="RSA-2048")
    with GpgInterop(keys_dir, pub_alg="RSA-2048") as gpg:
        checker = InteroperabilityChecker(
            {
                GO: go.as_endpoint(),
                GPG: gpg.as_endpoint(),
                JAVA: pending_endpoint(JAVA, "Java_Runner arrives in Task 11-12"),
            }
        )
        summary = checker.check(plaintext)

    by_dir = {(c.producer, c.consumer): c for c in summary.checks}
    assert by_dir[(GO, GPG)].result is InteropOutcome.PASS, by_dir[(GO, GPG)].reason
    assert by_dir[(GO, JAVA)].result is InteropOutcome.PENDING
    assert by_dir[(JAVA, GO)].result is InteropOutcome.PENDING
    assert by_dir[(JAVA, GPG)].result is InteropOutcome.PENDING
    # No failures -> still comparable; the report carries the pending pairs.
    assert summary.comparable is True
    assert any(c["result"] == "pass" for c in summary.interop_checks())


@_needs_go
@_needs_gpg
def test_real_tampered_go_ciphertext_fails_gpg(plaintext: Path, go_binary: Path, keys_dir: Path):
    # proving the gate actually detects broken interop rather than rubber-stamping.
    go = GoRunnerInterop(go_binary, keys_dir, pub_alg="RSA-2048")

    def corrupting_encrypt(src: Path, dst: Path) -> None:
        go.encrypt(src, dst)
        data = bytearray(dst.read_bytes())
        # Flip bytes in the middle of the packet stream to corrupt it.
        for i in range(len(data) // 4, len(data) // 4 + 8):
            data[i] ^= 0xFF
        dst.write_bytes(bytes(data))

    with GpgInterop(keys_dir, pub_alg="RSA-2048") as gpg:
        checker = InteroperabilityChecker(
            {
                GO: InteropEndpoint(name=GO, encrypt=corrupting_encrypt, decrypt=go.decrypt),
                GPG: gpg.as_endpoint(),
            },
            pairs=[InteropPair(GO, GPG)],
        )
        result = checker.check_pair(plaintext, InteropPair(GO, GPG))
    assert result.result is InteropOutcome.FAIL
    assert result.reason


@_needs_gpg
def test_gpg_unavailable_error_message(tmp_path: Path, keys_dir: Path):
    from harness.interop import GpgUnavailableError

    with pytest.raises(GpgUnavailableError):
        GpgInterop(keys_dir, pub_alg="RSA-2048", gpg_path="definitely-not-gpg-xyz")
