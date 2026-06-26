"""Human-readable report renderer: ``report.md`` / ``report.html``.

Consumes the same assembled dict produced by
:meth:`harness.report.ReportGenerator.build` (statistics are never recomputed)
and renders operator-facing Markdown and HTML summaries. Rendering is
defensive: a missing or empty section renders as a "not available" note rather
than raising.
"""

from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "render_markdown",
    "render_html",
    "write_markdown",
    "write_html",
    "write_reports",
    "NOT_AVAILABLE",
]

#: Sentinel text rendered for any section that is absent or empty in the dict.
NOT_AVAILABLE = "_not available_"

#: The deciding-metric statistics surfaced per Best_Variant.
_STAT_KEYS: tuple[str, ...] = ("min", "mean", "p50", "p95", "p99", "max")

#: Runner ids compared head-to-head.
_RUNNERS: tuple[str, ...] = ("go", "java")


def _as_mapping(value: Any) -> dict[str, Any]:
    """Return ``value`` as a dict, or an empty dict if it is not a mapping."""
    return dict(value) if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> list[Any]:
    """Return ``value`` as a list, or an empty list for non-sequence input."""
    if isinstance(value, (str, bytes, Mapping)):
        return []
    if isinstance(value, Sequence):
        return list(value)
    return []


def _fmt(value: Any) -> str:
    """Format a scalar for display; ``None`` becomes an em dash."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        # Trim noisy trailing zeros while keeping useful precision.
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text if text else "0"
    return str(value)


def _fmt_pct(value: Any) -> str:
    """Format a percentage value (already in percent units)."""
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _winner_label(head_to_head: Mapping[str, Any]) -> str:
    """Human label for a head-to-head outcome."""
    if not head_to_head:
        return "inconclusive"
    if head_to_head.get("inconclusive"):
        return "inconclusive"
    winner = head_to_head.get("winner")
    return str(winner) if winner else "inconclusive"


def _find_variant_stats(
    scenario: Mapping[str, Any], runner: str
) -> dict[str, Any]:
    """Return the ``byVariant`` record for ``runner``'s Best_Variant.

    Resolves ``bestVariant[runner].variantId`` against the ``byVariant`` array.
    Returns ``{}`` when the data is not present.
    """
    best = _as_mapping(_as_mapping(scenario.get("bestVariant")).get(runner))
    variant_id = best.get("variantId")
    for record in _as_sequence(scenario.get("byVariant")):
        rec = _as_mapping(record)
        if rec.get("runnerId") == runner and (
            variant_id is None or rec.get("variantId") == variant_id
        ):
            return rec
    return {}


def _stat_row(stats: Mapping[str, Any]) -> list[str]:
    """Format the canonical statistic keys as display cells."""
    return [_fmt(stats.get(key)) for key in _STAT_KEYS]


def _metadata_rows(report: Mapping[str, Any]) -> list[tuple[str, str]]:
    versions = _as_mapping(report.get("versions"))
    env = _as_mapping(report.get("environment"))
    rows: list[tuple[str, str]] = [
        ("POC start date", _fmt(report.get("pocStartDate"))),
        ("Started at", _fmt(report.get("startedAt"))),
        ("Finished at", _fmt(report.get("finishedAt"))),
        ("Go version", _fmt(versions.get("go"))),
        ("JDK version", _fmt(versions.get("jdk"))),
        ("Version match", _fmt(versions.get("versionMatch"))),
        ("OS / arch", f"{_fmt(env.get('os'))} / {_fmt(env.get('cpuArch'))}"),
        ("vCPU / RAM (MB)", f"{_fmt(env.get('vcpu'))} / {_fmt(env.get('ramMb'))}"),
    ]
    return rows


def _head_to_head_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build one head-to-head entry per Scenario."""
    rows: list[dict[str, Any]] = []
    for scenario in _as_sequence(report.get("scenarioResults")):
        sc = _as_mapping(scenario)
        best = _as_mapping(sc.get("bestVariant"))
        h2h = _as_mapping(sc.get("headToHead"))
        go_best = _as_mapping(best.get("go"))
        java_best = _as_mapping(best.get("java"))
        rows.append(
            {
                "scenarioId": sc.get("scenarioId", "—"),
                "mode": sc.get("mode", "—"),
                "comparable": sc.get("comparable", True),
                "goVariant": go_best.get("variantId"),
                "javaVariant": java_best.get("variantId"),
                "goValue": go_best.get("value"),
                "javaValue": java_best.get("value"),
                "decidedBy": h2h.get("decidedBy") or go_best.get("criterion"),
                "diffPct": h2h.get("diffPct"),
                "winner": _winner_label(h2h),
                "goStats": _find_variant_stats(sc, "go").get("encrypt") or {},
                "javaStats": _find_variant_stats(sc, "java").get("encrypt") or {},
            }
        )
    return rows


