"""Unit tests for the human-readable report renderer (task 9.2)."""

from __future__ import annotations

from pathlib import Path

from harness.report import ReportGenerator
from harness.report_human import (
    NOT_AVAILABLE,
    render_html,
    render_markdown,
    write_html,
    write_markdown,
    write_reports,
)


# A representative assembled dict (built via the real ReportGenerator)
def _go_variant() -> dict[str, object]:
    return {
        "runnerId": "go",
        "variantId": "go-stream-parallel",
        "keyType": "RSA",
        "keyBits": 2048,
        "cipher": "AES-256",
        "compression": "ZLIB",
        "outputEncoding": "binary",
        "memoryMode": "streaming",
        "sizeTier": "small",
        "encrypt": {
            "min": 1.2, "mean": 1.7, "p50": 1.6, "p95": 2.4, "p99": 3.1,
            "max": 4.0, "stddev": 0.3, "cv": 0.18, "sampleCount": 5000,
        },
        "roundTripMs": {"p50": 3.4},
        "aggregateThroughput": {"concurrency": 4, "mbPerSec": 1820.5, "filesPerSec": 1080.0},
        "cpuPct": {"avg": 72.0, "max": 98.0},
        "ramMb": {"avg": 210.0, "peak": 512.0},
        "errorRate": 0.0,
        "byFileType": {".pdf": {"p50Ms": 3.4, "ciphertextBytes": 612001}},
    }


def _java_variant() -> dict[str, object]:
    return {
        "runnerId": "java",
        "variantId": "java-native-stream-parallel",
        "keyType": "RSA",
        "keyBits": 2048,
        "cipher": "AES-256",
        "compression": "ZLIB",
        "outputEncoding": "binary",
        "memoryMode": "streaming",
        "sizeTier": "small",
        "encrypt": {
            "min": 1.4, "mean": 1.9, "p50": 1.8, "p95": 2.7, "p99": 3.5,
            "max": 4.6, "stddev": 0.35, "cv": 0.19, "sampleCount": 5000,
        },
        "roundTripMs": {"p50": 3.6},
        "aggregateThroughput": {"concurrency": 4, "mbPerSec": 1700.0, "filesPerSec": 1000.0},
        "cpuPct": {"avg": 75.0, "max": 99.0},
        "ramMb": {"avg": 240.0, "peak": 600.0},
        "errorRate": 0.0,
        "byFileType": {".pdf": {"p50Ms": 3.6, "ciphertextBytes": 612050}},
    }


def _representative_report() -> dict[str, object]:
    return ReportGenerator().build(
        poc_start_date="2025-01-15",
        started_at="2025-01-15T09:00:00+07:00",
        finished_at="2025-01-15T10:30:00+07:00",
        versions={"go": "1.25.1", "jdk": "25.0.1", "versionMatch": True},
        environment={"vcpu": 8, "ramMb": 8192, "os": "Linux", "cpuArch": "x86_64"},
        scenario_results=[
            {
                "scenarioId": "small-files-rsa2048",
                "mode": "steady_state",
                "comparable": True,
                "nonComparableReasons": [],
                "byVariant": [_go_variant(), _java_variant()],
                "bestVariant": {
                    "go": {"variantId": "go-stream-parallel", "criterion": "p50_roundtrip", "value": 3.4},
                    "java": {"variantId": "java-native-stream-parallel", "criterion": "p50_roundtrip", "value": 3.6},
                },
                "headToHead": {
                    "winner": "go", "decidedBy": "p50_roundtrip",
                    "diffPct": 5.6, "inconclusive": False,
                },
            },
            {
                "scenarioId": "large-files-cipher-unsupported",
                "mode": "steady_state",
                "comparable": False,
                "nonComparableReasons": ["java: cipher CAMELLIA-256 not supported"],
                "byVariant": [],
                "bestVariant": {},
                "headToHead": {},
            },
        ],
        conclusion={"preferredLanguage": "go", "rationale": "Lower p50 round-trip across scenarios.", "inconclusive": False},
    )


def test_markdown_has_head_to_head_table() -> None:
    md = render_markdown(_representative_report())
    assert "Head-to-head" in md
    assert "small-files-rsa2048" in md
    assert "go-stream-parallel" in md
    assert "java-native-stream-parallel" in md
    assert "p50_roundtrip" in md
    assert "5.60%" in md  # diff %
    assert "Deciding-metric statistics" in md
    assert "p50 (median)" in md


def test_html_has_head_to_head_table() -> None:
    out = render_html(_representative_report())
    assert "Head-to-head" in out
    assert "small-files-rsa2048" in out
    assert "go-stream-parallel" in out
    assert "java-native-stream-parallel" in out
    assert "5.60%" in out
    assert "<table>" in out


