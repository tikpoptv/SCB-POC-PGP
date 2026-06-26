"""Property-based tests for the deterministic Test_Corpus generator."""

import string
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness.corpus import Compressibility, FileSpec, generate_corpus

# A varied mix of supported, skip (.ctrl/.ctl) and unsupported extensions plus
# the no-extension case, so the generated plans cover every classification and
# every magic-prefixed binary type.
_EXTENSIONS = (
    ".txt", ".csv", ".pdf", ".dat", ".zip", ".gz", ".7z", ".xlsx", ".xls",
    ".ctrl", ".ctl", ".md", "",
)

_SUBDIRS = ("", "nested/", "a/b/")


@st.composite
def file_plans(draw):
    """Generate a small, varied corpus plan with guaranteed-unique file names.

    Each spec gets a per-index prefix so names never collide (a duplicate name
    would be rejected by ``generate_corpus`` and is not what this property is
    about). Sizes are kept tiny so generating the plan twice stays fast.
    """
    count = draw(st.integers(min_value=1, max_value=6))
    specs = []
    for i in range(count):
        ext = draw(st.sampled_from(_EXTENSIONS))
        subdir = draw(st.sampled_from(_SUBDIRS))
        base = draw(
            st.text(alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=8)
        )
        name = f"{subdir}f{i:02d}-{base}{ext}"
        size = draw(st.integers(min_value=0, max_value=2048))
        comp = draw(st.sampled_from(list(Compressibility)))
        specs.append(FileSpec(name=name, size_bytes=size, compressibility=comp))
    return specs


# Feature: pgp-encryption-benchmark-go-java, Property 15: ความเป็น deterministic ของการสร้าง Test_Corpus จาก seed
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(min_value=0, max_value=2**32 - 1), specs=file_plans())
def test_corpus_generation_is_deterministic(seed, specs):
    """For any seed + plan, generating twice yields byte-identical files and an
    identical aggregate corpus checksum (bit-for-bit reproducibility).
    """
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        m1 = generate_corpus(specs, d1, seed)
        m2 = generate_corpus(specs, d2, seed)

        # Aggregate corpus checksum must match exactly.
        assert m1.corpus_checksum == m2.corpus_checksum

        # Per-file checksums must match (manifests are otherwise order-stable).
        sums1 = {f.relative_path: f.sha256 for f in m1.files}
        sums2 = {f.relative_path: f.sha256 for f in m2.files}
        assert sums1 == sums2

        # Every file must be byte-for-byte identical on disk.
        for spec in specs:
            b1 = (Path(d1) / spec.name).read_bytes()
            b2 = (Path(d2) / spec.name).read_bytes()
            assert b1 == b2
            assert len(b1) == spec.size_bytes
