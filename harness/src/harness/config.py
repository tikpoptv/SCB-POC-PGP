"""ConfigLoader for the single source-of-truth ``config.json``.

Parses the config file into typed dataclasses and validates the run
parameters, raising :class:`ConfigError` (naming the offending parameter)
before a Benchmark_Run starts. On success :meth:`BenchmarkConfig.effective_values`
echoes every parameter actually used for recording into the Result_Report.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness.contract.models import CryptoProfile, OutputEncoding

__all__ = [
    "ConfigError",
    "FileSizeTier",
    "MemoryMode",
    "DataCompressibility",
    "RunMode",
    "KeyType",
    "KeySpec",
    "CryptoProfileConfig",
    "ScenarioConfig",
    "NullTestConfig",
    "SoakTestConfig",
    "BenchmarkConfig",
    "ConfigLoader",
    "ROUNDS_RANGE",
    "WARMUP_RANGE",
    "SAMPLING_INTERVAL_RANGE",
]


# Validation bounds (single source of truth for the numeric ranges)
ROUNDS_RANGE = (1, 1000)
WARMUP_RANGE = (0, 100)
SAMPLING_INTERVAL_RANGE = (10, 1000)


class ConfigError(ValueError):
    """Raised when ``config.json`` is invalid.

    Carries the offending ``parameter`` path and the human ``reason`` so the
    harness can stop before a Benchmark_Run and report exactly what is wrong.
    The string form is ``"<parameter>: <reason>"``.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        self.parameter = parameter
        self.reason = reason
        super().__init__(f"{parameter}: {reason}")


