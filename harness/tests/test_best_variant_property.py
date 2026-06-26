"""Property-based test for Best_Variant selection (task 8.11)."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.best_variant import (
    CRITERION_ROUNDTRIP_P50,
    VariantSelectionInput,
    select_best_variant,
)

# generated variant carries it in ``extra_metrics`` so selection by it is valid.
_CUSTOM_CRITERION = "encrypt_p50"

# Cost metrics are finite, non-negative numbers. Keep the magnitude range small
# so collisions (ties) happen often enough to exercise the tie-break chain.
_METRIC = st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False)
# peak RAM may be missing (not measured) -> None, treated as worst in tie-break.
_PEAK_RAM = st.one_of(st.none(), _METRIC)


@st.composite
def _variant(draw, variant_id):
    return VariantSelectionInput(
        variant_id=variant_id,
        p50_round_trip_ms=draw(_METRIC),
        p99_ms=draw(_METRIC),
        peak_ram_mb=draw(_PEAK_RAM),
        eligible=draw(st.booleans()),
        extra_metrics={_CUSTOM_CRITERION: draw(_METRIC)},
    )


@st.composite
def _variants(draw):
    """A list of variants with unique ids (a Scenario/language's aggregates)."""
    n = draw(st.integers(min_value=0, max_value=8))
    return [draw(_variant(f"v{i}")) for i in range(n)]


def _criterion_value(variant, criterion):
    if criterion == CRITERION_ROUNDTRIP_P50:
        return variant.p50_round_trip_ms
    return variant.extra_metrics[criterion]


def _independent_key(variant, criterion):
    """Independent re-derivation of the selection sort key."""
    ram = math.inf if variant.peak_ram_mb is None else variant.peak_ram_mb
    return (
        _criterion_value(variant, criterion),
        variant.p99_ms,
        ram,
        variant.variant_id,
    )


# Feature: pgp-encryption-benchmark-go-java, Property 11: การคัดเลือก Best_Variant (เกณฑ์ + correctness filter + tie-break)
@settings(max_examples=300)
@given(
    variants=_variants(),
    criterion=st.sampled_from([CRITERION_ROUNDTRIP_P50, _CUSTOM_CRITERION]),
)
def test_best_variant_selection_is_eligible_minimal_and_tie_broken(variants, criterion):
    result = select_best_variant(variants, criterion=criterion)

    eligible = [v for v in variants if v.eligible]
    eligible_ids = {v.variant_id for v in eligible}

    if not eligible:
        assert result.comparable is False
        assert result.variant_id is None
        assert result.value is None
        return

    # ineligible (fast-but-failing) variant can never be selected.
    assert result.comparable is True
    assert result.variant_id in eligible_ids

    # (b)+(c) Cross-check the winner against an independent min() over the
    # eligible variants using the (criterion, p99, peak RAM, id) key. This
    expected = min(eligible, key=lambda v: _independent_key(v, criterion))
    assert result.variant_id == expected.variant_id

    assert result.value == _criterion_value(expected, criterion)
    assert result.tie_break_p99 == expected.p99_ms
    assert result.tie_break_peak_ram_mb == expected.peak_ram_mb

    # The winner's key is <= every other eligible variant's key (minimality).
    winner_key = _independent_key(expected, criterion)
    for v in eligible:
        assert winner_key <= _independent_key(v, criterion)
