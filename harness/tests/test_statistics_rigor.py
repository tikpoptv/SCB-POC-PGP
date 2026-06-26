"""Unit tests for the statistical-rigor layer (task 8.15)."""

import math

import pytest

from harness.statistics import (
    INCONCLUSIVE_THRESHOLD_PCT,
    P95_MIN_RELIABLE_SAMPLES,
    P99_MIN_RELIABLE_SAMPLES,
    ConfidenceInterval,
    HeadToHead,
    ReliabilityMarking,
    StatisticsEngine,
    confidence_interval,
    effect_size,
    head_to_head,
    reliability_marking,
)


def test_p95_unreliable_just_below_threshold():
    marking = reliability_marking(19)
    assert isinstance(marking, ReliabilityMarking)
    assert marking.p95_reliable is False
    assert marking.p99_reliable is False
    assert marking.sample_count == 19


def test_p95_reliable_exactly_at_threshold():
    # Boundary is inclusive: exactly 20 -> p95 reliable, p99 still not.
    marking = reliability_marking(20)
    assert marking.p95_reliable is True
    assert marking.p99_reliable is False


def test_p99_unreliable_just_below_threshold():
    marking = reliability_marking(99)
    assert marking.p95_reliable is True  # 99 >= 20
    assert marking.p99_reliable is False


def test_p99_reliable_exactly_at_threshold():
    marking = reliability_marking(100)
    assert marking.p95_reliable is True
    assert marking.p99_reliable is True


def test_thresholds_match_requirement_constants():
    assert P95_MIN_RELIABLE_SAMPLES == 20
    assert P99_MIN_RELIABLE_SAMPLES == 100


def test_negative_count_treated_as_zero():
    marking = reliability_marking(-5)
    assert marking.sample_count == 0
    assert marking.p95_reliable is False
    assert marking.p99_reliable is False


def test_reliability_attached_to_latency_statistics():
    engine = StatisticsEngine()
    # 25 samples -> p95 reliable, p99 unreliable; flags flow into to_dict.
    stats = engine.compute([float(i) for i in range(25)])
    assert stats is not None
    assert stats.p95_reliable is True
    assert stats.p99_reliable is False
    d = stats.to_dict()
    assert d["p95Reliable"] is True
    assert d["p99Reliable"] is False


def test_confidence_interval_brackets_mean_and_is_sane():
    samples = [10.0, 12.0, 11.0, 13.0, 9.0, 10.5, 11.5, 12.5]
    ci = confidence_interval(samples, level=0.95)
    assert isinstance(ci, ConfidenceInterval)
    assert ci.reliable is True
    assert ci.level == 0.95
    # Interval is symmetric around the mean and ordered low <= mean <= high.
    assert ci.low < ci.mean < ci.high
    assert ci.mean == pytest.approx(sum(samples) / len(samples))
    assert (ci.mean - ci.low) == pytest.approx(ci.high - ci.mean)


def test_confidence_interval_known_value():
    # data = [1, 2, 3, 4, 5]: mean=3, sample sd=sqrt(2.5)=1.5811388,
    # se = sd/sqrt(5) = 0.7071068, t_crit(0.975, df=4) = 2.7764451,
    # margin = 2.7764451 * 0.7071068 = 1.9632432
    ci = confidence_interval([1.0, 2.0, 3.0, 4.0, 5.0], level=0.95)
    assert ci is not None
    assert ci.mean == pytest.approx(3.0)
    assert ci.low == pytest.approx(3.0 - 1.9632432, abs=1e-4)
    assert ci.high == pytest.approx(3.0 + 1.9632432, abs=1e-4)


def test_higher_level_widens_interval():
    samples = [10.0, 12.0, 11.0, 13.0, 9.0, 10.5, 11.5, 12.5]
    ci95 = confidence_interval(samples, level=0.95)
    ci99 = confidence_interval(samples, level=0.99)
    width95 = ci95.high - ci95.low
    width99 = ci99.high - ci99.low
    assert width99 > width95


def test_confidence_interval_single_sample_unreliable():
    ci = confidence_interval([42.0], level=0.95)
    assert ci is not None
    assert ci.reliable is False
    assert ci.low == ci.high == ci.mean == 42.0


