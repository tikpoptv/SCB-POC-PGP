"""Unit tests for Soak_Test trend detection (task 8.20)."""

import pytest

from harness.soak import (
    LATENCY_UNIT,
    RAM_UNIT,
    SECONDS_PER_HOUR,
    LatencyTrend,
    RamTrend,
    SoakTrends,
    latency_trend,
    ram_trend,
    soak_trends,
)


def test_flat_ram_series_not_flagged():
    # Constant RAM over an hour -> slope ~0 -> no leak.
    samples = [100.0] * 13  # 13 samples, 5-minute spacing -> 1 hour window
    timestamps = [i * 300.0 for i in range(13)]
    trend = ram_trend(samples, threshold_mb_per_hour=50.0, timestamps_sec=timestamps)
    assert isinstance(trend, RamTrend)
    assert trend.applicable is True
    assert trend.suspected_memory_leak is False
    assert trend.slope_mb_per_hour == pytest.approx(0.0, abs=1e-9)
    assert trend.unit == RAM_UNIT


def test_steep_upward_ram_series_flags_leak():
    # RAM climbs 100 MB over one hour -> 100 MB/hour >> 50 MB/hour threshold.
    timestamps = [i * 300.0 for i in range(13)]  # 0..3600s
    samples = [100.0 + 100.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = ram_trend(samples, threshold_mb_per_hour=50.0, timestamps_sec=timestamps)
    assert trend.applicable is True
    assert trend.suspected_memory_leak is True
    assert trend.slope_mb_per_hour == pytest.approx(100.0, rel=1e-6)
    assert trend.fitted_start_mb == pytest.approx(100.0, rel=1e-6)
    assert trend.fitted_end_mb == pytest.approx(200.0, rel=1e-6)
    assert trend.duration_hours == pytest.approx(1.0, rel=1e-9)


def test_decreasing_ram_series_not_flagged():
    # Shrinking RSS -> negative slope, well below a positive threshold.
    timestamps = [i * 300.0 for i in range(13)]
    samples = [200.0 - 50.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = ram_trend(samples, threshold_mb_per_hour=50.0, timestamps_sec=timestamps)
    assert trend.suspected_memory_leak is False
    assert trend.slope_mb_per_hour == pytest.approx(-50.0, rel=1e-6)


def test_ram_slope_exactly_at_threshold_not_flagged():
    timestamps = [i * 300.0 for i in range(13)]
    samples = [10.0 + 50.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = ram_trend(samples, threshold_mb_per_hour=50.0, timestamps_sec=timestamps)
    assert trend.slope_mb_per_hour == pytest.approx(50.0, rel=1e-6)
    assert trend.suspected_memory_leak is False


def test_ram_slope_just_above_threshold_flagged():
    timestamps = [i * 300.0 for i in range(13)]
    samples = [10.0 + 50.001 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = ram_trend(samples, threshold_mb_per_hour=50.0, timestamps_sec=timestamps)
    assert trend.suspected_memory_leak is True


def test_ram_uniform_interval_axis_matches_timestamps():
    # interval_ms axis should give the same slope as explicit timestamps.
    interval_ms = 300_000  # 5 minutes
    samples = [100.0 + 100.0 * (i * 300.0 / SECONDS_PER_HOUR) for i in range(13)]
    trend = ram_trend(samples, threshold_mb_per_hour=50.0, interval_ms=interval_ms)
    assert trend.slope_mb_per_hour == pytest.approx(100.0, rel=1e-6)
    assert trend.suspected_memory_leak is True


def test_ram_too_few_samples_not_applicable():
    trend = ram_trend([100.0], threshold_mb_per_hour=50.0, interval_ms=1000)
    assert trend.applicable is False
    assert trend.suspected_memory_leak is False
    assert trend.slope_mb_per_hour is None
    assert "fewer than 2" in (trend.reason or "")


def test_ram_zero_length_window_not_applicable():
    # All samples at the same instant -> cannot compute a slope.
    trend = ram_trend(
        [100.0, 200.0, 300.0],
        threshold_mb_per_hour=50.0,
        timestamps_sec=[5.0, 5.0, 5.0],
    )
    assert trend.applicable is False
    assert trend.suspected_memory_leak is False
    assert "zero-length" in (trend.reason or "")


def test_ram_no_threshold_reports_slope_without_flag():
    timestamps = [i * 300.0 for i in range(13)]
    samples = [100.0 + 100.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = ram_trend(samples, threshold_mb_per_hour=None, timestamps_sec=timestamps)
    assert trend.applicable is True
    assert trend.suspected_memory_leak is False
    assert trend.slope_mb_per_hour == pytest.approx(100.0, rel=1e-6)
    assert "not configured" in (trend.reason or "")


def test_ram_length_mismatch_not_applicable():
    trend = ram_trend(
        [100.0, 110.0, 120.0],
        threshold_mb_per_hour=50.0,
        timestamps_sec=[0.0, 300.0],
    )
    assert trend.applicable is False
    assert "same length" in (trend.reason or "")


def test_flat_latency_series_not_flagged():
    timestamps = [i * 300.0 for i in range(13)]
    samples = [20.0] * 13
    trend = latency_trend(samples, threshold_pct=10.0, timestamps_sec=timestamps)
    assert isinstance(trend, LatencyTrend)
    assert trend.applicable is True
    assert trend.performance_degradation is False
    assert trend.degradation_pct == pytest.approx(0.0, abs=1e-9)
    assert trend.unit == LATENCY_UNIT


def test_rising_latency_beyond_threshold_flags_degradation():
    # Latency rises from 20 ms to 26 ms over the window -> +30% >> 10% threshold.
    timestamps = [i * 300.0 for i in range(13)]
    samples = [20.0 + 6.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = latency_trend(samples, threshold_pct=10.0, timestamps_sec=timestamps)
    assert trend.applicable is True
    assert trend.performance_degradation is True
    assert trend.degradation_pct == pytest.approx(30.0, rel=1e-6)
    assert trend.fitted_start_ms == pytest.approx(20.0, rel=1e-6)
    assert trend.fitted_end_ms == pytest.approx(26.0, rel=1e-6)


def test_improving_latency_not_flagged():
    # Latency drops over time -> negative degradation -> never flagged.
    timestamps = [i * 300.0 for i in range(13)]
    samples = [30.0 - 6.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = latency_trend(samples, threshold_pct=10.0, timestamps_sec=timestamps)
    assert trend.performance_degradation is False
    assert trend.degradation_pct < 0.0


def test_latency_degradation_exactly_at_threshold_not_flagged():
    # +10% over the window with a 10% threshold -> NOT flagged (strict exceeds).
    timestamps = [i * 300.0 for i in range(13)]
    samples = [20.0 + 2.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = latency_trend(samples, threshold_pct=10.0, timestamps_sec=timestamps)
    assert trend.degradation_pct == pytest.approx(10.0, rel=1e-6)
    assert trend.performance_degradation is False


def test_latency_degradation_just_above_threshold_flagged():
    timestamps = [i * 300.0 for i in range(13)]
    samples = [20.0 + 2.01 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = latency_trend(samples, threshold_pct=10.0, timestamps_sec=timestamps)
    assert trend.degradation_pct > 10.0
    assert trend.performance_degradation is True


def test_latency_too_few_samples_not_applicable():
    trend = latency_trend([20.0], threshold_pct=10.0, interval_ms=1000)
    assert trend.applicable is False
    assert trend.performance_degradation is False
    assert trend.degradation_pct is None


def test_latency_no_threshold_reports_pct_without_flag():
    timestamps = [i * 300.0 for i in range(13)]
    samples = [20.0 + 6.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    trend = latency_trend(samples, threshold_pct=None, timestamps_sec=timestamps)
    assert trend.applicable is True
    assert trend.performance_degradation is False
    assert trend.degradation_pct == pytest.approx(30.0, rel=1e-6)
    assert "not configured" in (trend.reason or "")


# Combined softTrends + axis-arg validation
def test_soak_trends_combines_both():
    timestamps = [i * 300.0 for i in range(13)]
    ram = [100.0 + 100.0 * (t / SECONDS_PER_HOUR) for t in timestamps]
    lat = [20.0] * 13
    trends = soak_trends(
        ram,
        lat,
        ram_threshold_mb_per_hour=50.0,
        latency_threshold_pct=10.0,
        ram_timestamps_sec=timestamps,
        latency_timestamps_sec=timestamps,
    )
    assert isinstance(trends, SoakTrends)
    assert trends.suspected_memory_leak is True
    assert trends.performance_degradation is False
    rendered = trends.to_dict()
    assert rendered["suspectedMemoryLeak"] is True
    assert rendered["performanceDegradation"] is False
    assert rendered["ramTrend"]["slopeMbPerHour"] == pytest.approx(100.0, rel=1e-6)


def test_soak_trends_shared_interval():
    interval_ms = 300_000
    ram = [100.0 + 100.0 * (i * 300.0 / SECONDS_PER_HOUR) for i in range(13)]
    lat = [20.0 + 6.0 * (i * 300.0 / SECONDS_PER_HOUR) for i in range(13)]
    trends = soak_trends(
        ram,
        lat,
        ram_threshold_mb_per_hour=50.0,
        latency_threshold_pct=10.0,
        interval_ms=interval_ms,
    )
    assert trends.suspected_memory_leak is True
    assert trends.performance_degradation is True


def test_axis_requires_exactly_one_time_base():
    with pytest.raises(ValueError):
        ram_trend([1.0, 2.0], threshold_mb_per_hour=1.0)  # neither supplied
    with pytest.raises(ValueError):
        ram_trend(
            [1.0, 2.0],
            threshold_mb_per_hour=1.0,
            timestamps_sec=[0.0, 1.0],
            interval_ms=1000,
        )  # both supplied
