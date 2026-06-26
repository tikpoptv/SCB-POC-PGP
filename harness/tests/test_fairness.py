"""Unit tests for the fairness invariant checker (task 8.12)."""

from dataclasses import replace

import pytest

from harness.contract import CryptoProfile, OutputEncoding, RunnerId, RunnerOutput
from harness.fairness import (
    FairnessDimensions,
    RunDescriptor,
    check_fairness,
)
from harness.metrics import MetricsCollector
from harness.scheduler import ResourceQuota

_KS = "sha256:" + "ab" * 32
_CORPUS = "sha256:" + "cd" * 32


def _profile() -> CryptoProfile:
    return CryptoProfile(
        pub_alg="RSA-2048", cipher="AES-256", compression="ZLIB", hash="SHA-256"
    )


def _dims(**overrides) -> FairnessDimensions:
    base = FairnessDimensions(
        key_set_checksum=_KS,
        corpus_checksum=_CORPUS,
        crypto_profile=_profile(),
        concurrency=4,
        output_encoding=OutputEncoding.BINARY,
        hardware_accel=True,
        resource_quota=ResourceQuota(cpu_cores=8, memory_mb=3072),
    )
    return replace(base, **overrides)


def _run(runner: RunnerId, variant: str, dims: FairnessDimensions, *, prior=()):
    return RunDescriptor(
        runner_id=runner,
        variant_id=variant,
        dimensions=dims,
        prior_non_comparable_reasons=tuple(prior),
    )


def _go_java(go_dims: FairnessDimensions, java_dims: FairnessDimensions):
    return [
        _run(RunnerId.GO, "go-stream-parallel", go_dims),
        _run(RunnerId.JAVA, "java-stream-parallel", java_dims),
    ]


# All-equal -> comparable (Property 13 happy path)
def test_all_dimensions_equal_is_comparable():
    runs = _go_java(_dims(), _dims())
    result = check_fairness("small-files-rsa2048", runs)

    assert result.comparable is True
    assert result.non_comparable_reasons == ()
    assert all(r.comparable for r in result.runs)
    assert len(result.comparable_runs) == 2
    assert result.excluded_runs == ()


def test_more_than_two_variants_all_equal_is_comparable():
    runs = [
        _run(RunnerId.GO, "go-inmem-single", _dims()),
        _run(RunnerId.GO, "go-stream-parallel", _dims()),
        _run(RunnerId.JAVA, "java-stream-parallel", _dims()),
    ]
    result = check_fairness("s1", runs)
    assert result.comparable is True
    assert len(result.comparable_runs) == 3


# Each differing dimension -> non-comparable with the right reason
@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"key_set_checksum": "sha256:" + "ff" * 32}, "keySetChecksum mismatch"),
        ({"corpus_checksum": "sha256:" + "ff" * 32}, "corpusChecksum mismatch"),
        (
            {"crypto_profile": CryptoProfile("RSA-4096", "AES-256", "ZLIB", "SHA-256")},
            "cryptoProfile.pubAlg mismatch",
        ),
        (
            {"crypto_profile": CryptoProfile("RSA-2048", "AES-128", "ZLIB", "SHA-256")},
            "cryptoProfile.cipher mismatch",
        ),
        (
            {"crypto_profile": CryptoProfile("RSA-2048", "AES-256", "NONE", "SHA-256")},
            "cryptoProfile.compression mismatch",
        ),
        (
            {"crypto_profile": CryptoProfile("RSA-2048", "AES-256", "ZLIB", "SHA-512")},
            "cryptoProfile.hash mismatch",
        ),
        ({"concurrency": 1}, "concurrency mismatch"),
        ({"output_encoding": OutputEncoding.ARMORED}, "outputEncoding mismatch"),
        ({"hardware_accel": False}, "hardwareAccel mismatch"),
    ],
)
def test_each_differing_dimension_is_non_comparable(override, fragment):
    # Reference = Go (first run). Java differs on exactly one dimension.
    runs = _go_java(_dims(), _dims(**override))
    result = check_fairness("s1", runs)

    assert result.comparable is False
    # The Scenario reason names the differing dimension.
    assert any(fragment in reason for reason in result.non_comparable_reasons)

    go = next(r for r in result.runs if r.runner_id is RunnerId.GO)
    java = next(r for r in result.runs if r.runner_id is RunnerId.JAVA)
    # The reference run stays comparable; the offending run is excluded.
    assert go.comparable is True
    assert java.comparable is False
    assert any(fragment in reason for reason in java.non_comparable_reasons)
    assert result.comparable_runs == (go,)
    assert result.excluded_runs == (java,)


