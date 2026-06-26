"""Property-based test for reliability marking of statistics (Property 20)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics import (
    P95_MIN_RELIABLE_SAMPLES,
    P99_MIN_RELIABLE_SAMPLES,
    ReliabilityMarking,
    reliability_marking,
)

# Arbitrary sample counts spanning the whole input space: deep negatives, the
# region around both boundaries (20 and 100), and large counts. The wide
# ``integers`` range is unioned with tight boundary windows so hypothesis is
# guaranteed to probe the inclusive 20/100 edges, not just random large values.
_SAMPLE_COUNTS = st.one_of(
    st.integers(min_value=-1000, max_value=100000),
    st.integers(min_value=15, max_value=25),  # around the p95 boundary (20)
    st.integers(min_value=95, max_value=105),  # around the p99 boundary (100)
    st.integers(min_value=-5, max_value=5),  # around zero / negatives
)


# Feature: pgp-encryption-benchmark-go-java, Property 20: การ mark ค่าสถิติว่าไม่น่าเชื่อถือตามจำนวนตัวอย่าง
@settings(max_examples=500, deadline=None)
@given(sample_count=_SAMPLE_COUNTS)
def test_reliability_marking_follows_sample_count(sample_count):
    marking = reliability_marking(sample_count)
    assert isinstance(marking, ReliabilityMarking)

    # Negative counts are clamped to 0; otherwise the count is recorded as-is.
    expected_n = max(sample_count, 0)
    assert marking.sample_count == expected_n

    # n >= 100 — evaluated against the clamped count so negatives are not
    # reliable.
    assert marking.p95_reliable == (expected_n >= P95_MIN_RELIABLE_SAMPLES)
    assert marking.p99_reliable == (expected_n >= P99_MIN_RELIABLE_SAMPLES)

    # A negative count can never be reliable (clamped to 0 < both thresholds).
    if sample_count < 0:
        assert marking.sample_count == 0
        assert marking.p95_reliable is False
        assert marking.p99_reliable is False

    # p99 reliability is strictly stronger than p95 (100 > 20), so p99 reliable
    # implies p95 reliable — they can never disagree in the other direction.
    if marking.p99_reliable:
        assert marking.p95_reliable
