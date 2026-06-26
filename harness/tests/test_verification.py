"""Unit tests for the VerificationGate (task 7.1)."""

import json

import pytest

from harness.contract import FailureType, RunnerId, RunnerOutput
from harness.metrics import MetricsCollector
from harness.verification import (
    ExclusionCategory,
    VerificationGate,
    VerificationResult,
    VerificationSummary,
)

_CHECKSUM = "sha256:" + "ab" * 32
_OTHER_CHECKSUM = "sha256:" + "cd" * 32


# Builders
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


def _run(operations=None, *, key_chk=_CHECKSUM, corpus_chk=_CHECKSUM, runner="go"):
    if operations is None:
        operations = [_op()]
    return RunnerOutput.from_dict(
        {
            "runnerId": runner,
            "variantId": "go-stream-parallel",
            "mode": "steady_state",
            "scenarioId": "small-files-rsa2048",
            "cryptoProfileId": "aes256-zlib",
            "concurrency": 1,
            "outputEncoding": "binary",
            "hardwareAccel": True,
            "keySetChecksumSeen": key_chk,
            "corpusChecksumSeen": corpus_chk,
            "operations": operations,
        }
    )


class _FakeVersionReport:
    """Minimal stand-in for harness.version.VersionReport."""

    def __init__(self, version_match: bool, messages=None):
        self.version_match = version_match
        self._messages = messages or []

    def mismatch_messages(self):
        return list(self._messages)


# Happy path
def test_clean_run_passes_all_gates():
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(_run())

    assert result.excluded is False
    assert result.included is True
    assert result.comparable is True
    assert result.checksum_match is True
    assert result.version_match is True
    assert result.round_trip_ok is True
    assert result.categories == ()
    assert result.reasons == ()
    assert result.operation_failures == 0
    assert result.correctness_failures == 0
    assert result.affected_files == ()


def test_gate_accepts_metric_record():
    # The gate must work on a collected MetricRecord too, not only RunnerOutput.
    record = MetricsCollector().collect(_run())
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(record)
    assert result.included is True
    assert result.scenario_id == "small-files-rsa2048"


def test_no_reference_checksums_never_excludes():
    # Partial pipeline: nothing recorded to verify against -> never excluded.
    gate = VerificationGate()
    result = gate.verify(_run(key_chk="whatever", corpus_chk="other"))
    assert result.checksum_match is True
    assert result.included is True


def test_key_set_checksum_mismatch_excludes():
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(_run(key_chk=_OTHER_CHECKSUM))

    assert result.excluded is True
    assert result.checksum_match is False
    assert result.comparable is False
    assert ExclusionCategory.CHECKSUM_MISMATCH in result.categories
    assert any("key set checksum mismatch" in r for r in result.reasons)


def test_corpus_checksum_mismatch_excludes():
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(_run(corpus_chk=_OTHER_CHECKSUM))

    assert result.excluded is True
    assert result.checksum_match is False
    assert ExclusionCategory.CHECKSUM_MISMATCH in result.categories
    assert any("corpus checksum mismatch" in r for r in result.reasons)


def test_both_checksums_mismatch_reports_both_reasons():
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(_run(key_chk=_OTHER_CHECKSUM, corpus_chk=_OTHER_CHECKSUM))
    assert result.checksum_match is False
    # Only one CHECKSUM_MISMATCH category, but two distinct reasons.
    assert result.categories.count(ExclusionCategory.CHECKSUM_MISMATCH) == 1
    assert sum("checksum mismatch" in r for r in result.reasons) == 2


def test_version_mismatch_excludes_and_is_non_comparable():
    report = _FakeVersionReport(
        version_match=False,
        messages=["version mismatch for go: recorded '1.25.1' but detected '1.24.0'"],
    )
    gate = VerificationGate(
        key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM, version_report=report
    )
    result = gate.verify(_run())

    assert result.excluded is True
    assert result.version_match is False
    assert result.comparable is False
    assert ExclusionCategory.VERSION_MISMATCH in result.categories
    assert any("version mismatch for go" in r for r in result.reasons)


def test_version_mismatch_without_messages_has_default_reason():
    gate = VerificationGate(
        key_set_checksum=_CHECKSUM,
        corpus_checksum=_CHECKSUM,
        version_report=_FakeVersionReport(version_match=False),
    )
    result = gate.verify(_run())
    assert result.excluded is True
    assert any("version mismatch" in r for r in result.reasons)


def test_version_match_passes_version_gate():
    gate = VerificationGate(
        key_set_checksum=_CHECKSUM,
        corpus_checksum=_CHECKSUM,
        version_report=_FakeVersionReport(version_match=True),
    )
    result = gate.verify(_run())
    assert result.version_match is True
    assert result.included is True


def test_round_trip_mismatch_without_type_is_correctness_failure():
    run = _run([_op(fileName="a.txt", roundTripOk=False)])
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)

    assert result.round_trip_ok is False
    assert result.excluded is True
    assert result.correctness_failures == 1
    assert result.operation_failures == 0
    assert result.affected_files == ("a.txt",)
    assert ExclusionCategory.CORRECTNESS_FAILURE in result.categories
    # A correctness failure excludes timings but the run is still a comparable attempt.
    assert result.comparable is True


