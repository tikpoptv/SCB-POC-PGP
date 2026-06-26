"""Soak_Test trend detection: detect memory leaks and latency degradation.

Fits a straight line (ordinary least-squares) of value vs time to two
time-series per Runner — RAM usage (MB) and operation latency (ms):

* RAM — the fitted slope in MB/hour is the sustained growth rate; a slope that
  exceeds ``ramLeakThresholdMbPerHour`` flags ``suspectedMemoryLeak``.
* Latency — the fitted line is projected across the window; a percentage
  increase from start to end that exceeds ``latencyDegradationThresholdPct``
  flags ``performanceDegradation``.

"Exceeds" is strict (``> threshold``): a value exactly equal is not flagged.
These functions are pure (no I/O, no mutation of inputs).

Each series is sampled over time. Callers pass the sample times either as an
explicit ``timestamps_sec`` sequence or as a uniform ``interval_ms``; exactly
one must be supplied. Slope is always reported per hour. With fewer than two
distinct points in time the trend is not applicable and nothing is flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

__all__ = [
    "SECONDS_PER_HOUR",
    "RAM_UNIT",
    "LATENCY_UNIT",
    "RamTrend",
    "LatencyTrend",
    "SoakTrends",
    "ram_trend",
    "latency_trend",
    "soak_trends",
]

#: Seconds in one hour — slopes are reported per hour.
SECONDS_PER_HOUR: float = 3600.0

#: RAM is reported in MB.
RAM_UNIT: str = "MB"

#: Latency is reported in milliseconds.
LATENCY_UNIT: str = "ms"

# Reasons attached to a non-flagged / not-applicable trend so the report can
# explain why no judgement was made (rather than silently reporting False).
_REASON_TOO_FEW_SAMPLES = "fewer than 2 samples: trend slope is undefined"
_REASON_ZERO_WINDOW = "all samples share the same timestamp: zero-length window"
_REASON_LENGTH_MISMATCH = "timestamps and values must have the same length"
_REASON_NO_RAM_THRESHOLD = "ramLeakThresholdMbPerHour not configured: cannot flag"
_REASON_NO_LATENCY_THRESHOLD = (
    "latencyDegradationThresholdPct not configured: cannot flag"
)
_REASON_NONPOSITIVE_BASELINE = (
    "fitted latency at window start <= 0: degradation percentage undefined"
)


def _hours_axis(
    n: int,
    timestamps_sec: Sequence[float] | None,
    interval_ms: float | None,
) -> np.ndarray | None:
    """Build the time axis (in **hours**) for ``n`` samples.

    Exactly one of ``timestamps_sec`` / ``interval_ms`` must be supplied. Returns
    ``None`` when the axis cannot be built (length mismatch). The returned array
    starts at 0 so intercept = fitted value at the window start.
    """
    if timestamps_sec is not None and interval_ms is not None:
        raise ValueError("pass exactly one of timestamps_sec or interval_ms, not both")
    if timestamps_sec is None and interval_ms is None:
        raise ValueError("pass exactly one of timestamps_sec or interval_ms")

    if timestamps_sec is not None:
        ts = np.asarray(timestamps_sec, dtype=float)
        if ts.size != n:
            return None
        hours = (ts - ts[0]) / SECONDS_PER_HOUR
        return hours

    if interval_ms <= 0:
        raise ValueError(f"interval_ms must be > 0, got {interval_ms}")
    # Uniform sampling: sample i occurs at i * interval.
    step_hours = (interval_ms / 1000.0) / SECONDS_PER_HOUR
    return np.arange(n, dtype=float) * step_hours


def _fit_line(x_hours: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Ordinary least-squares fit; returns ``(slope_per_hour, intercept)``."""
    slope, intercept = np.polyfit(x_hours, y, 1)
    return float(slope), float(intercept)


