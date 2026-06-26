"""VerificationGate — correctness/integrity gate that runs before statistics.

Enforces the anti-fake guarantee: no timing enters the performance statistics
until the run clears the integrity gates. Implements three gates — checksum,
version, and round-trip correctness — producing value objects the
StatisticsEngine consumes to decide which runs feed the statistics. The gate is
pure and side-effect free. Cross-language/gpg interoperability is a separate gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Protocol, runtime_checkable

from harness.contract.models import FailureType, OperationSample, RunnerId

__all__ = [
    "ExclusionCategory",
    "FileFailure",
    "VerificationResult",
    "VerificationSummary",
    "VerificationGate",
]


@runtime_checkable
class VerifiableRun(Protocol):
    """Minimal shape the gate needs from a run.

    Both :class:`~harness.contract.RunnerOutput` and
    :class:`~harness.metrics.MetricRecord` satisfy this Protocol.
    """

    runner_id: RunnerId
    variant_id: str
    scenario_id: str
    key_set_checksum_seen: str
    corpus_checksum_seen: str
    operations: tuple[OperationSample, ...]


@runtime_checkable
class VersionReportLike(Protocol):
    """Minimal shape the gate needs from a VersionReport."""

    version_match: bool

    def mismatch_messages(self) -> list[str]: ...


class ExclusionCategory(str, Enum):
    """Why a run's timings were excluded from the performance statistics."""

    CHECKSUM_MISMATCH = "checksum_mismatch"
    VERSION_MISMATCH = "version_mismatch"
    CORRECTNESS_FAILURE = "correctness_failure"


@dataclass(frozen=True)
class FileFailure:
    """One per-file failure with full traceability."""

    file_name: str
    failure_type: FailureType
    runner_id: RunnerId
    variant_id: str
    scenario_id: str

    @property
    def is_correctness(self) -> bool:
        return self.failure_type is FailureType.CORRECTNESS_FAILURE

    @property
    def is_operation(self) -> bool:
        return self.failure_type is FailureType.OPERATION_FAILURE

    def to_dict(self) -> dict[str, Any]:
        return {
            "fileName": self.file_name,
            "failureType": self.failure_type.value,
            "runnerId": self.runner_id.value,
            "variantId": self.variant_id,
            "scenarioId": self.scenario_id,
        }


@dataclass(frozen=True)
class VerificationResult:
    """Per-run gate outcome consumed by the StatisticsEngine.

    ``excluded`` is the headline signal: when ``True`` the run's timings MUST
    NOT enter the performance statistics.
    """

    runner_id: RunnerId
    variant_id: str
    scenario_id: str

    checksum_match: bool
    version_match: bool
    # True when every non-skipped file round-tripped byte-for-byte.
    round_trip_ok: bool

    # Excluded from performance statistics (any gate failed).
    excluded: bool
    categories: tuple[ExclusionCategory, ...]
    reasons: tuple[str, ...]

    # Error-rate accounting — counted regardless of exclusion.
    operation_failures: int
    correctness_failures: int
    affected_files: tuple[str, ...]
    failures: tuple[FileFailure, ...]

    @property
    def included(self) -> bool:
        """True when this run's timings are eligible for the statistics."""
        return not self.excluded

    @property
    def comparable(self) -> bool:
        """False when a checksum/version gate marks the run non-comparable.

        A pure correctness failure excludes the timings but the run is still a
        comparable attempt; a checksum/version mismatch is not comparable at all.
        """
        return self.checksum_match and self.version_match

    @property
    def affected_file_count(self) -> int:
        return len(self.affected_files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runnerId": self.runner_id.value,
            "variantId": self.variant_id,
            "scenarioId": self.scenario_id,
            "checksumMatch": self.checksum_match,
            "versionMatch": self.version_match,
            "roundTripOk": self.round_trip_ok,
            "excluded": self.excluded,
            "comparable": self.comparable,
            "categories": [c.value for c in self.categories],
            "reasons": list(self.reasons),
            "operationFailures": self.operation_failures,
            "correctnessFailures": self.correctness_failures,
            "affectedFiles": list(self.affected_files),
            "affectedFileCount": self.affected_file_count,
            "failures": [f.to_dict() for f in self.failures],
        }


@dataclass(frozen=True)
class VerificationSummary:
    """Aggregate gate outcome across many runs.

    The StatisticsEngine consumes :meth:`included_results` to know which runs
    feed the statistics; the excluded counts are surfaced in the Result_Report.
    """

    results: tuple[VerificationResult, ...]

    @property
    def total_runs(self) -> int:
        return len(self.results)

    @property
    def excluded_runs(self) -> int:
        """Number of Benchmark_Runs excluded for any reason."""
        return sum(1 for r in self.results if r.excluded)

    @property
    def included_runs(self) -> int:
        return sum(1 for r in self.results if r.included)

    @property
    def correctness_excluded_runs(self) -> int:
        """Runs excluded specifically because of a correctness failure."""
        return sum(
            1
            for r in self.results
            if ExclusionCategory.CORRECTNESS_FAILURE in r.categories
        )

    @property
    def checksum_excluded_runs(self) -> int:
        return sum(
            1 for r in self.results if ExclusionCategory.CHECKSUM_MISMATCH in r.categories
        )

    @property
    def version_excluded_runs(self) -> int:
        return sum(
            1 for r in self.results if ExclusionCategory.VERSION_MISMATCH in r.categories
        )

    @property
    def affected_files(self) -> int:
        """Total files affected by correctness failures across all runs."""
        return sum(r.affected_file_count for r in self.results)

    @property
    def operation_failures(self) -> int:
        return sum(r.operation_failures for r in self.results)

    @property
    def correctness_failures(self) -> int:
        return sum(r.correctness_failures for r in self.results)

    def included_results(self) -> tuple[VerificationResult, ...]:
        """Results whose timings may enter the performance statistics."""
        return tuple(r for r in self.results if r.included)

    def excluded_results(self) -> tuple[VerificationResult, ...]:
        return tuple(r for r in self.results if r.excluded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "totalRuns": self.total_runs,
            "includedRuns": self.included_runs,
            "excludedRuns": self.excluded_runs,
            "correctnessExcludedRuns": self.correctness_excluded_runs,
            "checksumExcludedRuns": self.checksum_excluded_runs,
            "versionExcludedRuns": self.version_excluded_runs,
            "affectedFiles": self.affected_files,
            "operationFailures": self.operation_failures,
            "correctnessFailures": self.correctness_failures,
            "results": [r.to_dict() for r in self.results],
        }


