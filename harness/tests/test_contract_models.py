"""Unit tests for Command / RunnerOutput dataclasses and parsers."""

import json

import pytest

from harness.contract import (
    Command,
    ContractError,
    FailureType,
    Mode,
    Operation,
    OutputEncoding,
    RunnerId,
    RunnerOutput,
)


# Command
def test_command_parses_required_fields(valid_command_dict):
    cmd = Command.from_dict(valid_command_dict)
    assert cmd.variant_id == "go-stream-parallel"
    assert cmd.mode is Mode.STEADY_STATE
    assert cmd.operation is Operation.ROUNDTRIP
    assert cmd.warmup_iterations == 5
    assert cmd.concurrency == 4
    assert cmd.crypto_profile.cipher == "AES-256"


def test_command_output_encoding_field(valid_command_dict):
    cmd = Command.from_dict(valid_command_dict)
    assert cmd.output_encoding is OutputEncoding.BINARY

    armored = dict(valid_command_dict, outputEncoding="armored")
    assert Command.from_dict(armored).output_encoding is OutputEncoding.ARMORED


def test_command_rejects_invalid_output_encoding(valid_command_dict):
    bad = dict(valid_command_dict, outputEncoding="base64")
    with pytest.raises(ContractError, match="outputEncoding"):
        Command.from_dict(bad)


def test_command_rejects_missing_required_field(valid_command_dict):
    bad = dict(valid_command_dict)
    del bad["keySetChecksum"]
    with pytest.raises(ContractError, match="keySetChecksum"):
        Command.from_dict(bad)


@pytest.mark.parametrize("warmup", [-1, 101])
def test_command_rejects_out_of_range_warmup(valid_command_dict, warmup):
    bad = dict(valid_command_dict, warmupIterations=warmup)
    with pytest.raises(ContractError, match="warmupIterations"):
        Command.from_dict(bad)


def test_command_rejects_zero_concurrency(valid_command_dict):
    bad = dict(valid_command_dict, concurrency=0)
    with pytest.raises(ContractError, match="concurrency"):
        Command.from_dict(bad)


def test_command_rejects_wrong_command_verb(valid_command_dict):
    bad = dict(valid_command_dict, command="halt")
    with pytest.raises(ContractError, match="command"):
        Command.from_dict(bad)


def test_command_rejects_bool_as_int(valid_command_dict):
    bad = dict(valid_command_dict, concurrency=True)
    with pytest.raises(ContractError, match="concurrency"):
        Command.from_dict(bad)


def test_command_round_trips_through_dict_and_json(valid_command_dict):
    cmd = Command.from_dict(valid_command_dict)
    assert cmd.to_dict() == valid_command_dict
    assert Command.from_json(cmd.to_json()) == cmd


def test_command_from_json_rejects_malformed(valid_command_dict):
    with pytest.raises(ContractError, match="invalid JSON"):
        Command.from_json("{not json")


# RunnerOutput
def test_runner_output_parses(valid_runner_output_dict):
    out = RunnerOutput.from_dict(valid_runner_output_dict)
    assert out.runner_id is RunnerId.GO
    assert out.output_encoding is OutputEncoding.BINARY
    assert out.process_startup_ms is None
    assert out.gc is not None
    assert out.gc.collections == 14
    assert len(out.operations) == 2


def test_runner_output_operation_fields(valid_runner_output_dict):
    out = RunnerOutput.from_dict(valid_runner_output_dict)
    first, second = out.operations
    assert first.output_file_name == "doc-0001.pdf.pgp"
    assert first.ciphertext_bytes == 612001
    assert first.failure_type is None
    assert second.skipped is True
    assert second.skip_reason == "control_file"
    assert second.ciphertext_bytes is None


def test_runner_output_parses_failure_type():
    op = {
        "fileName": "x.txt",
        "fileType": ".txt",
        "originalBytes": 5,
        "skipped": False,
        "roundTripOk": False,
        "failureType": "correctness_failure",
    }
    base = {
        "runnerId": "java",
        "variantId": "java-inmem-single",
        "mode": "cold_start",
        "scenarioId": "s1",
        "cryptoProfileId": "p1",
        "concurrency": 1,
        "outputEncoding": "armored",
        "hardwareAccel": False,
        "keySetChecksumSeen": "sha256:" + "cd" * 32,
        "corpusChecksumSeen": "sha256:" + "cd" * 32,
        "operations": [op],
    }
    out = RunnerOutput.from_dict(base)
    assert out.operations[0].failure_type is FailureType.CORRECTNESS_FAILURE


def test_runner_output_allows_null_gc(valid_runner_output_dict):
    payload = dict(valid_runner_output_dict, gc=None)
    out = RunnerOutput.from_dict(payload)
    assert out.gc is None


def test_runner_output_rejects_invalid_runner_id(valid_runner_output_dict):
    bad = dict(valid_runner_output_dict, runnerId="rust")
    with pytest.raises(ContractError, match="runnerId"):
        RunnerOutput.from_dict(bad)


def test_runner_output_rejects_invalid_failure_type(valid_runner_output_dict):
    bad = json.loads(json.dumps(valid_runner_output_dict))
    bad["operations"][0]["failureType"] = "kaboom"
    with pytest.raises(ContractError, match="failureType"):
        RunnerOutput.from_dict(bad)


def test_runner_output_rejects_non_array_operations(valid_runner_output_dict):
    bad = dict(valid_runner_output_dict, operations={})
    with pytest.raises(ContractError, match="operations"):
        RunnerOutput.from_dict(bad)


def test_runner_output_from_json(valid_runner_output_dict):
    text = json.dumps(valid_runner_output_dict)
    out = RunnerOutput.from_json(text)
    assert out.scenario_id == "small-files-rsa2048"
