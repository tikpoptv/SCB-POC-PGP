"""Sample a Runner subprocess's CPU/RAM and merge Runner-reported GC stats."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

from harness.contract.models import GcStats

__all__ = [
    "ResourceSamplerError",
    "SAMPLING_INTERVAL_RANGE",
    "DEFAULT_SAMPLING_INTERVAL_MS",
    "BYTES_PER_MB",
    "GcSummary",
    "ResourceUsage",
    "ResourceSampler",
    "SamplingSession",
    "aggregate_samples",
]

# Sampling interval bounds. ConfigLoader independently enforces the same range.
SAMPLING_INTERVAL_RANGE = (10, 1000)
DEFAULT_SAMPLING_INTERVAL_MS = 100

BYTES_PER_MB = 1024 * 1024


class ResourceSamplerError(ValueError):
    """Raised for programmer errors configuring the sampler (e.g. bad interval)."""


@dataclass(frozen=True)
class GcSummary:
    """Merged garbage-collection summary reported by a Runner."""

    available: bool
    collections: int | None = None
    total_pause_ms: float | None = None
    gc_type: str | None = None
    heap_init_mb: float | None = None
    heap_max_mb: float | None = None
    unavailable_reason: str | None = None

    @classmethod
    def from_runner_gc(
        cls,
        gc: GcStats | None,
        *,
        reason_if_missing: str = "garbage collection stats not reported by runner",
    ) -> "GcSummary":
        """Merge the ``gc`` block of a RunnerOutput into a summary."""
        if gc is None:
            return cls(available=False, unavailable_reason=reason_if_missing)
        return cls(
            available=True,
            collections=gc.collections,
            total_pause_ms=gc.total_pause_ms,
            gc_type=gc.gc_type,
            heap_init_mb=gc.heap_init_mb,
            heap_max_mb=gc.heap_max_mb,
        )

    def to_dict(self) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "reason": self.unavailable_reason}
        return {
            "available": True,
            "collections": self.collections,
            "totalPauseMs": self.total_pause_ms,
            "gcType": self.gc_type,
            "heapInitMb": self.heap_init_mb,
            "heapMaxMb": self.heap_max_mb,
        }


@dataclass(frozen=True)
class ResourceUsage:
    """CPU/RAM usage of one Benchmark_Run plus the merged GC summary.

    CPU is a percent of allocated CPU in ``[0, 100]``; RAM is in MB. When
    sampling failed or was incomplete the aggregate values are ``None``,
    ``comparable`` is ``False`` and ``non_comparable_reason`` explains why.
    """

    cpu_pct_avg: float | None
    cpu_pct_max: float | None
    ram_mb_avg: float | None
    ram_mb_peak: float | None
    sample_count: int
    sampling_interval_ms: int
    allocated_cpu_cores: int
    comparable: bool
    non_comparable_reason: str | None = None
    gc: GcSummary | None = None

    def with_gc(self, gc: GcStats | None) -> "ResourceUsage":
        """Return a copy carrying the merged GC summary."""
        return ResourceUsage(
            cpu_pct_avg=self.cpu_pct_avg,
            cpu_pct_max=self.cpu_pct_max,
            ram_mb_avg=self.ram_mb_avg,
            ram_mb_peak=self.ram_mb_peak,
            sample_count=self.sample_count,
            sampling_interval_ms=self.sampling_interval_ms,
            allocated_cpu_cores=self.allocated_cpu_cores,
            comparable=self.comparable,
            non_comparable_reason=self.non_comparable_reason,
            gc=GcSummary.from_runner_gc(gc),
        )

    def to_dict(self) -> dict[str, Any]:
        """Render the per-variant resource block of the Result_Report."""
        return {
            "cpuPct": {"avg": self.cpu_pct_avg, "max": self.cpu_pct_max},
            "ramMb": {"avg": self.ram_mb_avg, "peak": self.ram_mb_peak},
            "sampleCount": self.sample_count,
            "samplingIntervalMs": self.sampling_interval_ms,
            "allocatedCpuCores": self.allocated_cpu_cores,
            "comparable": self.comparable,
            "nonComparableReason": self.non_comparable_reason,
            "gc": self.gc.to_dict() if self.gc is not None else None,
        }


def aggregate_samples(
    cpu_raw_samples: Sequence[float],
    rss_byte_samples: Sequence[int],
    *,
    allocated_cpu_cores: int,
    sampling_interval_ms: int,
    error_reason: str | None = None,
) -> ResourceUsage:
    """Aggregate raw per-process samples into a :class:`ResourceUsage`.

    Pure function: computes avg/max CPU (normalised to a percent of the
    allocated cores and clamped to ``[0, 100]``) and avg/peak RAM in MB. The run
    is non-comparable when ``error_reason`` is set or no samples were collected.
    """
    if allocated_cpu_cores < 1:
        raise ResourceSamplerError(
            f"allocated_cpu_cores must be >= 1, got {allocated_cpu_cores}"
        )

    count = min(len(cpu_raw_samples), len(rss_byte_samples))

    if error_reason is not None or count == 0:
        reason = error_reason or "no resource samples were collected"
        return ResourceUsage(
            cpu_pct_avg=None,
            cpu_pct_max=None,
            ram_mb_avg=None,
            ram_mb_peak=None,
            sample_count=count,
            sampling_interval_ms=sampling_interval_ms,
            allocated_cpu_cores=allocated_cpu_cores,
            comparable=False,
            non_comparable_reason=reason,
        )

    # Normalise raw CPU% (which spans all cores) to a percent of the allocated
    # CPU, clamped into [0, 100].
    cpu_norm = [
        max(0.0, min(100.0, raw / allocated_cpu_cores))
        for raw in cpu_raw_samples[:count]
    ]
    ram_mb = [rss / BYTES_PER_MB for rss in rss_byte_samples[:count]]

    return ResourceUsage(
        cpu_pct_avg=sum(cpu_norm) / count,
        cpu_pct_max=max(cpu_norm),
        ram_mb_avg=sum(ram_mb) / count,
        ram_mb_peak=max(ram_mb),
        sample_count=count,
        sampling_interval_ms=sampling_interval_ms,
        allocated_cpu_cores=allocated_cpu_cores,
        comparable=True,
        non_comparable_reason=None,
    )


class SamplingSession:
    """A running background sampler over a single process.

    Call :meth:`stop` (or leave the ``with`` block) to halt sampling and obtain
    the aggregated :class:`ResourceUsage`, also stored on :attr:`result`.
    """

    def __init__(
        self,
        process: Any,
        *,
        interval_ms: int,
        allocated_cpu_cores: int,
    ) -> None:
        self._process = process
        self._interval_ms = interval_ms
        self._interval_s = interval_ms / 1000.0
        self._allocated_cpu_cores = allocated_cpu_cores

        self._cpu_samples: list[float] = []
        self._rss_samples: list[int] = []
        self._error_reason: str | None = None

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.result: ResourceUsage | None = None

    def start(self) -> "SamplingSession":
        # Prime cpu_percent so the first in-loop reading reflects real usage
        # rather than the 0.0 that psutil returns on the very first call.
        try:
            self._process.cpu_percent(interval=None)
        except Exception:
            # Priming failure is not fatal; the loop will surface a real error
            # (or NoSuchProcess) on the first sample.
            pass
        self._thread = threading.Thread(
            target=self._run, name="resource-sampler", daemon=True
        )
        self._thread.start()
        return self

    def _run(self) -> None:
        import psutil

        while not self._stop_event.is_set():
            try:
                cpu = self._process.cpu_percent(interval=None)
                rss = self._process.memory_info().rss
            except psutil.NoSuchProcess:
                # The Runner finished/exited — a normal end to sampling.
                break
            except Exception as exc:  # AccessDenied, ZombieProcess, etc.
                # Sampling failure -> the run is non-comparable, but keep
                # whatever we already collected.
                self._error_reason = f"resource sampling failed: {exc!r}"
                break
            else:
                self._cpu_samples.append(float(cpu))
                self._rss_samples.append(int(rss))
            self._stop_event.wait(self._interval_s)

    def stop(self, *, join_timeout: float = 5.0) -> ResourceUsage:
        """Stop sampling and return the aggregated usage (idempotent)."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
            if self._thread.is_alive():
                # The sampling thread did not stop in time -> incomplete.
                self._error_reason = (
                    self._error_reason
                    or "resource sampling thread did not stop within timeout"
                )
            self._thread = None
        self.result = aggregate_samples(
            self._cpu_samples,
            self._rss_samples,
            allocated_cpu_cores=self._allocated_cpu_cores,
            sampling_interval_ms=self._interval_ms,
            error_reason=self._error_reason,
        )
        return self.result


