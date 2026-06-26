"""Unit tests for the Key Generator (``harness.keys``), task 3.4."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

import pytest

from harness.keys import (
    REQUIRED_KEY_SPECS,
    KeyGenerationError,
    KeyGenError,
    KeySpec,
    build_manifest,
    file_checksum,
    read_key_info,
    verify_key_spec,
)

_CHECKSUM_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")

# gpg is required to inspect armored key files; skip the gpg-backed tests when
# it is unavailable rather than failing the whole suite.
_HAS_GPG = shutil.which("gpg") is not None
_needs_gpg = pytest.mark.skipif(not _HAS_GPG, reason="gpg executable not available")


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "keys").is_dir() and (parent / "scripts" / "gen-keys.sh").is_file():
            return parent
    raise RuntimeError("could not locate repo root with keys/ and scripts/")


@pytest.fixture
def keys_dir() -> Path:
    return _repo_root() / "keys"


def test_file_checksum_matches_hashlib(tmp_path: Path):
    f = tmp_path / "blob.bin"
    data = b"the quick brown fox" * 100
    f.write_bytes(data)
    expected = "sha256:" + hashlib.sha256(data).hexdigest()
    assert file_checksum(f) == expected


def test_file_checksum_format_and_sensitivity(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.write_bytes(b"alpha")
    b.write_bytes(b"alphb")  # one byte different
    ca, cb = file_checksum(a), file_checksum(b)
    assert _CHECKSUM_RE.match(ca)
    assert _CHECKSUM_RE.match(cb)
    assert ca != cb


@_needs_gpg
def test_read_key_info_rsa(keys_dir: Path):
    info = read_key_info(keys_dir / "rsa2048-public.asc")
    assert info.algo == 1  # RSA
    assert info.key_length == 2048
    assert re.fullmatch(r"[0-9A-F]{40}", info.fingerprint)


@_needs_gpg
def test_read_key_info_ecc(keys_dir: Path):
    info = read_key_info(keys_dir / "cv25519-public.asc")
    assert info.algo == 22  # EdDSA primary
    assert info.curve == "ed25519"
    assert re.fullmatch(r"[0-9A-F]{40}", info.fingerprint)


@_needs_gpg
@pytest.mark.parametrize("spec", REQUIRED_KEY_SPECS, ids=lambda s: s.label)
def test_verify_each_required_spec(spec: KeySpec, keys_dir: Path):
    entry = verify_key_spec(spec, keys_dir)
    assert entry.id == spec.id
    assert entry.type == spec.key_type
    assert _CHECKSUM_RE.match(entry.public_checksum)
    assert _CHECKSUM_RE.match(entry.private_checksum)
    assert entry.checksum == entry.public_checksum
    assert re.fullmatch(r"[0-9A-F]{40}", entry.fingerprint)
    if spec.key_type == "RSA":
        assert entry.bits == spec.bits
    else:
        assert entry.curve == "Curve25519"


@_needs_gpg
def test_verify_rejects_wrong_bit_size(keys_dir: Path):
    # Point a 4096-bit spec at the 2048-bit key files: must be rejected.
    wrong = KeySpec(id="rsa2048", label="RSA-4096-mismatch", key_type="RSA", primary_algo=1, bits=4096)
    with pytest.raises(KeyGenError, match="RSA key length"):
        verify_key_spec(wrong, keys_dir)


def test_verify_missing_files_reports_them(tmp_path: Path):
    spec = REQUIRED_KEY_SPECS[0]
    with pytest.raises(KeyGenError, match="missing key file"):
        verify_key_spec(spec, tmp_path)


@_needs_gpg
def test_build_manifest_full_keyset(keys_dir: Path):
    manifest = build_manifest(keys_dir)
    assert len(manifest.entries) == len(REQUIRED_KEY_SPECS)
    assert _CHECKSUM_RE.match(manifest.key_set_checksum)

    types = {(e.type, e.bits, e.curve) for e in manifest.entries}
    assert ("RSA", 2048, None) in types
    assert ("RSA", 4096, None) in types  # both RSA sizes mandatory
    assert any(e.type == "ECC" for e in manifest.entries)  # elliptic curve

    fps = [e.fingerprint for e in manifest.entries]
    assert len(set(fps)) == len(fps)

    d = manifest.to_dict()
    assert d["keySetChecksum"] == manifest.key_set_checksum
    assert len(d["keySet"]) == len(REQUIRED_KEY_SPECS)


@_needs_gpg
def test_build_manifest_is_deterministic(keys_dir: Path):
    m1 = build_manifest(keys_dir)
    m2 = build_manifest(keys_dir)
    assert m1.key_set_checksum == m2.key_set_checksum


@_needs_gpg
def test_build_manifest_halts_naming_failed_specs(tmp_path: Path, keys_dir: Path):
    # Provide only the RSA-2048 pair; RSA-4096 and ECC are absent.
    for name in ("rsa2048-public.asc", "rsa2048-private.asc"):
        shutil.copy(keys_dir / name, tmp_path / name)

    with pytest.raises(KeyGenerationError) as excinfo:
        build_manifest(tmp_path)

    err = excinfo.value
    assert set(err.failures) == {"RSA-4096", "ECC-Curve25519"}
    assert "RSA-4096" in str(err)
    assert "ECC-Curve25519" in str(err)


def test_build_manifest_empty_dir_fails_all_specs(tmp_path: Path):
    if not _HAS_GPG:
        # Without gpg the missing-file check still fires before any gpg call.
        pass
    with pytest.raises(KeyGenerationError) as excinfo:
        build_manifest(tmp_path)
    assert set(excinfo.value.failures) == {s.label for s in REQUIRED_KEY_SPECS}