@dataclass(frozen=True)
class RamTrend:
    """RAM growth trend over a Soak_Test for one Runner.

    ``slope_mb_per_hour`` is the sustained growth rate from a least-squares fit
    of RAM (MB) vs time. ``suspected_memory_leak`` is ``True`` exactly when the
    trend was computable, a threshold was configured, and the slope exceeds that
    threshold. The fitted endpoints and duration travel alongside as supporting
    trend data.
    """

    applicable: bool
    suspected_memory_leak: bool
    slope_mb_per_hour: float | None
    threshold_mb_per_hour: float | None
    intercept_mb: float | None
    fitted_start_mb: float | None
    fitted_end_mb: float | None
    sample_count: int
    duration_hours: float | None
    reason: str | None = None
    unit: str = RAM_UNIT

    def to_dict(self) -> dict[str, Any]:
        """Render the RAM portion of the ``softTrends`` block."""
        return {
            "applicable": self.applicable,
            "suspectedMemoryLeak": self.suspected_memory_leak,
            "slopeMbPerHour": self.slope_mb_per_hour,
            "thresholdMbPerHour": self.threshold_mb_per_hour,
            "interceptMb": self.intercept_mb,
            "fittedStartMb": self.fitted_start_mb,
            "fittedEndMb": self.fitted_end_mb,
            "sampleCount": self.sample_count,
            "durationHours": self.duration_hours,
            "reason": self.reason,
            "unit": self.unit,
        }


def ram_trend(
    ram_mb_samples: Sequence[float] | None,
    *,
    threshold_mb_per_hour: float | None,
    timestamps_sec: Sequence[float] | None = None,
    interval_ms: float | None = None,
) -> RamTrend:
    """Detect a suspected memory leak from a RAM time-series.

    Fits a straight line to ``ram_mb_samples`` (MB) over time and reports the
    slope in MB/hour. When the slope exceeds ``threshold_mb_per_hour`` the result
    is flagged ``suspected_memory_leak`` with supporting trend data.

    Supply the time base as either ``timestamps_sec`` or a uniform
    ``interval_ms`` — exactly one. With fewer than two samples, a zero-length
    window, or a length mismatch the result is not-applicable. When
    ``threshold_mb_per_hour`` is ``None`` the slope is reported but not flagged.
    """
    samples = list(ram_mb_samples or ())
    n = len(samples)

    if n < 2:
        return RamTrend(
            applicable=False,
            suspected_memory_leak=False,
            slope_mb_per_hour=None,
            threshold_mb_per_hour=threshold_mb_per_hour,
            intercept_mb=None,
            fitted_start_mb=None,
            fitted_end_mb=None,
            sample_count=n,
            duration_hours=None,
            reason=_REASON_TOO_FEW_SAMPLES,
        )

    x_hours = _hours_axis(n, timestamps_sec, interval_ms)
    if x_hours is None:
        return RamTrend(
            applicable=False,
            suspected_memory_leak=False,
            slope_mb_per_hour=None,
            threshold_mb_per_hour=threshold_mb_per_hour,
            intercept_mb=None,
            fitted_start_mb=None,
            fitted_end_mb=None,
            sample_count=n,
            duration_hours=None,
            reason=_REASON_LENGTH_MISMATCH,
        )

    duration_hours = float(x_hours[-1] - x_hours[0])
    if duration_hours <= 0.0:
        return RamTrend(
            applicable=False,
            suspected_memory_leak=False,
            slope_mb_per_hour=None,
            threshold_mb_per_hour=threshold_mb_per_hour,
            intercept_mb=None,
            fitted_start_mb=None,
            fitted_end_mb=None,
            sample_count=n,
            duration_hours=duration_hours,
            reason=_REASON_ZERO_WINDOW,
        )

    y = np.asarray(samples, dtype=float)
    slope, intercept = _fit_line(x_hours, y)
    fitted_start = intercept + slope * float(x_hours[0])
    fitted_end = intercept + slope * float(x_hours[-1])

    if threshold_mb_per_hour is None:
        return RamTrend(
            applicable=True,
            suspected_memory_leak=False,
            slope_mb_per_hour=slope,
            threshold_mb_per_hour=None,
            intercept_mb=intercept,
            fitted_start_mb=fitted_start,
            fitted_end_mb=fitted_end,
            sample_count=n,
            duration_hours=duration_hours,
            reason=_REASON_NO_RAM_THRESHOLD,
        )

    # "Exceeds" is strict: equal to the threshold is NOT a leak.
    flagged = slope > threshold_mb_per_hour
    return RamTrend(
        applicable=True,
        suspected_memory_leak=flagged,
        slope_mb_per_hour=slope,
        threshold_mb_per_hour=threshold_mb_per_hour,
        intercept_mb=intercept,
        fitted_start_mb=fitted_start,
        fitted_end_mb=fitted_end,
        sample_count=n,
        duration_hours=duration_hours,
        reason=None,
    )


