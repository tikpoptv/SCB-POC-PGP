"""Shared Runner CLI contract: typed models, parsers, exit codes, and schemas.

The Python view of the language-neutral contract artifacts in ``contract/`` at
the repository root, mirrored by the Go_Runner and Java_Runner.
"""

from __future__ import annotations

from harness.contract.exit_codes import (
    RESERVED_EXIT_CODES,
    ExitCode,
    classify_exit_code,
)
from harness.contract.models import (
    Command,
    ContractError,
    CryptoProfile,
    FailureType,
    GcStats,
    Mode,
    Operation,
    OperationSample,
    OutputEncoding,
    RunnerId,
    RunnerOutput,
)
from harness.contract.schema import (
    contract_dir,
    load_command_schema,
    load_exit_codes,
    load_runner_output_schema,
    validate_command,
    validate_runner_output,
)

__all__ = [
    # exit codes
    "ExitCode",
    "classify_exit_code",
    "RESERVED_EXIT_CODES",
    # models
    "ContractError",
    "OutputEncoding",
    "Mode",
    "Operation",
    "RunnerId",
    "FailureType",
    "CryptoProfile",
    "Command",
    "GcStats",
    "OperationSample",
    "RunnerOutput",
    # schema
    "contract_dir",
    "load_command_schema",
    "load_runner_output_schema",
    "load_exit_codes",
    "validate_command",
    "validate_runner_output",
]
