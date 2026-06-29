"""Integration tests: full pipeline end-to-end (Task 14.2).

Drives Harness → fake subprocess runners → VerificationGate → StatisticsEngine
→ ReportGenerator on a small scenario set.

Uses fake/stub subprocess runners (like _fake_runner.py) for hermetic testing
— no real Go/Java binaries are required.

Validates:
  • Property 1 gate: round-trip byte-for-byte must pass before timing enters statistics
  • Property 2 gate: interop check (Go→Java, Java→Go) must pass
  • Round-trip failure → run excluded from statistics
  • results.json is written atomically (temp-then-rename)
  • results.json structure is complete after a successful run

Requirements: 3.1, 3.3, 20.1, 25.1, 25.2, 25.3
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.contract import Command, OutputEncoding, RunnerOutput
from harness.contract.models import (
    CryptoProfile,
    FailureType,
    GcStats,
    Mode,
    Operation,
    OperationSample,
    RunnerId,
)
from harness.interop import (
    GO,
    JAVA,
    InteropCheck,
    InteropEndpoint,
    InteropOutcome,
    InteropPair,
    InteropSummary,
    InteroperabilityChecker,
)
from harness.report import ReportGenerator
from harness.statistics_engine import round_trip_ms, throughput_mb_per_sec
from harness.subprocess_driver import SubprocessDriver
from harness.verification import ExclusionCategory, VerificationGate, VerificationSummary

# ---------------------------------------------------------------------------
# Constants & Paths
# ---------------------------------------------------------------------------

_FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "_fake_runner.py")
_CHECKSUM = "sha256:" + "ab" * 32

# ---------------------------------------------------------------------------
# Helpers: build fake RunnerOutput objects
# ---------------------------------------------------------------------------


def _make_operation(
    *,
    file_name: str = "doc.txt",
    file_type: str = ".txt",
    original_bytes: int = 1024,
    skipped: bool = False,
    round_trip_ok: bool = True,
    failure_type: FailureType | None = None,
    encrypt_ms: float = 1.0,
    decrypt_ms: float = 1.0,
) -> OperationSample:
    return OperationSample(
        file_name=file_name,
        file_type=file_type,
        original_bytes=original_bytes,
        ciphertext_bytes=original_bytes + 100 if not skipped else None,
        skipped=skipped,
        skip_reason="control_file" if skipped else None,
        encrypt_ms=encrypt_ms if not skipped else None,
        decrypt_ms=decrypt_ms if not skipped else None,
        round_trip_ok=round_trip_ok,
        failure_type=failure_type,
        output_file_name=f"{file_name}.pgp" if not skipped else None,
    )


def _make_runner_output(
    *,
    runner_id: RunnerId = RunnerId.GO,
    variant_id: str = "go-stream-parallel",
    scenario_id: str = "s1",
    operations: tuple[OperationSample, ...] | None = None,
    key_set_checksum: str = _CHECKSUM,
    corpus_checksum: str = _CHECKSUM,
) -> RunnerOutput:
    if operations is None:
        operations = (_make_operation(),)
    return RunnerOutput(
        runner_id=runner_id,
        variant_id=variant_id,
        mode=Mode.STEADY_STATE,
        scenario_id=scenario_id,
        crypto_profile_id="aes256-zlib",
        concurrency=1,
        output_encoding=OutputEncoding.BINARY,
        hardware_accel=True,
        key_set_checksum_seen=key_set_checksum,
        corpus_checksum_seen=corpus_checksum,
        operations=operations,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner_inputs(tmp_path: Path):
    """Create minimal Key_Set and Test_Corpus directories."""
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    (key_dir / "rsa2048-public.asc").write_text("FAKE-PUBLIC-KEY")
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "doc.txt").write_text("hello world")
    return key_dir, corpus_dir


@pytest.fixture
def make_command(runner_inputs, tmp_path: Path):
    key_dir, corpus_dir = runner_inputs

    def _make(variant_id: str = "go-stream-parallel", **overrides) -> Command:
        data = {
            "command": "run",
            "variantId": variant_id,
            "mode": "steady_state",
            "warmupIterations": 0,
            "concurrency": 1,
            "cryptoProfile": {
                "pubAlg": "RSA-2048",
                "cipher": "AES-256",
                "compression": "ZLIB",
                "hash": "SHA-256",
            },
            "outputEncoding": "binary",
            "keySetPath": str(key_dir),
            "keySetChecksum": _CHECKSUM,
            "corpusPath": str(corpus_dir),
            "corpusChecksum": _CHECKSUM,
            "outputDir": str(tmp_path / "out"),
            "operation": "roundtrip",
        }
        data.update(overrides)
        return Command.from_dict(data)

    return _make


@pytest.fixture
def result_dir(tmp_path: Path) -> Path:
    d = tmp_path / "results"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# SubprocessDriver helpers
# ---------------------------------------------------------------------------


def _fake_driver(*, env: dict | None = None) -> SubprocessDriver:
    """Return a SubprocessDriver wired to the fake runner."""
    return SubprocessDriver(
        [sys.executable, _FAKE_RUNNER],
        env=env,
        validate_inputs=False,
    )


# ===========================================================================
# Section 1: SubprocessDriver → VerificationGate pipeline
# ===========================================================================


class TestSubprocessToVerificationPipeline:
    """Verify that the SubprocessDriver → VerificationGate leg works end-to-end."""

    def test_fake_runner_output_passes_verification_gate(self, make_command):
        """Req 3.1, 5.4: a correctly-behaving runner clears the gate and is included."""
        driver = _fake_driver()
        cmd = make_command()
        result = driver.run(cmd)

        assert result.success, f"fake runner failed: {result.stderr}"
        assert result.output is not None

        gate = VerificationGate(
            key_set_checksum=_CHECKSUM,
            corpus_checksum=_CHECKSUM,
        )
        vr = gate.verify(result.output)
        assert vr.included, f"expected included, got categories={vr.categories}, reasons={vr.reasons}"
        assert vr.round_trip_ok
        assert vr.checksum_match

    def test_gate_excludes_run_with_checksum_mismatch(self, make_command):
        """Req 4.6: if Runner reports wrong checksum, gate marks run excluded (non-comparable)."""
        driver = _fake_driver()
        cmd = make_command()
        result = driver.run(cmd)
        assert result.success

        # Gate expects a DIFFERENT checksum than what the fake runner will echo back
        wrong_checksum = "sha256:" + "ff" * 32
        gate = VerificationGate(
            key_set_checksum=wrong_checksum,
            corpus_checksum=_CHECKSUM,
        )
        vr = gate.verify(result.output)
        assert vr.excluded
        assert ExclusionCategory.CHECKSUM_MISMATCH in vr.categories

    def test_gate_excludes_run_with_round_trip_failure(self):
        """Req 5.4, 5.5: Property 1 gate — correctness failure excludes run from stats."""
        output = _make_runner_output(
            operations=(
                _make_operation(round_trip_ok=False, failure_type=FailureType.CORRECTNESS_FAILURE),
            )
        )
        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
        vr = gate.verify(output)
        assert vr.excluded
        assert ExclusionCategory.CORRECTNESS_FAILURE in vr.categories
        assert not vr.round_trip_ok

    def test_skipped_files_do_not_affect_gate(self):
        """Req 32.3: .ctrl/.ctl files are skipped and must not count as failures."""
        output = _make_runner_output(
            operations=(
                _make_operation(file_name="data.txt", round_trip_ok=True),
                _make_operation(
                    file_name="skip.ctrl",
                    file_type=".ctrl",
                    skipped=True,
                    round_trip_ok=True,
                ),
            )
        )
        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
        vr = gate.verify(output)
        assert vr.included
        assert vr.round_trip_ok


# ===========================================================================
# Section 2: Multi-run VerificationSummary (Property 1 gate as a pipeline gate)
# ===========================================================================


class TestVerificationSummaryPipeline:
    """VerificationGate.verify_all across a small scenario set."""

    def test_mixed_runs_correct_included_excluded_count(self):
        """Req 5.4, 5.5: only passed runs feed statistics; failed runs are counted separately."""
        go_ok = _make_runner_output(
            runner_id=RunnerId.GO,
            variant_id="go-stream-parallel",
            operations=(_make_operation(round_trip_ok=True),),
        )
        java_ok = _make_runner_output(
            runner_id=RunnerId.JAVA,
            variant_id="java-inmem-single",
            operations=(_make_operation(file_name="file2.txt", round_trip_ok=True),),
        )
        go_fail = _make_runner_output(
            runner_id=RunnerId.GO,
            variant_id="go-stream-parallel",
            operations=(
                _make_operation(
                    file_name="bad.txt",
                    round_trip_ok=False,
                    failure_type=FailureType.CORRECTNESS_FAILURE,
                ),
            ),
        )

        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
        summary = gate.verify_all([go_ok, java_ok, go_fail])

        assert summary.total_runs == 3
        assert summary.included_runs == 2
        assert summary.excluded_runs == 1
        assert summary.correctness_excluded_runs == 1
        assert len(summary.included_results()) == 2
        assert all(r.included for r in summary.included_results())

    def test_round_trip_failure_excluded_from_stats_feed(self):
        """Property 1: a correctness failure MUST NOT enter performance statistics.

        Validates: Requirements 5.4, 5.5
        """
        bad_run = _make_runner_output(
            operations=(
                _make_operation(round_trip_ok=False, failure_type=FailureType.CORRECTNESS_FAILURE),
            )
        )
        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
        summary = gate.verify_all([bad_run])

        # The included_results() feed to StatisticsEngine must be empty
        assert summary.included_runs == 0
        assert len(summary.included_results()) == 0
        assert summary.correctness_failures > 0

    def test_all_clean_runs_all_included(self):
        """All-pass scenario: every run feeds statistics."""
        runs = [
            _make_runner_output(operations=(_make_operation(file_name=f"f{i}.txt"),))
            for i in range(5)
        ]
        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
        summary = gate.verify_all(runs)
        assert summary.included_runs == 5
        assert summary.excluded_runs == 0


# ===========================================================================
# Section 3: Property 2 gate — interoperability check
# ===========================================================================


def _copy_endpoint(name: str) -> InteropEndpoint:
    """Fake endpoint: 'encrypt'/'decrypt' by byte-copy (always passes interop)."""

    def enc(src: Path, dst: Path) -> None:
        shutil.copyfile(src, dst)

    def dec(src: Path, dst: Path) -> None:
        shutil.copyfile(src, dst)

    return InteropEndpoint(name=name, encrypt=enc, decrypt=dec)


def _tamper_consumer(name: str) -> InteropEndpoint:
    """Fake endpoint that produces wrong decryption output (forces a fail)."""

    def dec(src: Path, dst: Path) -> None:
        dst.write_bytes(b"TAMPERED_OUTPUT_MISMATCH")

    return InteropEndpoint(name=name, encrypt=lambda s, d: shutil.copyfile(s, d), decrypt=dec)


class TestInteropGatePipeline:
    """Property 2 gate: Go ↔ Java interop in the pipeline.

    Validates: Requirements 25.1, 25.2, 25.3
    """

    @pytest.fixture
    def plaintext_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "message.dat"
        p.write_bytes(b"pipeline integration test payload\x00\x01\x02" * 100)
        return p

    def test_property2_go_java_interop_passes_with_compatible_endpoints(
        self, plaintext_file: Path
    ):
        """Property 2: Go ciphertext must be decryptable by Java and vice-versa.

        Validates: Requirements 25.1, 25.2
        """
        checker = InteroperabilityChecker(
            {GO: _copy_endpoint(GO), JAVA: _copy_endpoint(JAVA)},
            pairs=[InteropPair(GO, JAVA), InteropPair(JAVA, GO)],
        )
        summary = checker.check(plaintext_file)

        assert summary.comparable, f"interop failed: {summary.non_comparable_reasons()}"
        by_dir = {(c.producer, c.consumer): c for c in summary.checks}
        assert by_dir[(GO, JAVA)].result is InteropOutcome.PASS
        assert by_dir[(JAVA, GO)].result is InteropOutcome.PASS

    def test_property2_interop_failure_marks_non_comparable(self, plaintext_file: Path):
        """Property 2: a decryption mismatch marks result non-comparable.

        Validates: Requirements 25.1, 25.2
        """
        checker = InteroperabilityChecker(
            {GO: _copy_endpoint(GO), JAVA: _tamper_consumer(JAVA)},
            pairs=[InteropPair(GO, JAVA)],
        )
        summary = checker.check(plaintext_file)

        assert not summary.comparable
        assert len(summary.failures) == 1
        assert summary.failures[0].producer == GO
        assert summary.failures[0].consumer == JAVA

    def test_property2_pending_java_does_not_block_comparability(self, plaintext_file: Path):
        """Req 25: pending interop endpoints do not cause non-comparable — only failures do."""
        from harness.interop import pending_endpoint

        checker = InteroperabilityChecker(
            {GO: _copy_endpoint(GO), JAVA: pending_endpoint(JAVA, "not yet integrated")},
            pairs=[InteropPair(GO, JAVA), InteropPair(JAVA, GO)],
        )
        summary = checker.check(plaintext_file)

        assert summary.comparable  # pending ≠ fail
        assert all(c.result is InteropOutcome.PENDING for c in summary.checks)

    def test_interop_summary_to_dict_shape_for_report(self, plaintext_file: Path):
        """Req 20.1: interop results appear in the final report under interopChecks."""
        checker = InteroperabilityChecker(
            {GO: _copy_endpoint(GO), JAVA: _copy_endpoint(JAVA)},
            pairs=[InteropPair(GO, JAVA), InteropPair(JAVA, GO)],
        )
        summary = checker.check(plaintext_file)
        d = summary.to_dict()

        assert "interopChecks" in d
        assert "comparable" in d
        checks = d["interopChecks"]
        assert len(checks) == 2
        assert all(c["result"] == "pass" for c in checks)


# ===========================================================================
# Section 4: StatisticsEngine feeds only from included runs
# ===========================================================================


class TestStatisticsEngineFromVerifiedRuns:
    """StatisticsEngine receives only runs that cleared the Verification Gate."""

    def test_round_trip_ms_matches_encrypt_plus_decrypt(self):
        """Property 6 sanity: round-trip time = encrypt + decrypt.

        Validates: Requirement 9.3
        """
        enc_ms, dec_ms = 2.5, 3.7
        assert round_trip_ms(enc_ms, dec_ms) == pytest.approx(enc_ms + dec_ms)

    def test_throughput_computed_from_included_runs_only(self):
        """Req 5.5: throughput is calculated only for runs that passed the gate.

        VerificationResult identifies which runs are included; the caller looks
        up the matching original RunnerOutput to access per-operation timings.
        """
        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)

        included_run = _make_runner_output(
            runner_id=RunnerId.GO,
            variant_id="go-stream-parallel",
            scenario_id="s1",
            operations=(_make_operation(original_bytes=1024, encrypt_ms=10.0, round_trip_ok=True),),
        )
        excluded_run = _make_runner_output(
            runner_id=RunnerId.GO,
            variant_id="go-stream-parallel",
            scenario_id="s2",
            operations=(
                _make_operation(
                    file_name="bad.txt",
                    original_bytes=99999,
                    round_trip_ok=False,
                    failure_type=FailureType.CORRECTNESS_FAILURE,
                ),
            ),
        )

        all_runs = [included_run, excluded_run]
        summary = gate.verify_all(all_runs)
        assert summary.included_runs == 1
        assert summary.excluded_runs == 1

        # Match VerificationResult back to the original RunnerOutput by scenario_id
        included_scenario_ids = {r.scenario_id for r in summary.included_results()}
        included_outputs = [r for r in all_runs if r.scenario_id in included_scenario_ids]

        included_ops = [
            op
            for output in included_outputs
            for op in output.operations
            if not op.skipped and op.encrypt_ms is not None
        ]
        total_bytes = sum(op.original_bytes for op in included_ops)
        total_enc_ms = sum(op.encrypt_ms for op in included_ops)

        tp = throughput_mb_per_sec(total_bytes, total_enc_ms)
        assert tp.computed
        assert tp.value is not None and tp.value > 0

        # Verify total_bytes doesn't include the excluded run's 99999 bytes
        assert total_bytes == 1024  # only the included run's 1024 bytes


# ===========================================================================
# Section 5: ReportGenerator — results.json atomic write
# ===========================================================================


class TestReportGeneratorAtomicWrite:
    """Req 20.1: results.json is created atomically (temp → rename)."""

    def test_results_json_is_created(self, result_dir: Path):
        """Basic smoke test: write_atomic produces results.json."""
        gen = ReportGenerator()
        path = result_dir / "results.json"
        gen.write_atomic(path, {"test": "value"})
        assert path.exists()

    def test_results_json_atomic_no_temp_file_after_success(self, result_dir: Path):
        """After successful write, no stray .tmp files remain (atomic write verification)."""
        gen = ReportGenerator()
        path = result_dir / "results.json"
        gen.write_atomic(path, {"atomic": True})

        tmp_files = list(result_dir.glob("*.tmp"))
        assert tmp_files == [], f"stray temp files found: {tmp_files}"

    def test_results_json_content_is_valid_json(self, result_dir: Path):
        """results.json must be valid, parseable JSON."""
        gen = ReportGenerator()
        path = result_dir / "results.json"
        payload = {"pocStartDate": "2025-01-01", "versions": {"go": "1.25.0"}}
        gen.write_atomic(path, payload)

        content = path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed["pocStartDate"] == "2025-01-01"
        assert parsed["versions"]["go"] == "1.25.0"

    def test_generate_builds_and_writes_full_report(self, result_dir: Path):
        """Req 20.1: generate() builds report dict and writes atomically in one step."""
        gen = ReportGenerator()
        path = result_dir / "results.json"
        result = gen.generate(
            path,
            poc_start_date="2025-08-01",
            started_at="2025-08-01T09:00:00+07:00",
            finished_at="2025-08-01T10:00:00+07:00",
            versions={"go": "1.25.0", "jdk": "25.0.0"},
            environment={"vcpu": 8, "ramMb": 8192},
            interop_checks=[
                {"producer": "go", "consumer": "java", "result": "pass"},
                {"producer": "java", "consumer": "go", "result": "pass"},
            ],
        )
        assert path.exists()
        assert result["pocStartDate"] == "2025-08-01"
        assert result["versions"]["go"] == "1.25.0"
        assert len(result["interopChecks"]) == 2

    def test_results_json_contains_required_top_level_keys(self, result_dir: Path):
        """Req 20.1: results.json has all required top-level schema keys."""
        from harness.report import RESULTS_SCHEMA_KEYS

        gen = ReportGenerator()
        path = result_dir / "results.json"
        gen.generate(path, poc_start_date="2025-08-01")

        content = json.loads(path.read_text())
        for key in RESULTS_SCHEMA_KEYS:
            assert key in content, f"Missing required key: {key!r}"


# ===========================================================================
# Section 6: Full end-to-end pipeline — Harness → fake runners → Gate → Report
# ===========================================================================


class TestFullPipelineEndToEnd:
    """Drive the complete pipeline:
    SubprocessDriver (fake runner) → VerificationGate → StatisticsEngine → ReportGenerator.

    Uses hermetic fake subprocess runners — no real Go/Java required.
    Validates Requirements 3.1, 3.3, 20.1.
    """

    def test_e2e_single_scenario_go_java_both_pass(self, make_command, result_dir: Path):
        """Req 3.1, 20.1: single scenario with both Go and Java fake runners passing.

        Both runners produce valid output → gate includes both → report written.
        """
        driver = _fake_driver()

        # Run fake Go runner
        go_cmd = make_command(variant_id="go-stream-parallel")
        go_result = driver.run(go_cmd)
        assert go_result.success

        # Run fake Java runner (same fake runner binary, different variantId)
        java_env = {**os.environ, "FAKE_STDOUT_MODE": "valid"}
        java_driver = _fake_driver(env=java_env)
        java_cmd = make_command(variant_id="java-inmem-single")
        java_result = java_driver.run(java_cmd)
        assert java_result.success

        # Verification gate
        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
        summary = gate.verify_all([go_result.output, java_result.output])
        assert summary.included_runs == 2
        assert summary.excluded_runs == 0

        # Write results.json
        gen = ReportGenerator()
        path = result_dir / "results.json"
        report = gen.generate(
            path,
            poc_start_date="2025-08-01",
            started_at="2025-08-01T09:00:00+07:00",
            finished_at="2025-08-01T09:30:00+07:00",
            versions={"go": "1.25.0", "jdk": "25.0.0"},
            environment={"vcpu": 4, "ramMb": 8192},
            interop_checks=[
                {"producer": "go", "consumer": "java", "result": "pass"},
                {"producer": "java", "consumer": "go", "result": "pass"},
            ],
            scenario_results=[{"scenarioId": "s1", "comparable": True}],
            conclusion={"preferredLanguage": "go", "rationale": "lower p50", "inconclusive": False},
        )

        assert path.exists()
        assert report["pocStartDate"] == "2025-08-01"
        assert len(report["interopChecks"]) == 2
        assert report["conclusion"]["preferredLanguage"] == "go"
        # No temp files after completion
        assert list(result_dir.glob("*.tmp")) == []

    def test_e2e_at_most_one_runner_active_per_vm(self, make_command):
        """Req 3.3: SubprocessDriver serialises runners — at most one active at a time."""
        import threading

        from harness.subprocess_driver import (
            peak_runner_count,
            reset_peak_runner_count,
        )

        reset_peak_runner_count()
        driver = _fake_driver()
        cmd = make_command()
        errors: list[Exception] = []

        def run_one():
            try:
                driver.run(cmd)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run_one) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Threads raised: {errors}"
        assert peak_runner_count() == 1, (
            f"More than one runner was active concurrently (peak={peak_runner_count()})"
        )

    def test_e2e_round_trip_failure_excluded_then_report_reflects_exclusion(
        self, result_dir: Path
    ):
        """Property 1: run with correctness failure is excluded; report reflects counts.

        Validates: Requirements 5.4, 5.5
        """
        # One good run and one bad run (round-trip failure)
        good_run = _make_runner_output(
            runner_id=RunnerId.GO,
            variant_id="go-stream-parallel",
            operations=(_make_operation(file_name="good.txt", round_trip_ok=True),),
        )
        bad_run = _make_runner_output(
            runner_id=RunnerId.GO,
            variant_id="go-stream-parallel",
            operations=(
                _make_operation(
                    file_name="corrupt.txt",
                    round_trip_ok=False,
                    failure_type=FailureType.CORRECTNESS_FAILURE,
                ),
            ),
        )

        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
        summary = gate.verify_all([good_run, bad_run])

        assert summary.included_runs == 1
        assert summary.excluded_runs == 1
        assert summary.correctness_excluded_runs == 1

        # Write verification summary to the report
        gen = ReportGenerator()
        path = result_dir / "results.json"
        report = gen.generate(
            path,
            poc_start_date="2025-08-01",
            scenario_results=[summary.to_dict()],
        )

        scenario = report["scenarioResults"][0]
        assert scenario["excludedRuns"] == 1
        assert scenario["includedRuns"] == 1
        assert scenario["correctnessExcludedRuns"] == 1


    def test_e2e_interop_gate_integrated_into_report(self, tmp_path: Path, result_dir: Path):
        """Property 2: interop check results are included in results.json.

        Validates: Requirements 25.1, 25.2, 25.3
        """
        plaintext = tmp_path / "payload.dat"
        plaintext.write_bytes(b"interop test data\x00" * 50)

        checker = InteroperabilityChecker(
            {GO: _copy_endpoint(GO), JAVA: _copy_endpoint(JAVA)},
            pairs=[InteropPair(GO, JAVA), InteropPair(JAVA, GO)],
        )
        interop_summary = checker.check(plaintext)
        assert interop_summary.comparable

        gen = ReportGenerator()
        path = result_dir / "results.json"
        report = gen.generate(
            path,
            poc_start_date="2025-08-01",
            interop_checks=interop_summary,
        )

        assert path.exists()
        checks = report["interopChecks"]
        assert len(checks) == 2
        assert all(c["result"] == "pass" for c in checks)

    def test_e2e_multiple_scenarios_small_set(self, make_command, result_dir: Path):
        """Req 3.1: run pipeline over a small multi-scenario set, report written once.

        Simulates: scenario-small (Go pass) + scenario-medium (Java pass).
        """
        driver = _fake_driver()

        scenario_results = []

        # Scenario 1: small files
        go_cmd = make_command(variant_id="go-stream-parallel")
        go_result = driver.run(go_cmd)
        assert go_result.success

        gate = VerificationGate(key_set_checksum=_CHECKSUM, corpus_checksum=_CHECKSUM)
        summary1 = gate.verify_all([go_result.output])
        scenario_results.append({
            "scenarioId": "small-files",
            **summary1.to_dict(),
        })

        # Scenario 2: medium files (same fake runner, just different variant_id label)
        java_cmd = make_command(variant_id="java-stream-single")
        java_result = driver.run(java_cmd)
        assert java_result.success

        summary2 = gate.verify_all([java_result.output])
        scenario_results.append({
            "scenarioId": "medium-files",
            **summary2.to_dict(),
        })

        gen = ReportGenerator()
        path = result_dir / "results.json"
        report = gen.generate(
            path,
            poc_start_date="2025-08-01",
            scenario_results=scenario_results,
        )

        assert path.exists()
        assert len(report["scenarioResults"]) == 2
        ids = [s["scenarioId"] for s in report["scenarioResults"]]
        assert "small-files" in ids
        assert "medium-files" in ids
        # No stray temp files
        assert list(result_dir.glob("*.tmp")) == []

    def test_e2e_results_json_overwrite_is_atomic(self, result_dir: Path):
        """Req 20.1: writing results.json a second time atomically replaces first version."""
        gen = ReportGenerator()
        path = result_dir / "results.json"

        # First write
        gen.write_atomic(path, {"run": 1})
        assert json.loads(path.read_text())["run"] == 1

        # Second write (overwrites atomically)
        gen.write_atomic(path, {"run": 2})
        assert json.loads(path.read_text())["run"] == 2

        # Still no stray temp files
        assert list(result_dir.glob("*.tmp")) == []