def test_confidence_interval_empty_returns_none():
    assert confidence_interval([], level=0.95) is None
    assert confidence_interval(None, level=0.95) is None


def test_confidence_interval_rejects_bad_level():
    with pytest.raises(ValueError):
        confidence_interval([1.0, 2.0, 3.0], level=1.0)
    with pytest.raises(ValueError):
        confidence_interval([1.0, 2.0, 3.0], level=0.0)


def test_cohens_d_positive_when_a_greater():
    a = [10.0, 11.0, 12.0, 9.0, 10.5]
    b = [5.0, 6.0, 5.5, 4.5, 5.2]
    d = effect_size(a, b)
    assert d is not None
    assert d > 0  # A has the larger mean


def test_cohens_d_negative_when_a_smaller():
    a = [5.0, 6.0, 5.5, 4.5, 5.2]
    b = [10.0, 11.0, 12.0, 9.0, 10.5]
    d = effect_size(a, b)
    assert d is not None
    assert d < 0


def test_cohens_d_known_magnitude():
    # a=[1,2,3,4,5] mean=3 var=2.5; b=[3,4,5,6,7] mean=5 var=2.5
    # pooled sd = sqrt(2.5) = 1.5811388; d = (3-5)/1.5811388 = -1.264911
    d = effect_size([1.0, 2.0, 3.0, 4.0, 5.0], [3.0, 4.0, 5.0, 6.0, 7.0])
    assert d == pytest.approx(-1.264911, abs=1e-5)


def test_cohens_d_zero_when_identical():
    a = [1.0, 2.0, 3.0, 4.0]
    d = effect_size(a, list(a))
    assert d == pytest.approx(0.0)


def test_cohens_d_none_for_too_few_samples():
    assert effect_size([1.0], [1.0, 2.0, 3.0]) is None
    assert effect_size([1.0, 2.0, 3.0], [5.0]) is None


def test_cohens_d_none_for_zero_spread_differing_means():
    # No variance in either set but different means -> undefined effect.
    assert effect_size([5.0, 5.0, 5.0], [9.0, 9.0, 9.0]) is None


def test_cohens_d_empty_returns_none():
    assert effect_size([], [1.0, 2.0]) is None
    assert effect_size(None, [1.0, 2.0]) is None


def test_diff_exactly_five_percent_is_inconclusive():
    # |95 - 100| / 100 = 5% -> inclusive boundary -> inconclusive.
    result = head_to_head(95.0, 100.0)
    assert isinstance(result, HeadToHead)
    assert result.diff_pct == pytest.approx(5.0)
    assert result.inconclusive is True
    assert result.winner is None


def test_diff_above_five_percent_names_faster_language():
    # |94 - 100| / 100 = 6% -> conclusive; 94 (go) is faster -> go wins.
    result = head_to_head(94.0, 100.0, label_a="go", label_b="java")
    assert result.diff_pct == pytest.approx(6.0)
    assert result.inconclusive is False
    assert result.winner == "go"


def test_winner_is_lower_latency_side():
    # java faster (lower) -> java wins.
    result = head_to_head(110.0, 100.0, label_a="go", label_b="java")
    assert result.inconclusive is False
    assert result.winner == "java"


def test_just_below_threshold_is_inconclusive():
    # diff_pct = 4.9% < 5% -> inconclusive.
    result = head_to_head(100.0, 104.9)
    assert result.diff_pct < INCONCLUSIVE_THRESHOLD_PCT
    assert result.inconclusive is True
    assert result.winner is None


def test_equal_values_inconclusive():
    result = head_to_head(50.0, 50.0)
    assert result.diff_pct == 0.0
    assert result.inconclusive is True
    assert result.winner is None


def test_both_zero_inconclusive_no_division_error():
    result = head_to_head(0.0, 0.0)
    assert result.diff_pct == 0.0
    assert result.inconclusive is True
    assert result.winner is None


def test_head_to_head_to_dict_shape():
    result = head_to_head(94.0, 100.0, label_a="go", label_b="java", decided_by="p50_roundtrip")
    d = result.to_dict()
    assert d["winner"] == "go"
    assert d["inconclusive"] is False
    assert d["decidedBy"] == "p50_roundtrip"
    assert d["go"] == 94.0
    assert d["java"] == 100.0
    assert math.isclose(d["diffPct"], 6.0)
