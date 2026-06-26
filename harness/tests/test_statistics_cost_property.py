"""Property-based test for the cost-per-million-operations calc (task 8.19)."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics_engine import OPS_PER_MILLION, cost_per_million_ops


# Non-negative, finite physical quantities. Keep the upper bounds realistic
# while still exercising a wide magnitude range; exclude NaN/inf so the formula
# stays well-defined.
_MEAN_TIME_MS = st.floats(
    min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
)
_RATE = st.floats(
    min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
)
_VCPUS = st.floats(
    min_value=0.0, max_value=128.0, allow_nan=False, allow_infinity=False
)

# Strictly positive factors used for the proportionality checks so that
# scaling an input scales the (possibly non-zero) output by the same factor.
_POS_FACTOR = st.floats(
    min_value=1e-3, max_value=1_000.0, allow_nan=False, allow_infinity=False
)


def _formula(mean_time_ms: float, rate: float, vcpus: float) -> float:
    """The reference cost-per-million formula, guarded to be non-negative."""
    cost = (mean_time_ms / 1000.0 / 3600.0) * vcpus * rate * OPS_PER_MILLION
    return cost if cost > 0.0 else 0.0


# Feature: pgp-encryption-benchmark-go-java, Property 24: การคำนวณต้นทุนต่อล้าน operation
@settings(max_examples=200)
@given(mean_time_ms=_MEAN_TIME_MS, rate=_RATE, vcpus=_VCPUS)
def test_cost_equals_formula_and_non_negative(mean_time_ms, rate, vcpus):
    result = cost_per_million_ops(mean_time_ms, rate, vcpus=vcpus)

    assert result == pytest.approx(_formula(mean_time_ms, rate, vcpus))
    # Always non-negative and finite.
    assert result >= 0.0
    assert math.isfinite(result)
    # Deterministic: same inputs -> identical output.
    assert result == cost_per_million_ops(mean_time_ms, rate, vcpus=vcpus)


# Feature: pgp-encryption-benchmark-go-java, Property 24: การคำนวณต้นทุนต่อล้าน operation
@settings(max_examples=200)
@given(rate=_RATE, vcpus=_VCPUS, mean_time_ms=_MEAN_TIME_MS)
def test_cost_zero_when_time_or_rate_zero(rate, vcpus, mean_time_ms):
    # Zero mean time -> zero cost regardless of rate / vcpus.
    assert cost_per_million_ops(0.0, rate, vcpus=vcpus) == 0.0
    # Zero rate -> zero cost regardless of time / vcpus.
    assert cost_per_million_ops(mean_time_ms, 0.0, vcpus=vcpus) == 0.0


# Feature: pgp-encryption-benchmark-go-java, Property 24: การคำนวณต้นทุนต่อล้าน operation
@settings(max_examples=200)
@given(mean_time_ms=_MEAN_TIME_MS, rate=_RATE, vcpus=_VCPUS, k=_POS_FACTOR)
def test_cost_proportional_to_mean_time(mean_time_ms, rate, vcpus, k):
    base = cost_per_million_ops(mean_time_ms, rate, vcpus=vcpus)
    scaled = cost_per_million_ops(mean_time_ms * k, rate, vcpus=vcpus)
    assert scaled == pytest.approx(k * base, rel=1e-9, abs=1e-12)


# Feature: pgp-encryption-benchmark-go-java, Property 24: การคำนวณต้นทุนต่อล้าน operation
@settings(max_examples=200)
@given(mean_time_ms=_MEAN_TIME_MS, rate=_RATE, vcpus=_VCPUS, k=_POS_FACTOR)
def test_cost_proportional_to_rate(mean_time_ms, rate, vcpus, k):
    base = cost_per_million_ops(mean_time_ms, rate, vcpus=vcpus)
    scaled = cost_per_million_ops(mean_time_ms, rate * k, vcpus=vcpus)
    assert scaled == pytest.approx(k * base, rel=1e-9, abs=1e-12)


# Feature: pgp-encryption-benchmark-go-java, Property 24: การคำนวณต้นทุนต่อล้าน operation
@settings(max_examples=200)
@given(mean_time_ms=_MEAN_TIME_MS, rate=_RATE, vcpus=_VCPUS, k=_POS_FACTOR)
def test_cost_proportional_to_vcpus(mean_time_ms, rate, vcpus, k):
    base = cost_per_million_ops(mean_time_ms, rate, vcpus=vcpus)
    scaled = cost_per_million_ops(mean_time_ms, rate, vcpus=vcpus * k)
    assert scaled == pytest.approx(k * base, rel=1e-9, abs=1e-12)
