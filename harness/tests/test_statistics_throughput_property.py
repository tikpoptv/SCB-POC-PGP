"""Property-based tests for throughput calculation (task 8.4, Property 5)."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics_engine import (
    BYTES_PER_MB,
    NON_POSITIVE_TIME_REASON,
    aggregate_throughput,
    throughput_files_per_sec,
    throughput_mb_per_sec,
)

# Positive, finite generators constrained to the real input space: a job that
# actually produced bytes/files and took a positive crypto-only time (ms).
_BYTES = st.floats(min_value=1.0, max_value=1e12, allow_nan=False, allow_infinity=False)
_FILES = st.floats(min_value=1.0, max_value=1e9, allow_nan=False, allow_infinity=False)
# time_ms stays comfortably away from 0 so the reciprocal is finite and the
# reference formula does not lose all precision for sub-microsecond windows.
_TIME_MS = st.floats(
    min_value=1e-3, max_value=1e9, allow_nan=False, allow_infinity=False
)
_NON_POSITIVE_TIME = st.one_of(
    st.just(0.0),
    st.floats(min_value=-1e9, max_value=-1e-6, allow_nan=False, allow_infinity=False),
)


# Feature: pgp-encryption-benchmark-go-java, Property 5: การคำนวณ throughput ถูกต้องตามสูตร หน่วย และฐานเวลา crypto-only
@settings(max_examples=300)
@given(byte_count=_BYTES, time_ms=_TIME_MS)
def test_mb_per_sec_matches_formula(byte_count, time_ms):
    res = throughput_mb_per_sec(byte_count, time_ms)
    expected = (byte_count / BYTES_PER_MB) / (time_ms / 1000.0)
    assert res.computed is True
    assert math.isclose(res.value, expected, rel_tol=1e-12, abs_tol=0.0)
    assert res.unit == "MB/sec"
    assert res.time_ms == time_ms
    assert res.reason is None
    assert math.isfinite(res.value)
    assert res.value >= 0.0


@settings(max_examples=300)
@given(file_count=_FILES, time_ms=_TIME_MS)
def test_files_per_sec_matches_formula(file_count, time_ms):
    res = throughput_files_per_sec(file_count, time_ms)
    expected = file_count / (time_ms / 1000.0)
    assert res.computed is True
    assert math.isclose(res.value, expected, rel_tol=1e-12, abs_tol=0.0)
    assert res.unit == "files/sec"
    assert res.time_ms == time_ms
    assert res.reason is None
    assert math.isfinite(res.value)
    assert res.value >= 0.0


@settings(max_examples=300)
@given(total_bytes=_BYTES, total_files=_FILES, window_ms=_TIME_MS)
def test_aggregate_uses_wall_clock_window_for_concurrency(total_bytes, total_files, window_ms):
    # For concurrency>1 the aggregate throughput is the total volume/files
    # divided by the wall-clock crypto window, NOT the sum of per-op times
    agg = aggregate_throughput(total_bytes, total_files, window_ms)
    expected_mb = (total_bytes / BYTES_PER_MB) / (window_ms / 1000.0)
    expected_files = total_files / (window_ms / 1000.0)

    assert agg.wall_clock_crypto_window_ms == window_ms
    assert math.isclose(agg.mb_per_sec.value, expected_mb, rel_tol=1e-12, abs_tol=0.0)
    assert math.isclose(agg.files_per_sec.value, expected_files, rel_tol=1e-12, abs_tol=0.0)
    # Both rates are derived from the same single window (same time base).
    assert agg.mb_per_sec.time_ms == window_ms
    assert agg.files_per_sec.time_ms == window_ms


@settings(max_examples=200)
@given(byte_count=_BYTES, file_count=_FILES, bad_time=_NON_POSITIVE_TIME)
def test_non_positive_time_not_computed_but_preserved(byte_count, file_count, bad_time):
    # preserved and a machine-readable reason is attached.
    mb = throughput_mb_per_sec(byte_count, bad_time)
    assert mb.computed is False
    assert mb.value is None
    assert mb.time_ms == bad_time
    assert mb.reason == NON_POSITIVE_TIME_REASON

    files = throughput_files_per_sec(file_count, bad_time)
    assert files.computed is False
    assert files.value is None
    assert files.time_ms == bad_time
    assert files.reason == NON_POSITIVE_TIME_REASON

    # The aggregate path inherits the same guard for a non-positive window.
    agg = aggregate_throughput(byte_count, file_count, bad_time)
    assert agg.mb_per_sec.computed is False
    assert agg.files_per_sec.computed is False
    assert agg.mb_per_sec.reason == NON_POSITIVE_TIME_REASON
    assert agg.files_per_sec.reason == NON_POSITIVE_TIME_REASON
    assert agg.wall_clock_crypto_window_ms == bad_time
