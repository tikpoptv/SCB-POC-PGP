"""Property-based test: Soak_Test trend detection (Property 21)."""

import math

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from harness.soak import SECONDS_PER_HOUR, latency_trend, ram_trend

# Generators
# Number of samples in the series — at least 2 so a slope is defined.
_N_SAMPLES = st.integers(min_value=2, max_value=40)
# Uniform sampling spacing in seconds (a realistic ResourceSampler interval).
_INTERVAL_SEC = st.floats(
    min_value=1.0, max_value=600.0, allow_nan=False, allow_infinity=False
)
# Positive baseline value (MB for RAM, ms for latency) at the window start.
_BASE = st.floats(
    min_value=1.0, max_value=1_000.0, allow_nan=False, allow_infinity=False
)
# Constructed slope per hour — spans negative (shrinking/improving), zero
# (flat) and positive (growing/degrading).
_SLOPE = st.floats(
    min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False
)
# Configured thresholds are positive (MB/hour for RAM, percent for latency).
_THRESHOLD = st.floats(
    min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False
)

# Slack used to skip cases that sit on the strict-comparison boundary, where a
# noise-free fit could land on either side by a floating-point hair.
_BOUNDARY_EPS = 1e-6


def _timestamps(n: int, interval_sec: float) -> list[float]:
    """Uniform timestamps in seconds, starting at 0 (so fitted_start = base)."""
    return [i * interval_sec for i in range(n)]


# Feature: pgp-encryption-benchmark-go-java, Property 21: การตรวจจับแนวโน้มใน Soak_Test
@settings(max_examples=200)
@given(n=_N_SAMPLES, interval_sec=_INTERVAL_SEC, base=_BASE, slope=_SLOPE, threshold=_THRESHOLD)
def test_ram_trend_flags_iff_slope_exceeds_threshold(n, interval_sec, base, slope, threshold):
    timestamps = _timestamps(n, interval_sec)
    # Construct a perfectly linear RAM series with the chosen slope (MB/hour).
    samples = [base + slope * (t / SECONDS_PER_HOUR) for t in timestamps]

    trend = ram_trend(
        samples, threshold_mb_per_hour=threshold, timestamps_sec=timestamps
    )

    # A series of >= 2 samples over a non-zero window is always applicable.
    assert trend.applicable is True
    assert trend.slope_mb_per_hour is not None

    assert trend.slope_mb_per_hour == _approx(slope)
    # Supporting trend data travels with the result.
    assert trend.fitted_start_mb == _approx(base)
    assert trend.fitted_end_mb == _approx(base + slope * (timestamps[-1] / SECONDS_PER_HOUR))

    # (b) The flag tracks the STRICT comparison against the threshold. Skip the
    #     razor's-edge boundary (covered exactly by the example tests).
    assume(abs(trend.slope_mb_per_hour - threshold) > _BOUNDARY_EPS * max(1.0, abs(threshold)))
    assert trend.suspected_memory_leak == (trend.slope_mb_per_hour > threshold)


# Feature: pgp-encryption-benchmark-go-java, Property 21: การตรวจจับแนวโน้มใน Soak_Test
@settings(max_examples=100)
@given(n=_N_SAMPLES, interval_sec=_INTERVAL_SEC, base=_BASE, slope=_SLOPE, threshold=_THRESHOLD)
def test_flat_or_decreasing_ram_is_never_flagged(n, interval_sec, base, slope, threshold):
    # A non-positive slope (flat or shrinking RSS) is below any positive
    non_positive_slope = -abs(slope)
    timestamps = _timestamps(n, interval_sec)
    samples = [base + non_positive_slope * (t / SECONDS_PER_HOUR) for t in timestamps]

    trend = ram_trend(
        samples, threshold_mb_per_hour=threshold, timestamps_sec=timestamps
    )
    assert trend.suspected_memory_leak is False


# Feature: pgp-encryption-benchmark-go-java, Property 21: การตรวจจับแนวโน้มใน Soak_Test
@settings(max_examples=200)
@given(n=_N_SAMPLES, interval_sec=_INTERVAL_SEC, base=_BASE, slope=_SLOPE, threshold=_THRESHOLD)
def test_latency_trend_flags_iff_degradation_exceeds_threshold(n, interval_sec, base, slope, threshold):
    timestamps = _timestamps(n, interval_sec)
    # Construct a perfectly linear latency series; base > 0 keeps the percentage
    # well-defined (fitted_start = base).
    samples = [base + slope * (t / SECONDS_PER_HOUR) for t in timestamps]

    trend = latency_trend(samples, threshold_pct=threshold, timestamps_sec=timestamps)

    assert trend.applicable is True
    assert trend.degradation_pct is not None

    # The known degradation over the window: (end - start) / start * 100.
    duration_hours = timestamps[-1] / SECONDS_PER_HOUR
    fitted_end = base + slope * duration_hours
    expected_pct = (fitted_end - base) / base * 100.0

    # (a) The recovered degradation matches the constructed degradation.
    assert trend.degradation_pct == _approx(expected_pct)
    assert trend.fitted_start_ms == _approx(base)
    assert trend.fitted_end_ms == _approx(fitted_end)

    # (b) The flag tracks the STRICT comparison against the threshold, skipping
    #     the razor's-edge boundary (covered by the example tests).
    assume(abs(trend.degradation_pct - threshold) > _BOUNDARY_EPS * max(1.0, abs(threshold)))
    assert trend.performance_degradation == (trend.degradation_pct > threshold)


# Feature: pgp-encryption-benchmark-go-java, Property 21: การตรวจจับแนวโน้มใน Soak_Test
@settings(max_examples=100)
@given(n=_N_SAMPLES, interval_sec=_INTERVAL_SEC, base=_BASE, slope=_SLOPE, threshold=_THRESHOLD)
def test_flat_or_improving_latency_is_never_flagged(n, interval_sec, base, slope, threshold):
    # A non-positive slope (flat or improving latency) yields degradation <= 0,
    non_positive_slope = -abs(slope)
    timestamps = _timestamps(n, interval_sec)
    samples = [base + non_positive_slope * (t / SECONDS_PER_HOUR) for t in timestamps]

    trend = latency_trend(samples, threshold_pct=threshold, timestamps_sec=timestamps)
    assert trend.performance_degradation is False


# Helpers
def _approx(expected: float) -> "_Approx":
    return _Approx(expected)


class _Approx:
    """Tolerant float comparison for noise-free least-squares recovery."""

    __slots__ = ("expected",)

    def __init__(self, expected: float) -> None:
        self.expected = expected

    def __eq__(self, actual: object) -> bool:  # pragma: no cover - thin shim
        if not isinstance(actual, (int, float)):
            return NotImplemented
        return math.isclose(actual, self.expected, rel_tol=1e-6, abs_tol=1e-6)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"approx({self.expected!r})"
