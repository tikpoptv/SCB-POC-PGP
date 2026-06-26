"""Fairness invariant checker — verify equal inputs/config across a Scenario.

Confirms that every Runner and Implementation_Variant compared within one
Scenario ran under identical conditions, and propagates non-comparable status
(with a specific reason) for anything that is not, keeping the offending run out
of head-to-head conclusions.

The dimensions that must match for a fair comparison: Key_Set checksum,
Test_Corpus checksum, Crypto_Profile, concurrency level, output encoding,
hardware acceleration, and resource quota.

This component is pure (no I/O, no crypto): it only inspects the fairness
context already captured on each run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from harness.contract.models import CryptoProfile, OutputEncoding, RunnerId
from harness.scheduler import ResourceQuota

__all__ = [
    "FairnessDimensions",
    "RunDescriptor",
    "RunComparability",
    "FairnessResult",
    "check_fairness",
]


@dataclass(frozen=True)
class FairnessDimensions:
    """Every dimension that must be identical across a Scenario.

    Two runs are fair to compare only when all of these match exactly (and the
    resource-quota difference is 0).
    """

    key_set_checksum: str
    corpus_checksum: str
    crypto_profile: CryptoProfile
    concurrency: int
    output_encoding: OutputEncoding
    hardware_accel: bool
    resource_quota: ResourceQuota


@dataclass(frozen=True)
class RunDescriptor:
    """One Runner/variant run plus its fairness context.

    ``prior_non_comparable_reasons`` carries any anomaly already known for this
    run; those are propagated onto the fairness result so the run is excluded
    from conclusions.
    """

    runner_id: RunnerId
    variant_id: str
    dimensions: FairnessDimensions
    prior_non_comparable_reasons: tuple[str, ...] = ()

    @classmethod
    def from_metric_record(
        cls,
        record: "object",
        crypto_profile: CryptoProfile,
        resource_quota: ResourceQuota,
    ) -> "RunDescriptor":
        """Build a descriptor from a :class:`~harness.metrics.MetricRecord`.

        The Metric_Record carries the per-run fairness context and any
        non-comparable reasons already accumulated, but not the full
        :class:`CryptoProfile` (only its id) nor the :class:`ResourceQuota` —
        those are supplied by the caller from the Scenario/scheduler.
        """
        dimensions = FairnessDimensions(
            key_set_checksum=record.key_set_checksum_seen,
            corpus_checksum=record.corpus_checksum_seen,
            crypto_profile=crypto_profile,
            concurrency=record.concurrency,
            output_encoding=record.output_encoding,
            hardware_accel=record.hardware_accel,
            resource_quota=resource_quota,
        )
        return cls(
            runner_id=record.runner_id,
            variant_id=record.variant_id,
            dimensions=dimensions,
            prior_non_comparable_reasons=tuple(record.all_non_comparable_reasons()),
        )

    @property
    def label(self) -> str:
        """Human-friendly ``runner=<id> variant='<id>'`` tag for reasons."""
        return f"runner={self.runner_id.value} variant={self.variant_id!r}"


@dataclass(frozen=True)
class RunComparability:
    """Comparability verdict for a single run within the Scenario."""

    runner_id: RunnerId
    variant_id: str
    comparable: bool
    non_comparable_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "runnerId": self.runner_id.value,
            "variantId": self.variant_id,
            "comparable": self.comparable,
            "nonComparableReasons": list(self.non_comparable_reasons),
        }


@dataclass(frozen=True)
class FairnessResult:
    """Result of the fairness check for one Scenario (Result_Report shape).

    ``comparable`` is True only when every run shares identical fairness
    dimensions and no run carries a propagated anomaly. ``non_comparable_reasons``
    aggregates the Scenario-level reasons. Per-run verdicts live on :attr:`runs`;
    :attr:`comparable_runs` is the subset that may enter head-to-head conclusions.
    """

    scenario_id: str
    comparable: bool
    non_comparable_reasons: tuple[str, ...]
    runs: tuple[RunComparability, ...]

    @property
    def comparable_runs(self) -> tuple[RunComparability, ...]:
        """Runs that are safe to include in the Scenario's conclusion."""
        return tuple(r for r in self.runs if r.comparable)

    @property
    def excluded_runs(self) -> tuple[RunComparability, ...]:
        """Runs excluded from the conclusion because they are non-comparable."""
        return tuple(r for r in self.runs if not r.comparable)

    def to_dict(self) -> dict[str, object]:
        return {
            "scenarioId": self.scenario_id,
            "comparable": self.comparable,
            "nonComparableReasons": list(self.non_comparable_reasons),
            "runs": [r.to_dict() for r in self.runs],
        }