@dataclass(frozen=True)
class LatencyTrend:
    """Latency degradation trend over a Soak_Test for one Runner.

    The fitted line is projected across the window; ``degradation_pct`` is the
    percentage increase from the fitted value at the window start to the fitted
    value at the window end (positive = getting slower). ``performance_degradation``
    is ``True`` exactly when the trend was computable, a threshold was
    configured, and ``degradation_pct`` exceeds that threshold.
    """

    applicable: bool
    performance_degradation: bool
    degradation_pct: float | None
    threshold_pct: float | None
    slope_ms_per_hour: float | None
    intercept_ms: float | None
    fitted_start_ms: float | None
    fitted_end_ms: float | None
    sample_count: int
    duration_hours: float | None
    reason: str | None = None
    unit: str = LATENCY_UNIT

    def to_dict(self) -> dict[str, Any]:
        """Render the latency portion of the ``softTrends`` block."""
        return {
            "applicable": self.applicable,
            "performanceDegradation": self.performance_degradation,
            "degradationPct": self.degradation_pct,
            "thresholdPct": self.threshold_pct,
            "slopeMsPerHour": self.slope_ms_per_hour,
            "interceptMs": self.intercept_ms,
            "fittedStartMs": self.fitted_start_ms,
            "fittedEndMs": self.fitted_end_ms,
            "sampleCount": self.sample_count,
            "durationHours": self.duration_hours,
            "reason": self.reason,
            "unit": self.unit,
        }


