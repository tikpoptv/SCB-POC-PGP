"""Unit tests for warm-up/startup exclusion + Cold_Start (task 8.6)."""

import json

import pytest

from harness.contract import RunnerOutput
from harness.metrics import MetricsCollector
from harness.statistics import (
    COLD_START_LABEL,
    EXCLUDING_WARMUP_LABEL,
    INCLUDING_WARMUP_LABEL,
    ColdStartMetric,
    StatisticsEngine,
    TwoSetOperationReport,
)


@pytest.fixture
def engine():
    return StatisticsEngine()


def _runner_output(
    *,
    process_startup_ms=None,
    mode="steady_state",
    encrypt=(2.0, 4.0),
    decrypt=(4.0, 8.0),
):
    ops = []
    for i, (e, d) in enumerate(zip(encrypt, decrypt)):
        ops.append(
            {
                "fileName": f"f{i}.txt",
                "fileType": ".txt",
                "originalBytes": 100,
                "skipped": False,
                "roundTripOk": True,
                "encryptMs": e,
                "decryptMs": d,
            }
        )
    base = {
        "runnerId": "go",
        "variantId": "go-stream-parallel",
        "mode": mode,
        "scenarioId": "s1",
        "cryptoProfileId": "p1",
        "concurrency": 1,
        "outputEncoding": "binary",
        "hardwareAccel": False,
        "keySetChecksumSeen": "sha256:" + "ab" * 32,
        "corpusChecksumSeen": "sha256:" + "ab" * 32,
        "operations": ops,
    }
    if process_startup_ms is not None:
        base["processStartupMs"] = process_startup_ms
    return RunnerOutput.from_dict(base)


def test_cold_start_total_is_startup_plus_jit(engine):
    cs = engine.cold_start_metric(12.4, jit_warmup_ms=85.0)
    assert isinstance(cs, ColdStartMetric)
    assert cs.process_startup_ms == 12.4
    assert cs.jit_warmup_ms == 85.0
    assert cs.total_cold_start_ms == pytest.approx(97.4)
    assert cs.label == COLD_START_LABEL == "supplementary_cold_start_not_in_steady_state"


def test_cold_start_total_without_jit_is_startup_only(engine):
    cs = engine.cold_start_metric(15.0)
    assert cs is not None
    assert cs.jit_warmup_ms is None
    assert cs.total_cold_start_ms == pytest.approx(15.0)


def test_cold_start_none_when_no_components(engine):
    assert engine.cold_start_metric(None) is None
    assert engine.cold_start_metric(None, None) is None


def test_cold_start_to_dict_shape_and_label(engine):
    d = engine.cold_start_metric(12.4, jit_warmup_ms=85.0).to_dict()
    assert d == {
        "processStartupMs": 12.4,
        "jitWarmupMs": 85.0,
        "totalColdStartMs": pytest.approx(97.4),
        "label": "supplementary_cold_start_not_in_steady_state",
        "unit": "ms",
    }
    assert "linear_interpolation_type7" not in json.dumps(d)  # not a stats block


def test_cold_start_from_record_reads_process_startup(engine):
    record = MetricsCollector().collect(
        _runner_output(process_startup_ms=12.4, mode="cold_start")
    )
    cs = engine.cold_start_for_record(record, jit_warmup_ms=85.0)
    assert cs is not None
    assert cs.process_startup_ms == 12.4
    assert cs.total_cold_start_ms == pytest.approx(97.4)


def test_cold_start_from_steady_state_record_is_none(engine):
    # steady_state carries no processStartupMs -> no cold-start to report.
    record = MetricsCollector().collect(_runner_output(mode="steady_state"))
    assert record.process_startup_ms is None
    assert engine.cold_start_for_record(record) is None


def test_core_stats_identical_with_or_without_cold_start_present(engine):
    """Process startup must not change a single core/steady-state number."""
    rec_no_startup = MetricsCollector().collect(
        _runner_output(process_startup_ms=None, encrypt=(2.0, 4.0), decrypt=(4.0, 8.0))
    )
    rec_with_huge_startup = MetricsCollector().collect(
        _runner_output(
            process_startup_ms=999999.0, encrypt=(2.0, 4.0), decrypt=(4.0, 8.0)
        )
    )
    core_a = engine.compute_for_record(rec_no_startup)
    core_b = engine.compute_for_record(rec_with_huge_startup)
    assert core_a.to_dict() == core_b.to_dict()
    # And the core numbers reflect only the crypto-only samples.
    assert core_b.encrypt.mean == pytest.approx(3.0)
    assert core_b.encrypt.maximum == 4.0  # not 999999
    assert core_b.decrypt.mean == pytest.approx(6.0)


