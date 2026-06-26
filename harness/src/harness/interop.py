"""InteroperabilityChecker — the cross-language / standard-tool interop gate.

Runs a set of (producer, consumer) pairs to prove each Runner emits standard,
interoperable OpenPGP: each Runner's ciphertext must be decryptable by the
other Runner and by the standard ``gpg`` CLI, byte-for-byte. Any failure marks
the related results non-comparable.

Producers/consumers are injectable :class:`InteropEndpoint` objects wrapping an
optional encrypt/decrypt callable, so the gate is testable with fake endpoints
and incremental (not-ready endpoints register as ``pending``). Two real
endpoints are provided: :class:`GoRunnerInterop` (the Go_Runner binary) and
:class:`GpgInterop` (the standard ``gpg`` CLI in an isolated ``GNUPGHOME``).
"""

from __future__ import annotations

import filecmp
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

__all__ = [
    "InteropOutcome",
    "InteropCheck",
    "InteropSummary",
    "InteropPair",
    "InteropEndpoint",
    "InteroperabilityChecker",
    "EncryptFn",
    "DecryptFn",
    "pending_endpoint",
    "default_interop_pairs",
    "GoRunnerInterop",
    "GpgInterop",
    "GpgUnavailableError",
    "InteropError",
    "GO",
    "JAVA",
    "GPG",
]

# Endpoint name constants used across the standard pair set and the report.
GO = "go"
JAVA = "java"
GPG = "gpg"

#: An encrypt callable: read ``plaintext`` and write OpenPGP ciphertext to
#: ``ciphertext``. Must raise on failure (the checker turns that into a ``fail``).
EncryptFn = Callable[[Path, Path], None]
#: A decrypt callable: read ``ciphertext`` and write the recovered plaintext to
#: ``recovered``. Must raise on failure.
DecryptFn = Callable[[Path, Path], None]


class InteropError(RuntimeError):
    """An endpoint could not perform an encrypt/decrypt operation."""


class GpgUnavailableError(InteropError):
    """Raised when the ``gpg`` executable needed for the interop check is missing."""


class InteropOutcome(str, Enum):
    """Outcome of one (producer, consumer) Interoperability_Check.

    ``PASS``/``FAIL`` are the recorded results. ``PENDING`` marks a pair whose
    producer or consumer is not available yet: the check has not run, so it does
    not mark anything non-comparable.
    """

    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"


@dataclass(frozen=True)
class InteropCheck:
    """Result of one (producer, consumer) pair with its direction and reason.

    ``reason`` is added when the pair failed or is pending so the cause is
    explicit.
    """

    producer: str
    consumer: str
    result: InteropOutcome
    reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.result is InteropOutcome.PASS

    @property
    def failed(self) -> bool:
        return self.result is InteropOutcome.FAIL

    @property
    def pending(self) -> bool:
        return self.result is InteropOutcome.PENDING

    @property
    def direction(self) -> str:
        """Human-readable direction, e.g. ``"go -> gpg"``."""
        return f"{self.producer} -> {self.consumer}"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "producer": self.producer,
            "consumer": self.consumer,
            "result": self.result.value,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class InteropSummary:
    """Aggregate of every Interoperability_Check for a Scenario.

    ``comparable`` is ``False`` when any pair failed. Pending pairs do not
    affect comparability — they simply have not run yet.
    """

    checks: tuple[InteropCheck, ...]

    @property
    def passed(self) -> tuple[InteropCheck, ...]:
        return tuple(c for c in self.checks if c.passed)

    @property
    def failures(self) -> tuple[InteropCheck, ...]:
        return tuple(c for c in self.checks if c.failed)

    @property
    def pending(self) -> tuple[InteropCheck, ...]:
        return tuple(c for c in self.checks if c.pending)

    @property
    def comparable(self) -> bool:
        """``False`` when any interop pair failed."""
        return len(self.failures) == 0

    def non_comparable_reasons(self) -> tuple[str, ...]:
        """Per-failure ``"<producer> -> <consumer>: <reason>"`` strings."""
        return tuple(
            f"interop fail: {c.direction}: {c.reason or 'ciphertext did not round-trip'}"
            for c in self.failures
        )

    def to_dict(self) -> dict[str, Any]:
        """Render the ``interopChecks`` array recorded in the Result_Report."""
        return {
            "comparable": self.comparable,
            "interopChecks": [c.to_dict() for c in self.checks],
            "nonComparableReasons": list(self.non_comparable_reasons()),
        }

    def interop_checks(self) -> list[dict[str, Any]]:
        """Just the ``interopChecks`` array."""
        return [c.to_dict() for c in self.checks]