# Closed enums for config fields
class FileSizeTier(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    MANY_SMALL = "many_small"
    CUSTOM = "custom"


class MemoryMode(str, Enum):
    IN_MEMORY = "in_memory"
    STREAMING = "streaming"
    BOTH = "both"


class DataCompressibility(str, Enum):
    COMPRESSIBLE = "compressible"
    INCOMPRESSIBLE = "incompressible"
    BOTH = "both"


class RunMode(str, Enum):
    COLD_START = "cold_start"
    STEADY_STATE = "steady_state"


class KeyType(str, Enum):
    RSA = "RSA"
    ECC = "ECC"


# Low-level field helpers (name the parameter on every failure)
def _require(data: Mapping[str, Any], key: str, where: str) -> Any:
    if not isinstance(data, Mapping):
        raise ConfigError(where, "must be an object")
    if key not in data:
        raise ConfigError(f"{where}.{key}" if where else key, "missing required field")
    return data[key]


def _as_int(value: Any, param: str) -> int:
    # bool is a subclass of int; reject it explicitly so true/false != 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(param, f"must be an integer, got {type(value).__name__}")
    return value


def _as_int_in_range(value: Any, param: str, low: int, high: int) -> int:
    n = _as_int(value, param)
    if not low <= n <= high:
        raise ConfigError(param, f"must be in [{low}, {high}], got {n}")
    return n


def _as_nonempty_str(value: Any, param: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(param, f"must be a string, got {type(value).__name__}")
    if not value.strip():
        raise ConfigError(param, "must be a non-empty string")
    return value


def _as_enum(enum_cls: type[Enum], value: Any, param: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(repr(m.value) for m in enum_cls)
        raise ConfigError(param, f"invalid value {value!r}; expected one of {allowed}") from None


# Typed config fragments
@dataclass(frozen=True)
class KeySpec:
    """A key specification. RSA needs ``bits``; ECC needs ``curve``."""

    type: KeyType
    bits: int | None = None
    curve: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str) -> "KeySpec":
        if not isinstance(data, Mapping):
            raise ConfigError(where, "must be an object")
        key_type = _as_enum(KeyType, _require(data, "type", where), f"{where}.type")
        if key_type is KeyType.RSA:
            bits = _as_int(_require(data, "bits", where), f"{where}.bits")
            if bits <= 0:
                raise ConfigError(f"{where}.bits", f"must be > 0, got {bits}")
            return cls(type=key_type, bits=bits)
        # ECC
        curve = _as_nonempty_str(_require(data, "curve", where), f"{where}.curve")
        return cls(type=key_type, curve=curve)

    def to_dict(self) -> dict[str, Any]:
        if self.type is KeyType.RSA:
            return {"type": self.type.value, "bits": self.bits}
        return {"type": self.type.value, "curve": self.curve}


@dataclass(frozen=True)
class CryptoProfileConfig:
    """A named Crypto_Profile: ``id`` plus the shared contract fields."""

    id: str
    profile: CryptoProfile

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str) -> "CryptoProfileConfig":
        if not isinstance(data, Mapping):
            raise ConfigError(where, "must be an object")
        profile_id = _as_nonempty_str(_require(data, "id", where), f"{where}.id")
        # Reuse the shared contract model; complete-fields enforced here so the
        # error names the exact missing/blank parameter.
        return cls(
            id=profile_id,
            profile=CryptoProfile(
                pub_alg=_as_nonempty_str(_require(data, "pubAlg", where), f"{where}.pubAlg"),
                cipher=_as_nonempty_str(_require(data, "cipher", where), f"{where}.cipher"),
                compression=_as_nonempty_str(
                    _require(data, "compression", where), f"{where}.compression"
                ),
                hash=_as_nonempty_str(_require(data, "hash", where), f"{where}.hash"),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, **self.profile.to_dict()}


@dataclass(frozen=True)
class ScenarioConfig:
    id: str
    file_size_tier: FileSizeTier
    key_spec: KeySpec
    concurrency: int
    memory_mode: MemoryMode
    crypto_profile_id: str
    data_compressibility: DataCompressibility
    output_encoding: OutputEncoding
    memory_quota_mb: int
    custom_size_bytes: int | None = None

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        where: str,
        *,
        vcpu: int,
        known_profile_ids: frozenset[str],
    ) -> "ScenarioConfig":
        if not isinstance(data, Mapping):
            raise ConfigError(where, "must be an object")

        scenario_id = _as_nonempty_str(_require(data, "id", where), f"{where}.id")
        tier = _as_enum(
            FileSizeTier, _require(data, "fileSizeTier", where), f"{where}.fileSizeTier"
        )

        # customSizeBytes must be > 0 when tier=custom.
        custom_size = data.get("customSizeBytes")
        if tier is FileSizeTier.CUSTOM:
            if custom_size is None:
                raise ConfigError(
                    f"{where}.customSizeBytes",
                    "must be > 0 when fileSizeTier is 'custom'",
                )
            custom_size = _as_int(custom_size, f"{where}.customSizeBytes")
            if custom_size <= 0:
                raise ConfigError(
                    f"{where}.customSizeBytes", f"must be > 0, got {custom_size}"
                )
        else:
            # If present for a non-custom tier it must still be a positive int or null.
            if custom_size is not None:
                custom_size = _as_int(custom_size, f"{where}.customSizeBytes")
                if custom_size <= 0:
                    raise ConfigError(
                        f"{where}.customSizeBytes", f"must be > 0, got {custom_size}"
                    )

        concurrency = _as_int(_require(data, "concurrency", where), f"{where}.concurrency")
        if not 1 <= concurrency <= vcpu:
            raise ConfigError(
                f"{where}.concurrency",
                f"must be in [1, vCPU={vcpu}], got {concurrency}",
            )

        crypto_profile_id = _as_nonempty_str(
            _require(data, "cryptoProfileId", where), f"{where}.cryptoProfileId"
        )
        if crypto_profile_id not in known_profile_ids:
            raise ConfigError(
                f"{where}.cryptoProfileId",
                f"references unknown cryptoProfile id {crypto_profile_id!r}",
            )

        memory_quota = _as_int(_require(data, "memoryQuotaMb", where), f"{where}.memoryQuotaMb")
        if memory_quota <= 0:
            raise ConfigError(f"{where}.memoryQuotaMb", f"must be > 0, got {memory_quota}")

        return cls(
            id=scenario_id,
            file_size_tier=tier,
            custom_size_bytes=custom_size,
            key_spec=KeySpec.from_dict(_require(data, "keySpec", where), f"{where}.keySpec"),
            concurrency=concurrency,
            memory_mode=_as_enum(
                MemoryMode, _require(data, "memoryMode", where), f"{where}.memoryMode"
            ),
            crypto_profile_id=crypto_profile_id,
            data_compressibility=_as_enum(
                DataCompressibility,
                _require(data, "dataCompressibility", where),
                f"{where}.dataCompressibility",
            ),
            output_encoding=_as_enum(
                OutputEncoding, _require(data, "outputEncoding", where), f"{where}.outputEncoding"
            ),
            memory_quota_mb=memory_quota,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fileSizeTier": self.file_size_tier.value,
            "customSizeBytes": self.custom_size_bytes,
            "keySpec": self.key_spec.to_dict(),
            "concurrency": self.concurrency,
            "memoryMode": self.memory_mode.value,
            "cryptoProfileId": self.crypto_profile_id,
            "dataCompressibility": self.data_compressibility.value,
            "outputEncoding": self.output_encoding.value,
            "memoryQuotaMb": self.memory_quota_mb,
        }


@dataclass(frozen=True)
class NullTestConfig:
    enabled: bool = False
    runner: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str) -> "NullTestConfig":
        if not isinstance(data, Mapping):
            raise ConfigError(where, "must be an object")
        enabled = _require(data, "enabled", where)
        if not isinstance(enabled, bool):
            raise ConfigError(f"{where}.enabled", "must be a boolean")
        runner = data.get("runner")
        if enabled and runner is None:
            raise ConfigError(f"{where}.runner", "must be set when nullTest is enabled")
        if runner is not None:
            runner = _as_nonempty_str(runner, f"{where}.runner")
        return cls(enabled=enabled, runner=runner)

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "runner": self.runner}


