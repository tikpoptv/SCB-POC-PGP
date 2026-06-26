"""Unit tests for StatisticsEngine throughput & round-trip (task 8.3)."""

import math

import pytest

from harness.statistics_engine import (
    BYTES_PER_MB,
    NON_POSITIVE_TIME_REASON,
    AggregateThroughput,
    ThroughputResult,
    aggregate_throughput,
    round_trip_ms,
    throughput_files_per_sec,
    throughput_mb_per_sec,
)


def test_one_mb_is_1048576_bytes():
    assert BYTES_PER_MB == 1_048_576


def test_round_trip_is_sum_of_encrypt_and_decrypt():
    assert round_trip_ms(1.83, 2.04) == pytest.approx(3.87)


def test_round_trip_with_zeros():
    assert round_trip_ms(0.0, 0.0) == 0.0


def test_mb_per_sec_reference_value():
    # 1,048,576 bytes in 1000 ms = exactly 1.0 MB/sec.
    res = throughput_mb_per_sec(BYTES_PER_MB, 1000.0)
    assert res.computed is True
    assert res.value == pytest.approx(1.0)
    assert res.unit == "MB/sec"
    assert res.time_ms == 1000.0
    assert res.reason is None


def test_mb_per_sec_half_second():
    # 1 MB in 500 ms = 2.0 MB/sec.
    res = throughput_mb_per_sec(BYTES_PER_MB, 500.0)
    assert res.value == pytest.approx(2.0)


def test_mb_per_sec_multi_mb():
    # 10 MB in 2000 ms = 5.0 MB/sec.
    res = throughput_mb_per_sec(10 * BYTES_PER_MB, 2000.0)
    assert res.value == pytest.approx(5.0)


@pytest.mark.parametrize("bad_time", [0.0, -1.0, -1000.0])
def test_mb_per_sec_non_positive_time_not_computed_but_time_preserved(bad_time):
    res = throughput_mb_per_sec(BYTES_PER_MB, bad_time)
    assert res.computed is False
    assert res.value is None
    assert res.time_ms == bad_time  # time preserved
    assert res.reason == NON_POSITIVE_TIME_REASON


def test_mb_per_sec_zero_bytes_positive_time_is_zero():
    res = throughput_mb_per_sec(0, 1000.0)
    assert res.value == pytest.approx(0.0)
    assert res.computed is True


def test_files_per_sec_reference_value():
    # 100 files in 1000 ms = 100 files/sec.
    res = throughput_files_per_sec(100, 1000.0)
    assert res.value == pytest.approx(100.0)
    assert res.unit == "files/sec"


def test_files_per_sec_fractional():
    # 1 file in 4000 ms = 0.25 files/sec.
    res = throughput_files_per_sec(1, 4000.0)
    assert res.value == pytest.approx(0.25)


@pytest.mark.parametrize("bad_time", [0.0, -5.0])
def test_files_per_sec_non_positive_time_not_computed(bad_time):
    res = throughput_files_per_sec(50, bad_time)
    assert res.computed is False
    assert res.value is None
    assert res.time_ms == bad_time
    assert res.reason == NON_POSITIVE_TIME_REASON


def test_aggregate_uses_wall_clock_window():
    # 8 MB total + 4 files processed in a 1000 ms wall-clock crypto window.
    agg = aggregate_throughput(8 * BYTES_PER_MB, 4, 1000.0)
    assert isinstance(agg, AggregateThroughput)
    assert agg.mb_per_sec.value == pytest.approx(8.0)
    assert agg.files_per_sec.value == pytest.approx(4.0)
    assert agg.wall_clock_crypto_window_ms == 1000.0


def test_aggregate_does_not_sum_per_operation_times():
    # Even though 4 ops each took ~1000ms of crypto time, the aggregate is
    # divided by the 1000ms wall-clock window of the parallel batch, not 4000ms.
    agg = aggregate_throughput(4 * BYTES_PER_MB, 4, 1000.0)
    assert agg.mb_per_sec.value == pytest.approx(4.0)  # 4 MB / 1s, not 1 MB/s


@pytest.mark.parametrize("bad_window", [0.0, -10.0])
def test_aggregate_non_positive_window_not_computed_but_preserved(bad_window):
    agg = aggregate_throughput(BYTES_PER_MB, 2, bad_window)
    assert agg.mb_per_sec.computed is False
    assert agg.files_per_sec.computed is False
    assert agg.mb_per_sec.reason == NON_POSITIVE_TIME_REASON
    assert agg.wall_clock_crypto_window_ms == bad_window


# Serialisation keeps time + reason on the skip path
def test_to_dict_preserves_time_and_reason_when_not_computed():
    res = throughput_mb_per_sec(BYTES_PER_MB, 0.0)
    d = res.to_dict()
    assert d == {
        "value": None,
        "unit": "MB/sec",
        "timeMs": 0.0,
        "reason": NON_POSITIVE_TIME_REASON,
    }


def test_aggregate_to_dict_shape():
    agg = aggregate_throughput(2 * BYTES_PER_MB, 8, 2000.0)
    d = agg.to_dict()
    assert d["mbPerSec"] == pytest.approx(1.0)
    assert d["filesPerSec"] == pytest.approx(4.0)
    assert d["wallClockCryptoWindowMs"] == 2000.0
    assert "wall_clock_crypto_window" in d["basis"]


def test_throughput_result_value_is_finite_for_tiny_positive_time():
    res = throughput_mb_per_sec(BYTES_PER_MB, 0.001)
    assert math.isfinite(res.value)
    assert res.computed is True
