"""Property-based test for the latency-statistics invariants (Property 7)."""

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics import LatencyStatistics, StatisticsEngine

_ENGINE = StatisticsEngine()

# Latencies are finite, non-negative ms. Keep the upper bound sane so that
# sums/variances stay well within float range while still spanning many orders
# of magnitude (sub-microsecond to multi-second). Zeros are allowed so the
# all-zero (mean == 0) case is reachable.
_LATENCY = st.floats(
    min_value=0.0,
    max_value=1.0e6,
    allow_nan=False,
    allow_infinity=False,
)

# Non-empty lists of varied sizes (1 .. 500 samples).
_SAMPLES = st.lists(_LATENCY, min_size=1, max_size=500)


# Feature: pgp-encryption-benchmark-go-java, Property 7: ความถูกต้องและ invariant ของค่าสถิติ
@settings(max_examples=300, deadline=None)
@given(samples=_SAMPLES)
def test_statistics_invariants_hold_for_any_nonempty_sample_set(samples):
    stats = _ENGINE.compute(samples)

    # Non-empty input always yields a result.
    assert isinstance(stats, LatencyStatistics)

    # Every reported value is finite (no NaN / inf leaks through).
    for value in (
        stats.minimum,
        stats.mean,
        stats.p50,
        stats.p95,
        stats.p99,
        stats.maximum,
        stats.stddev,
    ):
        assert math.isfinite(value)

    # Ordering invariant: min <= p50 <= p95 <= p99 <= max. These quantiles are
    # selected/interpolated directly from the data, so no rounding drift occurs
    # and the comparison can stay strict.
    assert stats.minimum <= stats.p50 <= stats.p95 <= stats.p99 <= stats.maximum

    # Mean is bounded by the extremes. In exact real arithmetic
    # min <= mean <= max always holds, but the mean is computed as a
    # sum-then-divide, which can round the result up to 1 ULP above max (or down
    # below min) for degenerate sets such as identical samples. That is a
    # floating-point rounding artifact, not an invariant violation, so we admit a
    # tiny relative+absolute tolerance at the boundary while still rejecting any
    # meaningful excursion outside [min, max].
    tol = 1e-9 * max(1.0, abs(stats.maximum), abs(stats.minimum))
    assert stats.mean >= stats.minimum - tol
    assert stats.mean <= stats.maximum + tol

    # Standard deviation is never negative.
    assert stats.stddev >= 0.0

    # CV definition: defined exactly when mean > 0, equal to stddev / mean.
    if stats.mean > 0.0:
        assert stats.cv is not None
        assert stats.cv == pytest.approx(stats.stddev / stats.mean)
    else:
        # mean == 0 only when every sample is 0 (non-negative inputs).
        assert stats.cv is None

    # Model-based reference oracle: percentiles equal numpy's type-7
    # (method="linear") result on the same data.
    assert stats.p50 == pytest.approx(
        float(np.percentile(samples, 50, method="linear"))
    )
    assert stats.p95 == pytest.approx(
        float(np.percentile(samples, 95, method="linear"))
    )
    assert stats.p99 == pytest.approx(
        float(np.percentile(samples, 99, method="linear"))
    )

    # min / max / mean also match their reference definitions.
    assert stats.minimum == pytest.approx(float(np.min(samples)))
    assert stats.maximum == pytest.approx(float(np.max(samples)))
    assert stats.mean == pytest.approx(float(np.mean(samples)))
