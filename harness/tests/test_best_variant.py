"""Unit tests for StatisticsEngine Best_Variant selection (task 8.10)."""

import pytest

from harness.best_variant import (
    CRITERION_ROUNDTRIP_P50,
    DEFAULT_BEST_VARIANT_CRITERION,
    BestVariantResult,
    UnknownCriterionError,
    VariantSelectionInput,
    select_best_variant,
    select_best_variants_by_language,
)


def _v(
    variant_id,
    *,
    p50=10.0,
    p99=20.0,
    peak_ram_mb=100.0,
    eligible=True,
    extra_metrics=None,
):
    return VariantSelectionInput(
        variant_id=variant_id,
        p50_round_trip_ms=p50,
        p99_ms=p99,
        peak_ram_mb=peak_ram_mb,
        eligible=eligible,
        extra_metrics=extra_metrics or {},
    )


def test_default_criterion_picks_lowest_p50_roundtrip():
    variants = [
        _v("a", p50=12.0),
        _v("b", p50=8.0),  # winner
        _v("c", p50=15.0),
    ]
    result = select_best_variant(variants)

    assert result.comparable is True
    assert result.variant_id == "b"
    assert result.criterion == CRITERION_ROUNDTRIP_P50 == DEFAULT_BEST_VARIANT_CRITERION
    assert result.value == pytest.approx(8.0)
    assert result.tie_break_p99 == pytest.approx(20.0)
    assert result.tie_break_peak_ram_mb == pytest.approx(100.0)
    assert result.excluded_variant_ids == ()
    assert set(result.eligible_variant_ids) == {"a", "b", "c"}


def test_records_criterion_and_deciding_values_in_dict():
    result = select_best_variant([_v("a", p50=5.0, p99=9.0, peak_ram_mb=64.0)])
    d = result.to_dict()
    assert d["comparable"] is True
    assert d["variantId"] == "a"
    assert d["criterion"] == "p50_roundtrip"
    assert d["value"] == pytest.approx(5.0)
    assert d["tieBreakP99"] == pytest.approx(9.0)
    assert d["tieBreakPeakRamMb"] == pytest.approx(64.0)
    assert d["nonComparableReason"] is None


def test_custom_criterion_uses_extra_metrics():
    variants = [
        # Lowest p50 would pick "a", but custom criterion "encrypt_p50" picks "b".
        _v("a", p50=5.0, extra_metrics={"encrypt_p50": 9.0}),
        _v("b", p50=10.0, extra_metrics={"encrypt_p50": 3.0}),  # winner by custom
    ]
    result = select_best_variant(variants, criterion="encrypt_p50")

    assert result.criterion == "encrypt_p50"
    assert result.variant_id == "b"
    assert result.value == pytest.approx(3.0)


def test_unknown_criterion_raises():
    with pytest.raises(UnknownCriterionError):
        select_best_variant([_v("a")], criterion="does_not_exist")


def test_tie_break_on_p99_when_p50_ties():
    variants = [
        _v("a", p50=10.0, p99=25.0),
        _v("b", p50=10.0, p99=18.0),  # winner: same p50, lower p99
        _v("c", p50=10.0, p99=30.0),
    ]
    result = select_best_variant(variants)
    assert result.variant_id == "b"
    assert result.value == pytest.approx(10.0)
    assert result.tie_break_p99 == pytest.approx(18.0)


def test_tie_break_on_peak_ram_when_p50_and_p99_tie():
    variants = [
        _v("a", p50=10.0, p99=20.0, peak_ram_mb=512.0),
        _v("b", p50=10.0, p99=20.0, peak_ram_mb=256.0),  # winner: lowest RAM
        _v("c", p50=10.0, p99=20.0, peak_ram_mb=1024.0),
    ]
    result = select_best_variant(variants)
    assert result.variant_id == "b"
    assert result.tie_break_peak_ram_mb == pytest.approx(256.0)


def test_full_tie_break_chain_orders_p50_then_p99_then_ram():
    # "fast" wins on p50 outright even though its p99/RAM are worse.
    variants = [
        _v("slow", p50=11.0, p99=15.0, peak_ram_mb=100.0),
        _v("fast", p50=9.0, p99=40.0, peak_ram_mb=900.0),  # winner on p50
    ]
    result = select_best_variant(variants)
    assert result.variant_id == "fast"


def test_missing_peak_ram_sorts_last_in_tie():
    variants = [
        _v("a", p50=10.0, p99=20.0, peak_ram_mb=None),
        _v("b", p50=10.0, p99=20.0, peak_ram_mb=300.0),  # winner: known RAM beats None
    ]
    result = select_best_variant(variants)
    assert result.variant_id == "b"


def test_total_tie_broken_deterministically_by_variant_id():
    variants = [
        _v("zeta", p50=10.0, p99=20.0, peak_ram_mb=100.0),
        _v("alpha", p50=10.0, p99=20.0, peak_ram_mb=100.0),
    ]
    result = select_best_variant(variants)
    assert result.variant_id == "alpha"


def test_correctness_filter_excludes_fast_but_failing_variant():
    variants = [
        _v("fast-broken", p50=1.0, eligible=False),  # fastest but failed round-trip
        _v("correct", p50=9.0, eligible=True),  # winner among eligible
        _v("correct-slow", p50=12.0, eligible=True),
    ]
    result = select_best_variant(variants)

    assert result.comparable is True
    assert result.variant_id == "correct"
    assert result.value == pytest.approx(9.0)
    assert "fast-broken" in result.excluded_variant_ids
    assert "fast-broken" not in result.eligible_variant_ids


def test_no_eligible_variant_marks_language_non_comparable():
    variants = [
        _v("a", eligible=False),
        _v("b", eligible=False),
    ]
    result = select_best_variant(variants)

    assert result.comparable is False
    assert result.variant_id is None
    assert result.value is None
    assert result.non_comparable_reason is not None
    assert set(result.excluded_variant_ids) == {"a", "b"}
    d = result.to_dict()
    assert d["comparable"] is False
    assert d["variantId"] is None
    assert d["nonComparableReason"]


def test_empty_variant_list_is_non_comparable():
    result = select_best_variant([])
    assert result.comparable is False
    assert result.variant_id is None


def test_select_best_variants_by_language():
    by_language = {
        "go": [_v("go-inmem", p50=8.0), _v("go-stream", p50=6.0)],
        "java": [_v("java-broken", p50=1.0, eligible=False)],
    }
    results = select_best_variants_by_language(by_language)

    assert results["go"].comparable is True
    assert results["go"].variant_id == "go-stream"
    assert results["java"].comparable is False
    assert results["java"].variant_id is None


def test_select_by_language_respects_custom_criterion():
    by_language = {
        "go": [
            _v("go-a", p50=5.0, extra_metrics={"p99_roundtrip": 30.0}),
            _v("go-b", p50=9.0, extra_metrics={"p99_roundtrip": 12.0}),
        ],
    }
    results = select_best_variants_by_language(by_language, criterion="p99_roundtrip")
    assert results["go"].variant_id == "go-b"
    assert results["go"].criterion == "p99_roundtrip"


def test_result_type_is_best_variant_result():
    assert isinstance(select_best_variant([_v("a")]), BestVariantResult)