def test_winner_is_shown() -> None:
    report = _representative_report()
    assert "go" in render_markdown(report)
    assert "go" in render_html(report)


def test_inconclusive_head_to_head_renders_inconclusive() -> None:
    report = ReportGenerator().build(
        scenario_results=[
            {
                "scenarioId": "tie",
                "mode": "steady_state",
                "comparable": True,
                "byVariant": [],
                "bestVariant": {"go": {"variantId": "g"}, "java": {"variantId": "j"}},
                "headToHead": {"winner": None, "diffPct": 2.0, "inconclusive": True},
            }
        ],
    )
    assert "inconclusive" in render_markdown(report)
    assert "inconclusive" in render_html(report)


def test_non_comparable_list_appears_in_both() -> None:
    report = _representative_report()
    md = render_markdown(report)
    out = render_html(report)
    assert "Non-comparable" in md and "Non-comparable" in out
    assert "large-files-cipher-unsupported" in md
    assert "large-files-cipher-unsupported" in out
    assert "CAMELLIA-256 not supported" in md
    assert "CAMELLIA-256 not supported" in out


# Breakdowns
def test_breakdowns_present_in_markdown() -> None:
    md = render_markdown(_representative_report())
    assert "By file type" in md
    assert ".pdf" in md
    assert "612001" in md            # ciphertext size
    assert "By cipher / compression" in md
    assert "AES-256" in md and "ZLIB" in md
    assert "By key type / size" in md
    assert "RSA" in md and "2048" in md
    assert "By size-tier" in md and "small" in md
    assert "By streaming vs in-memory" in md and "streaming" in md
    assert "By concurrency level" in md and "1820.5" in md


def test_breakdowns_present_in_html() -> None:
    out = render_html(_representative_report())
    assert "By file type" in out
    assert ".pdf" in out
    assert "612001" in out
    assert "By cipher / compression" in out
    assert "By key type / size" in out
    assert "By size-tier" in out
    assert "By streaming vs in-memory" in out
    assert "By concurrency level" in out


def test_conclusion_present_in_both() -> None:
    report = _representative_report()
    md = render_markdown(report)
    out = render_html(report)
    assert "Conclusion" in md and "Conclusion" in out
    assert "go" in md and "go" in out
    assert "Lower p50 round-trip" in md
    assert "Lower p50 round-trip" in out


def test_inconclusive_conclusion() -> None:
    report = ReportGenerator().build(conclusion={"inconclusive": True})
    md = render_markdown(report)
    assert "Inconclusive" in md
    assert "Inconclusive" in render_html(report)


def test_empty_report_renders_not_available_without_crashing() -> None:
    empty = ReportGenerator().build()
    md = render_markdown(empty)
    out = render_html(empty)
    # No crash, and missing sections are flagged rather than omitted.
    assert NOT_AVAILABLE in md
    assert "not available" in out
    # Conclusion absent -> not available.
    assert "Conclusion" in md and "Conclusion" in out
    # All breakdown headings still present.
    for heading in (
        "By file type",
        "By cipher / compression",
        "By key type / size",
        "By size-tier",
        "By streaming vs in-memory",
        "By concurrency level",
    ):
        assert heading in md
        assert heading in out


def test_render_does_not_crash_on_garbage_shapes() -> None:
    # Wrong-typed sections must degrade gracefully, not raise.
    weird = {
        "scenarioResults": "not-a-list",
        "versions": ["unexpected"],
        "conclusion": 42,
    }
    md = render_markdown(weird)
    out = render_html(weird)
    assert "Head-to-head" in md
    assert "Head-to-head" in out


def test_html_escapes_reason_text() -> None:
    report = ReportGenerator().build(
        scenario_results=[
            {
                "scenarioId": "x",
                "comparable": False,
                "nonComparableReasons": ["<script>alert('x')</script>"],
                "byVariant": [],
            }
        ]
    )
    out = render_html(report)
    assert "<script>alert" not in out
    assert "&lt;script&gt;" in out


# Write helpers
def test_write_markdown_and_html(tmp_path: Path) -> None:
    report = _representative_report()
    md_path = write_markdown(tmp_path / "report.md", report)
    html_path = write_html(tmp_path / "report.html", report)

    assert md_path.exists() and html_path.exists()
    assert "Head-to-head" in md_path.read_text(encoding="utf-8")
    assert "<html" in html_path.read_text(encoding="utf-8")


def test_write_reports_writes_both(tmp_path: Path) -> None:
    report = _representative_report()
    md_path, html_path = write_reports(tmp_path / "out", report)

    assert md_path.name == "report.md"
    assert html_path.name == "report.html"
    assert md_path.exists() and html_path.exists()
    assert "small-files-rsa2048" in md_path.read_text(encoding="utf-8")
    assert "small-files-rsa2048" in html_path.read_text(encoding="utf-8")