def test_cold_start_total_not_present_in_core_stats_dict(engine):
    record = MetricsCollector().collect(
        _runner_output(process_startup_ms=12.4, mode="cold_start")
    )
    core = engine.compute_for_record(record)
    cs = engine.cold_start_for_record(record, jit_warmup_ms=85.0)
    blob = json.dumps(core.to_dict())
    # The cold-start figures must not appear anywhere in the core stats block.
    assert "12.4" not in blob
    assert "85.0" not in blob
    assert str(cs.total_cold_start_ms) not in blob
    assert "coldStart" not in blob
    assert COLD_START_LABEL not in blob


def test_two_sets_no_warmup_supplied_sets_coincide(engine):
    report = engine.compute_two_sets([2.0, 4.0], [4.0, 8.0])
    assert isinstance(report, TwoSetOperationReport)
    assert report.warmup_samples_supplied is False
    assert report.excluding_warmup.to_dict() == report.including_warmup.to_dict()


def test_two_sets_excluding_is_core_steady_state(engine):
    # The excluding-warm-up set must equal plain core stats on recorded samples.
    report = engine.compute_two_sets(
        [2.0, 4.0], [4.0, 8.0], encrypt_warmup=[100.0], decrypt_warmup=[200.0]
    )
    core = engine.compute_operations([2.0, 4.0], [4.0, 8.0])
    assert report.excluding_warmup.to_dict() == core.to_dict()
    assert report.excluding_warmup.encrypt.maximum == 4.0  # warm-up 100 excluded


def test_two_sets_including_warmup_folds_warmup_back_in(engine):
    report = engine.compute_two_sets(
        [2.0, 4.0], [4.0, 8.0], encrypt_warmup=[12.0], decrypt_warmup=[24.0]
    )
    assert report.warmup_samples_supplied is True
    inc = report.including_warmup
    # including set spans warm-up + recorded samples.
    assert inc.encrypt.sample_count == 3
    assert inc.encrypt.maximum == 12.0
    assert inc.encrypt.mean == pytest.approx((12.0 + 2.0 + 4.0) / 3)
    assert inc.decrypt.maximum == 24.0
    # excluding set is unaffected by the warm-up samples.
    assert report.excluding_warmup.encrypt.sample_count == 2
    assert report.excluding_warmup.encrypt.maximum == 4.0


def test_two_sets_to_dict_has_two_distinct_labels(engine):
    report = engine.compute_two_sets(
        [2.0, 4.0], [4.0, 8.0], encrypt_warmup=[12.0], decrypt_warmup=[24.0]
    )
    d = report.to_dict()
    assert set(d) == {"excludingWarmup", "includingWarmup", "warmupSamplesSupplied"}
    assert d["excludingWarmup"]["label"] == EXCLUDING_WARMUP_LABEL
    assert d["includingWarmup"]["label"] == INCLUDING_WARMUP_LABEL
    assert d["excludingWarmup"]["label"] != d["includingWarmup"]["label"]
    assert d["warmupSamplesSupplied"] is True
    # JSON-serialisable for results.json.
    json.dumps(d)


def test_two_sets_for_record_with_separate_warmup_record(engine):
    recorded = MetricsCollector().collect(
        _runner_output(encrypt=(2.0, 4.0), decrypt=(4.0, 8.0))
    )
    warmup = MetricsCollector().collect(
        _runner_output(encrypt=(50.0,), decrypt=(60.0,))
    )
    report = engine.compute_two_sets_for_record(recorded, warmup_record=warmup)
    assert report.warmup_samples_supplied is True
    assert report.excluding_warmup.encrypt.maximum == 4.0
    assert report.including_warmup.encrypt.maximum == 50.0


def test_two_sets_for_record_without_warmup_record(engine):
    recorded = MetricsCollector().collect(_runner_output())
    report = engine.compute_two_sets_for_record(recorded)
    assert report.warmup_samples_supplied is False
    assert report.excluding_warmup.to_dict() == report.including_warmup.to_dict()
