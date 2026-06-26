"""Property-based tests for file-type classification + output naming."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness.corpus import (
    SKIP_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    Classification,
    classify_file,
    file_extension,
    output_name,
)

# A reasonable "stem" (base name) for a file: arbitrary text, but we forbid the
# path separators and the dot so the stem can never introduce another extension.
# The stem is non-empty so that ``stem + ext`` is a genuine file-with-extension
# (e.g. ``a.txt``) rather than a hidden dotfile like ``.txt``, which has no
_STEM = st.text(
    alphabet=st.characters(blacklist_characters="./\\", blacklist_categories=("Cs",)),
    min_size=1,
    max_size=24,
)

# Extensions we know about, generated with arbitrary case so we also cover the
# rule that classification is case-insensitive.
_SUPPORTED_EXTS = sorted(SUPPORTED_EXTENSIONS)
_SKIP_EXTS = sorted(SKIP_EXTENSIONS)


def _random_case(s: str, swap: bool) -> str:
    return s.upper() if swap else s


# An "unsupported" extension: arbitrary alphanumeric text that, once normalized,
# is neither a supported nor a skip extension (and is non-empty so the name has
# a real extension).
_UNSUPPORTED_EXT_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=8,
).filter(
    lambda s: f".{s.lower()}" not in SUPPORTED_EXTENSIONS
    and f".{s.lower()}" not in SKIP_EXTENSIONS
)


# Feature: pgp-encryption-benchmark-go-java, Property 3: กฎการจำแนกชนิดไฟล์และการตั้งชื่อผลลัพธ์
@settings(max_examples=300, suppress_health_check=[HealthCheck.filter_too_much])
@given(
    stem=_STEM,
    ext=st.sampled_from(_SUPPORTED_EXTS),
    upper=st.booleans(),
)
def test_supported_extension_outputs_name_plus_pgp(stem, ext, upper):
    name = stem + _random_case(ext, upper)
    assert classify_file(name) is Classification.SUPPORTED
    assert output_name(name) == name + ".pgp"


@settings(max_examples=300, suppress_health_check=[HealthCheck.filter_too_much])
@given(
    stem=_STEM,
    ext=st.sampled_from(_SKIP_EXTS),
    upper=st.booleans(),
)
def test_ctrl_ctl_are_skipped_without_output(stem, ext, upper):
    name = stem + _random_case(ext, upper)
    assert classify_file(name) is Classification.SKIP
    # Skipped files have no encrypted output name.
    try:
        output_name(name)
    except ValueError:
        pass
    else:  # pragma: no cover - asserts the rule, never reached on correct code
        raise AssertionError(f"output_name({name!r}) should raise for a skipped file")


@settings(max_examples=300, suppress_health_check=[HealthCheck.filter_too_much])
@given(stem=_STEM, ext_text=_UNSUPPORTED_EXT_TEXT)
def test_unsupported_extension_is_skipped_with_reason(stem, ext_text):
    name = f"{stem}.{ext_text}"
    assert classify_file(name) is Classification.UNSUPPORTED
    # Sanity: the normalized extension really is outside the known sets.
    ext = file_extension(name)
    assert ext not in SUPPORTED_EXTENSIONS
    assert ext not in SKIP_EXTENSIONS
    # Unsupported files have no encrypted output name either.
    try:
        output_name(name)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError(f"output_name({name!r}) should raise for an unsupported file")
