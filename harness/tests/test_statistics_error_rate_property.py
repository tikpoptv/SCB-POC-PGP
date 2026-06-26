"""Property-based test for the error-rate calculation (task 8.9)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics_engine import (
    NOT_APPLICABLE,
    error_rate,
    error_rate_from_failures,
)


# Attempted/failed counts are non-negative operation tallies. Constrain the
# generator to the valid input space (no negatives) and keep the upper bound
# realistic while still exercising large magnitudes.
_COUNTS = st.integers(min_value=0, max_value=10_000)


# A non-negative attempted count paired with a failed count that never exceeds
# it (the precondition error_rate enforces): draw attempted first, then failed
# in [0, attempted].
@st.composite
def _failed_and_attempted(draw):
    attempted = draw(_COUNTS)
    failed = draw(st.integers(min_value=0, max_value=attempted))
    return failed, attempted


# Two failure kinds whose sum never exceeds attempted (op_fail + corr_fail <=
# attempted): split an attempted count into op/corr failures plus successes.
@st.composite
def _failures_and_attempted(draw):
    attempted = draw(_COUNTS)
    op_fail = draw(st.integers(min_value=0, max_value=attempted))
    corr_fail = draw(st.integers(min_value=0, max_value=attempted - op_fail))
    return op_fail, corr_fail, attempted


# Feature: pgp-encryption-benchmark-go-java, Property 9: การคำนวณ error rate
@settings(max_examples=200)
@given(data=_failed_and_attempted())
def test_error_rate_in_unit_interval_and_equals_ratio(data):
    failed, attempted = data
    result = error_rate(failed, attempted)

    if attempted == 0:
        assert result == NOT_APPLICABLE
    else:
        assert isinstance(result, float)
        assert result == pytest.approx(failed / attempted)
        assert 0.0 <= result <= 1.0


# Feature: pgp-encryption-benchmark-go-java, Property 9: การคำนวณ error rate
@settings(max_examples=200)
@given(data=_failures_and_attempted())
def test_error_rate_counts_both_failure_kinds(data):
    op_fail, corr_fail, attempted = data
    result = error_rate_from_failures(op_fail, corr_fail, attempted)

    if attempted == 0:
        assert result == NOT_APPLICABLE
    else:
        assert isinstance(result, float)
        assert result == pytest.approx((op_fail + corr_fail) / attempted)
        assert 0.0 <= result <= 1.0
        assert result == error_rate(op_fail + corr_fail, attempted)
