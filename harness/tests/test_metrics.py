"""Unit tests for the Metrics Collector (task 6.6)."""

from dataclasses import dataclass

import pytest

from harness.contract import Mode, OutputEncoding, RunnerId, RunnerOutput
from harness.metrics import MetricRecord, MetricsCollector, ResourceUsage


@pytest.fixture
def runner_output(valid_runner_output_dict):
    return RunnerOutput.from_dict(valid_runner_output_dict)


@pytest.fixture
def resource():
    return ResourceUsage(
        cpu_avg_pct=72.0,
        cpu_max_pct=98.0,
        ram_avg_mb=210.0,
        ram_peak_mb=512.0,
        sampling_interval_ms=100,
        sample_count=50,
    )


# Combination + identifiers carried through
def test_collect_carries_identifiers(runner_output, resource):
    rec = MetricsCollector().collect(runner_output, resource)
    assert rec.runner_id is RunnerId.GO
    assert rec.variant_id == "go-stream-parallel"
    assert rec.scenario_id == "small-files-rsa2048"
    assert rec.crypto_profile_id == "aes256-zlib"
    assert rec.mode is Mode.STEADY_STATE
    assert rec.concurrency == 4
    assert rec.output_encoding is OutputEncoding.BINARY
    assert rec.hardware_accel is True
    assert rec.key_set_checksum_seen == runner_output.key_set_checksum_seen
    assert rec.corpus_checksum_seen == runner_output.corpus_checksum_seen


def test_collect_combines_gc_and_resources(runner_output, resource):
    rec = MetricsCollector().collect(runner_output, resource)
    assert rec.gc is runner_output.gc
    assert rec.gc.collections == 14
    assert rec.resource is resource
    assert rec.resource_samples_note == runner_output.resource_samples_note


def test_every_raw_sample_retained(runner_output, resource):
    rec = MetricsCollector().collect(runner_output, resource)
    # The collector must not aggregate samples away.
    assert rec.operations == runner_output.operations
    assert len(rec.operations) == 2


def test_to_dict_retains_all_operations(runner_output, resource):
    rec = MetricsCollector().collect(runner_output, resource)
    d = rec.to_dict()
    assert len(d["operations"]) == len(runner_output.operations)
    first = d["operations"][0]
    assert first["encryptMs"] == pytest.approx(1.83)
    assert first["decryptMs"] == pytest.approx(2.04)
    assert first["asymEncryptMs"] == pytest.approx(0.42)
    assert first["symDecryptMs"] == pytest.approx(1.49)
    assert first["ciphertextBytes"] == 612001
    assert first["outputFileName"] == "doc-0001.pdf.pgp"
    # Skipped control file preserved verbatim.
    assert d["operations"][1]["skipped"] is True
    assert d["operations"][1]["skipReason"] == "control_file"


def test_encrypt_decrypt_samples_exclude_skipped(runner_output, resource):
    rec = MetricsCollector().collect(runner_output, resource)
    assert rec.encrypt_samples_ms() == [pytest.approx(1.83)]
    assert rec.decrypt_samples_ms() == [pytest.approx(2.04)]
    assert rec.attempted_operations == 1
    assert rec.skipped_files == 1


def _base_output(operations):
    return {
        "runnerId": "java",
        "variantId": "java-inmem-single",
        "mode": "steady_state",
        "scenarioId": "s1",
        "cryptoProfileId": "p1",
        "concurrency": 1,
        "outputEncoding": "armored",
        "hardwareAccel": False,
        "keySetChecksumSeen": "sha256:" + "cd" * 32,
        "corpusChecksumSeen": "sha256:" + "cd" * 32,
        "operations": operations,
    }


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


def test_failure_counts_split_operation_and_correctness():
    ops = [
        _op(),  # success
        _op(roundTripOk=False, failureType="operation_failure"),
        _op(roundTripOk=False, failureType="correctness_failure"),
        _op(roundTripOk=False),  # round-trip mismatch w/o explicit type -> correctness
        _op(skipped=True, skipReason="control_file"),  # not counted
    ]
    rec = MetricsCollector().collect(RunnerOutput.from_dict(_base_output(ops)))
    assert rec.operation_failures == 1
    assert rec.correctness_failures == 2
    assert rec.failed_operations == 3
    assert rec.attempted_operations == 4  # skipped excluded
    assert rec.skipped_files == 1


# Resource / GC absent
def test_collect_without_resource(runner_output):
    rec = MetricsCollector().collect(runner_output)
    assert rec.resource is None
    d = rec.to_dict()
    assert d["cpuPct"] is None
    assert d["ramMb"] is None


def test_collect_with_null_gc(valid_runner_output_dict):
    payload = dict(valid_runner_output_dict, gc=None)
    rec = MetricsCollector().collect(RunnerOutput.from_dict(payload))
    assert rec.gc is None
    assert rec.to_dict()["gc"] is None


def test_comparable_by_default(runner_output, resource):
    rec = MetricsCollector().collect(runner_output, resource)
    assert rec.comparable is True
    assert rec.all_non_comparable_reasons() == ()
    assert rec.to_dict()["comparable"] is True


def test_non_comparable_resource_propagates(runner_output):
    failed = ResourceUsage(comparable=False, non_comparable_reason="psutil sampling gap")
    rec = MetricsCollector().collect(runner_output, failed)
    assert rec.comparable is False
    assert "psutil sampling gap" in rec.all_non_comparable_reasons()
    assert rec.to_dict()["comparable"] is False


def test_explicit_non_comparable_reasons_propagate(runner_output, resource):
    rec = MetricsCollector().collect(
        runner_output, resource, non_comparable_reasons=("env changed mid-run",)
    )
    assert rec.comparable is False
    d = rec.to_dict()
    assert d["nonComparableReasons"] == ["env changed mid-run"]


# ResourceUsage adapter accepts duck-typed aggregate (task 6.5 reconcile)
def test_resource_usage_from_duck_typed_aggregate(runner_output):
    @dataclass
    class FakeAgg:
        cpu_avg_pct: float = 50.0
        cpu_max_pct: float = 90.0
        ram_avg_mb: float = 100.0
        ram_peak_mb: float = 256.0
        comparable: bool = True
        non_comparable_reason: str | None = None

    rec = MetricsCollector().collect(runner_output, FakeAgg())
    assert isinstance(rec.resource, ResourceUsage)
    assert rec.resource.cpu_max_pct == 90.0
    d = rec.to_dict()
    assert d["cpuPct"] == {"avg": 50.0, "max": 90.0}
    assert d["ramMb"] == {"avg": 100.0, "peak": 256.0}


def test_to_dict_is_json_serializable(runner_output, resource):
    import json

    rec = MetricsCollector().collect(runner_output, resource)
    text = json.dumps(rec.to_dict())
    assert "small-files-rsa2048" in text
