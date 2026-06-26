"""Unit tests for the ReportGenerator (task 9.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness.report import RESULTS_SCHEMA_KEYS, ReportGenerator, to_jsonable


# Helpers — stand-ins for the real component value objects (they too expose
# to_dict()), to prove the assembler accepts the to_dict() contract.
@dataclass(frozen=True)
class _FakeVersions:
    def to_dict(self) -> dict[str, object]:
        return {"go": "1.25.1", "jdk": "25.0.1", "versionMatch": True}


@dataclass(frozen=True)
class _FakeManifest:
    def to_dict(self) -> dict[str, object]:
        return {
            "keysDir": "/keys",
            "keySetChecksum": "sha256:abc",
            "keySet": [
                {"type": "RSA", "bits": 2048, "fingerprint": "FP1", "checksum": "sha256:k1"}
            ],
        }


@dataclass(frozen=True)
class _FakeInteropSummary:
    def to_dict(self) -> dict[str, object]:
        return {
            "comparable": True,
            "interopChecks": [
                {"producer": "go", "consumer": "gpg", "result": "pass"},
            ],
            "nonComparableReasons": [],
        }


def _representative_kwargs() -> dict[str, object]:
    """A full, representative set of build inputs mixing dicts and objects."""
    return dict(
        poc_start_date="2025-01-15",
        started_at="2025-01-15T09:00:00+07:00",
        finished_at="2025-01-15T10:30:00+07:00",
        versions=_FakeVersions(),
        environment={"vcpu": 8, "ramMb": 8192, "os": "Linux", "comparable": True},
        resource_quota={"cpuCores": 8, "memoryMb": 8192},
        config_used={"rounds": 30, "warmupIterations": 5},
        key_set=_FakeManifest(),
        corpus_checksum="sha256:corpus",
        noise_floor={"runner": "go", "cvRoundTrip": 0.018, "meanDiffPct": 0.7},
        interop_checks=_FakeInteropSummary(),
        rounds=[{"round": 1, "order": ["go", "java"], "warmup": 5}],
        scenario_results=[
            {
                "scenarioId": "small-files-rsa2048",
                "mode": "steady_state",
                "comparable": True,
                "nonComparableReasons": [],
                "byVariant": [
                    {
                        "runnerId": "go",
                        "variantId": "go-stream-parallel",
                        "encrypt": {"p50": 1.6, "sampleCount": 5000},
                    }
                ],
                "bestVariant": {"go": {"variantId": "go-stream-parallel"}},
                "headToHead": {"winner": "go", "inconclusive": False},
            }
        ],
        soft_trends={"suspectedMemoryLeak": False},
        cost_energy={"go": {"costPerMillionOps": 1.23, "joulesPerOp": None}},
        thermal_throttle_events=[],
        conclusion={"preferredLanguage": "go", "inconclusive": False},
    )


# Assembly
def test_build_contains_every_schema_section() -> None:
    report = ReportGenerator().build(**_representative_kwargs())
    for key in RESULTS_SCHEMA_KEYS:
        assert key in report, f"missing top-level section {key!r}"


def test_build_is_json_serializable() -> None:
    report = ReportGenerator().build(**_representative_kwargs())
    # Round-trips through JSON with no custom encoder.
    text = json.dumps(report)
    assert json.loads(text) == report


def test_build_metadata_passthrough() -> None:
    report = ReportGenerator().build(**_representative_kwargs())
    assert report["pocStartDate"] == "2025-01-15"
    assert report["startedAt"] == "2025-01-15T09:00:00+07:00"
    assert report["finishedAt"] == "2025-01-15T10:30:00+07:00"
    assert report["corpusChecksum"] == "sha256:corpus"
    assert report["versions"] == {"go": "1.25.1", "jdk": "25.0.1", "versionMatch": True}
    assert report["rounds"] == [{"round": 1, "order": ["go", "java"], "warmup": 5}]


def test_build_lifts_key_set_array_and_checksum_from_manifest() -> None:
    report = ReportGenerator().build(**_representative_kwargs())
    assert isinstance(report["keySet"], list)
    assert report["keySet"][0]["bits"] == 2048
    # keySetChecksum lifted to the top level from the manifest.
    assert report["keySetChecksum"] == "sha256:abc"


def test_build_unwraps_interop_summary_to_bare_array() -> None:
    report = ReportGenerator().build(**_representative_kwargs())
    assert report["interopChecks"] == [
        {"producer": "go", "consumer": "gpg", "result": "pass"}
    ]


def test_build_accepts_bare_key_set_and_interop_list() -> None:
    report = ReportGenerator().build(
        key_set=[{"type": "RSA", "bits": 4096}],
        key_set_checksum="sha256:explicit",
        interop_checks=[{"producer": "go", "consumer": "java", "result": "pass"}],
    )
    assert report["keySet"] == [{"type": "RSA", "bits": 4096}]
    assert report["keySetChecksum"] == "sha256:explicit"
    assert report["interopChecks"][0]["consumer"] == "java"


def test_build_defaults_are_sensible_when_empty() -> None:
    report = ReportGenerator().build()
    assert report["versions"] == {}
    assert report["environment"] == {}
    assert report["keySet"] == []
    assert report["interopChecks"] == []
    assert report["rounds"] == []
    assert report["scenarioResults"] == []
    assert report["thermalThrottleEvents"] == []
    assert report["noiseFloor"] is None
    assert report["conclusion"] is None
    # Still fully serialisable.
    json.dumps(report)


def test_write_atomic_produces_complete_file(tmp_path: Path) -> None:
    gen = ReportGenerator()
    report = gen.build(**_representative_kwargs())
    target = tmp_path / "results.json"

    gen.write_atomic(target, report)

    assert target.exists()
    # The file is complete and parses back to the same document.
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == report
    # No temp/scratch files left behind in the directory.
    assert [p.name for p in tmp_path.iterdir()] == ["results.json"]


def test_generate_builds_and_writes_and_returns_dict(tmp_path: Path) -> None:
    gen = ReportGenerator()
    target = tmp_path / "out" / "results.json"  # parent created on demand

    report = gen.generate(target, **_representative_kwargs())

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == report


def test_write_atomic_failure_leaves_no_partial_file(tmp_path: Path) -> None:
    gen = ReportGenerator()
    target = tmp_path / "results.json"

    # A non-serialisable value (raw bytes) must abort during serialisation,
    # before any file is created.
    bad_report = {"scenarioResults": [{"blob": b"\x00\x01"}]}

    with pytest.raises(TypeError):
        gen.write_atomic(target, bad_report)

    # Neither the target nor any temp file exists.
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_atomic_overwrites_existing_atomically(tmp_path: Path) -> None:
    gen = ReportGenerator()
    target = tmp_path / "results.json"
    target.write_text("old-and-stale", encoding="utf-8")

    report = gen.build(poc_start_date="2025-02-02")
    gen.write_atomic(target, report)

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["pocStartDate"] == "2025-02-02"
    assert [p.name for p in tmp_path.iterdir()] == ["results.json"]


def test_write_atomic_cleans_temp_on_rename_failure(tmp_path: Path, monkeypatch) -> None:
    gen = ReportGenerator()
    report = gen.build(**_representative_kwargs())
    target = tmp_path / "results.json"

    # Simulate a crash at the rename step (after the temp file is written).
    def _boom(src, dst):  # noqa: ANN001
        raise OSError("simulated rename failure")

    monkeypatch.setattr("harness.report.os.replace", _boom)

    with pytest.raises(OSError, match="simulated rename failure"):
        gen.write_atomic(target, report)

    # Target never created and the temp file was cleaned up.
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


# to_jsonable helper
def test_to_jsonable_unwraps_nested_to_dict_objects() -> None:
    out = to_jsonable({"versions": _FakeVersions(), "items": [_FakeManifest()]})
    assert out["versions"]["go"] == "1.25.1"
    assert out["items"][0]["keySetChecksum"] == "sha256:abc"


def test_to_jsonable_rejects_unserialisable() -> None:
    with pytest.raises(TypeError):
        to_jsonable(object())