def _non_comparable_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Scenarios marked non-comparable, with reasons."""
    rows: list[dict[str, Any]] = []
    for scenario in _as_sequence(report.get("scenarioResults")):
        sc = _as_mapping(scenario)
        reasons = _as_sequence(sc.get("nonComparableReasons"))
        if sc.get("comparable") is False or reasons:
            rows.append(
                {
                    "scenarioId": sc.get("scenarioId", "—"),
                    "mode": sc.get("mode", "—"),
                    "reasons": [str(r) for r in reasons] or ["(unspecified)"],
                }
            )
    return rows


def _iter_variants(report: Mapping[str, Any]):
    """Yield ``(scenarioId, variantRecord)`` for every byVariant entry."""
    for scenario in _as_sequence(report.get("scenarioResults")):
        sc = _as_mapping(scenario)
        scenario_id = sc.get("scenarioId", "—")
        for record in _as_sequence(sc.get("byVariant")):
            yield scenario_id, _as_mapping(record)


def _by_file_type_rows(report: Mapping[str, Any]) -> list[list[str]]:
    """Breakdown by file type, incl. ciphertext size."""
    rows: list[list[str]] = []
    for scenario_id, rec in _iter_variants(report):
        by_file = _as_mapping(rec.get("byFileType"))
        for file_type, stats in by_file.items():
            st = _as_mapping(stats)
            rows.append(
                [
                    str(scenario_id),
                    _fmt(rec.get("runnerId")),
                    _fmt(rec.get("variantId")),
                    str(file_type),
                    _fmt(st.get("p50Ms")),
                    _fmt(st.get("ciphertextBytes")),
                ]
            )
    return rows


def _cipher_compression_rows(report: Mapping[str, Any]) -> list[list[str]]:
    """Breakdown by cipher / compression with ciphertext size."""
    rows: list[list[str]] = []
    for scenario_id, rec in _iter_variants(report):
        if rec.get("cipher") is None and rec.get("compression") is None:
            continue
        round_trip = _as_mapping(rec.get("roundTripMs")).get("p50")
        # Ciphertext size: sum across file types when available.
        ciphertext = None
        sizes = [
            _as_mapping(s).get("ciphertextBytes")
            for s in _as_mapping(rec.get("byFileType")).values()
        ]
        sizes = [s for s in sizes if isinstance(s, (int, float))]
        if sizes:
            ciphertext = sum(sizes)
        rows.append(
            [
                str(scenario_id),
                _fmt(rec.get("runnerId")),
                _fmt(rec.get("cipher")),
                _fmt(rec.get("compression")),
                _fmt(rec.get("outputEncoding")),
                _fmt(round_trip),
                _fmt(ciphertext),
            ]
        )
    return rows


def _key_rows(report: Mapping[str, Any]) -> list[list[str]]:
    """Breakdown by key type / size."""
    rows: list[list[str]] = []
    for scenario_id, rec in _iter_variants(report):
        if rec.get("keyType") is None and rec.get("keyBits") is None:
            continue
        round_trip = _as_mapping(rec.get("roundTripMs")).get("p50")
        rows.append(
            [
                str(scenario_id),
                _fmt(rec.get("runnerId")),
                _fmt(rec.get("variantId")),
                _fmt(rec.get("keyType")),
                _fmt(rec.get("keyBits")),
                _fmt(round_trip),
            ]
        )
    return rows


def _size_tier_rows(report: Mapping[str, Any]) -> list[list[str]]:
    """Breakdown by size-tier where present."""
    rows: list[list[str]] = []
    for scenario_id, rec in _iter_variants(report):
        tier = rec.get("sizeTier")
        if tier is None:
            continue
        round_trip = _as_mapping(rec.get("roundTripMs")).get("p50")
        ram = _as_mapping(rec.get("ramMb"))
        rows.append(
            [
                str(scenario_id),
                _fmt(rec.get("runnerId")),
                str(tier),
                _fmt(round_trip),
                _fmt(ram.get("avg")),
                _fmt(ram.get("peak")),
            ]
        )
    return rows


def _memory_mode_rows(report: Mapping[str, Any]) -> list[list[str]]:
    """Breakdown by streaming vs in-memory.

    Uses an explicit ``memoryMode`` field when present; otherwise infers from
    the variant id (``stream`` / ``in-mem``/``inmem``).
    """
    rows: list[list[str]] = []
    for scenario_id, rec in _iter_variants(report):
        mode = rec.get("memoryMode")
        if mode is None:
            variant_id = str(rec.get("variantId") or "").lower()
            if "stream" in variant_id:
                mode = "streaming"
            elif "inmem" in variant_id or "in-mem" in variant_id:
                mode = "in-memory"
        if mode is None:
            continue
        round_trip = _as_mapping(rec.get("roundTripMs")).get("p50")
        ram = _as_mapping(rec.get("ramMb"))
        rows.append(
            [
                str(scenario_id),
                _fmt(rec.get("runnerId")),
                str(mode),
                _fmt(round_trip),
                _fmt(ram.get("avg")),
                _fmt(ram.get("peak")),
            ]
        )
    return rows


def _concurrency_rows(report: Mapping[str, Any]) -> list[list[str]]:
    """Breakdown by concurrency level."""
    rows: list[list[str]] = []
    for scenario_id, rec in _iter_variants(report):
        agg = _as_mapping(rec.get("aggregateThroughput"))
        if not agg:
            continue
        cpu = _as_mapping(rec.get("cpuPct"))
        rows.append(
            [
                str(scenario_id),
                _fmt(rec.get("runnerId")),
                _fmt(agg.get("concurrency")),
                _fmt(agg.get("mbPerSec")),
                _fmt(agg.get("filesPerSec")),
                _fmt(cpu.get("avg")),
                _fmt(cpu.get("max")),
            ]
        )
    return rows


def _conclusion(report: Mapping[str, Any]) -> dict[str, Any]:
    """Overall conclusion view."""
    conclusion = _as_mapping(report.get("conclusion"))
    if not conclusion:
        return {"text": NOT_AVAILABLE, "rationale": None}
    if conclusion.get("inconclusive"):
        text = "Inconclusive — no language is decisively more suitable (Req 20.4)."
    else:
        lang = conclusion.get("preferredLanguage")
        text = (
            f"**{lang}** is the more suitable language for the PGP "
            "encrypt/decrypt workload."
            if lang
            else "Inconclusive."
        )
    return {"text": text, "rationale": conclusion.get("rationale")}


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        return NOT_AVAILABLE + "\n"
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out) + "\n"


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render the assembled ``results`` dict to a Markdown ``report.md`` string.

    Consumes the same dict produced by :meth:`harness.report.ReportGenerator.build`
    (no statistics are recomputed). Missing/empty sections render as
    :data:`NOT_AVAILABLE`.
    """
    report = _as_mapping(report)
    parts: list[str] = ["# PGP Benchmark — Go vs Java\n"]

    # 1. Metadata
    parts.append("## Run metadata\n")
    parts.append(
        _md_table(
            ["Field", "Value"],
            [[k, v] for k, v in _metadata_rows(report)],
        )
    )

    # 2. Head-to-head per scenario
    parts.append("## Head-to-head: Go Best_Variant vs Java Best_Variant\n")
    h2h_rows = _head_to_head_rows(report)
    if not h2h_rows:
        parts.append(NOT_AVAILABLE + "\n")
    else:
        summary = [
            [
                r["scenarioId"],
                r["mode"],
                _fmt(r["goVariant"]),
                _fmt(r["javaVariant"]),
                _fmt(r["decidedBy"]),
                _fmt(r["goValue"]),
                _fmt(r["javaValue"]),
                _fmt_pct(r["diffPct"]),
                r["winner"],
            ]
            for r in h2h_rows
        ]
        parts.append(
            _md_table(
                [
                    "Scenario",
                    "Mode",
                    "Go variant",
                    "Java variant",
                    "Decided by",
                    "Go value",
                    "Java value",
                    "Diff %",
                    "Winner",
                ],
                summary,
            )
        )
        # Deciding-metric statistics per Best_Variant.
        parts.append("\n### Deciding-metric statistics (per Best_Variant)\n")
        stat_rows: list[list[str]] = []
        for r in h2h_rows:
            for runner, stats in (("go", r["goStats"]), ("java", r["javaStats"])):
                stat_rows.append(
                    [r["scenarioId"], runner, *_stat_row(_as_mapping(stats))]
                )
        parts.append(
            _md_table(
                ["Scenario", "Runner", *[_STAT_KEYS_LABEL[k] for k in _STAT_KEYS]],
                stat_rows,
            )
        )

    # 3. Non-comparable
    parts.append("\n## Non-comparable scenarios / runs\n")
    nc_rows = _non_comparable_rows(report)
    if not nc_rows:
        parts.append("None — all scenarios were comparable.\n")
    else:
        parts.append(
            _md_table(
                ["Scenario", "Mode", "Reason(s)"],
                [
                    [r["scenarioId"], r["mode"], "; ".join(r["reasons"])]
                    for r in nc_rows
                ],
            )
        )

    # 4. Breakdowns
    parts.append("\n## Breakdowns\n")
    parts.append("\n### By file type (Req 32.6)\n")
    parts.append(
        _md_table(
            ["Scenario", "Runner", "Variant", "File type", "p50 (ms)", "Ciphertext (bytes)"],
            _by_file_type_rows(report),
        )
    )
    parts.append("\n### By cipher / compression (Req 18.3, 30.3)\n")
    parts.append(
        _md_table(
            ["Scenario", "Runner", "Cipher", "Compression", "Encoding", "Round-trip p50 (ms)", "Ciphertext (bytes)"],
            _cipher_compression_rows(report),
        )
    )
    parts.append("\n### By key type / size (Req 14.4)\n")
    parts.append(
        _md_table(
            ["Scenario", "Runner", "Variant", "Key type", "Key bits", "Round-trip p50 (ms)"],
            _key_rows(report),
        )
    )
    parts.append("\n### By size-tier (Req 13.3)\n")
    parts.append(
        _md_table(
            ["Scenario", "Runner", "Size tier", "Round-trip p50 (ms)", "RAM avg (MB)", "RAM peak (MB)"],
            _size_tier_rows(report),
        )
    )
    parts.append("\n### By streaming vs in-memory (Req 15.3)\n")
    parts.append(
        _md_table(
            ["Scenario", "Runner", "Memory mode", "Round-trip p50 (ms)", "RAM avg (MB)", "RAM peak (MB)"],
            _memory_mode_rows(report),
        )
    )
    parts.append("\n### By concurrency level (Req 16.3)\n")
    parts.append(
        _md_table(
            ["Scenario", "Runner", "Concurrency", "MB/sec", "files/sec", "CPU avg %", "CPU max %"],
            _concurrency_rows(report),
        )
    )

    # 5. Conclusion
    parts.append("\n## Conclusion\n")
    concl = _conclusion(report)
    parts.append(concl["text"] + "\n")
    if concl["rationale"]:
        parts.append("\n> " + str(concl["rationale"]) + "\n")

    return "\n".join(parts).rstrip() + "\n"


