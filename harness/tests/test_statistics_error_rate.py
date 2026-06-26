"""Unit tests for StatisticsEngine error-rate calculation (task 8.8)."""

import pytest

from harness.contract import RunnerId, RunnerOutput
from harness.metrics import MetricsCollector
from harness.statistics_engine import (
    NOT_APPLICABLE,
    ErrorRate,
    aggregate_error_rate,
    error_rate,
    error_rate_by_runner,
    error_rate_by_variant,
    error_rate_from_failures,
)


# Helpers to build MetricRecords with chosen failure shapes.
def _op(**overrides):
    op = {
        "fileName": "x.txt",
        "fileType": ".txt",
        "originalBytes": 100,
        "skipped": False,
        "roundTripOk": True,
    }
    op.update(overrides)
    return op


def _record(runner="go", variant="go-inmem-single", operations=None):
    payload = {
        "runnerId": runner,
        "variantId": variant,
        "mode": "steady_state",
        "scenarioId": "s1",
        "cryptoProfileId": "p1",
        "concurrency": 1,
        "outputEncoding": "binary",
        "hardwareAccel": False,
        "keySetChecksumSeen": "sha256:" + "ab" * 32,
        "corpusChecksumSeen": "sha256:" + "ab" * 32,
        "operations": operations or [],
    }
    return MetricsCollector().collect(RunnerOutput.from_dict(payload))


def test_error_rate_basic_ratio():
    assert error_rate(1, 4) == pytest.approx(0.25)


def test_error_rate_zero_failures_is_zero():
    assert error_rate(0, 10) == 0.0


def test_error_rate_all_failed_is_one():
    assert error_rate(7, 7) == 1.0


def test_error_rate_in_unit_interval():
    for failed, attempted in [(0, 1), (1, 3), (5, 5), (2, 1000)]:
        r = error_rate(failed, attempted)
        assert isinstance(r, float)
        assert 0.0 <= r <= 1.0


def test_error_rate_attempted_zero_not_applicable():
    assert error_rate(0, 0) == NOT_APPLICABLE


def test_error_rate_rejects_negative_and_overflow():
    with pytest.raises(ValueError):
        error_rate(-1, 5)
    with pytest.raises(ValueError):
        error_rate(2, -5)
    with pytest.raises(ValueError):
        error_rate(6, 5)  # failed cannot exceed attempted


def test_error_rate_from_failures_counts_both_kinds():
    # 2 operation failures + 1 correctness failure out of 10 attempted -> 0.3
    assert error_rate_from_failures(2, 1, 10) == pytest.approx(0.3)


def test_error_rate_from_failures_attempted_zero_not_applicable():
    assert error_rate_from_failures(0, 0, 0) == NOT_APPLICABLE


def test_error_rate_from_failures_rejects_negative():
    with pytest.raises(ValueError):
        error_rate_from_failures(-1, 0, 5)
    with pytest.raises(ValueError):
        error_rate_from_failures(0, -1, 5)


# ErrorRate value object
def test_error_rate_object_applicable():
    er = ErrorRate(failed=3, attempted=12)
    assert er.applicable is True
    assert er.rate == pytest.approx(0.25)
    assert er.report_value() == pytest.approx(0.25)
    assert er.to_dict() == {"errorRate": pytest.approx(0.25), "failedOps": 3, "attemptedOps": 12}


def test_error_rate_object_not_applicable():
    er = ErrorRate(failed=0, attempted=0)
    assert er.applicable is False
    assert er.rate is None
    assert er.report_value() == NOT_APPLICABLE
    assert er.to_dict() == {"errorRate": NOT_APPLICABLE, "failedOps": 0, "attemptedOps": 0}


# Aggregation across records counts both failure kinds, excludes skipped/warm-up
def test_aggregate_counts_operation_and_correctness_failures():
    rec = _record(
        operations=[
            _op(),  # success
            _op(roundTripOk=False, failureType="operation_failure"),
            _op(roundTripOk=False, failureType="correctness_failure"),
            _op(roundTripOk=False),  # implicit correctness failure
            _op(skipped=True, skipReason="control_file"),  # excluded
        ]
    )
    er = aggregate_error_rate([rec])
    assert er.failed == 3  # 1 operation + 2 correctness
    assert er.attempted == 4  # skipped excluded
    assert er.rate == pytest.approx(0.75)


def test_aggregate_empty_is_not_applicable():
    er = aggregate_error_rate([])
    assert er.applicable is False
    assert er.report_value() == NOT_APPLICABLE


def test_aggregate_only_skipped_is_not_applicable():
    rec = _record(operations=[_op(skipped=True, skipReason="control_file")])
    er = aggregate_error_rate([rec])
    assert er.attempted == 0
    assert er.report_value() == NOT_APPLICABLE


def test_error_rate_by_runner_breakdown():
    go_clean = _record(runner="go", variant="go-inmem-single", operations=[_op(), _op()])
    java_bad = _record(
        runner="java",
        variant="java-inmem-single",
        operations=[_op(), _op(roundTripOk=False, failureType="operation_failure")],
    )
    by_runner = error_rate_by_runner([go_clean, java_bad])

    assert by_runner[RunnerId.GO].failed == 0
    assert by_runner[RunnerId.GO].attempted == 2
    assert by_runner[RunnerId.GO].rate == 0.0

    assert by_runner[RunnerId.JAVA].failed == 1
    assert by_runner[RunnerId.JAVA].attempted == 2
    assert by_runner[RunnerId.JAVA].rate == pytest.approx(0.5)


def test_error_rate_by_runner_aggregates_multiple_records_per_runner():
    r1 = _record(runner="go", operations=[_op(), _op(roundTripOk=False)])
    r2 = _record(runner="go", operations=[_op(), _op()])
    by_runner = error_rate_by_runner([r1, r2])
    assert set(by_runner) == {RunnerId.GO}
    assert by_runner[RunnerId.GO].failed == 1
    assert by_runner[RunnerId.GO].attempted == 4
    assert by_runner[RunnerId.GO].rate == pytest.approx(0.25)


def test_error_rate_by_variant_breakdown():
    inmem = _record(variant="go-inmem-single", operations=[_op(), _op()])
    stream = _record(
        variant="go-stream-single",
        operations=[_op(roundTripOk=False, failureType="correctness_failure")],
    )
    by_variant = error_rate_by_variant([inmem, stream])

    assert by_variant["go-inmem-single"].rate == 0.0
    assert by_variant["go-stream-single"].failed == 1
    assert by_variant["go-stream-single"].attempted == 1
    assert by_variant["go-stream-single"].rate == 1.0
