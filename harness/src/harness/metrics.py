"""Metrics Collector: combine a Runner's output with resource samples into a Metric_Record.

Retains every raw per-operation sample verbatim; statistics (percentiles,
throughput, error rates) are computed later by the StatisticsEngine, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from harness.contract.models import (
    FailureType,
    GcStats,
    Mode,
    OperationSample,
    OutputEncoding,
    RunnerId,
    RunnerOutput,
)

__all__ = [
    "ResourceUsage",
    "ResourceAggregate",
    "MetricRecord",
    "MetricsCollector",
]


@runtime_checkable
class ResourceAggregate(Protocol):
    """Minimal interface the Metrics Collector accepts for CPU/RAM input.

    Any duck-typed object exposing these attributes is accepted (see
    :meth:`ResourceUsage.from_aggregate`):

    * ``cpu_avg_pct`` / ``cpu_max_pct`` — average and peak CPU percent, 0–100;
      ``None`` when not measured.
    * ``ram_avg_mb`` / ``ram_peak_mb`` — average and peak resident memory in MB;
      ``None`` when not measured.
    * ``comparable`` — ``False`` when CPU/RAM sampling failed or was incomplete.
    * ``non_comparable_reason`` — human-readable cause when not comparable.
    """

    cpu_avg_pct: float | None
    cpu_max_pct: float | None
    ram_avg_mb: float | None
    ram_peak_mb: float | None
    comparable: bool
    non_comparable_reason: str | None


@dataclass(frozen=True)
class ResourceUsage:
    """CPU/RAM aggregate for one Benchmark_Run.

    Fields are optional so a partial/failed sampling result can still be carried
    through with :attr:`comparable` set to ``False`` and a reason.
    """

    cpu_avg_pct: float | None = None
    cpu_max_pct: float | None = None
    ram_avg_mb: float | None = None
    ram_peak_mb: float | None = None
    comparable: bool = True
    non_comparable_reason: str | None = None
    sampling_interval_ms: int | None = None
    sample_count: int | None = None

    @classmethod
    def from_aggregate(cls, agg: ResourceAggregate) -> "ResourceUsage":
        """Adapt any object satisfying :class:`ResourceAggregate` to this type."""
        if isinstance(agg, cls):
            return agg
        return cls(
            cpu_avg_pct=getattr(agg, "cpu_avg_pct", None),
            cpu_max_pct=getattr(agg, "cpu_max_pct", None),
            ram_avg_mb=getattr(agg, "ram_avg_mb", None),
            ram_peak_mb=getattr(agg, "ram_peak_mb", None),
            comparable=bool(getattr(agg, "comparable", True)),
            non_comparable_reason=getattr(agg, "non_comparable_reason", None),
            sampling_interval_ms=getattr(agg, "sampling_interval_ms", None),
            sample_count=getattr(agg, "sample_count", None),
        )

    def cpu_to_dict(self) -> dict[str, Any]:
        """Render the ``cpuPct`` block."""
        return {"avg": self.cpu_avg_pct, "max": self.cpu_max_pct}

    def ram_to_dict(self) -> dict[str, Any]:
        """Render the ``ramMb`` block."""
        return {"avg": self.ram_avg_mb, "peak": self.ram_peak_mb}


def _operation_to_dict(op: OperationSample) -> dict[str, Any]:
    """Serialise one raw per-operation sample back to its JSON shape."""
    return {
        "fileName": op.file_name,
        "fileType": op.file_type,
        "originalBytes": op.original_bytes,
        "ciphertextBytes": op.ciphertext_bytes,
        "skipped": op.skipped,
        "skipReason": op.skip_reason,
        "encryptMs": op.encrypt_ms,
        "decryptMs": op.decrypt_ms,
        "asymEncryptMs": op.asym_encrypt_ms,
        "asymDecryptMs": op.asym_decrypt_ms,
        "symEncryptMs": op.sym_encrypt_ms,
        "symDecryptMs": op.sym_decrypt_ms,
        "roundTripOk": op.round_trip_ok,
        "failureType": op.failure_type.value if op.failure_type is not None else None,
        "outputFileName": op.output_file_name,
    }


def _gc_to_dict(gc: GcStats) -> dict[str, Any]:
    """Serialise the GC stats the Runner reported."""
    return {
        "collections": gc.collections,
        "totalPauseMs": gc.total_pause_ms,
        "gcType": gc.gc_type,
        "heapInitMb": gc.heap_init_mb,
        "heapMaxMb": gc.heap_max_mb,
    }


@dataclass(frozen=True)
class MetricRecord:
    """One Benchmark_Run's combined metrics.

    Combines a single :class:`RunnerOutput` (with its retained raw per-operation
    samples and GC stats) with the externally-sampled CPU/RAM aggregate and any
    accumulated non-comparable reasons. JSON-serialisable via :meth:`to_dict`.
    """

    # Identifiers / fairness context (carried through from RunnerOutput).
    runner_id: RunnerId
    variant_id: str
    scenario_id: str
    crypto_profile_id: str
    mode: Mode
    concurrency: int
    output_encoding: OutputEncoding
    hardware_accel: bool

    # Inputs actually seen by the Runner (fairness audit).
    key_set_checksum_seen: str
    corpus_checksum_seen: str

    # Raw per-operation samples — every sample retained.
    operations: tuple[OperationSample, ...]

    # GC stats reported by the Runner; None when unavailable.
    gc: GcStats | None = None

    # Cold-start supplementary input; kept raw, not merged here.
    process_startup_ms: float | None = None

    # Externally-sampled CPU/RAM aggregate; None when absent.
    resource: ResourceUsage | None = None

    # Pass-through note from the Runner about resource sampling.
    resource_samples_note: str | None = None

    # Non-comparable reasons accumulated for this run.
    non_comparable_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def comparable(self) -> bool:
        """True when no non-comparable reason applies to this run."""
        return not self.all_non_comparable_reasons()

    def all_non_comparable_reasons(self) -> tuple[str, ...]:
        """Every non-comparable reason, including the resource sampler's."""
        reasons = list(self.non_comparable_reasons)
        if self.resource is not None and not self.resource.comparable:
            reason = self.resource.non_comparable_reason or "resource sampling not comparable"
            if reason not in reasons:
                reasons.append(reason)
        return tuple(reasons)

    # Lightweight raw-value accessors for the StatisticsEngine (no aggregation here).
    @property
    def measured_operations(self) -> tuple[OperationSample, ...]:
        """Operations that were actually attempted (not skipped)."""
        return tuple(op for op in self.operations if not op.skipped)

    def encrypt_samples_ms(self) -> list[float]:
        """Per-operation encrypt times (ms) for non-skipped ops."""
        return [
            op.encrypt_ms
            for op in self.operations
            if not op.skipped and op.encrypt_ms is not None
        ]

    def decrypt_samples_ms(self) -> list[float]:
        """Per-operation decrypt times (ms) for non-skipped ops."""
        return [
            op.decrypt_ms
            for op in self.operations
            if not op.skipped and op.decrypt_ms is not None
        ]

    @property
    def skipped_files(self) -> int:
        """Count of skipped files (.ctrl/.ctl/unsupported)."""
        return sum(1 for op in self.operations if op.skipped)

    @property
    def attempted_operations(self) -> int:
        """Count of attempted (non-skipped) operations."""
        return len(self.measured_operations)

    @property
    def operation_failures(self) -> int:
        """Count of operation failures."""
        return sum(
            1 for op in self.measured_operations if op.failure_type is FailureType.OPERATION_FAILURE
        )

    @property
    def correctness_failures(self) -> int:
        """Count of correctness failures (round-trip mismatch)."""
        return sum(
            1
            for op in self.measured_operations
            if op.failure_type is FailureType.CORRECTNESS_FAILURE
            or (op.failure_type is None and not op.round_trip_ok)
        )

    @property
    def failed_operations(self) -> int:
        """Total failed operations = operation + correctness failures."""
        return self.operation_failures + self.correctness_failures

    def to_dict(self) -> dict[str, Any]:
        """Render the JSON shape used in ``results.json`` (raw samples retained)."""
        reasons = self.all_non_comparable_reasons()
        return {
            "runnerId": self.runner_id.value,
            "variantId": self.variant_id,
            "scenarioId": self.scenario_id,
            "cryptoProfileId": self.crypto_profile_id,
            "mode": self.mode.value,
            "concurrency": self.concurrency,
            "outputEncoding": self.output_encoding.value,
            "hardwareAccel": self.hardware_accel,
            "keySetChecksumSeen": self.key_set_checksum_seen,
            "corpusChecksumSeen": self.corpus_checksum_seen,
            "comparable": not reasons,
            "nonComparableReasons": list(reasons),
            "cpuPct": self.resource.cpu_to_dict() if self.resource is not None else None,
            "ramMb": self.resource.ram_to_dict() if self.resource is not None else None,
            "gc": _gc_to_dict(self.gc) if self.gc is not None else None,
            "processStartupMs": self.process_startup_ms,
            "resourceSamplesNote": self.resource_samples_note,
            "skippedFiles": self.skipped_files,
            "attemptedOps": self.attempted_operations,
            "failedOps": self.failed_operations,
            "operationFailures": self.operation_failures,
            "correctnessFailures": self.correctness_failures,
            # Raw per-operation samples retained verbatim for audit.
            "operations": [_operation_to_dict(op) for op in self.operations],
        }