def latency_trend(
    latency_ms_samples: Sequence[float] | None,
    *,
    threshold_pct: float | None,
    timestamps_sec: Sequence[float] | None = None,
    interval_ms: float | None = None,
) -> LatencyTrend:
    """Detect performance degradation from a latency time-series.

    Fits a straight line to ``latency_ms_samples`` (ms) over time, projects it
    across the window, and reports ``degradation_pct`` — the percentage increase
    from the fitted value at the window start to the fitted value at the window
    end. When ``degradation_pct`` exceeds ``threshold_pct`` the result is flagged
    ``performance_degradation`` with supporting trend data.

    Supply the time base as either ``timestamps_sec`` or a uniform
    ``interval_ms`` — exactly one. With fewer than two samples, a zero-length
    window, or a length mismatch the result is not-applicable. When the fitted
    latency at the window start is ``<= 0`` the percentage is undefined and the
    result is not flagged. When ``threshold_pct`` is ``None`` the trend is
    reported but not flagged.
    """
    samples = list(latency_ms_samples or ())
    n = len(samples)

    def _not_applicable(reason: str, duration: float | None = None) -> LatencyTrend:
        return LatencyTrend(
            applicable=False,
            performance_degradation=False,
            degradation_pct=None,
            threshold_pct=threshold_pct,
            slope_ms_per_hour=None,
            intercept_ms=None,
            fitted_start_ms=None,
            fitted_end_ms=None,
            sample_count=n,
            duration_hours=duration,
            reason=reason,
        )

    if n < 2:
        return _not_applicable(_REASON_TOO_FEW_SAMPLES)

    x_hours = _hours_axis(n, timestamps_sec, interval_ms)
    if x_hours is None:
        return _not_applicable(_REASON_LENGTH_MISMATCH)

    duration_hours = float(x_hours[-1] - x_hours[0])
    if duration_hours <= 0.0:
        return _not_applicable(_REASON_ZERO_WINDOW, duration_hours)

    y = np.asarray(samples, dtype=float)
    slope, intercept = _fit_line(x_hours, y)
    fitted_start = intercept + slope * float(x_hours[0])
    fitted_end = intercept + slope * float(x_hours[-1])

    if fitted_start <= 0.0:
        # Percentage change is undefined against a non-positive baseline.
        return LatencyTrend(
            applicable=True,
            performance_degradation=False,
            degradation_pct=None,
            threshold_pct=threshold_pct,
            slope_ms_per_hour=slope,
            intercept_ms=intercept,
            fitted_start_ms=fitted_start,
            fitted_end_ms=fitted_end,
            sample_count=n,
            duration_hours=duration_hours,
            reason=_REASON_NONPOSITIVE_BASELINE,
        )

    degradation_pct = (fitted_end - fitted_start) / fitted_start * 100.0

    if threshold_pct is None:
        return LatencyTrend(
            applicable=True,
            performance_degradation=False,
            degradation_pct=degradation_pct,
            threshold_pct=None,
            slope_ms_per_hour=slope,
            intercept_ms=intercept,
            fitted_start_ms=fitted_start,
            fitted_end_ms=fitted_end,
            sample_count=n,
            duration_hours=duration_hours,
            reason=_REASON_NO_LATENCY_THRESHOLD,
        )

    # "Exceeds" is strict: equal to the threshold is NOT degradation.
    flagged = degradation_pct > threshold_pct
    return LatencyTrend(
        applicable=True,
        performance_degradation=flagged,
        degradation_pct=degradation_pct,
        threshold_pct=threshold_pct,
        slope_ms_per_hour=slope,
        intercept_ms=intercept,
        fitted_start_ms=fitted_start,
        fitted_end_ms=fitted_end,
        sample_count=n,
        duration_hours=duration_hours,
        reason=None,
    )


@dataclass(frozen=True)
class SoakTrends:
    """The ``softTrends`` block for one Runner: RAM + latency trends."""

    ram: RamTrend
    latency: LatencyTrend

    @property
    def suspected_memory_leak(self) -> bool:
        return self.ram.suspected_memory_leak

    @property
    def performance_degradation(self) -> bool:
        return self.latency.performance_degradation

    def to_dict(self) -> dict[str, Any]:
        """Render the ``softTrends`` block."""
        return {
            "ramTrend": self.ram.to_dict(),
            "latencyTrend": self.latency.to_dict(),
            "suspectedMemoryLeak": self.suspected_memory_leak,
            "performanceDegradation": self.performance_degradation,
        }


def soak_trends(
    ram_mb_samples: Sequence[float] | None,
    latency_ms_samples: Sequence[float] | None,
    *,
    ram_threshold_mb_per_hour: float | None,
    latency_threshold_pct: float | None,
    ram_timestamps_sec: Sequence[float] | None = None,
    latency_timestamps_sec: Sequence[float] | None = None,
    interval_ms: float | None = None,
) -> SoakTrends:
    """Compute both Soak_Test trends for one Runner.

    Convenience wrapper over :func:`ram_trend` and :func:`latency_trend`. The RAM
    and latency series may carry their own timestamps; when neither is supplied a
    shared uniform ``interval_ms`` is used for both.
    """
    ram = ram_trend(
        ram_mb_samples,
        threshold_mb_per_hour=ram_threshold_mb_per_hour,
        timestamps_sec=ram_timestamps_sec,
        interval_ms=None if ram_timestamps_sec is not None else interval_ms,
    )
    latency = latency_trend(
        latency_ms_samples,
        threshold_pct=latency_threshold_pct,
        timestamps_sec=latency_timestamps_sec,
        interval_ms=None if latency_timestamps_sec is not None else interval_ms,
    )
    return SoakTrends(ram=ram, latency=latency)
