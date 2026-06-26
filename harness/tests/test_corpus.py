"""Unit tests for the deterministic Test_Corpus generator."""

import hashlib
import zlib

import pytest

from harness.corpus import (
    INMEM_CAP_BYTES,
    MANY_SMALL_MAX_BYTES,
    MANY_SMALL_MIN_FILES,
    Classification,
    Compressibility,
    CorpusManifest,
    FileSpec,
    SizeTier,
    build_plan,
    classify_file,
    classify_size_tier,
    default_compressibility,
    file_extension,
    generate_corpus,
    output_name,
    should_stream,
)

SEED = 123456789


@pytest.mark.parametrize(
    "name,expected",
    [
        ("report.pdf", Classification.SUPPORTED),
        ("data.TXT", Classification.SUPPORTED),  # case-insensitive
        ("book.xlsx", Classification.SUPPORTED),
        ("legacy.xls", Classification.SUPPORTED),
        ("rows.csv", Classification.SUPPORTED),
        ("bundle.zip", Classification.SUPPORTED),
        ("archive.7z", Classification.SUPPORTED),
        ("blob.dat", Classification.SUPPORTED),
        ("packed.gz", Classification.SUPPORTED),
        ("job.ctrl", Classification.SKIP),
        ("job.ctl", Classification.SKIP),
        ("notes.md", Classification.UNSUPPORTED),
        ("noext", Classification.UNSUPPORTED),
    ],
)
def test_classify_file(name, expected):
    assert classify_file(name) is expected


def test_output_name_appends_pgp():
    assert output_name("report.pdf") == "report.pdf.pgp"
    assert output_name("bundle.zip") == "bundle.zip.pgp"


@pytest.mark.parametrize("name", ["job.ctrl", "job.ctl", "notes.md"])
def test_output_name_rejects_non_supported(name):
    with pytest.raises(ValueError):
        output_name(name)


def test_file_extension_lowercases():
    assert file_extension("X.PDF") == ".pdf"
    assert file_extension("noext") == ""


@pytest.mark.parametrize(
    "size,tier",
    [
        (1024, SizeTier.SMALL),
        (1 * 1024 * 1024, SizeTier.SMALL),
        (1 * 1024 * 1024 + 1, SizeTier.MEDIUM),
        (100 * 1024 * 1024, SizeTier.MEDIUM),
        (100 * 1024 * 1024 + 1, SizeTier.LARGE),
        (1 * 1024 * 1024 * 1024, SizeTier.LARGE),
    ],
)
def test_classify_size_tier(size, tier):
    assert classify_size_tier(size) is tier


def test_should_stream_uses_inmem_cap():
    assert should_stream(INMEM_CAP_BYTES) is False
    assert should_stream(INMEM_CAP_BYTES + 1) is True


def test_default_compressibility_by_type():
    assert default_compressibility("a.txt") is Compressibility.COMPRESSIBLE
    assert default_compressibility("a.csv") is Compressibility.COMPRESSIBLE
    assert default_compressibility("a.zip") is Compressibility.INCOMPRESSIBLE
    assert default_compressibility("a.gz") is Compressibility.INCOMPRESSIBLE
    assert default_compressibility("a.7z") is Compressibility.INCOMPRESSIBLE


def _small_specs():
    return [
        FileSpec("a.txt", 4096, Compressibility.COMPRESSIBLE),
        FileSpec("b.dat", 5000, Compressibility.INCOMPRESSIBLE),
        FileSpec("c.csv", 1024, Compressibility.COMPRESSIBLE),
    ]


def test_generate_writes_exact_sizes(tmp_path):
    manifest = generate_corpus(_small_specs(), tmp_path, SEED)
    for spec in _small_specs():
        written = (tmp_path / spec.name).read_bytes()
        assert len(written) == spec.size_bytes


def test_manifest_records_checksum_per_file(tmp_path):
    manifest = generate_corpus(_small_specs(), tmp_path, SEED)
    assert isinstance(manifest, CorpusManifest)
    assert len(manifest.files) == 3
    for f in manifest.files:
        on_disk = (tmp_path / f.relative_path).read_bytes()
        assert f.sha256 == hashlib.sha256(on_disk).hexdigest()
        assert f.size_bytes == len(on_disk)


def test_aggregate_checksum_prefixed_and_changes_with_content(tmp_path):
    m1 = generate_corpus(_small_specs(), tmp_path / "one", SEED)
    assert m1.corpus_checksum.startswith("sha256:")

    # A different seed yields different content -> different aggregate checksum.
    m2 = generate_corpus(_small_specs(), tmp_path / "two", SEED + 1)
    assert m1.corpus_checksum != m2.corpus_checksum


def test_aggregate_checksum_independent_of_spec_order(tmp_path):
    specs = _small_specs()
    m1 = generate_corpus(specs, tmp_path / "a", SEED)
    m2 = generate_corpus(list(reversed(specs)), tmp_path / "b", SEED)
    assert m1.corpus_checksum == m2.corpus_checksum


def test_manifest_to_dict_is_serializable(tmp_path):
    import json

    manifest = generate_corpus(_small_specs(), tmp_path, SEED)
    text = json.dumps(manifest.to_dict())
    assert "corpusChecksum" in text