class MetricsCollector:
    """Combine RunnerOutput + CPU/RAM samples + GC stats into a Metric_Record.

    Stateless: :meth:`collect` builds one :class:`MetricRecord` per
    Benchmark_Run, folding the externally-sampled CPU/RAM aggregate and any
    non-comparable reasons into the data already on the :class:`RunnerOutput`.
    """

    def collect(
        self,
        runner_output: RunnerOutput,
        resource: ResourceAggregate | None = None,
        *,
        non_comparable_reasons: tuple[str, ...] | list[str] = (),
    ) -> MetricRecord:
        """Build the Metric_Record for one Benchmark_Run."""
        usage = None if resource is None else ResourceUsage.from_aggregate(resource)
        return MetricRecord(
            runner_id=runner_output.runner_id,
            variant_id=runner_output.variant_id,
            scenario_id=runner_output.scenario_id,
            crypto_profile_id=runner_output.crypto_profile_id,
            mode=runner_output.mode,
            concurrency=runner_output.concurrency,
            output_encoding=runner_output.output_encoding,
            hardware_accel=runner_output.hardware_accel,
            key_set_checksum_seen=runner_output.key_set_checksum_seen,
            corpus_checksum_seen=runner_output.corpus_checksum_seen,
            operations=runner_output.operations,
            gc=runner_output.gc,
            process_startup_ms=runner_output.process_startup_ms,
            resource=usage,
            resource_samples_note=runner_output.resource_samples_note,
            non_comparable_reasons=tuple(non_comparable_reasons),
        )