#: Display labels for the statistic keys.
_STAT_KEYS_LABEL = {
    "min": "min",
    "mean": "mean",
    "p50": "p50 (median)",
    "p95": "p95",
    "p99": "p99",
    "max": "max",
}


def _h(value: Any) -> str:
    """HTML-escape a value for safe embedding."""
    return html.escape(str(value), quote=True)


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return f'<p class="not-available">{_h(NOT_AVAILABLE)}</p>'
    head = "".join(f"<th>{_h(c)}</th>" for c in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_h(c)}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(report: Mapping[str, Any]) -> str:
    """Render the assembled ``results`` dict to a self-contained ``report.html``.

    Mirrors :func:`render_markdown` section-for-section. Missing/empty sections
    render as a *"not available"* note.
    """
    report = _as_mapping(report)
    sections: list[str] = []

    # 1. Metadata
    sections.append("<h2>Run metadata</h2>")
    sections.append(
        _html_table(["Field", "Value"], [[k, v] for k, v in _metadata_rows(report)])
    )

    # 2. Head-to-head
    sections.append("<h2>Head-to-head: Go Best_Variant vs Java Best_Variant</h2>")
    h2h_rows = _head_to_head_rows(report)
    if not h2h_rows:
        sections.append(f'<p class="not-available">{_h(NOT_AVAILABLE)}</p>')
    else:
        summary = [
            [
                r["scenarioId"],
                r["mode"],
                _fmt(r["goVariant"]),
                _fmt(r["javaVariant"]),
                _fmt(r["decidedBy"]),
                _fmt(r["goValue"]),
                _fmt(r["javaValue"]),
                _fmt_pct(r["diffPct"]),
                r["winner"],
            ]
            for r in h2h_rows
        ]
        sections.append(
            _html_table(
                [
                    "Scenario",
                    "Mode",
                    "Go variant",
                    "Java variant",
                    "Decided by",
                    "Go value",
                    "Java value",
                    "Diff %",
                    "Winner",
                ],
                summary,
            )
        )
        sections.append("<h3>Deciding-metric statistics (per Best_Variant)</h3>")
        stat_rows: list[list[Any]] = []
        for r in h2h_rows:
            for runner, stats in (("go", r["goStats"]), ("java", r["javaStats"])):
                stat_rows.append([r["scenarioId"], runner, *_stat_row(_as_mapping(stats))])
        sections.append(
            _html_table(
                ["Scenario", "Runner", *[_STAT_KEYS_LABEL[k] for k in _STAT_KEYS]],
                stat_rows,
            )
        )

    # 3. Non-comparable
    sections.append("<h2>Non-comparable scenarios / runs</h2>")
    nc_rows = _non_comparable_rows(report)
    if not nc_rows:
        sections.append("<p>None — all scenarios were comparable.</p>")
    else:
        sections.append(
            _html_table(
                ["Scenario", "Mode", "Reason(s)"],
                [[r["scenarioId"], r["mode"], "; ".join(r["reasons"])] for r in nc_rows],
            )
        )

    # 4. Breakdowns
    sections.append("<h2>Breakdowns</h2>")
    sections.append("<h3>By file type (Req 32.6)</h3>")
    sections.append(
        _html_table(
            ["Scenario", "Runner", "Variant", "File type", "p50 (ms)", "Ciphertext (bytes)"],
            _by_file_type_rows(report),
        )
    )
    sections.append("<h3>By cipher / compression (Req 18.3, 30.3)</h3>")
    sections.append(
        _html_table(
            ["Scenario", "Runner", "Cipher", "Compression", "Encoding", "Round-trip p50 (ms)", "Ciphertext (bytes)"],
            _cipher_compression_rows(report),
        )
    )
    sections.append("<h3>By key type / size (Req 14.4)</h3>")
    sections.append(
        _html_table(
            ["Scenario", "Runner", "Variant", "Key type", "Key bits", "Round-trip p50 (ms)"],
            _key_rows(report),
        )
    )
    sections.append("<h3>By size-tier (Req 13.3)</h3>")
    sections.append(
        _html_table(
            ["Scenario", "Runner", "Size tier", "Round-trip p50 (ms)", "RAM avg (MB)", "RAM peak (MB)"],
            _size_tier_rows(report),
        )
    )
    sections.append("<h3>By streaming vs in-memory (Req 15.3)</h3>")
    sections.append(
        _html_table(
            ["Scenario", "Runner", "Memory mode", "Round-trip p50 (ms)", "RAM avg (MB)", "RAM peak (MB)"],
            _memory_mode_rows(report),
        )
    )
    sections.append("<h3>By concurrency level (Req 16.3)</h3>")
    sections.append(
        _html_table(
            ["Scenario", "Runner", "Concurrency", "MB/sec", "files/sec", "CPU avg %", "CPU max %"],
            _concurrency_rows(report),
        )
    )

    # 5. Conclusion
    sections.append("<h2>Conclusion</h2>")
    concl = _conclusion(report)
    # Strip Markdown emphasis markers for HTML display.
    text = str(concl["text"]).replace("**", "")
    sections.append(f"<p>{_h(text)}</p>")
    if concl["rationale"]:
        sections.append(f"<blockquote>{_h(concl['rationale'])}</blockquote>")

    body = "\n".join(sections)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        "<title>PGP Benchmark — Go vs Java</title>\n"
        "<style>\n"
        "body{font-family:system-ui,Arial,sans-serif;margin:2rem;color:#1a1a1a;}\n"
        "table{border-collapse:collapse;margin:0.5rem 0 1.5rem;}\n"
        "th,td{border:1px solid #ccc;padding:0.35rem 0.6rem;text-align:left;}\n"
        "th{background:#f2f2f2;}\n"
        ".not-available{color:#888;font-style:italic;}\n"
        "blockquote{border-left:4px solid #ccc;margin:0.5rem 0;padding-left:1rem;color:#444;}\n"
        "</style>\n</head>\n<body>\n"
        "<h1>PGP Benchmark — Go vs Java</h1>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def write_markdown(path: str | os.PathLike[str], report: Mapping[str, Any]) -> Path:
    """Render ``report`` to Markdown and write it to ``path`` (``report.md``)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(report), encoding="utf-8")
    return target


def write_html(path: str | os.PathLike[str], report: Mapping[str, Any]) -> Path:
    """Render ``report`` to HTML and write it to ``path`` (``report.html``)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(report), encoding="utf-8")
    return target


def write_reports(
    directory: str | os.PathLike[str],
    report: Mapping[str, Any],
    *,
    md_name: str = "report.md",
    html_name: str = "report.html",
) -> tuple[Path, Path]:
    """Write both ``report.md`` and ``report.html`` into ``directory``.

    Returns ``(markdown_path, html_path)``.
    """
    base = Path(directory)
    return (
        write_markdown(base / md_name, report),
        write_html(base / html_name, report),
    )
