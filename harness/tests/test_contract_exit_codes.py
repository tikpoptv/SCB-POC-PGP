"""Tests for shared exit-code constants and their sync with the contract file."""

import pytest

from harness.contract import ExitCode, classify_exit_code
from harness.contract.schema import load_exit_codes


def test_exit_code_values():
    assert ExitCode.SUCCESS == 0
    assert ExitCode.OPERATION_FAILURE == 1
    assert ExitCode.CHECKSUM_OR_VERSION_MISMATCH == 2
    assert ExitCode.CONFIG_ERROR == 3
    assert ExitCode.UNSUPPORTED_CRYPTO_PROFILE == 4


def test_python_constants_match_shared_contract_file():
    """The Python mirror must not drift from contract/exit-codes.json."""
    shared = {entry["name"]: entry["code"] for entry in load_exit_codes()["codes"]}
    assert shared["SUCCESS"] == ExitCode.SUCCESS
    assert shared["OPERATION_FAILURE"] == ExitCode.OPERATION_FAILURE
    assert shared["CHECKSUM_OR_VERSION_MISMATCH"] == ExitCode.CHECKSUM_OR_VERSION_MISMATCH
    assert shared["CONFIG_ERROR"] == ExitCode.CONFIG_ERROR
    assert shared["UNSUPPORTED_CRYPTO_PROFILE"] == ExitCode.UNSUPPORTED_CRYPTO_PROFILE


def test_reserved_codes_match_contract_file():
    reserved = set(load_exit_codes()["reserved"])
    assert reserved == {2, 3, 4}


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0, ExitCode.SUCCESS),
        (2, ExitCode.CHECKSUM_OR_VERSION_MISMATCH),
        (3, ExitCode.CONFIG_ERROR),
        (4, ExitCode.UNSUPPORTED_CRYPTO_PROFILE),
        (1, ExitCode.OPERATION_FAILURE),
        (5, ExitCode.OPERATION_FAILURE),
        (137, ExitCode.OPERATION_FAILURE),
    ],
)
def test_classify_exit_code(raw, expected):
    """Any non-zero, non-reserved code collapses to OPERATION_FAILURE."""
    assert classify_exit_code(raw) == expected
