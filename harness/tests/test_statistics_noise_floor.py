"""Unit tests for NoiseFloor calculation (Task 14.3).

Validates Requirements 27.4 and 27.5:
  - compute_noise_floor() calculates CV and mean_diff_pct correctly.
  - NoiseFloor serialises to the expected JSON shape.
  - NoiseFloorDisabled serialises correctly when null test is disabled.
  - Edge cases: empty samples, single samples, zero mean.
"""

from __future__ import annotations

import math

import pytest

from harness.statistics_engine import (
    NoiseFloor,
    NoiseFloorDisabled,
    compute_noise_floor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mean(samples: list[float]) -> float:
    return sum(samples) / len(samples)


def _stddev(samples: list[float]) -> float:
    n = len(samples)
    mean = _mean(samples)
    variance = sum((x - mean) ** 2 for x in samples) / (n - 1)
    return math.sqrt(variance)


# ---------------------------------------------------------------------------
# compute_noise_floor — basic correctness
# ---------------------------------------------------------------------------

def test_cv_round_trip_equals_stddev_over_mean():
    """CV = stddev(all samples) / mean(all samples), pooled across both runs."""
    run1 = [2.0, 2.1, 1.9, 2.05]
    run2 = [2.2, 2.15, 1.95, 2.0]
    result = compute_noise_floor("go", run1, run2)

    all_samples = run1 + run2
    expected_cv = _stddev(all_samples) / _mean(all_samples)
    assert result.cv_round_trip is not None
    assert math.isclose(result.cv_round_trip, expected_cv, rel_tol=1e-9)


def test_mean_diff_pct_formula():
    """meanDiffPct = |mean1 - mean2| / ((mean1 + mean2) / 2) * 100."""
    run1 = [1.0, 1.0, 1.0]   # mean = 1.0
    run2 = [1.1, 1.1, 1.1]   # mean = 1.1
    result = compute_noise_floor("go", run1, run2)

    mean1, mean2 = 1.0, 1.1
    expected = abs(mean1 - mean2) / ((mean1 + mean2) / 2) * 100.0
    assert result.mean_diff_pct is not None
    assert math.isclose(result.mean_diff_pct, expected, rel_tol=1e-9)


def test_runner_name_preserved():
    run1 = [1.0, 1.1]
    run2 = [1.0, 1.1]
    go_result = compute_noise_floor("go", run1, run2)
    java_result = compute_noise_floor("java", run1, run2)
    assert go_result.runner == "go"
    assert java_result.runner == "java"


def test_identical_runs_produce_zero_mean_diff():
    """When both runs are identical the mean difference is exactly 0."""
    samples = [1.5, 2.0, 1.8, 1.7]
    result = compute_noise_floor("go", samples, samples)
    assert result.mean_diff_pct is not None
    assert math.isclose(result.mean_diff_pct, 0.0, abs_tol=1e-12)


def test_identical_runs_produce_nonzero_cv():
    """CV reflects the variability even when runs are identical."""
    samples = [1.0, 2.0]   # std=sqrt(0.5)  mean=1.5  cv≈0.471
    result = compute_noise_floor("go", samples, samples)
    assert result.cv_round_trip is not None
    assert result.cv_round_trip > 0.0


def test_typical_low_noise_values():
    """Representative real-world low-noise result, as shown in design.md:
    cvRoundTrip ≈ 0.018, meanDiffPct ≈ 0.7"""
    # Simulate 10 measurements per run with ~1.8% variation
    import random
    rng = random.Random(42)
    base = 5.0  # 5 ms base round-trip
    run1 = [base + rng.gauss(0, 0.09) for _ in range(50)]
    run2 = [base + rng.gauss(0, 0.09) for _ in range(50)]
    result = compute_noise_floor("go", run1, run2)
    assert result.cv_round_trip is not None
    assert 0.0 <= result.cv_round_trip <= 0.1  # low noise
    assert result.mean_diff_pct is not None
    assert 0.0 <= result.mean_diff_pct <= 10.0  # small diff


# ---------------------------------------------------------------------------
# compute_noise_floor — edge cases
# ---------------------------------------------------------------------------

def test_empty_run1_gives_none_mean_diff():
    run2 = [1.0, 1.1]
    result = compute_noise_floor("go", [], run2)
    assert result.mean_diff_pct is None


def test_empty_run2_gives_none_mean_diff():
    run1 = [1.0, 1.1]
    result = compute_noise_floor("go", run1, [])
    assert result.mean_diff_pct is None


def test_both_empty_gives_none_for_both_metrics():
    result = compute_noise_floor("go", [], [])
    assert result.cv_round_trip is None
    assert result.mean_diff_pct is None


def test_single_sample_each_gives_none_cv_but_valid_mean_diff():
    """CV requires at least 2 samples total; with 1+1=2 samples CV is valid."""
    result = compute_noise_floor("go", [2.0], [3.0])
    # 2 pooled samples: mean=2.5, stddev=sqrt(0.5), cv=sqrt(0.5)/2.5
    assert result.cv_round_trip is not None
    expected_cv = math.sqrt(0.5) / 2.5
    assert math.isclose(result.cv_round_trip, expected_cv, rel_tol=1e-9)
    # mean_diff_pct: |2-3| / ((2+3)/2) * 100 = 1/2.5*100 = 40
    assert result.mean_diff_pct is not None
    assert math.isclose(result.mean_diff_pct, 40.0, rel_tol=1e-9)


def test_single_pooled_sample_gives_none_cv():
    """Only 1 total sample → CV is undefined (needs at least 2)."""
    result = compute_noise_floor("go", [2.0], [])
    assert result.cv_round_trip is None


def test_zero_mean_gives_none_cv():
    """When the pooled mean is 0, CV cannot be computed."""
    result = compute_noise_floor("go", [0.0, 0.0], [0.0, 0.0])
    assert result.cv_round_trip is None


def test_zero_midpoint_gives_none_mean_diff():
    """When both run means are 0, the midpoint is 0 and mean_diff_pct is None."""
    result = compute_noise_floor("go", [0.0, 0.0], [0.0, 0.0])
    assert result.mean_diff_pct is None


def test_large_diff_greater_than_100_pct():
    """mean_diff_pct can exceed 100% when runs are very different."""
    run1 = [1.0]
    run2 = [10.0]
    result = compute_noise_floor("go", run1, run2)
    # |1-10| / ((1+10)/2) * 100 = 9/5.5*100 ≈ 163.6
    assert result.mean_diff_pct is not None
    assert result.mean_diff_pct > 100.0


# ---------------------------------------------------------------------------
# NoiseFloor.to_dict
# ---------------------------------------------------------------------------

def test_to_dict_contains_all_required_keys():
    nf = NoiseFloor(runner="go", cv_round_trip=0.018, mean_diff_pct=0.7)
    d = nf.to_dict()
    assert set(d.keys()) == {"runner", "cvRoundTrip", "meanDiffPct"}


def test_to_dict_values_match():
    nf = NoiseFloor(runner="go", cv_round_trip=0.018, mean_diff_pct=0.7)
    d = nf.to_dict()
    assert d["runner"] == "go"
    assert math.isclose(d["cvRoundTrip"], 0.018, rel_tol=1e-9)
    assert math.isclose(d["meanDiffPct"], 0.7, rel_tol=1e-9)


def test_to_dict_none_values_preserved():
    nf = NoiseFloor(runner="java", cv_round_trip=None, mean_diff_pct=None)
    d = nf.to_dict()
    assert d["cvRoundTrip"] is None
    assert d["meanDiffPct"] is None


def test_to_dict_round_trip_from_compute():
    run1 = [2.0, 2.1, 1.9]
    run2 = [2.0, 2.05, 1.95]
    result = compute_noise_floor("go", run1, run2)
    d = result.to_dict()
    assert d["runner"] == "go"
    assert "cvRoundTrip" in d
    assert "meanDiffPct" in d


# ---------------------------------------------------------------------------
# NoiseFloorDisabled.to_dict
# ---------------------------------------------------------------------------

def test_noise_floor_disabled_to_dict():
    disabled = NoiseFloorDisabled()
    d = disabled.to_dict()
    assert d == {"enabled": False}
    assert d["enabled"] is False


def test_noise_floor_disabled_default_value():
    d = NoiseFloorDisabled()
    assert d.enabled is False


# ---------------------------------------------------------------------------
# Integration with Result_Report shape (Req 27.5)
# ---------------------------------------------------------------------------

def test_noise_floor_result_matches_design_doc_schema():
    """The JSON shape must match design.md:
    {"runner": "go", "cvRoundTrip": 0.018, "meanDiffPct": 0.7}
    """
    nf = NoiseFloor(runner="go", cv_round_trip=0.018, mean_diff_pct=0.7)
    d = nf.to_dict()
    # Exact key names from design.md
    assert "runner" in d
    assert "cvRoundTrip" in d
    assert "meanDiffPct" in d
    assert isinstance(d["runner"], str)
    assert isinstance(d["cvRoundTrip"], float)
    assert isinstance(d["meanDiffPct"], float)