class VerificationGate:
    """Run the checksum, version, and round-trip correctness gates.

    A ``None`` reference is treated as "nothing to verify against" and never
    excludes a run.
    """

    def __init__(
        self,
        key_set_checksum: str | None = None,
        corpus_checksum: str | None = None,
        version_report: VersionReportLike | None = None,
    ) -> None:
        self.key_set_checksum = key_set_checksum
        self.corpus_checksum = corpus_checksum
        self.version_report = version_report

    def verify(self, run: VerifiableRun) -> VerificationResult:
        """Apply all three gates to one run and return its outcome."""
        categories: list[ExclusionCategory] = []
        reasons: list[str] = []

        checksum_match = self._check_checksums(run, reasons, categories)
        version_match = self._check_version(reasons, categories)

        failures = self._classify_failures(run)
        correctness = tuple(f for f in failures if f.is_correctness)
        operation = tuple(f for f in failures if f.is_operation)
        affected_files = tuple(dict.fromkeys(f.file_name for f in correctness))
        round_trip_ok = len(correctness) == 0

        if not round_trip_ok:
            categories.append(ExclusionCategory.CORRECTNESS_FAILURE)
            reasons.append(
                f"correctness failure: {len(correctness)} file(s) failed round-trip "
                f"({', '.join(affected_files)})"
            )

        excluded = len(categories) > 0

        return VerificationResult(
            runner_id=run.runner_id,
            variant_id=run.variant_id,
            scenario_id=run.scenario_id,
            checksum_match=checksum_match,
            version_match=version_match,
            round_trip_ok=round_trip_ok,
            excluded=excluded,
            categories=tuple(categories),
            reasons=tuple(reasons),
            operation_failures=len(operation),
            correctness_failures=len(correctness),
            affected_files=affected_files,
            failures=failures,
        )

    def verify_all(self, runs: Iterable[VerifiableRun]) -> VerificationSummary:
        """Verify a collection of runs and aggregate the exclusion counts."""
        return VerificationSummary(results=tuple(self.verify(run) for run in runs))

    def _check_checksums(
        self,
        run: VerifiableRun,
        reasons: list[str],
        categories: list[ExclusionCategory],
    ) -> bool:
        """Compare the checksums the Runner saw against the references."""
        mismatched = False

        if self.key_set_checksum is not None and (
            run.key_set_checksum_seen != self.key_set_checksum
        ):
            mismatched = True
            reasons.append(
                "key set checksum mismatch: runner saw "
                f"{run.key_set_checksum_seen!r}, expected {self.key_set_checksum!r}"
            )

        if self.corpus_checksum is not None and (
            run.corpus_checksum_seen != self.corpus_checksum
        ):
            mismatched = True
            reasons.append(
                "corpus checksum mismatch: runner saw "
                f"{run.corpus_checksum_seen!r}, expected {self.corpus_checksum!r}"
            )

        if mismatched:
            categories.append(ExclusionCategory.CHECKSUM_MISMATCH)
            return False
        return True

    def _check_version(
        self,
        reasons: list[str],
        categories: list[ExclusionCategory],
    ) -> bool:
        """Validate recorded vs detected versions."""
        if self.version_report is None:
            return True
        if self.version_report.version_match:
            return True

        categories.append(ExclusionCategory.VERSION_MISMATCH)
        messages = self.version_report.mismatch_messages()
        if messages:
            reasons.extend(messages)
        else:
            reasons.append("version mismatch: detected versions do not match recorded values")
        return False

    def _classify_failures(self, run: VerifiableRun) -> tuple[FileFailure, ...]:
        """Classify every non-skipped operation into correctness/operation failures."""
        failures: list[FileFailure] = []
        for op in run.operations:
            if op.skipped:
                continue
            failure_type = self._failure_type_for(op)
            if failure_type is None:
                continue
            failures.append(
                FileFailure(
                    file_name=op.file_name,
                    failure_type=failure_type,
                    runner_id=run.runner_id,
                    variant_id=run.variant_id,
                    scenario_id=run.scenario_id,
                )
            )
        return tuple(failures)

    @staticmethod
    def _failure_type_for(op: OperationSample) -> FailureType | None:
        """Return the failure classification for one operation, or ``None``."""
        if op.failure_type is FailureType.OPERATION_FAILURE:
            return FailureType.OPERATION_FAILURE
        if op.failure_type is FailureType.CORRECTNESS_FAILURE:
            return FailureType.CORRECTNESS_FAILURE
        if not op.round_trip_ok:
            # Round-trip mismatch without an explicit type is a correctness failure.
            return FailureType.CORRECTNESS_FAILURE
        return None
