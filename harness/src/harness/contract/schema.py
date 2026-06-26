"""Locate and load the shared, language-neutral contract artifacts.

The JSON Schemas and exit-code table live in ``contract/`` at the repository
root, shared by the Runners and this harness. This module finds that directory,
loads the artifacts, and offers optional structural validation against the
schemas via :mod:`jsonschema` (raising a clear error if it is not installed).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "contract_dir",
    "load_command_schema",
    "load_runner_output_schema",
    "load_exit_codes",
    "validate_command",
    "validate_runner_output",
]

_CONTRACT_DIR_ENV = "PGP_BENCHMARK_CONTRACT_DIR"
_MARKER_FILES = ("command.schema.json", "runner-output.schema.json", "exit-codes.json")


@lru_cache(maxsize=1)
def contract_dir() -> Path:
    """Return the path to the repo-root ``contract/`` directory.

    Resolution order:

    1. ``$PGP_BENCHMARK_CONTRACT_DIR`` if set.
    2. A ``contract/`` directory found by walking up from this file.
    """
    override = os.environ.get(_CONTRACT_DIR_ENV)
    if override:
        path = Path(override).resolve()
        _assert_contract_dir(path)
        return path

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract"
        if candidate.is_dir() and all((candidate / m).is_file() for m in _MARKER_FILES):
            return candidate

    raise FileNotFoundError(
        "Could not locate the shared 'contract/' directory. Set "
        f"${_CONTRACT_DIR_ENV} to point at it."
    )


def _assert_contract_dir(path: Path) -> None:
    missing = [m for m in _MARKER_FILES if not (path / m).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Contract directory {path} is missing expected files: {', '.join(missing)}"
        )


def _load_json(name: str) -> Any:
    with (contract_dir() / name).open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def load_command_schema() -> dict[str, Any]:
    return _load_json("command.schema.json")


@lru_cache(maxsize=1)
def load_runner_output_schema() -> dict[str, Any]:
    return _load_json("runner-output.schema.json")


@lru_cache(maxsize=1)
def load_exit_codes() -> dict[str, Any]:
    return _load_json("exit-codes.json")


def _validate(instance: Any, schema: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise RuntimeError(
            "jsonschema is required for contract validation; install the "
            "harness with its runtime dependencies."
        ) from exc
    jsonschema.validate(instance=instance, schema=schema)


def validate_command(instance: Any) -> None:
    """Validate a Command payload (dict) against ``command.schema.json``."""
    _validate(instance, load_command_schema())


def validate_runner_output(instance: Any) -> None:
    """Validate a RunnerOutput payload (dict) against ``runner-output.schema.json``."""
    _validate(instance, load_runner_output_schema())
