"""Tests that the shared JSON Schemas load and validate contract payloads."""

import pytest

from harness.contract import (
    Command,
    RunnerOutput,
    contract_dir,
    load_command_schema,
    load_runner_output_schema,
    validate_command,
    validate_runner_output,
)


def test_contract_dir_contains_artifacts():
    d = contract_dir()
    assert (d / "command.schema.json").is_file()
    assert (d / "runner-output.schema.json").is_file()
    assert (d / "exit-codes.json").is_file()


def test_schemas_load_as_objects():
    assert load_command_schema()["title"] == "Command"
    assert load_runner_output_schema()["title"] == "RunnerOutput"


def test_valid_command_passes_schema(valid_command_dict):
    validate_command(valid_command_dict)


def test_valid_runner_output_passes_schema(valid_runner_output_dict):
    validate_runner_output(valid_runner_output_dict)


def test_command_dataclass_serialization_matches_schema(valid_command_dict):
    """Round-tripping through the dataclass still yields schema-valid JSON."""
    cmd = Command.from_dict(valid_command_dict)
    validate_command(cmd.to_dict())


def test_schema_rejects_unknown_command_field(valid_command_dict):
    import jsonschema

    bad = dict(valid_command_dict, surprise=1)
    with pytest.raises(jsonschema.ValidationError):
        validate_command(bad)


def test_schema_rejects_bad_checksum_pattern(valid_command_dict):
    import jsonschema

    bad = dict(valid_command_dict, keySetChecksum="md5:nope")
    with pytest.raises(jsonschema.ValidationError):
        validate_command(bad)


def test_schema_rejects_bad_output_encoding(valid_runner_output_dict):
    import jsonschema

    bad = dict(valid_runner_output_dict, outputEncoding="hex")
    with pytest.raises(jsonschema.ValidationError):
        validate_runner_output(bad)


def test_runner_output_from_fixture_parses_and_validates(valid_runner_output_dict):
    # Cross-check: the parser accepts exactly what the schema accepts here.
    RunnerOutput.from_dict(valid_runner_output_dict)
    validate_runner_output(valid_runner_output_dict)
