"""Typed models and parsers for the shared Runner CLI contract.

Python view of the JSON shapes defined by the schemas in ``contract/`` at the
repository root: ``Command`` (Harness -> Runner stdin) and ``RunnerOutput``
(Runner stdout -> Harness). Parsing is strict about required fields and closed
enums; full structural validation lives in :mod:`harness.contract.schema`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

__all__ = [
    "ContractError",
    "OutputEncoding",
    "Mode",
    "Operation",
    "RunnerId",
    "FailureType",
    "CryptoProfile",
    "Command",
    "GcStats",
    "OperationSample",
    "RunnerOutput",
]


class ContractError(ValueError):
    """Raised when a JSON payload violates the CLI contract."""


class OutputEncoding(str, Enum):
    """OpenPGP output encoding shared by all Runners in a Scenario."""

    BINARY = "binary"
    ARMORED = "armored"


class Mode(str, Enum):
    COLD_START = "cold_start"
    STEADY_STATE = "steady_state"


class Operation(str, Enum):
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"
    ROUNDTRIP = "roundtrip"


class RunnerId(str, Enum):
    GO = "go"
    JAVA = "java"


class FailureType(str, Enum):
    OPERATION_FAILURE = "operation_failure"
    CORRECTNESS_FAILURE = "correctness_failure"


# Parsing helpers
def _require(data: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise ContractError(f"{where}: missing required field {key!r}")
    return data[key]


def _as_str(value: Any, key: str, where: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{where}: field {key!r} must be a string, got {type(value).__name__}")
    return value


def _as_int(value: Any, key: str, where: str) -> int:
    # bool is a subclass of int; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{where}: field {key!r} must be an integer, got {type(value).__name__}")
    return value


def _as_bool(value: Any, key: str, where: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{where}: field {key!r} must be a boolean, got {type(value).__name__}")
    return value


def _as_number_opt(value: Any, key: str, where: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{where}: field {key!r} must be a number or null, got {type(value).__name__}")
    return float(value)


def _as_int_opt(value: Any, key: str, where: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, key, where)


def _as_enum(enum_cls: type[Enum], value: Any, key: str, where: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(repr(m.value) for m in enum_cls)
        raise ContractError(
            f"{where}: field {key!r} has invalid value {value!r}; expected one of {allowed}"
        ) from None


# Command (stdin)
@dataclass(frozen=True)
class CryptoProfile:
    pub_alg: str
    cipher: str
    compression: str
    hash: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str = "cryptoProfile") -> "CryptoProfile":
        if not isinstance(data, Mapping):
            raise ContractError(f"{where}: must be an object")
        return cls(
            pub_alg=_as_str(_require(data, "pubAlg", where), "pubAlg", where),
            cipher=_as_str(_require(data, "cipher", where), "cipher", where),
            compression=_as_str(_require(data, "compression", where), "compression", where),
            hash=_as_str(_require(data, "hash", where), "hash", where),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pubAlg": self.pub_alg,
            "cipher": self.cipher,
            "compression": self.compression,
            "hash": self.hash,
        }


@dataclass(frozen=True)
class Command:
    """Command JSON the harness sends to a Runner on stdin."""

    variant_id: str
    mode: Mode
    warmup_iterations: int
    concurrency: int
    crypto_profile: CryptoProfile
    output_encoding: OutputEncoding
    key_set_path: str
    key_set_checksum: str
    corpus_path: str
    corpus_checksum: str
    output_dir: str
    operation: Operation
    command: str = "run"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Command":
        where = "Command"
        if not isinstance(data, Mapping):
            raise ContractError(f"{where}: must be a JSON object")

        command = _as_str(_require(data, "command", where), "command", where)
        if command != "run":
            raise ContractError(f"{where}: field 'command' must be 'run', got {command!r}")

        warmup = _as_int(_require(data, "warmupIterations", where), "warmupIterations", where)
        if not 0 <= warmup <= 100:
            raise ContractError(f"{where}: 'warmupIterations' must be in [0, 100], got {warmup}")

        concurrency = _as_int(_require(data, "concurrency", where), "concurrency", where)
        if concurrency < 1:
            raise ContractError(f"{where}: 'concurrency' must be >= 1, got {concurrency}")

        return cls(
            command=command,
            variant_id=_as_str(_require(data, "variantId", where), "variantId", where),
            mode=_as_enum(Mode, _require(data, "mode", where), "mode", where),
            warmup_iterations=warmup,
            concurrency=concurrency,
            crypto_profile=CryptoProfile.from_dict(
                _require(data, "cryptoProfile", where), f"{where}.cryptoProfile"
            ),
            output_encoding=_as_enum(
                OutputEncoding, _require(data, "outputEncoding", where), "outputEncoding", where
            ),
            key_set_path=_as_str(_require(data, "keySetPath", where), "keySetPath", where),
            key_set_checksum=_as_str(_require(data, "keySetChecksum", where), "keySetChecksum", where),
            corpus_path=_as_str(_require(data, "corpusPath", where), "corpusPath", where),
            corpus_checksum=_as_str(_require(data, "corpusChecksum", where), "corpusChecksum", where),
            output_dir=_as_str(_require(data, "outputDir", where), "outputDir", where),
            operation=_as_enum(Operation, _require(data, "operation", where), "operation", where),
        )

    @classmethod
    def from_json(cls, text: str) -> "Command":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ContractError(f"Command: invalid JSON: {exc}") from exc
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "variantId": self.variant_id,
            "mode": self.mode.value,
            "warmupIterations": self.warmup_iterations,
            "concurrency": self.concurrency,
            "cryptoProfile": self.crypto_profile.to_dict(),
            "outputEncoding": self.output_encoding.value,
            "keySetPath": self.key_set_path,
            "keySetChecksum": self.key_set_checksum,
            "corpusPath": self.corpus_path,
            "corpusChecksum": self.corpus_checksum,
            "outputDir": self.output_dir,
            "operation": self.operation.value,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# RunnerOutput (stdout)
@dataclass(frozen=True)
class GcStats:
    collections: int
    total_pause_ms: float
    gc_type: str
    heap_init_mb: float | None = None
    heap_max_mb: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str = "gc") -> "GcStats":
        if not isinstance(data, Mapping):
            raise ContractError(f"{where}: must be an object or null")
        return cls(
            collections=_as_int(_require(data, "collections", where), "collections", where),
            total_pause_ms=float(
                _as_number_opt(_require(data, "totalPauseMs", where), "totalPauseMs", where) or 0.0
            ),
            gc_type=_as_str(_require(data, "gcType", where), "gcType", where),
            heap_init_mb=_as_number_opt(data.get("heapInitMb"), "heapInitMb", where),
            heap_max_mb=_as_number_opt(data.get("heapMaxMb"), "heapMaxMb", where),
        )


@dataclass(frozen=True)
class OperationSample:
    """One raw per-operation sample."""

    file_name: str
    file_type: str
    original_bytes: int
    skipped: bool
    round_trip_ok: bool
    ciphertext_bytes: int | None = None
    skip_reason: str | None = None
    encrypt_ms: float | None = None
    decrypt_ms: float | None = None
    asym_encrypt_ms: float | None = None
    asym_decrypt_ms: float | None = None
    sym_encrypt_ms: float | None = None
    sym_decrypt_ms: float | None = None
    failure_type: FailureType | None = None
    output_file_name: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str = "operation") -> "OperationSample":
        if not isinstance(data, Mapping):
            raise ContractError(f"{where}: must be an object")

        failure_raw = data.get("failureType")
        failure = (
            None if failure_raw is None else _as_enum(FailureType, failure_raw, "failureType", where)
        )

        return cls(
            file_name=_as_str(_require(data, "fileName", where), "fileName", where),
            file_type=_as_str(_require(data, "fileType", where), "fileType", where),
            original_bytes=_as_int(_require(data, "originalBytes", where), "originalBytes", where),
            skipped=_as_bool(_require(data, "skipped", where), "skipped", where),
            round_trip_ok=_as_bool(_require(data, "roundTripOk", where), "roundTripOk", where),
            ciphertext_bytes=_as_int_opt(data.get("ciphertextBytes"), "ciphertextBytes", where),
            skip_reason=(None if data.get("skipReason") is None else _as_str(data["skipReason"], "skipReason", where)),
            encrypt_ms=_as_number_opt(data.get("encryptMs"), "encryptMs", where),
            decrypt_ms=_as_number_opt(data.get("decryptMs"), "decryptMs", where),
            asym_encrypt_ms=_as_number_opt(data.get("asymEncryptMs"), "asymEncryptMs", where),
            asym_decrypt_ms=_as_number_opt(data.get("asymDecryptMs"), "asymDecryptMs", where),
            sym_encrypt_ms=_as_number_opt(data.get("symEncryptMs"), "symEncryptMs", where),
            sym_decrypt_ms=_as_number_opt(data.get("symDecryptMs"), "symDecryptMs", where),
            failure_type=failure,
            output_file_name=(
                None if data.get("outputFileName") is None else _as_str(data["outputFileName"], "outputFileName", where)
            ),
        )


@dataclass(frozen=True)
class RunnerOutput:
    """RunnerOutput JSON a Runner writes to stdout."""

    runner_id: RunnerId
    variant_id: str
    mode: Mode
    scenario_id: str
    crypto_profile_id: str
    concurrency: int
    output_encoding: OutputEncoding
    hardware_accel: bool
    key_set_checksum_seen: str
    corpus_checksum_seen: str
    operations: tuple[OperationSample, ...]
    process_startup_ms: float | None = None
    gc: GcStats | None = None
    resource_samples_note: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunnerOutput":
        where = "RunnerOutput"
        if not isinstance(data, Mapping):
            raise ContractError(f"{where}: must be a JSON object")

        concurrency = _as_int(_require(data, "concurrency", where), "concurrency", where)
        if concurrency < 1:
            raise ContractError(f"{where}: 'concurrency' must be >= 1, got {concurrency}")

        ops_raw = _require(data, "operations", where)
        if not isinstance(ops_raw, list):
            raise ContractError(f"{where}: 'operations' must be an array")
        operations = tuple(
            OperationSample.from_dict(op, f"{where}.operations[{i}]") for i, op in enumerate(ops_raw)
        )

        gc_raw = data.get("gc")
        gc = None if gc_raw is None else GcStats.from_dict(gc_raw, f"{where}.gc")

        return cls(
            runner_id=_as_enum(RunnerId, _require(data, "runnerId", where), "runnerId", where),
            variant_id=_as_str(_require(data, "variantId", where), "variantId", where),
            mode=_as_enum(Mode, _require(data, "mode", where), "mode", where),
            scenario_id=_as_str(_require(data, "scenarioId", where), "scenarioId", where),
            crypto_profile_id=_as_str(_require(data, "cryptoProfileId", where), "cryptoProfileId", where),
            concurrency=concurrency,
            output_encoding=_as_enum(
                OutputEncoding, _require(data, "outputEncoding", where), "outputEncoding", where
            ),
            hardware_accel=_as_bool(_require(data, "hardwareAccel", where), "hardwareAccel", where),
            key_set_checksum_seen=_as_str(
                _require(data, "keySetChecksumSeen", where), "keySetChecksumSeen", where
            ),
            corpus_checksum_seen=_as_str(
                _require(data, "corpusChecksumSeen", where), "corpusChecksumSeen", where
            ),
            operations=operations,
            process_startup_ms=_as_number_opt(data.get("processStartupMs"), "processStartupMs", where),
            gc=gc,
            resource_samples_note=(
                None
                if data.get("resourceSamplesNote") is None
                else _as_str(data["resourceSamplesNote"], "resourceSamplesNote", where)
            ),
        )

    @classmethod
    def from_json(cls, text: str) -> "RunnerOutput":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ContractError(f"RunnerOutput: invalid JSON: {exc}") from exc
        return cls.from_dict(data)