@dataclass(frozen=True)
class InteropPair:
    """A directed interop check: ``producer`` encrypts, ``consumer`` decrypts."""

    producer: str
    consumer: str

    def __post_init__(self) -> None:
        if self.producer == self.consumer:
            raise ValueError(
                f"interop pair producer and consumer must differ, got {self.producer!r}"
            )


@dataclass(frozen=True)
class InteropEndpoint:
    """A named participant that can encrypt and/or decrypt OpenPGP data.

    ``encrypt``/``decrypt`` are the injected callables; either may be ``None``
    when the endpoint cannot play that role. ``available`` is ``False`` for an
    endpoint that is not ready yet; such an endpoint turns its pairs into
    ``pending`` checks with ``pending_reason``.
    """

    name: str
    encrypt: EncryptFn | None = None
    decrypt: DecryptFn | None = None
    available: bool = True
    pending_reason: str | None = None

    def can_produce(self) -> bool:
        return self.available and self.encrypt is not None

    def can_consume(self) -> bool:
        return self.available and self.decrypt is not None


def pending_endpoint(name: str, reason: str) -> InteropEndpoint:
    """Build a not-yet-available endpoint whose pairs report ``pending``."""
    return InteropEndpoint(name=name, available=False, pending_reason=reason)


def default_interop_pairs(
    *, runners: Sequence[str] = (GO, JAVA), standard_tool: str = GPG
) -> tuple[InteropPair, ...]:
    """The standard interop pair set: every ordered pair of distinct runners,
    and every runner -> standard tool.
    """
    pairs: list[InteropPair] = []
    for producer in runners:
        for consumer in runners:
            if producer != consumer:
                pairs.append(InteropPair(producer, consumer))
    for producer in runners:
        pairs.append(InteropPair(producer, standard_tool))
    return tuple(pairs)


class InteroperabilityChecker:
    """Run (producer, consumer) interop pairs over a plaintext.

    Parameters
    ----------
    endpoints:
        Mapping of endpoint name -> :class:`InteropEndpoint`. Endpoints that are
        not present, or are present but not available, turn their pairs into
        ``pending`` checks.
    pairs:
        The directed pairs to check. Defaults to :func:`default_interop_pairs`
        restricted to the endpoint names actually supplied.
    """

    def __init__(
        self,
        endpoints: Mapping[str, InteropEndpoint],
        pairs: Sequence[InteropPair] | None = None,
    ) -> None:
        self._endpoints = dict(endpoints)
        if pairs is None:
            names = set(self._endpoints)
            pairs = tuple(
                p
                for p in default_interop_pairs()
                if p.producer in names and p.consumer in names
            )
        self._pairs = tuple(pairs)

    @property
    def pairs(self) -> tuple[InteropPair, ...]:
        return self._pairs

    def check_pair(
        self, plaintext: str | Path, pair: InteropPair, *, workdir: str | Path | None = None
    ) -> InteropCheck:
        """Encrypt ``plaintext`` with the producer, decrypt with the consumer,
        and compare byte-for-byte.

        Returns ``pending`` when either endpoint is unavailable, ``fail`` (with a
        reason) when an operation errors or the recovered bytes differ, and
        ``pass`` only on an exact byte-for-byte match.
        """
        plaintext = Path(plaintext)
        producer = self._endpoints.get(pair.producer)
        consumer = self._endpoints.get(pair.consumer)

        pending = self._pending_reason(pair, producer, consumer)
        if pending is not None:
            return InteropCheck(pair.producer, pair.consumer, InteropOutcome.PENDING, pending)

        # Both endpoints are available — drive the real round-trip in a scratch
        # dir so producer ciphertext and consumer output never collide.
        owns_workdir = workdir is None
        work = Path(tempfile.mkdtemp(prefix="interop-")) if owns_workdir else Path(workdir)
        try:
            work.mkdir(parents=True, exist_ok=True)
            ciphertext = work / f"{pair.producer}-to-{pair.consumer}.ct"
            recovered = work / f"{pair.producer}-to-{pair.consumer}.out"

            try:
                assert producer is not None and producer.encrypt is not None
                producer.encrypt(plaintext, ciphertext)
            except Exception as exc:  # noqa: BLE001 - turn any failure into a fail result
                return InteropCheck(
                    pair.producer, pair.consumer, InteropOutcome.FAIL,
                    f"{pair.producer} failed to encrypt: {exc}",
                )

            try:
                assert consumer is not None and consumer.decrypt is not None
                consumer.decrypt(ciphertext, recovered)
            except Exception as exc:  # noqa: BLE001
                return InteropCheck(
                    pair.producer, pair.consumer, InteropOutcome.FAIL,
                    f"{pair.consumer} failed to decrypt {pair.producer} ciphertext: {exc}",
                )

            if not recovered.exists():
                return InteropCheck(
                    pair.producer, pair.consumer, InteropOutcome.FAIL,
                    f"{pair.consumer} produced no output decrypting {pair.producer} ciphertext",
                )
            if not _files_equal(plaintext, recovered):
                return InteropCheck(
                    pair.producer, pair.consumer, InteropOutcome.FAIL,
                    f"recovered plaintext differs from original "
                    f"({plaintext.stat().st_size} vs {recovered.stat().st_size} bytes)",
                )
            return InteropCheck(pair.producer, pair.consumer, InteropOutcome.PASS)
        finally:
            if owns_workdir:
                shutil.rmtree(work, ignore_errors=True)

    def check(self, plaintext: str | Path) -> InteropSummary:
        """Run every configured pair over ``plaintext`` and aggregate."""
        return InteropSummary(tuple(self.check_pair(plaintext, p) for p in self._pairs))

    def _pending_reason(
        self,
        pair: InteropPair,
        producer: InteropEndpoint | None,
        consumer: InteropEndpoint | None,
    ) -> str | None:
        """Return why a pair is pending, or ``None`` when it can run."""
        if producer is None:
            return f"producer {pair.producer!r} not registered"
        if consumer is None:
            return f"consumer {pair.consumer!r} not registered"
        if not producer.available:
            return producer.pending_reason or f"producer {pair.producer!r} not available yet"
        if not consumer.available:
            return consumer.pending_reason or f"consumer {pair.consumer!r} not available yet"
        if producer.encrypt is None:
            return f"producer {pair.producer!r} cannot encrypt"
        if consumer.decrypt is None:
            return f"consumer {pair.consumer!r} cannot decrypt"
        return None


