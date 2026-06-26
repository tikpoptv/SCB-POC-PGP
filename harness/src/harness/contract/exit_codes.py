"""Shared Runner process exit codes (CLI contract).

Mirrors ``contract/exit-codes.json`` at the repository root, the
language-neutral source of truth shared by the Runners and this harness. A test
asserts these values stay in sync with that file.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["ExitCode", "classify_exit_code", "RESERVED_EXIT_CODES"]


class ExitCode(IntEnum):
    """Canonical Runner exit codes.

    Any code > 0 that is not reserved (2, 3, 4) is a generic operation failure.
    """

    SUCCESS = 0
    """Success; recorded per-file correctness failures still exit 0."""

    OPERATION_FAILURE = 1
    """Generic operation failure (canonical value; see ``classify_exit_code``)."""

    CHECKSUM_OR_VERSION_MISMATCH = 2
    """Input checksum or version mismatch — excluded from statistics."""

    CONFIG_ERROR = 3
    """Invalid config/command JSON."""

    UNSUPPORTED_CRYPTO_PROFILE = 4
    """Crypto-profile not supported by this Runner."""


#: Exit codes with a dedicated, specific meaning. Every other non-zero code is
#: treated as a generic operation failure.
RESERVED_EXIT_CODES: frozenset[int] = frozenset(
    {
        ExitCode.CHECKSUM_OR_VERSION_MISMATCH,
        ExitCode.CONFIG_ERROR,
        ExitCode.UNSUPPORTED_CRYPTO_PROFILE,
    }
)


def classify_exit_code(code: int) -> ExitCode:
    """Map a raw process exit code to its :class:`ExitCode` meaning.

    ``0`` is success; ``2``/``3``/``4`` keep their specific meaning; every
    other non-zero code collapses to :attr:`ExitCode.OPERATION_FAILURE`.
    """
    if code == ExitCode.SUCCESS:
        return ExitCode.SUCCESS
    if code in RESERVED_EXIT_CODES:
        return ExitCode(code)
    return ExitCode.OPERATION_FAILURE
