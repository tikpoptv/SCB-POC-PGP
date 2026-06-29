"""Property-based tests for the NoiseFloor computation (Task 14.3).

Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation

Validates Requirements 27.4, 27.5:
  - CV = stddev / mean of the pooled round-trip samples (when well-defined).
  - meanDiffPct = |mean1 - mean2| / ((mean1 + mean2) / 2) * 100 (when well-defined).
  - cv_round_trip is always >= 0 when defined.
  - mean_diff_pct is always >= 0 when defined.
  - Swapping run1 and run2 preserves both metrics (symmetry).
"""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics_engine import NoiseFloor, compute_noise_floor

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# Positive round-trip times in ms (realistic benchmark range: 0.001 ms – 10 s)
_pos_ms = st.floats(min_value=1e-3, max_value=10_000.0, allow_nan=False, allow_infinity=False)
_run = st.lists(_pos_ms, min_size=1, max_size=200)
_run_maybe_empty = st.lists(_pos_ms, min_size=0, max_size=200)


# Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation
# Validates: Requirements 27.4, 27.5
@settings(max_examples=200, deadline=None)
@given(run1=_run, run2=_run)
def test_cv_is_nonnegative_when_defined(run1: list[float], run2: list[float]) -> None:
    """cv_round_trip is always >= 0 when it is not None."""
    result = compute_noise_floor("go", run1, run2)
    if result.cv_round_trip is not None:
        assert result.cv_round_trip >= 0.0


# Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation
# Validates: Requirements 27.4, 27.5
@settings(max_examples=200, deadline=None)
@given(run1=_run, run2=_run)
def test_mean_diff_pct_is_nonnegative_when_defined(
    run1: list[float], run2: list[float]
) -> None:
    """mean_diff_pct is always >= 0 when it is not None."""
    result = compute_noise_floor("go", run1, run2)
    if result.mean_diff_pct is not None:
        assert result.mean_diff_pct >= 0.0


# Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation
# Validates: Requirements 27.4, 27.5
@settings(max_examples=200, deadline=None)
@given(run1=_run, run2=_run)
def test_swapping_runs_preserves_metrics(
    run1: list[float], run2: list[float]
) -> None:
    """compute_noise_floor is symmetric: swapping run1/run2 gives the same result."""
    forward = compute_noise_floor("go", run1, run2)
    backward = compute_noise_floor("go", run2, run1)

    # CV is identical because pooling is commutative.
    assert forward.cv_round_trip == backward.cv_round_trip

    # mean_diff_pct is symmetric.
    if forward.mean_diff_pct is None:
        assert backward.mean_diff_pct is None
    else:
        assert backward.mean_diff_pct is not None
        assert math.isclose(forward.mean_diff_pct, backward.mean_diff_pct, rel_tol=1e-9)


# Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation
# Validates: Requirements 27.4, 27.5
@settings(max_examples=200, deadline=None)
@given(run1=_run, run2=_run)
def test_cv_matches_stddev_over_mean(
    run1: list[float], run2: list[float]
) -> None:
    """cv_round_trip == stddev(pooled) / mean(pooled) for non-degenerate cases."""
    result = compute_noise_floor("go", run1, run2)
    if result.cv_round_trip is None:
        return  # degenerate case; skip formula check

    all_samples = run1 + run2
    n = len(all_samples)
    if n < 2:
        return
    mean = sum(all_samples) / n
    if mean <= 0.0:
        return
    variance = sum((x - mean) ** 2 for x in all_samples) / (n - 1)
    expected_cv = math.sqrt(variance) / mean
    assert math.isclose(result.cv_round_trip, expected_cv, rel_tol=1e-9)


# Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation
# Validates: Requirements 27.4, 27.5
@settings(max_examples=200, deadline=None)
@given(run1=_run, run2=_run)
def test_mean_diff_pct_matches_formula(
    run1: list[float], run2: list[float]
) -> None:
    """mean_diff_pct == |mean1-mean2| / ((mean1+mean2)/2) * 100."""
    result = compute_noise_floor("go", run1, run2)
    if result.mean_diff_pct is None:
        return  # degenerate case; skip formula check

    mean1 = sum(run1) / len(run1)
    mean2 = sum(run2) / len(run2)
    midpoint = (mean1 + mean2) / 2.0
    if midpoint == 0.0:
        return
    expected = abs(mean1 - mean2) / midpoint * 100.0
    assert math.isclose(result.mean_diff_pct, expected, rel_tol=1e-9)


# Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation
# Validates: Requirements 27.4, 27.5
@settings(max_examples=200, deadline=None)
@given(run1=_run_maybe_empty, run2=_run_maybe_empty)
def test_cv_is_none_iff_fewer_than_2_pooled_or_zero_mean(
    run1: list[float], run2: list[float]
) -> None:
    """cv_round_trip is None iff pooled sample count < 2 or pooled mean is 0."""
    result = compute_noise_floor("go", run1, run2)
    all_samples = run1 + run2
    n = len(all_samples)

    if n < 2:
        assert result.cv_round_trip is None
    else:
        mean = sum(all_samples) / n
        if mean <= 0.0:
            assert result.cv_round_trip is None
        else:
            assert result.cv_round_trip is not None


# Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation
# Validates: Requirements 27.4, 27.5
@settings(max_examples=200, deadline=None)
@given(run1=_run_maybe_empty, run2=_run_maybe_empty)
def test_mean_diff_pct_is_none_iff_empty_or_zero_midpoint(
    run1: list[float], run2: list[float]
) -> None:
    """mean_diff_pct is None iff either run is empty or midpoint is 0."""
    result = compute_noise_floor("go", run1, run2)

    if not run1 or not run2:
        assert result.mean_diff_pct is None
    else:
        mean1 = sum(run1) / len(run1)
        mean2 = sum(run2) / len(run2)
        midpoint = (mean1 + mean2) / 2.0
        if midpoint == 0.0:
            assert result.mean_diff_pct is None
        else:
            assert result.mean_diff_pct is not None


# Feature: pgp-encryption-benchmark-go-java, Property 17: Noise_Floor computation
# Validates: Requirements 27.4, 27.5
@settings(max_examples=200, deadline=None)
@given(
    runner=st.sampled_from(["go", "java"]),
    run1=_run,
    run2=_run,
)
def test_to_dict_shape_is_always_valid(
    runner: str, run1: list[float], run2: list[float]
) -> None:
    """to_dict always returns a dict with keys runner/cvRoundTrip/meanDiffPct."""
    result = compute_noise_floor(runner, run1, run2)
    d = result.to_dict()
    assert isinstance(d, dict)
    assert set(d.keys()) == {"runner", "cvRoundTrip", "meanDiffPct"}
    assert d["runner"] == runner
    # Values must be float or None
    assert d["cvRoundTrip"] is None or isinstance(d["cvRoundTrip"], float)
    assert d["meanDiffPct"] is None or isinstance(d["meanDiffPct"], float)
