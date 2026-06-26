"""Best_Variant selection and tie-break for the StatisticsEngine.

For one language within a Scenario this picks the single Implementation_Variant
that should advance to the head-to-head comparison and records why it was
chosen. The module is pure and side-effect free.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "DEFAULT_BEST_VARIANT_CRITERION",
    "CRITERION_ROUNDTRIP_P50",
    "VariantSelectionInput",
    "BestVariantResult",
    "UnknownCriterionError",
    "select_best_variant",
    "select_best_variants_by_language",
]

#: Built-in criterion key: lowest p50 round-trip time.
CRITERION_ROUNDTRIP_P50: str = "p50_roundtrip"

#: Default Best_Variant criterion.
DEFAULT_BEST_VARIANT_CRITERION: str = CRITERION_ROUNDTRIP_P50


class UnknownCriterionError(ValueError):
    """Raised when a criterion is requested that a variant cannot supply."""


@dataclass(frozen=True)
class VariantSelectionInput:
    """Aggregated stats for one Implementation_Variant in one Scenario/language.

    Lower is better for all criteria/tie-break values. ``peak_ram_mb`` is
    ``None`` when not measured and treated as worst for the tie-break only.
    ``eligible`` is ``True`` only when the variant passed the round-trip
    correctness check in every run.
    """

    variant_id: str
    p50_round_trip_ms: float
    p99_ms: float
    peak_ram_mb: float | None
    eligible: bool
    extra_metrics: Mapping[str, float] = field(default_factory=dict)

    def criterion_value(self, criterion: str) -> float:
        """Return this variant's value for ``criterion``.

        Resolves the built-in :data:`CRITERION_ROUNDTRIP_P50` directly; any
        other criterion is looked up in :attr:`extra_metrics`.
        """
        if criterion == CRITERION_ROUNDTRIP_P50:
            return self.p50_round_trip_ms
        try:
            return self.extra_metrics[criterion]
        except KeyError as exc:
            raise UnknownCriterionError(
                f"variant {self.variant_id!r} has no value for criterion "
                f"{criterion!r}; known criteria: {CRITERION_ROUNDTRIP_P50!r} plus "
                f"{sorted(self.extra_metrics)}"
            ) from exc


@dataclass(frozen=True)
class BestVariantResult:
    """Outcome of Best_Variant selection for one language/Scenario.

    When :attr:`comparable` is ``True`` the remaining fields describe the chosen
    variant and the values that decided it. When ``False`` no eligible variant
    existed: :attr:`variant_id` is ``None`` and :attr:`non_comparable_reason`
    explains why.
    """

    comparable: bool
    criterion: str
    variant_id: str | None = None
    value: float | None = None
    tie_break_p99: float | None = None
    tie_break_peak_ram_mb: float | None = None
    non_comparable_reason: str | None = None
    # Audit: which variants were eligible / excluded by the correctness filter.
    eligible_variant_ids: tuple[str, ...] = ()
    excluded_variant_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Render the per-language ``bestVariant`` block."""
        return {
            "comparable": self.comparable,
            "criterion": self.criterion,
            "variantId": self.variant_id,
            "value": self.value,
            "tieBreakP99": self.tie_break_p99,
            "tieBreakPeakRamMb": self.tie_break_peak_ram_mb,
            "nonComparableReason": self.non_comparable_reason,
            "eligibleVariants": list(self.eligible_variant_ids),
            "excludedVariants": list(self.excluded_variant_ids),
        }


def _ram_sort_key(peak_ram_mb: float | None) -> float:
    """Tie-break sort value for peak RAM: ``None`` sorts last (worst)."""
    return math.inf if peak_ram_mb is None else peak_ram_mb


def select_best_variant(
    variants: Iterable[VariantSelectionInput],
    criterion: str = DEFAULT_BEST_VARIANT_CRITERION,
) -> BestVariantResult:
    """Select the Best_Variant for one language within one Scenario.

    Considers only eligible variants. Among them the winner has the lowest
    ``criterion`` value (default lowest p50 round-trip), breaking ties by lowest
    p99 latency, then lowest peak RAM, then ``variant_id`` for determinism. When
    no variant is eligible the language is marked non-comparable for the
    Scenario.
    """
    candidates = list(variants)
    eligible = [v for v in candidates if v.eligible]
    excluded_ids = tuple(v.variant_id for v in candidates if not v.eligible)

    if not eligible:
        reason = (
            "no implementation variant passed round-trip correctness in every run"
        )
        return BestVariantResult(
            comparable=False,
            criterion=criterion,
            non_comparable_reason=reason,
            eligible_variant_ids=(),
            excluded_variant_ids=excluded_ids,
        )

    # ``criterion_value`` raises UnknownCriterionError if any eligible variant
    # cannot supply the criterion.
    def sort_key(v: VariantSelectionInput) -> tuple[float, float, float, str]:
        return (
            v.criterion_value(criterion),
            v.p99_ms,
            _ram_sort_key(v.peak_ram_mb),
            v.variant_id,
        )

    winner = min(eligible, key=sort_key)

    return BestVariantResult(
        comparable=True,
        criterion=criterion,
        variant_id=winner.variant_id,
        value=winner.criterion_value(criterion),
        tie_break_p99=winner.p99_ms,
        tie_break_peak_ram_mb=winner.peak_ram_mb,
        eligible_variant_ids=tuple(v.variant_id for v in eligible),
        excluded_variant_ids=excluded_ids,
    )


def select_best_variants_by_language(
    variants_by_language: Mapping[str, Sequence[VariantSelectionInput]],
    criterion: str = DEFAULT_BEST_VARIANT_CRITERION,
) -> dict[str, BestVariantResult]:
    """Select the Best_Variant for each language in a Scenario.

    A language with no eligible variant is marked non-comparable rather than
    omitted, so the report can state it explicitly.
    """
    return {
        language: select_best_variant(variants, criterion)
        for language, variants in variants_by_language.items()
    }