def _files_equal(a: Path, b: Path) -> bool:
    """Byte-for-byte file comparison."""
    return filecmp.cmp(a, b, shallow=False)


def _file_sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _key_set_checksum(keys_dir: Path) -> str:
    """Reproduce harness.keys._aggregate_checksum / Go ComputeKeySetChecksum.

    Lines ``"<filename>:sha256:<hex>"`` for every ``*-public.asc`` /
    ``*-private.asc`` file, sorted, joined with ``"\\n"``, then SHA-256'd. The
    Go_Runner recomputes the same value and rejects a mismatch.
    """
    lines: list[str] = []
    for name in os.listdir(keys_dir):
        if name.endswith("-public.asc") or name.endswith("-private.asc"):
            lines.append(f"{name}:sha256:{_file_sha256_hex(keys_dir / name)}")
    lines.sort()
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _corpus_checksum(root: Path) -> str:
    """Reproduce harness.corpus._aggregate_checksum / Go ComputeCorpusChecksum.

    For every regular file (sorted by POSIX relative path) feed
    ``"<relpath>\\x00<hex>\\n"`` into one SHA-256 hasher, where ``<hex>`` is the
    bare file digest.
    """
    entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            entries.append((rel, _file_sha256_hex(path)))
    entries.sort()
    h = hashlib.sha256()
    for rel, hexsum in entries:
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(hexsum.encode("ascii"))
        h.update(b"\n")
    return "sha256:" + h.hexdigest()


# Crypto_Profile public-key algorithm -> (key id prefix, gpg uid email). Mirrors
# runners/go/keys.go pubAlgToKeyID and keys/KEYINFO.md.
_PUB_ALG_TO_KEY: dict[str, tuple[str, str]] = {
    "RSA-2048": ("rsa2048", "poc-rsa2048@example.com"),
    "RSA-4096": ("rsa4096", "poc-rsa4096@example.com"),
    "CURVE25519": ("cv25519", "poc-cv25519@example.com"),
    "ECC-CURVE25519": ("cv25519", "poc-cv25519@example.com"),
    "ECC": ("cv25519", "poc-cv25519@example.com"),
}


def _resolve_pub_alg(pub_alg: str) -> tuple[str, str]:
    key = pub_alg.upper().replace("_", "-")
    if key not in _PUB_ALG_TO_KEY:
        raise InteropError(f"unsupported public-key algorithm for interop: {pub_alg!r}")
    return _PUB_ALG_TO_KEY[key]


