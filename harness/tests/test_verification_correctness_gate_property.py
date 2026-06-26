"""Property-based test for the correctness gate (task 7.4)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.contract import RunnerOutput
from harness.verification import ExclusionCategory, VerificationGate

_CHECKSUM = "sha256:" + "ab" * 32


# Operation generators — one strategy per outcome kind. Every operation is
# given a unique file name by the run builder so the "affected files" count is
# unambiguous (the gate de-duplicates by file name).
# A clean round-trip: never a failure, never excludes.
_OK = st.just("ok")
#   * roundTripOk False with no explicit type, or
#   * an explicit correctness_failure type.
_CORRECTNESS = st.sampled_from(["correctness_implicit", "correctness_explicit"])
# An operation failure: recorded for the error rate but NOT a correctness
_OPERATION = st.just("operation")
# A skipped file (control file / unsupported): never a failure of any kind.
_SKIPPED = st.just("skipped")

_KIND = st.one_of(_OK, _CORRECTNESS, _OPERATION, _SKIPPED)


def _op_for(kind: str, file_name: str) -> dict:
    """Build one RunnerOutput operation dict for the given outcome kind."""
    base = {
        "fileName": file_name,
        "fileType": ".txt",
        "originalBytes": 100,
        "skipped": False,
        "roundTripOk": True,
    }
    if kind == "ok":
        return base
    if kind == "correctness_implicit":
        # Round-trip mismatch with no explicit type -> correctness failure.
        return {**base, "roundTripOk": False}
    if kind == "correctness_explicit":
        return {**base, "roundTripOk": False, "failureType": "correctness_failure"}
    if kind == "operation":
        return {**base, "roundTripOk": False, "failureType": "operation_failure"}
    if kind == "skipped":
        # Skipped files are excluded from classification entirely, even when
        # their roundTripOk flag is False.
        return {
            **base,
            "skipped": True,
            "skipReason": "control_file",
            "roundTripOk": False,
        }
    raise AssertionError(f"unknown kind {kind!r}")


def _is_correctness(kind: str) -> bool:
    return kind in ("correctness_implicit", "correctness_explicit")


@st.composite
def _run_kinds(draw, min_size: int = 0, max_size: int = 12):
    """Draw a list of per-file outcome kinds for a single run."""
    return draw(st.lists(_KIND, min_size=min_size, max_size=max_size))


def _build_run(kinds, *, runner: str = "go", run_index: int = 0) -> RunnerOutput:
    """Assemble a RunnerOutput from a list of outcome kinds with unique names.

    Matching reference checksums are used so only correctness drives exclusion.
    """
    operations = [
        _op_for(kind, f"r{run_index}-f{i}-{kind}.txt") for i, kind in enumerate(kinds)
    ]
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
            "keySetChecksumSeen": _CHECKSUM,
            "corpusChecksumSeen": _CHECKSUM,
            "operations": operations,
        }
    )


def _gate() -> VerificationGate:
    # Matching reference checksums and no version report: only the correctness
    # gate can exclude a run.
    return VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)


# Feature: pgp-encryption-benchmark-go-java, Property 10: Correctness gate กันเวลาที่ไม่ถูกต้องออกจากสถิติ
@settings(max_examples=300)
@given(kinds=_run_kinds())
def test_run_excluded_iff_it_has_a_correctness_failure(kinds):
    run = _build_run(kinds)
    result = _gate().verify(run)

    correctness_count = sum(1 for k in kinds if _is_correctness(k))
    operation_count = sum(1 for k in kinds if k == "operation")
    has_correctness = correctness_count >= 1

    assert result.excluded is has_correctness
    assert result.included is (not has_correctness)
    assert result.round_trip_ok is (not has_correctness)

    # The correctness gate is the only category that can fire here (matching
    # checksums, no version report).
    if has_correctness:
        assert ExclusionCategory.CORRECTNESS_FAILURE in result.categories
    else:
        assert result.categories == ()

    assert result.correctness_failures == correctness_count
    assert result.operation_failures == operation_count

    # unique file names make this an exact equality.
    assert result.affected_file_count == correctness_count

    # A pure correctness/operation failure is still a *comparable* attempt.
    assert result.comparable is True


# Feature: pgp-encryption-benchmark-go-java, Property 10: Correctness gate กันเวลาที่ไม่ถูกต้องออกจากสถิติ
@settings(max_examples=200)
@given(
    op_failures=st.integers(min_value=0, max_value=8),
    skipped=st.integers(min_value=0, max_value=8),
    oks=st.integers(min_value=0, max_value=8),
)
def test_operation_failures_and_skips_never_exclude(op_failures, skipped, oks):
    kinds = (
        ["operation"] * op_failures + ["skipped"] * skipped + ["ok"] * oks
    )
    run = _build_run(kinds)
    result = _gate().verify(run)

    assert result.excluded is False
    assert result.included is True
    assert result.round_trip_ok is True
    assert result.correctness_failures == 0
    assert result.affected_file_count == 0
    assert result.operation_failures == op_failures


# Feature: pgp-encryption-benchmark-go-java, Property 10: Correctness gate กันเวลาที่ไม่ถูกต้องออกจากสถิติ
@settings(max_examples=200)
@given(runs_kinds=st.lists(_run_kinds(), min_size=1, max_size=10))
def test_summary_counts_excluded_runs_and_affected_files(runs_kinds):
    runs = [
        _build_run(kinds, run_index=i) for i, kinds in enumerate(runs_kinds)
    ]
    summary = _gate().verify_all(runs)

    expected_affected = sum(
        sum(1 for k in kinds if _is_correctness(k)) for kinds in runs_kinds
    )
    expected_excluded_runs = sum(
        1 for kinds in runs_kinds if any(_is_correctness(k) for k in kinds)
    )
    expected_included_runs = len(runs_kinds) - expected_excluded_runs

    assert summary.total_runs == len(runs_kinds)
    # Only the correctness gate fires, so every exclusion is a correctness one.
    assert summary.excluded_runs == expected_excluded_runs
    assert summary.correctness_excluded_runs == expected_excluded_runs
    assert summary.checksum_excluded_runs == 0
    assert summary.version_excluded_runs == 0
    assert summary.included_runs == expected_included_runs

    assert summary.affected_files == expected_affected

    # The included results are exactly the runs with no correctness failure, and
    # excluded results never leak into the statistics input.
    included = summary.included_results()
    assert len(included) == expected_included_runs
    assert all(not r.excluded for r in included)
    assert all(r.included for r in summary.results if not r.excluded)
    assert len(summary.excluded_results()) == expected_excluded_runs