def test_quota_cpu_difference_is_non_comparable():
    java_dims = _dims(resource_quota=ResourceQuota(cpu_cores=4, memory_mb=3072))
    result = check_fairness("s1", _go_java(_dims(), java_dims))

    assert result.comparable is False
    reason = next(r for r in result.non_comparable_reasons if "resourceQuota" in r)
    assert "cpuCores" in reason
    assert "Req 3.4" in reason


def test_quota_memory_difference_is_non_comparable():
    java_dims = _dims(resource_quota=ResourceQuota(cpu_cores=8, memory_mb=2048))
    result = check_fairness("s1", _go_java(_dims(), java_dims))

    assert result.comparable is False
    reason = next(r for r in result.non_comparable_reasons if "resourceQuota" in r)
    assert "memoryMb" in reason


def test_multiple_dimensions_differ_reports_all():
    java_dims = _dims(concurrency=2, output_encoding=OutputEncoding.ARMORED)
    result = check_fairness("s1", _go_java(_dims(), java_dims))

    java = next(r for r in result.runs if r.runner_id is RunnerId.JAVA)
    assert not java.comparable
    assert any("concurrency mismatch" in r for r in java.non_comparable_reasons)
    assert any("outputEncoding mismatch" in r for r in java.non_comparable_reasons)


# Propagated anomalies (Property 18) — unsupported crypto/key, env change, …
def test_prior_non_comparable_reason_is_propagated():
    reason = "Java does not support cipher 'ChaCha20' (Req 18.5)"
    runs = [
        _run(RunnerId.GO, "go-stream-parallel", _dims()),
        _run(RunnerId.JAVA, "java-stream-parallel", _dims(), prior=[reason]),
    ]
    result = check_fairness("s1", runs)

    assert result.comparable is False
    assert reason in result.non_comparable_reasons
    java = next(r for r in result.runs if r.runner_id is RunnerId.JAVA)
    assert not java.comparable
    assert reason in java.non_comparable_reasons
    # Go remains comparable and is the only run kept for the conclusion.
    assert result.comparable_runs == (
        next(r for r in result.runs if r.runner_id is RunnerId.GO),
    )


# Reference override + edge cases
def test_expected_reference_flags_all_runs_that_differ():
    # When an explicit expected config is supplied, even the first run is judged
    # against it (no run is implicitly canonical).
    expected = _dims(concurrency=8)
    runs = _go_java(_dims(concurrency=4), _dims(concurrency=4))
    result = check_fairness("s1", runs, expected=expected)

    assert result.comparable is False
    assert all(not r.comparable for r in result.runs)
    assert all(
        any("concurrency mismatch" in reason for reason in r.non_comparable_reasons)
        for r in result.runs
    )


def test_no_runs_is_non_comparable():
    result = check_fairness("s1", [])
    assert result.comparable is False
    assert result.non_comparable_reasons == ("no runs to compare for this Scenario",)
    assert result.runs == ()


def test_to_dict_shape_matches_result_report():
    result = check_fairness("s1", _go_java(_dims(), _dims(concurrency=1)))
    d = result.to_dict()
    assert d["scenarioId"] == "s1"
    assert d["comparable"] is False
    assert isinstance(d["nonComparableReasons"], list)
    assert len(d["runs"]) == 2
    run = d["runs"][0]
    assert set(run) == {"runnerId", "variantId", "comparable", "nonComparableReasons"}


# Integration with MetricRecord (from_metric_record adapter)
def test_from_metric_record_round_trips_dimensions(valid_runner_output_dict):
    record = MetricsCollector().collect(
        RunnerOutput.from_dict(valid_runner_output_dict)
    )
    quota = ResourceQuota(cpu_cores=8, memory_mb=3072)
    desc = RunDescriptor.from_metric_record(record, _profile(), quota)

    assert desc.runner_id is RunnerId.GO
    assert desc.variant_id == "go-stream-parallel"
    assert desc.dimensions.concurrency == record.concurrency
    assert desc.dimensions.output_encoding is record.output_encoding
    assert desc.dimensions.hardware_accel is record.hardware_accel
    assert desc.dimensions.key_set_checksum == record.key_set_checksum_seen
    assert desc.dimensions.resource_quota == quota


def test_from_metric_record_propagates_run_anomalies(valid_runner_output_dict):
    record = MetricsCollector().collect(
        RunnerOutput.from_dict(valid_runner_output_dict),
        non_comparable_reasons=("env changed mid-set: vcpu (Req 3.5)",),
    )
    desc = RunDescriptor.from_metric_record(
        record, _profile(), ResourceQuota(cpu_cores=8, memory_mb=3072)
    )
    result = check_fairness("s1", [desc])
    assert result.comparable is False
    assert "env changed mid-set: vcpu (Req 3.5)" in result.non_comparable_reasons