@dataclass(frozen=True)
class _Dimension:
    """A single comparable dimension: how to read it and which Req it backs."""

    name: str
    requirement: str
    get: Callable[[FairnessDimensions], object]


#: Every scalar dimension that must match across a Scenario. The resource quota
#: is handled separately so its differing sub-fields can be reported individually.
_DIMENSIONS: tuple[_Dimension, ...] = (
    _Dimension("keySetChecksum", "Req 4.1, 31.2", lambda d: d.key_set_checksum),
    _Dimension("corpusChecksum", "Req 4.2, 30.2", lambda d: d.corpus_checksum),
    _Dimension("cryptoProfile.pubAlg", "Req 4.3, 14.3, 31.2", lambda d: d.crypto_profile.pub_alg),
    _Dimension("cryptoProfile.cipher", "Req 4.3, 18.4", lambda d: d.crypto_profile.cipher),
    _Dimension("cryptoProfile.compression", "Req 4.3, 18.4", lambda d: d.crypto_profile.compression),
    _Dimension("cryptoProfile.hash", "Req 4.3", lambda d: d.crypto_profile.hash),
    _Dimension("concurrency", "Req 16.2", lambda d: d.concurrency),
    _Dimension("outputEncoding", "Req 4.7", lambda d: d.output_encoding),
    _Dimension("hardwareAccel", "Req 23.4", lambda d: d.hardware_accel),
)


def _value_repr(value: object) -> str:
    """Stable repr for a dimension value (unwrap enums to their value)."""
    if isinstance(value, OutputEncoding):
        return repr(value.value)
    return repr(value)


def _dimension_reasons(
    run: RunDescriptor, reference: FairnessDimensions
) -> list[str]:
    """Reasons for every dimension on ``run`` that differs from ``reference``."""
    reasons: list[str] = []
    for dim in _DIMENSIONS:
        ref_val = dim.get(reference)
        got_val = dim.get(run.dimensions)
        if ref_val != got_val:
            reasons.append(
                f"{dim.name} mismatch for {run.label}: "
                f"expected {_value_repr(ref_val)}, got {_value_repr(got_val)} "
                f"({dim.requirement})"
            )
    # Resource quota: report the exact differing sub-fields.
    quota_diff = reference.resource_quota.difference(run.dimensions.resource_quota)
    if quota_diff:
        reasons.append(
            f"resourceQuota mismatch for {run.label}: {quota_diff} "
            f"(Req 3.4 requires the difference to be 0)"
        )
    return reasons


def check_fairness(
    scenario_id: str,
    runs: Iterable[RunDescriptor],
    *,
    expected: FairnessDimensions | None = None,
) -> FairnessResult:
    """Verify all runs in a Scenario share identical fairness dimensions.

    Every Runner/variant in ``runs`` is checked against a reference set of
    :class:`FairnessDimensions`. When ``expected`` is given it is the reference;
    otherwise the first run's dimensions are used. A run that differs on any
    dimension — or that carries a propagated anomaly in
    ``prior_non_comparable_reasons`` — is marked non-comparable with a reason
    naming the differing dimension and Runner, and the whole Scenario is marked
    non-comparable so that run is excluded from the head-to-head conclusion.

    An empty ``runs`` collection yields a non-comparable Scenario.
    """
    run_list: Sequence[RunDescriptor] = list(runs)

    if not run_list:
        return FairnessResult(
            scenario_id=scenario_id,
            comparable=False,
            non_comparable_reasons=("no runs to compare for this Scenario",),
            runs=(),
        )

    reference = expected if expected is not None else run_list[0].dimensions

    run_verdicts: list[RunComparability] = []
    scenario_reasons: list[str] = []

    for run in run_list:
        reasons: list[str] = []
        # Dimension mismatches vs the reference.
        reasons.extend(_dimension_reasons(run, reference))
        # Propagated anomalies already known for this run — keep them on the
        # verdict so the run is excluded.
        for prior in run.prior_non_comparable_reasons:
            if prior not in reasons:
                reasons.append(prior)

        comparable = not reasons
        run_verdicts.append(
            RunComparability(
                runner_id=run.runner_id,
                variant_id=run.variant_id,
                comparable=comparable,
                non_comparable_reasons=tuple(reasons),
            )
        )
        for reason in reasons:
            if reason not in scenario_reasons:
                scenario_reasons.append(reason)

    return FairnessResult(
        scenario_id=scenario_id,
        comparable=not scenario_reasons,
        non_comparable_reasons=tuple(scenario_reasons),
        runs=tuple(run_verdicts),
    )