def test_explicit_correctness_failure_excludes():
    run = _run(
        [_op(fileName="b.pdf", roundTripOk=False, failureType="correctness_failure")]
    )
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)
    assert result.excluded is True
    assert result.correctness_failures == 1
    assert result.affected_files == ("b.pdf",)
    failure = result.failures[0]
    assert failure.failure_type is FailureType.CORRECTNESS_FAILURE
    assert failure.runner_id is RunnerId.GO
    assert failure.variant_id == "go-stream-parallel"
    assert failure.scenario_id == "small-files-rsa2048"


def test_single_correctness_failure_excludes_whole_run():
    run = _run(
        [
            _op(fileName="ok1.txt"),
            _op(fileName="ok2.txt"),
            _op(fileName="bad.txt", roundTripOk=False),
        ]
    )
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)
    assert result.excluded is True
    assert result.correctness_failures == 1
    assert result.affected_files == ("bad.txt",)


def test_multiple_affected_files_counted():
    run = _run(
        [
            _op(fileName="a.txt", roundTripOk=False),
            _op(fileName="b.txt", roundTripOk=False, failureType="correctness_failure"),
            _op(fileName="c.txt"),
        ]
    )
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)
    assert result.correctness_failures == 2
    assert set(result.affected_files) == {"a.txt", "b.txt"}
    assert result.affected_file_count == 2


def test_operation_failure_does_not_exclude_timings():
    # on its own, exclude the run's timings (only correctness failures do).
    run = _run([_op(fileName="boom.txt", roundTripOk=False, failureType="operation_failure")])
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)

    assert result.operation_failures == 1
    assert result.correctness_failures == 0
    assert result.round_trip_ok is True
    assert result.excluded is False
    assert result.affected_files == ()


def test_operation_and_correctness_failures_classified_separately():
    run = _run(
        [
            _op(fileName="op.txt", roundTripOk=False, failureType="operation_failure"),
            _op(fileName="corr.txt", roundTripOk=False, failureType="correctness_failure"),
            _op(fileName="ok.txt"),
        ]
    )
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)
    assert result.operation_failures == 1
    assert result.correctness_failures == 1
    assert result.affected_files == ("corr.txt",)
    assert result.excluded is True  # excluded due to the correctness failure


def test_skipped_files_are_not_failures():
    run = _run(
        [
            _op(fileName="ok.txt"),
            _op(fileName="ctrl.ctrl", skipped=True, skipReason="control_file", roundTripOk=False),
        ]
    )
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)
    # The skipped control file must not count as a correctness failure.
    assert result.correctness_failures == 0
    assert result.excluded is False


# Combined gates
def test_checksum_and_correctness_both_excluded():
    run = _run([_op(fileName="a.txt", roundTripOk=False)], key_chk=_OTHER_CHECKSUM)
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)
    assert result.excluded is True
    assert ExclusionCategory.CHECKSUM_MISMATCH in result.categories
    assert ExclusionCategory.CORRECTNESS_FAILURE in result.categories


def test_summary_counts_excluded_runs_and_affected_files():
    runs = [
        _run([_op(fileName="ok.txt")]),  # included
        _run([_op(fileName="a.txt", roundTripOk=False), _op(fileName="b.txt", roundTripOk=False)]),  # 2 files
        _run([_op(fileName="c.txt", roundTripOk=False)]),  # 1 file
        _run([_op()], key_chk=_OTHER_CHECKSUM),  # checksum excluded, 0 affected files
    ]
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    summary = gate.verify_all(runs)

    assert summary.total_runs == 4
    assert summary.included_runs == 1
    assert summary.excluded_runs == 3
    assert summary.correctness_excluded_runs == 2
    assert summary.checksum_excluded_runs == 1
    assert summary.affected_files == 3  # 2 + 1 + 0
    assert len(summary.included_results()) == 1
    assert len(summary.excluded_results()) == 3


def test_summary_aggregates_failure_counts():
    runs = [
        _run([_op(fileName="op.txt", roundTripOk=False, failureType="operation_failure")]),
        _run([_op(fileName="corr.txt", roundTripOk=False, failureType="correctness_failure")]),
    ]
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    summary = gate.verify_all(runs)
    assert summary.operation_failures == 1
    assert summary.correctness_failures == 1


# Serialisation
def test_result_to_dict_is_json_serialisable():
    run = _run([_op(fileName="a.txt", roundTripOk=False)])
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    result = gate.verify(run)
    text = json.dumps(result.to_dict())
    payload = json.loads(text)
    assert payload["excluded"] is True
    assert payload["affectedFiles"] == ["a.txt"]
    assert payload["categories"] == ["correctness_failure"]
    assert payload["failures"][0]["failureType"] == "correctness_failure"


def test_summary_to_dict_is_json_serialisable():
    runs = [_run(), _run([_op(fileName="a.txt", roundTripOk=False)])]
    gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
    summary = gate.verify_all(runs)
    text = json.dumps(summary.to_dict())
    payload = json.loads(text)
    assert payload["totalRuns"] == 2
    assert payload["excludedRuns"] == 1
    assert payload["affectedFiles"] == 1
    assert len(payload["results"]) == 2