@dataclass(frozen=True)
class SoakTestConfig:
    enabled: bool = False
    duration_sec: int | None = None
    total_operations: int | None = None
    ram_leak_threshold_mb_per_hour: float | None = None
    latency_degradation_threshold_pct: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str) -> "SoakTestConfig":
        if not isinstance(data, Mapping):
            raise ConfigError(where, "must be an object")
        enabled = _require(data, "enabled", where)
        if not isinstance(enabled, bool):
            raise ConfigError(f"{where}.enabled", "must be a boolean")
        duration = data.get("durationSec")
        if duration is not None:
            duration = _as_int(duration, f"{where}.durationSec")
            if duration <= 0:
                raise ConfigError(f"{where}.durationSec", f"must be > 0, got {duration}")
        if enabled and duration is None and data.get("totalOperations") is None:
            raise ConfigError(
                f"{where}.durationSec",
                "either durationSec or totalOperations must be set when soakTest is enabled",
            )
        total_ops = data.get("totalOperations")
        if total_ops is not None:
            total_ops = _as_int(total_ops, f"{where}.totalOperations")
            if total_ops <= 0:
                raise ConfigError(f"{where}.totalOperations", f"must be > 0, got {total_ops}")
        return cls(
            enabled=enabled,
            duration_sec=duration,
            total_operations=total_ops,
            ram_leak_threshold_mb_per_hour=_opt_number(
                data.get("ramLeakThresholdMbPerHour"), f"{where}.ramLeakThresholdMbPerHour"
            ),
            latency_degradation_threshold_pct=_opt_number(
                data.get("latencyDegradationThresholdPct"),
                f"{where}.latencyDegradationThresholdPct",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "durationSec": self.duration_sec,
            "totalOperations": self.total_operations,
            "ramLeakThresholdMbPerHour": self.ram_leak_threshold_mb_per_hour,
            "latencyDegradationThresholdPct": self.latency_degradation_threshold_pct,
        }


def _opt_number(value: Any, param: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(param, f"must be a number, got {type(value).__name__}")
    return float(value)


# Top-level config
@dataclass(frozen=True)
class BenchmarkConfig:
    rounds: int
    warmup_iterations: int
    seed: int
    sampling_interval_ms: int
    crypto_profiles: tuple[CryptoProfileConfig, ...]
    key_specs: tuple[KeySpec, ...]
    scenarios: tuple[ScenarioConfig, ...]
    modes: tuple[RunMode, ...]
    vcpu: int
    result_dir: str = "./results"
    corpus_on_tmpfs: bool = True
    stability_threshold_cv: float | None = None
    confidence_level: float = 0.95
    best_variant_criterion: str = "p50_roundtrip"
    null_test: NullTestConfig = field(default_factory=NullTestConfig)
    soak_test: SoakTestConfig = field(default_factory=SoakTestConfig)

    def effective_values(self) -> dict[str, Any]:
        """The echo of every parameter actually used, for the Result_Report."""
        return {
            "rounds": self.rounds,
            "warmupIterations": self.warmup_iterations,
            "seed": self.seed,
            "samplingIntervalMs": self.sampling_interval_ms,
            "resultDir": self.result_dir,
            "corpusOnTmpfs": self.corpus_on_tmpfs,
            "stabilityThresholdCV": self.stability_threshold_cv,
            "confidenceLevel": self.confidence_level,
            "bestVariantCriterion": self.best_variant_criterion,
            "vCPU": self.vcpu,
            "cryptoProfiles": [p.to_dict() for p in self.crypto_profiles],
            "keySpecs": [k.to_dict() for k in self.key_specs],
            "scenarios": [s.to_dict() for s in self.scenarios],
            "modes": [m.value for m in self.modes],
            "nullTest": self.null_test.to_dict(),
            "soakTest": self.soak_test.to_dict(),
        }


class ConfigLoader:
    """Loads and validates the single ``config.json``."""

    def __init__(self, vcpu: int | None = None) -> None:
        """``vcpu`` bounds per-scenario concurrency; defaults to the CPU count."""
        detected = vcpu if vcpu is not None else (os.cpu_count() or 1)
        if isinstance(detected, bool) or not isinstance(detected, int) or detected < 1:
            raise ConfigError("vCPU", f"must be an integer >= 1, got {detected!r}")
        self.vcpu = detected

    def load_file(self, path: str | os.PathLike[str]) -> BenchmarkConfig:
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError("config.json", f"cannot read file {p}: {exc}") from exc
        return self.load_text(text)

    def load_text(self, text: str) -> BenchmarkConfig:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError("config.json", f"invalid JSON: {exc}") from exc
        return self.load_dict(data)

    def load_dict(self, data: Any) -> BenchmarkConfig:
        if not isinstance(data, Mapping):
            raise ConfigError("config.json", "top-level value must be a JSON object")

        where = ""  # top-level params are named directly (e.g. "rounds")

        rounds = _as_int_in_range(
            _require(data, "rounds", where), "rounds", *ROUNDS_RANGE
        )
        warmup = _as_int_in_range(
            _require(data, "warmupIterations", where), "warmupIterations", *WARMUP_RANGE
        )
        sampling = _as_int_in_range(
            _require(data, "samplingIntervalMs", where),
            "samplingIntervalMs",
            *SAMPLING_INTERVAL_RANGE,
        )
        seed = _as_int(_require(data, "seed", where), "seed")

        crypto_profiles = self._parse_crypto_profiles(_require(data, "cryptoProfiles", where))
        key_specs = self._parse_key_specs(_require(data, "keySpecs", where))
        modes = self._parse_modes(_require(data, "modes", where))

        known_ids = frozenset(p.id for p in crypto_profiles)
        scenarios = self._parse_scenarios(_require(data, "scenarios", where), known_ids)

        # Optional fields with defaults.
        result_dir = data.get("resultDir", "./results")
        if not isinstance(result_dir, str) or not result_dir.strip():
            raise ConfigError("resultDir", "must be a non-empty string")

        corpus_on_tmpfs = data.get("corpusOnTmpfs", True)
        if not isinstance(corpus_on_tmpfs, bool):
            raise ConfigError("corpusOnTmpfs", "must be a boolean")

        stability_cv = _opt_number(data.get("stabilityThresholdCV"), "stabilityThresholdCV")
        if stability_cv is not None and not 0.0 < stability_cv <= 1.0:
            raise ConfigError("stabilityThresholdCV", f"must be in (0, 1], got {stability_cv}")

        confidence = data.get("confidenceLevel", 0.95)
        confidence = _opt_number(confidence, "confidenceLevel")
        if confidence is None or not 0.0 < confidence < 1.0:
            raise ConfigError("confidenceLevel", f"must be in (0, 1), got {confidence}")

        criterion = data.get("bestVariantCriterion", "p50_roundtrip")
        if not isinstance(criterion, str) or not criterion.strip():
            raise ConfigError("bestVariantCriterion", "must be a non-empty string")

        null_test = (
            NullTestConfig.from_dict(data["nullTest"], "nullTest")
            if data.get("nullTest") is not None
            else NullTestConfig()
        )
        soak_test = (
            SoakTestConfig.from_dict(data["soakTest"], "soakTest")
            if data.get("soakTest") is not None
            else SoakTestConfig()
        )

        return BenchmarkConfig(
            rounds=rounds,
            warmup_iterations=warmup,
            seed=seed,
            sampling_interval_ms=sampling,
            crypto_profiles=crypto_profiles,
            key_specs=key_specs,
            scenarios=scenarios,
            modes=modes,
            vcpu=self.vcpu,
            result_dir=result_dir,
            corpus_on_tmpfs=corpus_on_tmpfs,
            stability_threshold_cv=stability_cv,
            confidence_level=confidence,
            best_variant_criterion=criterion,
            null_test=null_test,
            soak_test=soak_test,
        )

    # List parsers
    @staticmethod
    def _require_nonempty_list(value: Any, param: str) -> Sequence[Any]:
        if not isinstance(value, list):
            raise ConfigError(param, "must be an array")
        if not value:
            raise ConfigError(param, "must contain at least one entry")
        return value

    def _parse_crypto_profiles(self, value: Any) -> tuple[CryptoProfileConfig, ...]:
        items = self._require_nonempty_list(value, "cryptoProfiles")
        profiles = tuple(
            CryptoProfileConfig.from_dict(item, f"cryptoProfiles[{i}]")
            for i, item in enumerate(items)
        )
        seen: set[str] = set()
        for i, p in enumerate(profiles):
            if p.id in seen:
                raise ConfigError(f"cryptoProfiles[{i}].id", f"duplicate id {p.id!r}")
            seen.add(p.id)
        return profiles

    def _parse_key_specs(self, value: Any) -> tuple[KeySpec, ...]:
        items = self._require_nonempty_list(value, "keySpecs")
        return tuple(
            KeySpec.from_dict(item, f"keySpecs[{i}]") for i, item in enumerate(items)
        )

    def _parse_modes(self, value: Any) -> tuple[RunMode, ...]:
        items = self._require_nonempty_list(value, "modes")
        modes = tuple(
            _as_enum(RunMode, item, f"modes[{i}]") for i, item in enumerate(items)
        )
        return modes

    def _parse_scenarios(
        self, value: Any, known_profile_ids: frozenset[str]
    ) -> tuple[ScenarioConfig, ...]:
        items = self._require_nonempty_list(value, "scenarios")
        scenarios = tuple(
            ScenarioConfig.from_dict(
                item,
                f"scenarios[{i}]",
                vcpu=self.vcpu,
                known_profile_ids=known_profile_ids,
            )
            for i, item in enumerate(items)
        )
        seen: set[str] = set()
        for i, s in enumerate(scenarios):
            if s.id in seen:
                raise ConfigError(f"scenarios[{i}].id", f"duplicate id {s.id!r}")
            seen.add(s.id)
        return scenarios
