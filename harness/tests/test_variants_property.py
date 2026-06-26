"""Property-based tests for Implementation_Variant set validation (Task 7.5).

# Feature: pgp-encryption-benchmark-go-java, Property 17: ความถูกต้องของเซต Implementation_Variant
"""

from __future__ import annotations

from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.variants import (
    VARIANT_COUNT_RANGE,
    MemoryMode,
    Parallelism,
    Variant,
    VariantSetError,
    validate_variant_set,
)

_LOW, _HIGH = VARIANT_COUNT_RANGE  # (2, 20)

# The four possible (memory_mode, parallelism) dimension pairs.
_ALL_DIMENSIONS = [
    (m, p) for m in MemoryMode for p in Parallelism
]

_languages = st.sampled_from(["Go", "Java"])
_memory_modes = st.sampled_from(list(MemoryMode))
_parallelisms = st.sampled_from(list(Parallelism))
_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz-0123456789",
    min_size=1,
    max_size=12,
)


# Independent oracle: the rule the validator must agree with
def _is_valid(variants: list[Variant]) -> bool:
    count = len(variants)
    if not (_LOW <= count <= _HIGH):
        return False
    ids = [v.id for v in variants]
    if len(set(ids)) != count:
        return False
    dims = [v.dimensions for v in variants]
    if len(set(dims)) != count:
        return False
    return True


@st.composite
def arbitrary_variant_set(draw: st.DrawFn) -> list[Variant]:
    """A freely-generated set: any size, ids and dimensions may collide.

    Sized a little past the [2, 20] bounds (0..24) so out-of-range counts and
    both kinds of collision (id, dimensions) arise naturally.
    """
    n = draw(st.integers(min_value=0, max_value=24))
    variants = [
        Variant(
            id=draw(_ids),
            memory_mode=draw(_memory_modes),
            parallelism=draw(_parallelisms),
        )
        for _ in range(n)
    ]
    return variants


@st.composite
def valid_variant_set(draw: st.DrawFn) -> list[Variant]:
    """A set guaranteed to satisfy every rule.

    Distinct dimension pairs (so count is capped at 4) with unique ids — a
    well-formed declaration the validator must accept.
    """
    k = draw(st.integers(min_value=_LOW, max_value=len(_ALL_DIMENSIONS)))
    dims = draw(
        st.lists(
            st.sampled_from(_ALL_DIMENSIONS),
            min_size=k,
            max_size=k,
            unique=True,
        )
    )
    return [
        Variant(id=f"variant-{i}", memory_mode=m, parallelism=p)
        for i, (m, p) in enumerate(dims)
    ]


@settings(max_examples=300)
@given(language=_languages, variants=arbitrary_variant_set())
def test_validator_verdict_matches_rule(language, variants):
    expected_valid = _is_valid(variants)

    if expected_valid:
        # Accepted sets validate without raising.
        assert validate_variant_set(language, variants) is None
    else:
        # Rejected sets raise an error that names the offending language.
        try:
            validate_variant_set(language, variants)
        except VariantSetError as exc:
            assert exc.language == language
            assert language in str(exc)
        else:
            raise AssertionError(
                f"expected rejection for invalid set of size {len(variants)}"
            )


@settings(max_examples=200)
@given(language=_languages, variants=valid_variant_set())
def test_well_formed_set_is_accepted(language, variants):
    assert _LOW <= len(variants) <= _HIGH
    assert len({v.id for v in variants}) == len(variants)
    assert len({v.dimensions for v in variants}) == len(variants)
    assert validate_variant_set(language, variants) is None


@settings(max_examples=100)
@given(
    language=_languages,
    variants=st.lists(
        st.builds(
            Variant,
            id=_ids,
            memory_mode=_memory_modes,
            parallelism=_parallelisms,
        ),
        min_size=0,
        max_size=1,
    ),
)
def test_too_few_variants_halts_naming_language(language, variants):
    try:
        validate_variant_set(language, variants)
    except VariantSetError as exc:
        assert exc.language == language
        assert language in str(exc)
    else:
        raise AssertionError("a set with < 2 variants must be rejected (Req 6.6)")


@settings(max_examples=200)
@given(
    language=_languages,
    mode=_memory_modes,
    par=_parallelisms,
    extra=st.lists(st.sampled_from(_ALL_DIMENSIONS), max_size=3),
)
def test_duplicate_dimension_pair_rejected(language, mode, par, extra):
    # Two variants identical on BOTH dimensions, with unique ids and an
    # in-range count, so the dimension rule is the only thing that can fail.
    variants = [
        Variant(id="dup-a", memory_mode=mode, parallelism=par),
        Variant(id="dup-b", memory_mode=mode, parallelism=par),
    ]
    for i, (m, p) in enumerate(extra):
        variants.append(Variant(id=f"extra-{i}", memory_mode=m, parallelism=p))

    # Guard: keep the count within range so we isolate the dimension violation.
    assert _LOW <= len(variants) <= _HIGH
    assert len({v.id for v in variants}) == len(variants)  # ids unique
    assert max(Counter(v.dimensions for v in variants).values()) >= 2

    try:
        validate_variant_set(language, variants)
    except VariantSetError as exc:
        assert exc.language == language
    else:
        raise AssertionError("duplicate dimension pair must be rejected (Req 6.2/6.3)")
