"""StatisticsEngine — throughput & round-trip time calculations.

Pure, composable statistics functions. Conventions: time is in milliseconds
(crypto-only, excludes key load, file I/O and warm-up); 1 MB = 1,048,576 bytes;
``roundTripMs = encryptMs + decryptMs``. Aggregate throughput for parallel
batches divides total volume by the wall-clock crypto window of the batch.
When the measured time is ``<= 0`` throughput is not computed; the time value
is preserved and a machine-readable reason is attached.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from harness.contract.models import RunnerId

if TYPE_CHECKING:  # pragma: no cover - typing only
    from harness.metrics import MetricRecord

__all__ = [
    "BYTES_PER_MB",
    "NON_POSITIVE_TIME_REASON",
    "ThroughputResult",
    "AggregateThroughput",
    "round_trip_ms",
    "throughput_mb_per_sec",
    "throughput_files_per_sec",
    "aggregate_throughput",
    # Error rate
    "NOT_APPLICABLE",
    "ErrorRate",
    "error_rate",
    "error_rate_from_failures",
    "aggregate_error_rate",
    "error_rate_by_runner",
    "error_rate_by_variant",
    # Cost / energy
    "MS_PER_HOUR",
    "OPS_PER_MILLION",
    "ENERGY_UNSUPPORTED_REASON",
    "CostEnergyRecord",
    "cost_per_million_ops",
    "cost_energy_record",
]

#: 1 MB = 1,048,576 bytes.
BYTES_PER_MB: int = 1_048_576

#: Reason recorded when throughput cannot be computed because time <= 0.
NON_POSITIVE_TIME_REASON: str = "time<=0: throughput not computed; measured time preserved"


@dataclass(frozen=True)
class ThroughputResult:
    """One throughput value together with the time base it was derived from.

    Preserves the measured ``time_ms`` even when the value could not be computed.
    ``value`` is ``None`` exactly when ``reason`` is set (time was ``<= 0``);
    otherwise it holds the computed throughput in the unit named by :attr:`unit`.
    """

    value: float | None
    time_ms: float
    unit: str
    reason: str | None = None

    @property
    def computed(self) -> bool:
        """True when a throughput value was computed (time was positive)."""
        return self.value is not None

    def to_dict(self) -> dict[str, object]:
        """JSON shape for the Result_Report (keeps time + reason on skip)."""
        return {
            "value": self.value,
            "unit": self.unit,
            "timeMs": self.time_ms,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AggregateThroughput:
    """Aggregate throughput for a parallel batch (concurrency > 1).

    Both rates share the same wall-clock crypto window of the parallel batch:
    total successful bytes/files divided by that window.
    """

    mb_per_sec: ThroughputResult
    files_per_sec: ThroughputResult
    wall_clock_crypto_window_ms: float

    def to_dict(self) -> dict[str, object]:
        return {
            "mbPerSec": self.mb_per_sec.value,
            "filesPerSec": self.files_per_sec.value,
            "wallClockCryptoWindowMs": self.wall_clock_crypto_window_ms,
            "basis": "total_bytes_or_files / wall_clock_crypto_window_of_parallel_batch",
            "mbPerSecDetail": self.mb_per_sec.to_dict(),
            "filesPerSecDetail": self.files_per_sec.to_dict(),
        }


def round_trip_ms(encrypt_ms: float, decrypt_ms: float) -> float:
    """Round-trip time (ms) = encrypt time + decrypt time for the same job."""
    return encrypt_ms + decrypt_ms


def throughput_mb_per_sec(byte_count: float, time_ms: float) -> ThroughputResult:
    """Throughput in MB/sec = bytes / 1,048,576 / (time_ms / 1000).

    When ``time_ms <= 0`` the value is not computed; the time is preserved and a
    reason attached.
    """
    if time_ms <= 0:
        return ThroughputResult(
            value=None, time_ms=time_ms, unit="MB/sec", reason=NON_POSITIVE_TIME_REASON
        )
    seconds = time_ms / 1000.0
    value = (byte_count / BYTES_PER_MB) / seconds
    return ThroughputResult(value=value, time_ms=time_ms, unit="MB/sec")


def throughput_files_per_sec(file_count: float, time_ms: float) -> ThroughputResult:
    """Throughput in files/sec = successful files / (time_ms / 1000).

    When ``time_ms <= 0`` the value is not computed; the time is preserved and a
    reason attached.
    """
    if time_ms <= 0:
        return ThroughputResult(
            value=None, time_ms=time_ms, unit="files/sec", reason=NON_POSITIVE_TIME_REASON
        )
    seconds = time_ms / 1000.0
    value = file_count / seconds
    return ThroughputResult(value=value, time_ms=time_ms, unit="files/sec")


def aggregate_throughput(
    total_bytes: float,
    total_files: float,
    wall_clock_crypto_window_ms: float,
) -> AggregateThroughput:
    """Aggregate throughput for a concurrency>1 parallel batch.

    Both MB/sec and files/sec are computed against the wall-clock crypto window
    of the parallel batch (not the sum of per-operation times). The same
    ``time_ms <= 0`` guard applies: when the window is non-positive, neither rate
    is computed but the window is preserved with a reason.
    """
    return AggregateThroughput(
        mb_per_sec=throughput_mb_per_sec(total_bytes, wall_clock_crypto_window_ms),
        files_per_sec=throughput_files_per_sec(total_files, wall_clock_crypto_window_ms),
        wall_clock_crypto_window_ms=wall_clock_crypto_window_ms,
    )


# Error-rate convention: rate = (operation_failure + correctness_failure) /
# attempted, over operations attempted after warm-up (warm-up is never recorded).
# The value is a decimal in [0.0, 1.0]; when attempted == 0 the ratio is
# undefined and the sentinel NOT_APPLICABLE is reported instead of dividing by
# zero. Reported broken down by Runner and by Implementation_Variant.

#: Sentinel reported when no operations were attempted.
NOT_APPLICABLE: str = "not applicable"


@dataclass(frozen=True)
class ErrorRate:
    """Error-rate summary for one breakdown (Runner or variant).

    Carries the failed and attempted counts that produced the rate. ``rate`` is
    ``None`` when not applicable; :meth:`report_value` renders the user-facing
    value (float in ``[0.0, 1.0]`` or :data:`NOT_APPLICABLE`).
    """

    failed: int
    attempted: int

    @property
    def applicable(self) -> bool:
        """True when at least one operation was attempted."""
        return self.attempted > 0

    @property
    def rate(self) -> float | None:
        """The ratio in ``[0.0, 1.0]``, or ``None`` when not applicable."""
        if self.attempted <= 0:
            return None
        return self.failed / self.attempted

    def report_value(self) -> float | str:
        """The value to place in the report: a float, or :data:`NOT_APPLICABLE`."""
        r = self.rate
        return NOT_APPLICABLE if r is None else r

    def to_dict(self) -> dict[str, object]:
        """Render the ``errorRate``/``failedOps``/``attemptedOps`` block."""
        return {
            "errorRate": self.report_value(),
            "failedOps": self.failed,
            "attemptedOps": self.attempted,
        }


def _validate_error_counts(failed: int, attempted: int) -> None:
    if failed < 0:
        raise ValueError(f"failed operations must be >= 0, got {failed}")
    if attempted < 0:
        raise ValueError(f"attempted operations must be >= 0, got {attempted}")
    if failed > attempted:
        raise ValueError(
            f"failed operations ({failed}) cannot exceed attempted ({attempted})"
        )


def error_rate(failed_operations: int, attempted_operations: int) -> float | str:
    """Compute the error rate ``failed / attempted``.

    Returns a decimal in ``[0.0, 1.0]`` when ``attempted_operations > 0``, or the
    :data:`NOT_APPLICABLE` sentinel when ``attempted_operations == 0`` rather
    than dividing by zero. ``failed_operations`` is the combined count of
    operation and correctness failures. Raises ``ValueError`` for negative
    counts or ``failed > attempted``.
    """
    _validate_error_counts(failed_operations, attempted_operations)
    if attempted_operations == 0:
        return NOT_APPLICABLE
    return failed_operations / attempted_operations


def error_rate_from_failures(
    operation_failures: int,
    correctness_failures: int,
    attempted_operations: int,
) -> float | str:
    """Error rate counting both failure kinds.

    The numerator is ``operation_failures + correctness_failures``. Returns a
    float in ``[0.0, 1.0]`` or :data:`NOT_APPLICABLE` when
    ``attempted_operations == 0``.
    """
    if operation_failures < 0:
        raise ValueError(f"operation_failures must be >= 0, got {operation_failures}")
    if correctness_failures < 0:
        raise ValueError(
            f"correctness_failures must be >= 0, got {correctness_failures}"
        )
    return error_rate(operation_failures + correctness_failures, attempted_operations)


def aggregate_error_rate(records: Iterable["MetricRecord"]) -> ErrorRate:
    """Sum failed/attempted across ``records`` into one :class:`ErrorRate`.

    Attempted operations exclude skipped files and warm-up. An empty collection
    — or one with only skipped files — yields ``attempted == 0`` and therefore a
    not-applicable rate.
    """
    failed = 0
    attempted = 0
    for rec in records:
        failed += rec.failed_operations
        attempted += rec.attempted_operations
    return ErrorRate(failed=failed, attempted=attempted)


def error_rate_by_runner(
    records: Iterable["MetricRecord"],
) -> dict[RunnerId, ErrorRate]:
    """Error rate broken down per Runner.

    Groups the Metric_Records by ``runner_id`` and aggregates each group. Runners
    with only skipped operations still appear, reporting a not-applicable rate.
    """
    grouped: dict[RunnerId, list["MetricRecord"]] = defaultdict(list)
    for rec in records:
        grouped[rec.runner_id].append(rec)
    return {runner: aggregate_error_rate(group) for runner, group in grouped.items()}


def error_rate_by_variant(
    records: Iterable["MetricRecord"],
) -> dict[str, ErrorRate]:
    """Error rate broken down per Implementation_Variant.

    Groups the Metric_Records by ``variant_id`` and aggregates each group.
    """
    grouped: dict[str, list["MetricRecord"]] = defaultdict(list)
    for rec in records:
        grouped[rec.variant_id].append(rec)
    return {variant: aggregate_error_rate(group) for variant, group in grouped.items()}


# Cost per 1 million operations is deterministic in the mean per-op time and the
# vCPU cost rate:
#     hours_per_op = mean_time_ms / 1000 / 3600
#     cost_per_op  = hours_per_op * vcpus * vcpu_rate_per_hour
#     cost_per_1M  = cost_per_op * 1_000_000
# The result is non-negative and proportional to both the mean time and rate.
# Energy (joulesPerOp) is recorded only where the environment supports it;
# otherwise the value is None with a reason. Binary/image size and idle RAM are
# recorded per Runner when available, None otherwise.

#: Milliseconds per hour — converts a per-op ms time into vCPU·hours.
MS_PER_HOUR: int = 3_600_000

#: Operation count the cost figure is normalised to.
OPS_PER_MILLION: int = 1_000_000

#: Reason recorded when ``joulesPerOp`` is absent because the environment does
#: not support energy measurement.
ENERGY_UNSUPPORTED_REASON: str = "energy measurement not supported by environment"


def cost_per_million_ops(
    mean_time_ms: float,
    vcpu_rate_per_hour: float,
    vcpus: float = 1.0,
) -> float:
    """Cost to run 1 million operations, billed by vCPU time.

    Deterministic function of the mean per-operation time and the vCPU cost
    rate::

        cost = (mean_time_ms / 1000 / 3600) * vcpus * vcpu_rate_per_hour * 1_000_000

    The result is proportional to both ``mean_time_ms`` and ``vcpu_rate_per_hour``
    and is always non-negative for non-negative inputs. Raises ``ValueError`` for
    negative inputs.
    """
    if mean_time_ms < 0:
        raise ValueError(f"mean_time_ms must be >= 0, got {mean_time_ms}")
    if vcpu_rate_per_hour < 0:
        raise ValueError(f"vcpu_rate_per_hour must be >= 0, got {vcpu_rate_per_hour}")
    if vcpus < 0:
        raise ValueError(f"vcpus must be >= 0, got {vcpus}")

    hours_per_op = (mean_time_ms / 1000.0) / 3600.0
    cost = hours_per_op * vcpus * vcpu_rate_per_hour * OPS_PER_MILLION
    # Guard against tiny negative values from floating-point noise.
    return cost if cost > 0.0 else 0.0


@dataclass(frozen=True)
class CostEnergyRecord:
    """Per-Runner cost / energy / deploy-size summary.

    ``cost_per_million_ops`` is always present. ``joules_per_op`` is ``None``
    when the environment does not support energy measurement, with the reason in
    :attr:`energy_reason`. ``binary_size_mb`` and ``idle_ram_mb`` are in MB and
    ``None`` when unavailable.
    """

    cost_per_million_ops: float
    joules_per_op: float | None
    binary_size_mb: float | None
    idle_ram_mb: float | None
    energy_reason: str | None = None

    @property
    def energy_supported(self) -> bool:
        """True when an energy figure (joulesPerOp) was recorded."""
        return self.joules_per_op is not None

    def to_dict(self) -> dict[str, object]:
        """Render the per-runner ``costEnergy`` JSON shape."""
        return {
            "joulesPerOp": self.joules_per_op,
            "costPerMillionOps": self.cost_per_million_ops,
            "binarySizeMb": self.binary_size_mb,
            "idleRamMb": self.idle_ram_mb,
            "energyReason": self.energy_reason,
        }


def cost_energy_record(
    mean_time_ms: float,
    vcpu_rate_per_hour: float,
    *,
    vcpus: float = 1.0,
    joules_per_op: float | None = None,
    binary_size_mb: float | None = None,
    idle_ram_mb: float | None = None,
    energy_reason: str | None = None,
) -> CostEnergyRecord:
    """Build a :class:`CostEnergyRecord` for one Runner.

    ``cost_per_million_ops`` is computed deterministically from ``mean_time_ms``,
    ``vcpu_rate_per_hour`` and ``vcpus`` via :func:`cost_per_million_ops`.

    Energy (``joules_per_op``) is optional: pass the measured joules-per-op when
    the environment supports energy measurement. When it is ``None`` a reason is
    recorded; when supplied the reason is cleared.
    """
    if joules_per_op is None:
        reason = energy_reason or ENERGY_UNSUPPORTED_REASON
    else:
        if joules_per_op < 0:
            raise ValueError(f"joules_per_op must be >= 0, got {joules_per_op}")
        reason = None

    return CostEnergyRecord(
        cost_per_million_ops=cost_per_million_ops(
            mean_time_ms, vcpu_rate_per_hour, vcpus
        ),
        joules_per_op=joules_per_op,
        binary_size_mb=binary_size_mb,
        idle_ram_mb=idle_ram_mb,
        energy_reason=reason,
    )
