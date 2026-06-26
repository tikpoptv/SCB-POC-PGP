"""Implementation_Variant set validation.

Each language declares a set of Implementation_Variants. Before any run,
:func:`validate_variant_set` confirms the set is well-formed: the count is in
:data:`VARIANT_COUNT_RANGE`, all ids are unique, and no two variants share the
same ``(memory_mode, parallelism)`` pair. On any violation it raises
:class:`VariantSetError` naming the offending language. Pure and side-effect free.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

__all__ = [
    "MemoryMode",
    "Parallelism",
    "Variant",
    "VariantSetError",
    "VARIANT_COUNT_RANGE",
    "validate_variant_set",
]


#: Allowed number of Implementation_Variants per language, inclusive.
VARIANT_COUNT_RANGE = (2, 20)


class MemoryMode(str, Enum):
    """Memory-management dimension of an Implementation_Variant."""

    IN_MEMORY = "in_memory"
    STREAMING = "streaming"


class Parallelism(str, Enum):
    """Parallelism dimension of an Implementation_Variant."""

    SINGLE = "single"
    PARALLEL = "parallel"


@dataclass(frozen=True)
class Variant:
    """One declared Implementation_Variant, identified by a unique ``id``."""

    id: str
    memory_mode: MemoryMode
    parallelism: Parallelism

    @property
    def dimensions(self) -> tuple[MemoryMode, Parallelism]:
        """The ``(memory_mode, parallelism)`` pair used for the duplicate check."""
        return (self.memory_mode, self.parallelism)


class VariantSetError(ValueError):
    """Raised when a language's Implementation_Variant set is invalid.

    Carries the offending ``language`` and a human ``reason``. The string form
    is ``"<language>: <reason>"``.
    """

    def __init__(self, language: str, reason: str) -> None:
        self.language = language
        self.reason = reason
        super().__init__(f"{language}: {reason}")


def validate_variant_set(language: str, variants: Sequence[Variant]) -> None:
    """Validate a language's Implementation_Variant set.

    Raises :class:`VariantSetError` (naming ``language``) when the set is
    ill-formed; returns ``None`` when valid. A set is valid iff its size is
    within :data:`VARIANT_COUNT_RANGE`, all ``id`` values are unique, and no two
    variants share the same ``(memory_mode, parallelism)`` pair.
    """
    low, high = VARIANT_COUNT_RANGE
    count = len(variants)

    if count < low:
        raise VariantSetError(
            language,
            f"requires at least {low} Implementation_Variants, found {count}",
        )
    if count > high:
        raise VariantSetError(
            language,
            f"supports at most {high} Implementation_Variants, found {count}",
        )

    # Identifiers must be unique across the set.
    id_counts = Counter(v.id for v in variants)
    duplicate_ids = sorted(vid for vid, n in id_counts.items() if n > 1)
    if duplicate_ids:
        raise VariantSetError(
            language,
            f"duplicate Implementation_Variant identifier(s): {duplicate_ids}",
        )

    # No two variants identical on BOTH dimensions.
    dim_counts = Counter(v.dimensions for v in variants)
    duplicate_dims = sorted(
        f"({mode.value}, {par.value})"
        for (mode, par), n in dim_counts.items()
        if n > 1
    )
    if duplicate_dims:
        raise VariantSetError(
            language,
            "two or more Implementation_Variants are identical on both "
            f"dimensions (memory_mode, parallelism): {duplicate_dims}",
        )
