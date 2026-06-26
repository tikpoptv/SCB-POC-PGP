"""Key Generator: owns the shared Key_Set manifest (fingerprints, specs, checksums)."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "KeyGenError",
    "GpgUnavailableError",
    "KeyGenerationError",
    "KeyType",
    "KeySpec",
    "KeyInfo",
    "KeyManifestEntry",
    "KeySetManifest",
    "REQUIRED_KEY_SPECS",
    "RSA_ALGO",
    "EDDSA_ALGO",
    "ECDH_ALGO",
    "file_checksum",
    "read_key_info",
    "verify_key_spec",
    "build_manifest",
    "generate_key_set",
    "ensure_key_set",
]

# OpenPGP public-key algorithm numbers (RFC 4880 / gpg --with-colons field 4).
RSA_ALGO = 1
EDDSA_ALGO = 22  # ed25519 primary (sign/cert)
ECDH_ALGO = 18  # cv25519 encryption subkey


class KeyGenError(Exception):
    """Base class for Key Generator failures."""


class GpgUnavailableError(KeyGenError):
    """Raised when the ``gpg`` executable needed to inspect keys is missing."""


class KeyGenerationError(KeyGenError):
    """Raised when one or more required key specs are missing or invalid.

    The message names every failed key spec; the structured ``failures``
    mapping (spec label -> reason) is available for programmatic handling.
    """

    def __init__(self, failures: Mapping[str, str]) -> None:
        self.failures: dict[str, str] = dict(failures)
        detail = "; ".join(f"{label}: {reason}" for label, reason in self.failures.items())
        super().__init__(
            "key generation/verification failed before Benchmark_Run for "
            f"{len(self.failures)} key spec(s): {detail}"
        )


class KeyType(str):
    """Marker string type for a key family ('RSA' or 'ECC')."""


@dataclass(frozen=True)
class KeySpec:
    """A required key in the shared Key_Set.

    ``primary_algo`` is the expected OpenPGP algorithm number of the primary
    key; ``curve`` (ECC only) is the expected curve name. :func:`verify_key_spec`
    checks the on-disk key against these so a placeholder key cannot pass.
    """

    id: str
    label: str
    key_type: str  # "RSA" | "ECC"
    primary_algo: int
    bits: int | None = None  # RSA modulus size; None for ECC
    curve: str | None = None  # e.g. "Curve25519"; None for RSA
    primary_curve_token: str | None = None  # gpg curve token, e.g. "ed25519"

    @property
    def public_filename(self) -> str:
        return f"{self.id}-public.asc"

    @property
    def private_filename(self) -> str:
        return f"{self.id}-private.asc"


#: The Key_Set the harness must have before any Benchmark_Run.
REQUIRED_KEY_SPECS: tuple[KeySpec, ...] = (
    KeySpec(id="rsa2048", label="RSA-2048", key_type="RSA", primary_algo=RSA_ALGO, bits=2048),
    KeySpec(id="rsa4096", label="RSA-4096", key_type="RSA", primary_algo=RSA_ALGO, bits=4096),
    KeySpec(
        id="cv25519",
        label="ECC-Curve25519",
        key_type="ECC",
        primary_algo=EDDSA_ALGO,
        curve="Curve25519",
        primary_curve_token="ed25519",
    ),
)


def file_checksum(path: str | Path) -> str:
    """Return the ``sha256:<64 hex>`` checksum of a file's bytes."""
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _aggregate_checksum(entries: Iterable["KeyManifestEntry"]) -> str:
    """Deterministic checksum over the whole Key_Set (per-file checksums, sorted)."""
    lines: list[str] = []
    for entry in entries:
        lines.append(f"{entry.public_file}:{entry.public_checksum}")
        lines.append(f"{entry.private_file}:{entry.private_checksum}")
    lines.sort()
    h = hashlib.sha256()
    h.update("\n".join(lines).encode("utf-8"))
    return f"sha256:{h.hexdigest()}"