class ResourceSampler:
    """Samples CPU/RAM of a Runner subprocess at a fixed interval.

    The ``interval_ms`` is supplied by the scheduler and reused for both Runners
    within a Scenario; ``allocated_cpu_cores`` is the CPU quota granted to the
    Runner, used to express CPU as a percent of the allocated CPU.
    """

    def __init__(
        self,
        *,
        interval_ms: int = DEFAULT_SAMPLING_INTERVAL_MS,
        allocated_cpu_cores: int | None = None,
    ) -> None:
        low, high = SAMPLING_INTERVAL_RANGE
        if isinstance(interval_ms, bool) or not isinstance(interval_ms, int):
            raise ResourceSamplerError(
                f"interval_ms must be an integer, got {type(interval_ms).__name__}"
            )
        if not low <= interval_ms <= high:
            raise ResourceSamplerError(
                f"interval_ms must be in [{low}, {high}], got {interval_ms}"
            )
        self.interval_ms = interval_ms

        if allocated_cpu_cores is None:
            allocated_cpu_cores = _default_cpu_cores()
        if isinstance(allocated_cpu_cores, bool) or not isinstance(allocated_cpu_cores, int):
            raise ResourceSamplerError(
                f"allocated_cpu_cores must be an integer, got {type(allocated_cpu_cores).__name__}"
            )
        if allocated_cpu_cores < 1:
            raise ResourceSamplerError(
                f"allocated_cpu_cores must be >= 1, got {allocated_cpu_cores}"
            )
        self.allocated_cpu_cores = allocated_cpu_cores

    def start(self, process: Any) -> SamplingSession:
        """Begin sampling ``process`` (a ``psutil.Process``) in the background."""
        return SamplingSession(
            process,
            interval_ms=self.interval_ms,
            allocated_cpu_cores=self.allocated_cpu_cores,
        ).start()

    @contextmanager
    def sample(self, process: Any) -> Iterator[SamplingSession]:
        """Context manager that samples ``process`` for the block's duration.

        The aggregated :class:`ResourceUsage` is available on the yielded
        session's ``result`` attribute after the block exits.
        """
        session = self.start(process)
        try:
            yield session
        finally:
            session.stop()

    @staticmethod
    def merge_gc(
        usage: ResourceUsage,
        runner_output_gc: GcStats | None,
    ) -> ResourceUsage:
        """Attach the Runner-reported GC summary to ``usage``."""
        return usage.with_gc(runner_output_gc)


def _default_cpu_cores() -> int:
    try:
        import psutil

        n = psutil.cpu_count(logical=True)
        if n:
            return int(n)
    except Exception:
        pass
    import os

    return int(os.cpu_count() or 1)
