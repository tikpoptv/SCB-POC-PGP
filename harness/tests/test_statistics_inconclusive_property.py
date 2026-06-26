"""Property-based test: head-to-head inconclusive-5% rule (task 8.17)."""

# Feature: pgp-encryption-benchmark-go-java, Property 19: เกณฑ์ inconclusive ที่ 5%

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics import (
    INCONCLUSIVE_THRESHOLD_PCT,
    head_to_head,
)

# A positive deciding-metric value (e.g. p50 round-trip ms): strictly positive,
# finite, spanning many orders of magnitude so the relative rule is exercised
# across both tiny and huge gaps.
_VALUE = st.floats(
    min_value=1e-6, max_value=1e9, allow_nan=False, allow_infinity=False
)


@given(value_a=_VALUE, value_b=_VALUE)
@settings(max_examples=200)
def test_inconclusive_five_percent_rule(value_a: float, value_b: float) -> None:
    """diff_pct formula, inclusive-5% inconclusive band, and faster-side winner."""
    result = head_to_head(value_a, value_b, label_a="go", label_b="java")

    # diff_pct is the relative gap as a percentage of the larger (slower) value.
    expected_diff_pct = abs(value_a - value_b) / max(abs(value_a), abs(value_b)) * 100.0
    assert math.isclose(result.diff_pct, expected_diff_pct, rel_tol=1e-9, abs_tol=1e-12)

    assert result.inconclusive == (result.diff_pct <= INCONCLUSIVE_THRESHOLD_PCT)

    if result.inconclusive:
        # An inconclusive verdict never names a winner.
        assert result.winner is None
    else:
        assert result.winner is not None
        expected_winner = "go" if value_a < value_b else "java"
        assert result.winner == expected_winner


@given(value=_VALUE)
@settings(max_examples=200)
def test_equal_values_always_inconclusive(value: float) -> None:
    """Equal deciding-metric values are a 0% gap -> inconclusive, no winner."""
    result = head_to_head(value, value)
    assert result.diff_pct == 0.0
    assert result.inconclusive is True
    assert result.winner is None


def test_both_zero_inconclusive_no_division_error() -> None:
    """Both values zero -> 0% gap, inconclusive, and no ZeroDivisionError."""
    result = head_to_head(0.0, 0.0)
    assert result.diff_pct == 0.0
    assert result.inconclusive is True
    assert result.winner is None
