"""Core latency statistics: summary stats, reliability, CI, effect size, head-to-head."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from scipy import stats as _scipy_stats

__all__ = [
    "PERCENTILE_METHOD_LABEL",
    "LATENCY_UNIT",
    "COLD_START_LABEL",
    "EXCLUDING_WARMUP_LABEL",
    "INCLUDING_WARMUP_LABEL",
    "P95_MIN_RELIABLE_SAMPLES",
    "P99_MIN_RELIABLE_SAMPLES",
    "MIN_CI_SAMPLES",
    "INCONCLUSIVE_THRESHOLD_PCT",
    "CI_METHOD_LABEL",
    "EFFECT_SIZE_METHOD_LABEL",
    "LatencyStatistics",
    "OperationStatistics",
    "ColdStartMetric",
    "TwoSetOperationReport",
    "ReliabilityMarking",
    "ConfidenceInterval",
    "HeadToHead",
    "reliability_marking",
    "confidence_interval",
    "effect_size",
    "head_to_head",
    "StatisticsEngine",
]

# Percentiles use the type-7 (Hyndman & Fan) definition, i.e. numpy's default.
PERCENTILE_METHOD_LABEL = "linear_interpolation_type7"
_NUMPY_PERCENTILE_METHOD = "linear"

LATENCY_UNIT = "ms"

# Travels with the supplementary Cold_Start total so it is never read as a
# core/steady-state number.
COLD_START_LABEL = "supplementary_cold_start_not_in_steady_state"

# Labels for the "two sets" report: excluding warm-up is the core/steady-state
# metric, including warm-up is supplementary.
EXCLUDING_WARMUP_LABEL = "core_steady_state_excludes_warmup"
INCLUDING_WARMUP_LABEL = "supplementary_includes_warmup"

# Sample counts below which a percentile is flagged unreliable.
P95_MIN_RELIABLE_SAMPLES = 20
P99_MIN_RELIABLE_SAMPLES = 100

# Minimum samples for a meaningful confidence interval / effect size.
MIN_CI_SAMPLES = 2

# A deciding-metric difference <= 5% is reported as "inconclusive".
INCONCLUSIVE_THRESHOLD_PCT = 5.0

CI_METHOD_LABEL = "student_t_two_sided"
EFFECT_SIZE_METHOD_LABEL = "cohens_d_pooled_sd"


@dataclass(frozen=True)
class LatencyStatistics:
    """Core summary statistics for one set of latency samples (ms).

    :attr:`cv` is ``None`` when the mean is not strictly positive.
    """

    sample_count: int
    minimum: float
    mean: float
    p50: float
    p95: float
    p99: float
    maximum: float
    stddev: float
    cv: float | None
    p95_reliable: bool = True
    p99_reliable: bool = True
    percentile_method: str = PERCENTILE_METHOD_LABEL
    unit: str = LATENCY_UNIT

    def to_dict(self) -> dict[str, Any]:
        """Render the JSON shape used in ``results.json``."""
        return {
            "applicable": True,
            "sampleCount": self.sample_count,
            "unit": self.unit,
            "percentileMethod": self.percentile_method,
            "min": self.minimum,
            "mean": self.mean,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "max": self.maximum,
            "stddev": self.stddev,
            "cv": self.cv,
            "p95Reliable": self.p95_reliable,
            "p99Reliable": self.p99_reliable,
        }


@dataclass(frozen=True)
class OperationStatistics:
    """Encrypt + decrypt statistics for one Scenario / aggregation."""

    encrypt: LatencyStatistics | None
    decrypt: LatencyStatistics | None

    def to_dict(self) -> dict[str, Any]:
        """Render both operation blocks; absent sets show ``applicable=False``."""
        return {
            "encrypt": self._block(self.encrypt),
            "decrypt": self._block(self.decrypt),
        }

    @staticmethod
    def _block(stats: LatencyStatistics | None) -> dict[str, Any]:
        if stats is None:
            return {
                "applicable": False,
                "sampleCount": 0,
                "unit": LATENCY_UNIT,
                "percentileMethod": PERCENTILE_METHOD_LABEL,
            }
        return stats.to_dict()


@dataclass(frozen=True)
class ColdStartMetric:
    """Supplementary Cold_Start total — kept strictly separate from core stats.

    All values are in milliseconds. :attr:`jit_warmup_ms` is ``None`` when the
    runtime exposes no JIT warm-up figure; :attr:`total_cold_start_ms` is then
    just the process startup time, and ``None`` when no component is available.
    """

    process_startup_ms: float | None
    jit_warmup_ms: float | None
    total_cold_start_ms: float | None
    label: str = COLD_START_LABEL
    unit: str = LATENCY_UNIT

    def to_dict(self) -> dict[str, Any]:
        """Render the ``coldStart`` block used in ``results.json``."""
        return {
            "processStartupMs": self.process_startup_ms,
            "jitWarmupMs": self.jit_warmup_ms,
            "totalColdStartMs": self.total_cold_start_ms,
            "label": self.label,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class TwoSetOperationReport:
    """Two explicitly-labelled statistic sets: excluding vs including warm-up.

    :attr:`excluding_warmup` is always the core set (recorded post-warm-up
    samples only). :attr:`including_warmup` folds the warm-up samples back in;
    when none were supplied it is identical to the core set and
    :attr:`warmup_samples_supplied` is ``False``.
    """

    excluding_warmup: OperationStatistics
    including_warmup: OperationStatistics
    warmup_samples_supplied: bool

    def to_dict(self) -> dict[str, Any]:
        """Render both labelled sets."""
        excluding = self.excluding_warmup.to_dict()
        excluding["label"] = EXCLUDING_WARMUP_LABEL
        including = self.including_warmup.to_dict()
        including["label"] = INCLUDING_WARMUP_LABEL
        return {
            "excludingWarmup": excluding,
            "includingWarmup": including,
            "warmupSamplesSupplied": self.warmup_samples_supplied,
        }


class StatisticsEngine:
    """Compute core latency statistics from raw per-operation samples.

    Stateless. Percentiles use linear interpolation type-7; standard deviation
    is the sample standard deviation (``ddof=1``), reported as ``0.0`` for a
    single sample so the ``stddev >= 0`` invariant holds.
    """

    def compute(self, samples: Sequence[float] | None) -> LatencyStatistics | None:
        """Compute core statistics for one latency sample set (ms).

        Returns ``None`` for an empty / ``None`` input.
        """
        if not samples:
            return None

        data = np.asarray(samples, dtype=float)
        count = int(data.size)

        minimum = float(np.min(data))
        maximum = float(np.max(data))
        mean = float(np.mean(data))

        p50, p95, p99 = (
            float(value)
            for value in np.percentile(
                data, (50, 95, 99), method=_NUMPY_PERCENTILE_METHOD
            )
        )

        # Sample standard deviation (ddof=1); undefined for n<2 -> 0.0.
        if count < 2:
            stddev = 0.0
        else:
            stddev = float(np.std(data, ddof=1))
        if stddev < 0.0:
            stddev = 0.0

        cv = stddev / mean if mean > 0.0 else None

        marking = reliability_marking(count)

        return LatencyStatistics(
            sample_count=count,
            minimum=minimum,
            mean=mean,
            p50=p50,
            p95=p95,
            p99=p99,
            maximum=maximum,
            stddev=stddev,
            cv=cv,
            p95_reliable=marking.p95_reliable,
            p99_reliable=marking.p99_reliable,
        )

    def compute_operations(
        self,
        encrypt_samples: Sequence[float] | None,
        decrypt_samples: Sequence[float] | None,
    ) -> OperationStatistics:
        """Compute encrypt and decrypt statistics separately."""
        return OperationStatistics(
            encrypt=self.compute(encrypt_samples),
            decrypt=self.compute(decrypt_samples),
        )

    def compute_for_record(self, record: Any) -> OperationStatistics:
        """Compute core/steady-state statistics from a ``MetricRecord``.

        Uses the record's retained per-operation samples; skipped operations
        are already excluded. Never includes process startup / JIT warm-up cost;
        use :meth:`cold_start_for_record` for the supplementary Cold_Start total.
        """
        return self.compute_operations(
            record.encrypt_samples_ms(),
            record.decrypt_samples_ms(),
        )

    def cold_start_metric(
        self,
        process_startup_ms: float | None,
        jit_warmup_ms: float | None = None,
    ) -> ColdStartMetric | None:
        """Build the supplementary :class:`ColdStartMetric`.

        ``total_cold_start_ms`` sums the available components (startup + JIT
        warm-up). Returns ``None`` when neither component is available.
        """
        if process_startup_ms is None and jit_warmup_ms is None:
            return None
        components = [v for v in (process_startup_ms, jit_warmup_ms) if v is not None]
        total = float(sum(components)) if components else None
        return ColdStartMetric(
            process_startup_ms=process_startup_ms,
            jit_warmup_ms=jit_warmup_ms,
            total_cold_start_ms=total,
        )

    def cold_start_for_record(
        self,
        record: Any,
        jit_warmup_ms: float | None = None,
    ) -> ColdStartMetric | None:
        """Cold_Start metric from a ``MetricRecord``.

        Combines the record's ``process_startup_ms`` with an optional
        ``jit_warmup_ms``. Returns ``None`` when neither is available.
        """
        return self.cold_start_metric(
            getattr(record, "process_startup_ms", None),
            jit_warmup_ms,
        )

    def compute_two_sets(
        self,
        encrypt_recorded: Sequence[float] | None,
        decrypt_recorded: Sequence[float] | None,
        *,
        encrypt_warmup: Sequence[float] | None = None,
        decrypt_warmup: Sequence[float] | None = None,
    ) -> TwoSetOperationReport:
        """Produce the excluding- and including-warm-up statistic sets.

        ``*_recorded`` (post-warm-up samples) form the excluding-warm-up set.
        ``*_warmup``, when supplied, are folded back in to form the
        including-warm-up set; otherwise both sets coincide and
        ``warmup_samples_supplied`` is ``False``.
        """
        excluding = self.compute_operations(encrypt_recorded, decrypt_recorded)

        enc_warm = list(encrypt_warmup or ())
        dec_warm = list(decrypt_warmup or ())
        supplied = bool(enc_warm or dec_warm)
        if not supplied:
            including = excluding
        else:
            including = self.compute_operations(
                enc_warm + list(encrypt_recorded or ()),
                dec_warm + list(decrypt_recorded or ()),
            )
        return TwoSetOperationReport(
            excluding_warmup=excluding,
            including_warmup=including,
            warmup_samples_supplied=supplied,
        )

    def compute_two_sets_for_record(
        self,
        record: Any,
        warmup_record: Any | None = None,
    ) -> TwoSetOperationReport:
        """Two-set report from recorded and (optional) warm-up Metric_Records.

        Without ``warmup_record`` the two sets coincide.
        """
        enc_warm = warmup_record.encrypt_samples_ms() if warmup_record is not None else None
        dec_warm = warmup_record.decrypt_samples_ms() if warmup_record is not None else None
        return self.compute_two_sets(
            record.encrypt_samples_ms(),
            record.decrypt_samples_ms(),
            encrypt_warmup=enc_warm,
            decrypt_warmup=dec_warm,
        )


@dataclass(frozen=True)
class ReliabilityMarking:
    """Whether p95/p99 are backed by enough samples to be trusted.

    p95 needs at least :data:`P95_MIN_RELIABLE_SAMPLES` samples and p99 at least
    :data:`P99_MIN_RELIABLE_SAMPLES`.
    """

    sample_count: int
    p95_reliable: bool
    p99_reliable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sampleCount": self.sample_count,
            "p95Reliable": self.p95_reliable,
            "p99Reliable": self.p99_reliable,
            "p95MinSamples": P95_MIN_RELIABLE_SAMPLES,
            "p99MinSamples": P99_MIN_RELIABLE_SAMPLES,
        }


def reliability_marking(sample_count: int) -> ReliabilityMarking:
    """Mark p95 / p99 reliable based on the sample count.

    p95 is reliable iff ``sample_count >= 20`` and p99 iff
    ``sample_count >= 100`` (boundaries inclusive). A negative count is ``0``.
    """
    n = max(int(sample_count), 0)
    return ReliabilityMarking(
        sample_count=n,
        p95_reliable=n >= P95_MIN_RELIABLE_SAMPLES,
        p99_reliable=n >= P99_MIN_RELIABLE_SAMPLES,
    )


@dataclass(frozen=True)
class ConfidenceInterval:
    """A two-sided Student-t confidence interval for the mean (ms).

    ``reliable`` is ``False`` when there were too few samples (``n < 2``).
    """

    level: float
    mean: float
    low: float
    high: float
    sample_count: int
    reliable: bool
    method: str = CI_METHOD_LABEL

    def to_dict(self) -> dict[str, Any]:
        """Render the ``confidenceInterval`` block."""
        return {
            "level": self.level,
            "mean": self.mean,
            "low": self.low,
            "high": self.high,
            "sampleCount": self.sample_count,
            "reliable": self.reliable,
            "method": self.method,
        }


def confidence_interval(
    samples: Sequence[float] | None,
    level: float = 0.95,
) -> ConfidenceInterval | None:
    """Two-sided Student-t confidence interval for the mean.

    ``level`` is the confidence level (default ``0.95``) and must lie in
    ``(0, 1)``. Returns ``None`` for empty / ``None`` input. With a single
    sample the interval collapses to the mean and is flagged ``reliable=False``.

    Raises ``ValueError`` if ``level`` is not in ``(0, 1)``.
    """
    if not 0.0 < level < 1.0:
        raise ValueError(f"confidence level must be in (0, 1), got {level}")
    if not samples:
        return None

    data = np.asarray(samples, dtype=float)
    count = int(data.size)
    mean = float(np.mean(data))

    if count < MIN_CI_SAMPLES:
        # Not enough samples; collapse the bounds onto the mean.
        return ConfidenceInterval(
            level=level,
            mean=mean,
            low=mean,
            high=mean,
            sample_count=count,
            reliable=False,
        )

    stddev = float(np.std(data, ddof=1))
    standard_error = stddev / np.sqrt(count)
    t_crit = float(_scipy_stats.t.ppf(0.5 + level / 2.0, df=count - 1))
    margin = t_crit * standard_error
    return ConfidenceInterval(
        level=level,
        mean=mean,
        low=mean - margin,
        high=mean + margin,
        sample_count=count,
        reliable=True,
    )


def effect_size(
    samples_a: Sequence[float] | None,
    samples_b: Sequence[float] | None,
) -> float | None:
    """Cohen's *d* effect size between two sample sets.

    ``d = (mean_a - mean_b) / pooled_sd``. Returns ``None`` when either set has
    fewer than 2 samples, or when the pooled standard deviation is 0 while the
    means differ; returns ``0.0`` when both means are equal.
    """
    if not samples_a or not samples_b:
        return None

    a = np.asarray(samples_a, dtype=float)
    b = np.asarray(samples_b, dtype=float)
    n_a = int(a.size)
    n_b = int(b.size)
    if n_a < 2 or n_b < 2:
        return None

    mean_a = float(np.mean(a))
    mean_b = float(np.mean(b))
    mean_diff = mean_a - mean_b

    var_a = float(np.var(a, ddof=1))
    var_b = float(np.var(b, ddof=1))
    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
    pooled_sd = np.sqrt(pooled_var)

    if pooled_sd == 0.0:
        # No spread: identical means -> 0.0; differing means -> undefined.
        return 0.0 if mean_diff == 0.0 else None

    return float(mean_diff / pooled_sd)


@dataclass(frozen=True)
class HeadToHead:
    """Head-to-head verdict between two deciding-metric values.

    When ``diff_pct <= 5`` the result is ``inconclusive`` and ``winner`` is
    ``None``; otherwise ``winner`` names the side with the lower (faster) value.
    """

    winner: str | None
    diff_pct: float
    inconclusive: bool
    value_a: float
    value_b: float
    label_a: str
    label_b: str
    decided_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Render the ``headToHead`` verdict fields."""
        result = {
            "winner": self.winner,
            "diffPct": self.diff_pct,
            "inconclusive": self.inconclusive,
            self.label_a: self.value_a,
            self.label_b: self.value_b,
        }
        if self.decided_by is not None:
            result["decidedBy"] = self.decided_by
        return result


def head_to_head(
    value_a: float,
    value_b: float,
    *,
    label_a: str = "go",
    label_b: str = "java",
    decided_by: str | None = None,
) -> HeadToHead:
    """Apply the inconclusive-5% rule to two deciding-metric values.

    Lower is faster/better. ``diff_pct`` is ``|a - b| / max(|a|, |b|) * 100``.

    * ``diff_pct <= 5`` -> ``inconclusive=True``, ``winner=None`` (5% inclusive).
    * ``diff_pct > 5``  -> ``winner`` is the lower-value (faster) side.

    Equal values (including both zero) are inconclusive.
    """
    diff = abs(value_a - value_b)
    base = max(abs(value_a), abs(value_b))
    diff_pct = 0.0 if base == 0.0 else (diff / base) * 100.0

    inconclusive = diff_pct <= INCONCLUSIVE_THRESHOLD_PCT
    if inconclusive:
        winner: str | None = None
    else:
        winner = label_a if value_a < value_b else label_b

    return HeadToHead(
        winner=winner,
        diff_pct=diff_pct,
        inconclusive=inconclusive,
        value_a=value_a,
        value_b=value_b,
        label_a=label_a,
        label_b=label_b,
        decided_by=decided_by,
    )