@dataclass(frozen=True)
class KeyInfo:
    """What ``gpg`` reports about a key file (primary key only)."""

    fingerprint: str
    algo: int
    key_length: int
    curve: str | None


def _resolve_gpg(gpg_path: str | None) -> str:
    exe = gpg_path or "gpg"
    found = shutil.which(exe)
    if found is None:
        raise GpgUnavailableError(
            f"could not find the '{exe}' executable needed to read OpenPGP key "
            "files; install GnuPG or pass an explicit gpg_path"
        )
    return found


def read_key_info(path: str | Path, *, gpg_path: str | None = None) -> KeyInfo:
    """Inspect an armored key file without importing it into any keyring."""
    exe = _resolve_gpg(gpg_path)
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"key file not found: {p}")

    proc = subprocess.run(
        [
            exe,
            "--batch",
            "--with-colons",
            "--import-options",
            "show-only",
            "--import",
            str(p),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise KeyGenError(f"gpg failed to read {p.name}: {proc.stderr.strip() or 'unknown error'}")

    pub_fields: list[str] | None = None
    fingerprint: str | None = None
    for line in proc.stdout.splitlines():
        fields = line.split(":")
        if fields[0] == "pub" and pub_fields is None:
            pub_fields = fields
        elif fields[0] == "fpr" and pub_fields is not None and fingerprint is None:
            # field index 9 holds the fingerprint
            if len(fields) > 9 and fields[9]:
                fingerprint = fields[9]
            break

    if pub_fields is None or fingerprint is None:
        raise KeyGenError(f"gpg output for {p.name} did not contain a primary public key")

    try:
        key_length = int(pub_fields[2]) if pub_fields[2] else 0
        algo = int(pub_fields[3]) if pub_fields[3] else 0
    except (IndexError, ValueError) as exc:
        raise KeyGenError(f"could not parse gpg record for {p.name}: {exc}") from exc

    curve = pub_fields[16] if len(pub_fields) > 16 and pub_fields[16] else None
    return KeyInfo(fingerprint=fingerprint, algo=algo, key_length=key_length, curve=curve)


@dataclass(frozen=True)
class KeyManifestEntry:
    """One key's reproducible record for the Result_Report."""

    id: str
    type: str  # "RSA" | "ECC"
    fingerprint: str
    public_file: str
    private_file: str
    public_checksum: str
    private_checksum: str
    bits: int | None = None
    curve: str | None = None

    @property
    def checksum(self) -> str:
        """Canonical per-key checksum (the public key, used for encrypt)."""
        return self.public_checksum

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "fingerprint": self.fingerprint,
            "checksum": self.checksum,
            "publicFile": self.public_file,
            "privateFile": self.private_file,
            "publicChecksum": self.public_checksum,
            "privateChecksum": self.private_checksum,
        }
        if self.bits is not None:
            out["bits"] = self.bits
        if self.curve is not None:
            out["curve"] = self.curve
        return out


@dataclass(frozen=True)
class KeySetManifest:
    """The full Key_Set manifest: per-key records + an aggregate checksum."""

    keys_dir: str
    entries: tuple[KeyManifestEntry, ...]
    key_set_checksum: str

    def entry(self, spec_id: str) -> KeyManifestEntry:
        for e in self.entries:
            if e.id == spec_id:
                return e
        raise KeyError(spec_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "keysDir": self.keys_dir,
            "keySetChecksum": self.key_set_checksum,
            "keySet": [e.to_dict() for e in self.entries],
        }


def verify_key_spec(
    spec: KeySpec, keys_dir: str | Path, *, gpg_path: str | None = None
) -> KeyManifestEntry:
    """Verify one key spec on disk and build its manifest entry."""
    keys_dir = Path(keys_dir)
    pub = keys_dir / spec.public_filename
    priv = keys_dir / spec.private_filename

    missing = [f.name for f in (pub, priv) if not f.is_file()]
    if missing:
        raise KeyGenError(f"missing key file(s): {', '.join(missing)}")

    info = read_key_info(pub, gpg_path=gpg_path)

    if info.algo != spec.primary_algo:
        raise KeyGenError(
            f"unexpected public-key algorithm {info.algo} (expected {spec.primary_algo})"
        )

    if spec.key_type == "RSA":
        if spec.bits is not None and info.key_length != spec.bits:
            raise KeyGenError(
                f"unexpected RSA key length {info.key_length} bits (expected {spec.bits})"
            )
    elif spec.key_type == "ECC":
        if spec.primary_curve_token is not None and info.curve != spec.primary_curve_token:
            raise KeyGenError(
                f"unexpected ECC curve {info.curve!r} (expected {spec.primary_curve_token!r})"
            )

    return KeyManifestEntry(
        id=spec.id,
        type=spec.key_type,
        fingerprint=info.fingerprint,
        public_file=spec.public_filename,
        private_file=spec.private_filename,
        public_checksum=file_checksum(pub),
        private_checksum=file_checksum(priv),
        bits=spec.bits,
        curve=spec.curve,
    )


def build_manifest(
    keys_dir: str | Path,
    specs: Iterable[KeySpec] = REQUIRED_KEY_SPECS,
    *,
    gpg_path: str | None = None,
) -> KeySetManifest:
    """Verify every required key spec and build the Key_Set manifest.

    If any spec is missing or invalid, raise :class:`KeyGenerationError` naming
    all failed specs so the harness halts before a Benchmark_Run.
    """
    keys_dir = Path(keys_dir)
    entries: list[KeyManifestEntry] = []
    failures: dict[str, str] = {}

    for spec in specs:
        try:
            entries.append(verify_key_spec(spec, keys_dir, gpg_path=gpg_path))
        except GpgUnavailableError:
            # No gpg means we cannot verify any spec; surface it directly.
            raise
        except (KeyGenError, FileNotFoundError) as exc:
            failures[spec.label] = str(exc)

    if failures:
        raise KeyGenerationError(failures)

    return KeySetManifest(
        keys_dir=str(keys_dir),
        entries=tuple(entries),
        key_set_checksum=_aggregate_checksum(entries),
    )


def _default_script_path() -> Path:
    # repo-root/scripts/gen-keys.sh, found by walking up from this file.
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "gen-keys.sh"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("could not locate scripts/gen-keys.sh from the harness package")


def generate_key_set(
    *,
    script_path: str | Path | None = None,
    force: bool = False,
    timeout: float | None = 600.0,
) -> None:
    """Run the existing ``scripts/gen-keys.sh`` to (re)create the Key_Set.

    The script is idempotent: existing key files are kept unless ``force`` is
    set (``FORCE=1``). This keeps recorded fingerprints stable across runs.
    """
    script = Path(script_path) if script_path is not None else _default_script_path()
    if not script.is_file():
        raise FileNotFoundError(f"key generation script not found: {script}")

    env_force = {"FORCE": "1"} if force else {}

    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env={**os.environ, **env_force},
    )
    if proc.returncode != 0:
        raise KeyGenError(
            "scripts/gen-keys.sh failed: " + (proc.stderr.strip() or proc.stdout.strip())
        )


def ensure_key_set(
    keys_dir: str | Path,
    specs: Iterable[KeySpec] = REQUIRED_KEY_SPECS,
    *,
    generate: bool = False,
    script_path: str | Path | None = None,
    gpg_path: str | None = None,
) -> KeySetManifest:
    """Build the manifest, optionally generating missing keys first.

    With ``generate=True`` the gen-keys script is run before verification so a
    fresh checkout can produce the Key_Set automatically.
    """
    specs = tuple(specs)
    if generate:
        generate_key_set(script_path=script_path)
    return build_manifest(keys_dir, specs, gpg_path=gpg_path)
