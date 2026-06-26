"""Property-based test for checksum verification (Task 3.5)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.keys import file_checksum


def _write(path: Path, data: bytes) -> Path:
    """Write ``data`` to ``path`` and return the path (helper for clarity)."""
    path.write_bytes(data)
    return path


def verify(path: Path, expected_checksum: str) -> bool:
    """The harness verification rule: on-disk bytes must match the reference checksum."""
    return file_checksum(path) == expected_checksum


# Feature: pgp-encryption-benchmark-go-java, Property 4: Checksum verification เป็น round-trip และตรวจจับความไม่ตรงได้เสมอ
@settings(max_examples=200)
@given(content=st.binary(min_size=0, max_size=4096))
def test_checksum_roundtrip_always_verifies(tmp_path_factory, content: bytes):
    """verify(content, checksum(content)) is always true and deterministic."""
    d = tmp_path_factory.mktemp("rt")
    f = _write(d / "blob.bin", content)

    checksum = file_checksum(f)

    # Round-trip: the produced checksum always re-verifies the same bytes.
    assert verify(f, checksum) is True

    # Deterministic: recomputing yields the identical checksum string, and it
    # matches the independent reference implementation in the expected format.
    assert file_checksum(f) == checksum
    assert checksum == "sha256:" + hashlib.sha256(content).hexdigest()


# Feature: pgp-encryption-benchmark-go-java, Property 4: Checksum verification เป็น round-trip และตรวจจับความไม่ตรงได้เสมอ
@settings(max_examples=200)
@given(reference=st.binary(min_size=0, max_size=4096), data=st.data())
def test_checksum_detects_any_single_byte_difference(tmp_path_factory, reference: bytes, data):
    """Content differing by >= 1 byte from the reference must fail verification."""
    d = tmp_path_factory.mktemp("mm")

    ref_file = _write(d / "reference.bin", reference)
    reference_checksum = file_checksum(ref_file)

    # Build content guaranteed to differ from the reference by at least one byte.
    if reference:
        # Flip a single byte at an arbitrary position.
        idx = data.draw(st.integers(min_value=0, max_value=len(reference) - 1))
        mutated = bytearray(reference)
        mutated[idx] ^= data.draw(st.integers(min_value=1, max_value=255))
        modified = bytes(mutated)
    else:
        # Empty reference: any non-empty content differs by one byte.
        modified = data.draw(st.binary(min_size=1, max_size=4096))

    assert modified != reference

    mod_file = _write(d / "modified.bin", modified)

    # The mismatched input must be rejected so it never enters the statistics.
    assert verify(mod_file, reference_checksum) is False
    # And it correctly verifies against its own checksum (no false negatives).
    assert verify(mod_file, file_checksum(mod_file)) is True
