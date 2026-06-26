"""Unit tests for the StatisticsEngine core statistics (task 8.1)."""

import math

import numpy as np
import pytest

from harness.statistics import (
    LATENCY_UNIT,
    PERCENTILE_METHOD_LABEL,
    LatencyStatistics,
    OperationStatistics,
    StatisticsEngine,
)


@pytest.fixture
def engine():
    return StatisticsEngine()


# Known reference values (hand-computed type-7 percentiles)
def test_known_reference_values_five_samples(engine):
    # data = [1, 2, 3, 4, 5]; type-7 percentiles computed by hand:
    #   p50 -> rank 4*0.50 = 2.00 -> x[2]                 = 3.0
    #   p95 -> rank 4*0.95 = 3.80 -> x[3] + 0.80*(x4-x3)  = 4.8
    #   p99 -> rank 4*0.99 = 3.96 -> x[3] + 0.96*(x4-x3)  = 4.96
    #   sample stddev (ddof=1) = sqrt(10/4) = 1.5811388300841898
    stats = engine.compute([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats is not None
    assert stats.sample_count == 5
    assert stats.minimum == 1.0
    assert stats.maximum == 5.0
    assert stats.mean == pytest.approx(3.0)
    assert stats.p50 == pytest.approx(3.0)
    assert stats.p95 == pytest.approx(4.8)
    assert stats.p99 == pytest.approx(4.96)
    assert stats.stddev == pytest.approx(1.5811388300841898)
    assert stats.cv == pytest.approx(1.5811388300841898 / 3.0)


def test_known_reference_values_ten_samples(engine):
    # data = [1..10]; p50=5.5, p95=9.55, p99=9.91 (type-7).
    stats = engine.compute([float(i) for i in range(1, 11)])
    assert stats is not None
    assert stats.p50 == pytest.approx(5.5)
    assert stats.p95 == pytest.approx(9.55)
    assert stats.p99 == pytest.approx(9.91)


def test_matches_numpy_linear_method(engine):
    # Reference algorithm check: percentiles equal numpy method="linear" (type-7).
    rng = np.random.default_rng(1234)
    data = (rng.random(500) * 50.0).tolist()
    stats = engine.compute(data)
    assert stats is not None
    assert stats.p50 == pytest.approx(float(np.percentile(data, 50, method="linear")))
    assert stats.p95 == pytest.approx(float(np.percentile(data, 95, method="linear")))
    assert stats.p99 == pytest.approx(float(np.percentile(data, 99, method="linear")))


def test_records_method_count_and_unit(engine):
    stats = engine.compute([2.0, 4.0, 6.0])
    assert stats is not None
    assert stats.percentile_method == PERCENTILE_METHOD_LABEL == "linear_interpolation_type7"
    assert stats.unit == LATENCY_UNIT == "ms"
    assert stats.sample_count == 3
    d = stats.to_dict()
    assert d["applicable"] is True
    assert d["percentileMethod"] == "linear_interpolation_type7"
    assert d["unit"] == "ms"
    assert d["sampleCount"] == 3


# Invariants (Property 7 illustrated as examples; full property test is 8.2)
def test_invariants_hold_on_example(engine):
    stats = engine.compute([5.0, 1.0, 9.0, 3.0, 7.0, 2.0])
    assert stats is not None
    assert stats.minimum <= stats.p50 <= stats.p95 <= stats.p99 <= stats.maximum
    assert stats.minimum <= stats.mean <= stats.maximum
    assert stats.stddev >= 0.0
    assert stats.cv == pytest.approx(stats.stddev / stats.mean)


def test_constant_samples_zero_spread(engine):
    stats = engine.compute([4.0, 4.0, 4.0, 4.0])
    assert stats is not None
    assert stats.stddev == pytest.approx(0.0)
    assert stats.cv == pytest.approx(0.0)
    assert stats.minimum == stats.maximum == stats.mean == 4.0


# Edge cases
def test_empty_input_returns_none(engine):
    assert engine.compute([]) is None
    assert engine.compute(None) is None


def test_single_sample_stddev_zero(engine):
    stats = engine.compute([7.5])
    assert stats is not None
    assert stats.sample_count == 1
    assert stats.minimum == stats.maximum == stats.mean == 7.5
    assert stats.p50 == stats.p95 == stats.p99 == 7.5
    assert stats.stddev == 0.0
    assert stats.cv == pytest.approx(0.0)


def test_cv_none_when_mean_not_positive(engine):
    stats = engine.compute([0.0, 0.0, 0.0])
    assert stats is not None
    assert stats.mean == 0.0
    assert stats.cv is None
    assert stats.to_dict()["cv"] is None


def test_no_nan_or_inf_produced(engine):
    stats = engine.compute([0.001, 0.002, 0.003])
    assert stats is not None
    for value in (
        stats.minimum,
        stats.mean,
        stats.p50,
        stats.p95,
        stats.p99,
        stats.maximum,
        stats.stddev,
    ):
        assert math.isfinite(value)


def test_compute_operations_separately(engine):
    ops = engine.compute_operations([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    assert isinstance(ops, OperationStatistics)
    assert ops.encrypt is not None and ops.decrypt is not None
    assert ops.encrypt.mean == pytest.approx(2.0)
    assert ops.decrypt.mean == pytest.approx(20.0)
    # Independent sample sets -> independent stats.
    assert ops.encrypt.maximum == 3.0
    assert ops.decrypt.maximum == 30.0


def test_compute_operations_missing_set_marked_not_applicable(engine):
    ops = engine.compute_operations([1.0, 2.0, 3.0], [])
    assert ops.encrypt is not None
    assert ops.decrypt is None
    d = ops.to_dict()
    assert d["encrypt"]["applicable"] is True
    assert d["decrypt"]["applicable"] is False
    assert d["decrypt"]["sampleCount"] == 0
    assert d["decrypt"]["unit"] == "ms"


def test_to_dict_is_json_serializable(engine):
    import json

    ops = engine.compute_operations([1.0, 2.0, 3.0], None)
    text = json.dumps(ops.to_dict())
    assert "linear_interpolation_type7" in text


def test_compute_for_record_uses_non_skipped_samples(engine):
    from harness.contract import RunnerOutput
    from harness.metrics import MetricsCollector

    base = {
        "runnerId": "go",
        "variantId": "go-stream-parallel",
        "mode": "steady_state",
        "scenarioId": "s1",
        "cryptoProfileId": "p1",
        "concurrency": 1,
        "outputEncoding": "binary",
        "hardwareAccel": False,
        "keySetChecksumSeen": "sha256:" + "ab" * 32,
        "corpusChecksumSeen": "sha256:" + "ab" * 32,
        "operations": [
            {
                "fileName": "a.txt",
                "fileType": ".txt",
                "originalBytes": 100,
                "skipped": False,
                "roundTripOk": True,
                "encryptMs": 2.0,
                "decryptMs": 4.0,
            },
            {
                "fileName": "b.txt",
                "fileType": ".txt",
                "originalBytes": 100,
                "skipped": False,
                "roundTripOk": True,
                "encryptMs": 4.0,
                "decryptMs": 8.0,
            },
            {
                "fileName": "c.ctrl",
                "fileType": ".ctrl",
                "originalBytes": 0,
                "skipped": True,
                "skipReason": "control_file",
                "roundTripOk": True,
            },
        ],
    }
    record = MetricsCollector().collect(RunnerOutput.from_dict(base))
    ops = engine.compute_for_record(record)
    assert ops.encrypt is not None and ops.decrypt is not None
    assert ops.encrypt.sample_count == 2  # skipped op excluded
    assert ops.encrypt.mean == pytest.approx(3.0)
    assert ops.decrypt.mean == pytest.approx(6.0)