def test_same_seed_produces_identical_bytes(tmp_path):
    specs = _small_specs()
    m1 = generate_corpus(specs, tmp_path / "run1", SEED)
    m2 = generate_corpus(specs, tmp_path / "run2", SEED)
    assert m1.corpus_checksum == m2.corpus_checksum
    for f in specs:
        b1 = (tmp_path / "run1" / f.name).read_bytes()
        b2 = (tmp_path / "run2" / f.name).read_bytes()
        assert b1 == b2


def test_chunk_size_does_not_affect_content(tmp_path):
    specs = [FileSpec("big.dat", 300_000, Compressibility.INCOMPRESSIBLE)]
    m1 = generate_corpus(specs, tmp_path / "c1", SEED, chunk_size=4096)
    m2 = generate_corpus(specs, tmp_path / "c2", SEED, chunk_size=65536)
    assert (tmp_path / "c1" / "big.dat").read_bytes() == (tmp_path / "c2" / "big.dat").read_bytes()
    assert m1.corpus_checksum == m2.corpus_checksum


def test_compressible_content_compresses_far_better_than_incompressible(tmp_path):
    size = 256 * 1024
    specs = [
        FileSpec("text.txt", size, Compressibility.COMPRESSIBLE),
        FileSpec("rand.dat", size, Compressibility.INCOMPRESSIBLE),
    ]
    generate_corpus(specs, tmp_path, SEED)

    comp_ratio = len(zlib.compress((tmp_path / "text.txt").read_bytes())) / size
    incomp_ratio = len(zlib.compress((tmp_path / "rand.dat").read_bytes())) / size

    assert comp_ratio < 0.2, "compressible data should shrink a lot"
    assert incomp_ratio > 0.9, "incompressible data should barely shrink"


def test_binary_types_get_magic_prefix(tmp_path):
    specs = [
        FileSpec("doc.pdf", 4096, Compressibility.COMPRESSIBLE),
        FileSpec("a.zip", 4096, Compressibility.INCOMPRESSIBLE),
        FileSpec("a.gz", 4096, Compressibility.INCOMPRESSIBLE),
        FileSpec("a.7z", 4096, Compressibility.INCOMPRESSIBLE),
    ]
    generate_corpus(specs, tmp_path, SEED)
    assert (tmp_path / "doc.pdf").read_bytes().startswith(b"%PDF-1.7")
    assert (tmp_path / "a.zip").read_bytes().startswith(b"PK\x03\x04")
    assert (tmp_path / "a.gz").read_bytes().startswith(b"\x1f\x8b")
    assert (tmp_path / "a.7z").read_bytes().startswith(b"7z\xbc\xaf")


def test_skip_files_marked_in_manifest(tmp_path):
    specs = [
        FileSpec("ok.txt", 1024, Compressibility.COMPRESSIBLE),
        FileSpec("job.ctrl", 100, Compressibility.COMPRESSIBLE),
        FileSpec("job.ctl", 100, Compressibility.COMPRESSIBLE),
    ]
    manifest = generate_corpus(specs, tmp_path, SEED)
    by_name = {f.relative_path: f for f in manifest.files}

    assert by_name["ok.txt"].skipped is False
    assert by_name["ok.txt"].skip_reason is None

    assert by_name["job.ctrl"].skipped is True
    assert by_name["job.ctrl"].skip_reason == "control_file"
    assert by_name["job.ctl"].classification is Classification.SKIP

    # Skip files are still written so a Runner can prove it skips them.
    assert (tmp_path / "job.ctrl").exists()


def test_generate_rejects_duplicate_names(tmp_path):
    specs = [
        FileSpec("dup.txt", 10, Compressibility.COMPRESSIBLE),
        FileSpec("dup.txt", 20, Compressibility.COMPRESSIBLE),
    ]
    with pytest.raises(ValueError, match="duplicate"):
        generate_corpus(specs, tmp_path, SEED)


def test_generate_rejects_negative_size(tmp_path):
    with pytest.raises(ValueError):
        generate_corpus([FileSpec("x.txt", -1, Compressibility.COMPRESSIBLE)], tmp_path, SEED)


def test_build_plan_many_small_meets_minimum():
    plan = build_plan(SEED)
    many_small = [s for s in plan if s.resolved_tier() is SizeTier.MANY_SMALL]
    assert len(many_small) >= MANY_SMALL_MIN_FILES
    assert all(s.size_bytes <= MANY_SMALL_MAX_BYTES for s in many_small)


def test_build_plan_covers_all_tiers_and_both_compressibilities():
    plan = build_plan(SEED)
    tiers = {s.resolved_tier() for s in plan}
    assert {SizeTier.SMALL, SizeTier.MEDIUM, SizeTier.LARGE, SizeTier.MANY_SMALL} <= tiers

    comps = {s.compressibility for s in plan}
    assert comps == {Compressibility.COMPRESSIBLE, Compressibility.INCOMPRESSIBLE}


def test_build_plan_includes_skip_files():
    plan = build_plan(SEED)
    exts = {file_extension(s.name) for s in plan}
    assert ".ctrl" in exts and ".ctl" in exts


def test_build_plan_is_deterministic():
    assert build_plan(SEED) == build_plan(SEED)


def test_build_plan_rejects_oversized_many_small():
    with pytest.raises(ValueError, match="cap"):
        build_plan(SEED, many_small_size=MANY_SMALL_MAX_BYTES + 1)