class GoRunnerInterop:
    """Drive the real Go_Runner binary as an interop endpoint.

    Encrypt/decrypt go through the exact shared CLI contract the harness uses: a
    one-file corpus, ``operation=encrypt``/``decrypt``, with the Key_Set/Corpus
    checksums computed the same way the runner recomputes them. The same class
    works as a producer (``encrypt``) and a consumer (``decrypt``).
    """

    # A supported corpus filename (see runners/go/classify.go): ``.dat`` is in
    # the supported set, so the runner processes it rather than skipping it.
    _CORPUS_NAME = "payload.dat"

    def __init__(
        self,
        binary: str | Path,
        key_set_path: str | Path,
        *,
        pub_alg: str = "RSA-2048",
        cipher: str = "AES-256",
        compression: str = "ZLIB",
        hash_alg: str = "SHA-256",
        output_encoding: str = "binary",
        variant_id: str = "go-inmem-single",
        timeout_s: float = 120.0,
    ) -> None:
        self._binary = str(binary)
        self._keys = Path(key_set_path)
        self._pub_alg = pub_alg
        self._cipher = cipher
        self._compression = compression
        self._hash = hash_alg
        self._output_encoding = output_encoding
        self._variant_id = variant_id
        self._timeout_s = float(timeout_s)
        # Validate the algorithm maps to a known key up front.
        _resolve_pub_alg(pub_alg)

    def as_endpoint(self, name: str = GO) -> InteropEndpoint:
        """Wrap this runner as an :class:`InteropEndpoint` (producer+consumer)."""
        return InteropEndpoint(name=name, encrypt=self.encrypt, decrypt=self.decrypt)

    def encrypt(self, plaintext: Path, ciphertext: Path) -> None:
        """Encrypt ``plaintext`` to ``ciphertext`` via the Go_Runner."""
        with tempfile.TemporaryDirectory(prefix="go-interop-enc-") as tmp:
            tmp_path = Path(tmp)
            corpus = tmp_path / "corpus"
            out = tmp_path / "out"
            corpus.mkdir()
            out.mkdir()
            shutil.copyfile(plaintext, corpus / self._CORPUS_NAME)

            self._invoke(corpus, out, operation="encrypt")

            produced = out / f"{self._CORPUS_NAME}.pgp"
            if not produced.exists():
                raise InteropError(
                    f"Go_Runner produced no ciphertext at {produced} (output dir: "
                    f"{sorted(p.name for p in out.iterdir())})"
                )
            ciphertext.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(produced, ciphertext)

    def decrypt(self, ciphertext: Path, recovered: Path) -> None:
        """Decrypt ``ciphertext`` to ``recovered`` via the Go_Runner."""
        with tempfile.TemporaryDirectory(prefix="go-interop-dec-") as tmp:
            tmp_path = Path(tmp)
            corpus = tmp_path / "corpus"
            out = tmp_path / "out"
            corpus.mkdir()
            out.mkdir()
            # Name the ciphertext with a supported extension so the runner does
            # not skip it by file-type classification.
            shutil.copyfile(ciphertext, corpus / self._CORPUS_NAME)

            self._invoke(corpus, out, operation="decrypt")

            produced = out / f"{self._CORPUS_NAME}.dec"
            if not produced.exists():
                raise InteropError(
                    f"Go_Runner produced no plaintext at {produced} (output dir: "
                    f"{sorted(p.name for p in out.iterdir())})"
                )
            recovered.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(produced, recovered)

    def _invoke(self, corpus: Path, out: Path, *, operation: str) -> None:
        command = {
            "command": "run",
            "variantId": self._variant_id,
            "mode": "cold_start",
            "warmupIterations": 0,
            "concurrency": 1,
            "cryptoProfile": {
                "pubAlg": self._pub_alg,
                "cipher": self._cipher,
                "compression": self._compression,
                "hash": self._hash,
            },
            "outputEncoding": self._output_encoding,
            "keySetPath": str(self._keys),
            "keySetChecksum": _key_set_checksum(self._keys),
            "corpusPath": str(corpus),
            "corpusChecksum": _corpus_checksum(corpus),
            "outputDir": str(out),
            "operation": operation,
        }
        try:
            proc = subprocess.run(
                [self._binary],
                input=json.dumps(command),
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
        except FileNotFoundError as exc:
            raise InteropError(f"Go_Runner binary not found: {self._binary!r}") from exc
        except subprocess.TimeoutExpired as exc:
            raise InteropError(f"Go_Runner timed out after {self._timeout_s:g}s") from exc

        if proc.returncode != 0:
            raise InteropError(
                f"Go_Runner {operation} exited {proc.returncode}: {proc.stderr.strip()}"
            )


class GpgInterop:
    """Drive the standard ``gpg`` CLI as an interop endpoint.

    Proves a Runner emits standard OpenPGP: ``gpg`` must be able to decrypt the
    Runner's ciphertext byte-for-byte. A private, temporary ``GNUPGHOME`` is
    created and the shared Key_Set imported into it, so the check never touches
    the operator's real keyring. Use as a context manager (or call
    :meth:`close`) to clean the temporary home up. ``gpg`` is used as a consumer
    (decrypt), but :meth:`encrypt` is provided too.
    """

    def __init__(
        self,
        key_set_path: str | Path,
        *,
        pub_alg: str = "RSA-2048",
        gpg_path: str = "gpg",
        armored: bool = False,
    ) -> None:
        self._keys = Path(key_set_path)
        self._pub_alg = pub_alg
        self._key_id, self._recipient = _resolve_pub_alg(pub_alg)
        self._gpg = shutil.which(gpg_path)
        if self._gpg is None:
            raise GpgUnavailableError(
                f"could not find the {gpg_path!r} executable required for the "
                "interop check (Req 25.3)"
            )
        self._armored = armored
        self._home: Path | None = None
        self._imported_public = False
        self._imported_private = False

    def __enter__(self) -> "GpgInterop":
        self._ensure_home()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._home is not None:
            shutil.rmtree(self._home, ignore_errors=True)
            self._home = None
            self._imported_public = False
            self._imported_private = False

    def as_endpoint(self, name: str = GPG, *, decrypt_only: bool = True) -> InteropEndpoint:
        """Wrap gpg as an :class:`InteropEndpoint`.

        By default gpg is a decrypt-only consumer; pass ``decrypt_only=False`` to
        also expose it as an encrypting producer.
        """
        return InteropEndpoint(
            name=name,
            encrypt=None if decrypt_only else self.encrypt,
            decrypt=self.decrypt,
        )

    def decrypt(self, ciphertext: Path, recovered: Path) -> None:
        """Decrypt ``ciphertext`` with gpg into ``recovered`` (keys have no passphrase)."""
        self._ensure_home()
        self._import_private()
        recovered.parent.mkdir(parents=True, exist_ok=True)
        self._run_gpg(
            [
                "--yes",
                "--pinentry-mode",
                "loopback",
                "--output",
                str(recovered),
                "--decrypt",
                str(ciphertext),
            ],
            what="decrypt",
        )

    def encrypt(self, plaintext: Path, ciphertext: Path) -> None:
        """Encrypt ``plaintext`` to ``ciphertext`` with gpg for the Key_Set recipient."""
        self._ensure_home()
        self._import_public()
        ciphertext.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "--yes",
            "--trust-model",
            "always",
            "--recipient",
            self._recipient,
            "--output",
            str(ciphertext),
        ]
        if self._armored:
            args.append("--armor")
        args += ["--encrypt", str(plaintext)]
        self._run_gpg(args, what="encrypt")

    def _ensure_home(self) -> None:
        if self._home is None:
            self._home = Path(tempfile.mkdtemp(prefix="interop-gnupg-"))
            os.chmod(self._home, 0o700)

    def _import_public(self) -> None:
        if not self._imported_public:
            self._run_gpg(
                ["--import", str(self._keys / f"{self._key_id}-public.asc")], what="import-public"
            )
            self._imported_public = True

    def _import_private(self) -> None:
        if not self._imported_private:
            self._run_gpg(
                ["--import", str(self._keys / f"{self._key_id}-private.asc")],
                what="import-private",
            )
            self._imported_private = True

    def _run_gpg(self, args: list[str], *, what: str) -> None:
        assert self._home is not None and self._gpg is not None
        env = dict(os.environ, GNUPGHOME=str(self._home))
        try:
            proc = subprocess.run(
                [self._gpg, "--batch", *args],
                capture_output=True,
                text=True,
                env=env,
                timeout=120.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise InteropError(f"gpg {what} timed out") from exc
        if proc.returncode != 0:
            raise InteropError(f"gpg {what} exited {proc.returncode}: {proc.stderr.strip()}")
