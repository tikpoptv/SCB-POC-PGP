"""Unit tests for SubprocessDriver."""

import os
import sys
import threading
import time

import pytest

from harness.contract import Command, ExitCode, OutputEncoding, RunnerId
from harness.subprocess_driver import (
    DEFAULT_TIMEOUT_S,
    RunnerInputError,
    RunnerProtocolError,
    RunnerSpawnError,
    RunnerTimeoutError,
    SubprocessDriver,
    active_runner_count,
    peak_runner_count,
    reset_peak_runner_count,
)

_FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "_fake_runner.py")
_CHECKSUM = "sha256:" + "ab" * 32


@pytest.fixture
def runner_inputs(tmp_path):
    """Create real, readable Key_Set and Test_Corpus paths for a Command."""
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    (key_dir / "rsa2048-public.asc").write_text("KEY")
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "doc.txt").write_text("hello")
    return str(key_dir), str(corpus_dir)


@pytest.fixture
def make_command(runner_inputs):
    key_path, corpus_path = runner_inputs

    def _make(**overrides):
        data = {
            "command": "run",
            "variantId": "go-stream-parallel",
            "mode": "steady_state",
            "warmupIterations": 5,
            "concurrency": 4,
            "cryptoProfile": {
                "pubAlg": "RSA-2048",
                "cipher": "AES-256",
                "compression": "ZLIB",
                "hash": "SHA-256",
            },
            "outputEncoding": "binary",
            "keySetPath": key_path,
            "keySetChecksum": _CHECKSUM,
            "corpusPath": corpus_path,
            "corpusChecksum": _CHECKSUM,
            "outputDir": str(corpus_path) + "-out",
            "operation": "roundtrip",
        }
        data.update(overrides)
        return Command.from_dict(data)

    return _make


def _driver(*, env=None, timeout_s=DEFAULT_TIMEOUT_S, validate_inputs=True):
    return SubprocessDriver(
        [sys.executable, _FAKE_RUNNER],
        env=env,
        timeout_s=timeout_s,
        validate_inputs=validate_inputs,
    )


# Happy path: contract exchange
def test_run_returns_parsed_runner_output(make_command):
    result = _driver().run(make_command())

    assert result.success is True
    assert result.exit_code == 0
    assert result.classified is ExitCode.SUCCESS
    assert result.output is not None
    assert result.output.runner_id is RunnerId.GO
    assert result.duration_s >= 0.0


def test_command_json_is_delivered_on_stdin(make_command):
    # The fake runner echoes fields it read from the Command back into the
    # RunnerOutput, proving the JSON reached its stdin intact.
    cmd = make_command(variantId="go-inmem-single", concurrency=2, outputEncoding="armored")
    result = _driver().run(cmd)

    assert result.output.variant_id == "go-inmem-single"
    assert result.output.concurrency == 2
    assert result.output.output_encoding is OutputEncoding.ARMORED
    assert result.output.key_set_checksum_seen == _CHECKSUM
    assert result.output.corpus_checksum_seen == _CHECKSUM


def test_stderr_is_captured(make_command):
    result = _driver(env={**os.environ, "FAKE_STDERR": "diagnostic log line"}).run(
        make_command()
    )
    assert "diagnostic log line" in result.stderr


@pytest.mark.parametrize(
    "code,expected",
    [
        (2, ExitCode.CHECKSUM_OR_VERSION_MISMATCH),
        (3, ExitCode.CONFIG_ERROR),
        (4, ExitCode.UNSUPPORTED_CRYPTO_PROFILE),
        (1, ExitCode.OPERATION_FAILURE),
        (7, ExitCode.OPERATION_FAILURE),
    ],
)
def test_nonzero_exit_codes_are_classified_not_raised(make_command, code, expected):
    env = {**os.environ, "FAKE_EXIT_CODE": str(code), "FAKE_STDOUT_MODE": "empty"}
    result = _driver(env=env).run(make_command())

    assert result.exit_code == code
    assert result.classified is expected
    assert result.success is False
    assert result.output is None  # non-zero exits do not yield a parsed output


def test_success_with_empty_stdout_raises_protocol_error(make_command):
    env = {**os.environ, "FAKE_EXIT_CODE": "0", "FAKE_STDOUT_MODE": "empty"}
    with pytest.raises(RunnerProtocolError, match="no RunnerOutput"):
        _driver(env=env).run(make_command())


def test_success_with_garbage_stdout_raises_protocol_error(make_command):
    env = {**os.environ, "FAKE_EXIT_CODE": "0", "FAKE_STDOUT_MODE": "garbage"}
    with pytest.raises(RunnerProtocolError, match="not a valid RunnerOutput"):
        _driver(env=env).run(make_command())


def test_missing_keyset_raises_input_error(make_command, tmp_path):
    cmd = make_command(keySetPath=str(tmp_path / "does-not-exist"))
    with pytest.raises(RunnerInputError, match="Key_Set"):
        _driver().run(cmd)


def test_missing_corpus_raises_input_error(make_command, tmp_path):
    cmd = make_command(corpusPath=str(tmp_path / "missing-corpus"))
    with pytest.raises(RunnerInputError, match="Test_Corpus"):
        _driver().run(cmd)


def test_unreadable_input_raises_input_error(make_command, runner_inputs, tmp_path):
    if os.geteuid() == 0:  # pragma: no cover - root bypasses permission bits
        pytest.skip("permission bits are not enforced for root")
    locked = tmp_path / "locked-keys"
    locked.mkdir()
    os.chmod(locked, 0o000)
    try:
        cmd = make_command(keySetPath=str(locked))
        with pytest.raises(RunnerInputError, match="not readable"):
            _driver().run(cmd)
    finally:
        os.chmod(locked, 0o755)


def test_spawn_failure_raises_spawn_error(make_command):
    driver = SubprocessDriver(["/nonexistent/runner/binary-xyz"])
    with pytest.raises(RunnerSpawnError, match="failed to spawn"):
        driver.run(make_command())


def test_timeout_kills_runner_and_raises(make_command):
    env = {**os.environ, "FAKE_SLEEP": "5"}
    driver = _driver(env=env, timeout_s=0.5)
    start = time.monotonic()
    with pytest.raises(RunnerTimeoutError, match="exceeded timeout"):
        driver.run(make_command())
    # The driver should not block for the full sleep; it kills the child.
    assert time.monotonic() - start < 4.0


def test_at_most_one_runner_active_under_concurrency(make_command):
    reset_peak_runner_count()
    env = {**os.environ, "FAKE_SLEEP": "0.3"}
    driver = _driver(env=env)
    cmd = make_command()

    errors: list[BaseException] = []

    def worker():
        try:
            driver.run(cmd)
        except BaseException as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert peak_runner_count() == 1
    assert active_runner_count() == 0


# Construction guards
def test_empty_executable_rejected():
    with pytest.raises(ValueError, match="executable"):
        SubprocessDriver([])


def test_non_positive_timeout_rejected():
    with pytest.raises(ValueError, match="timeout_s"):
        SubprocessDriver([sys.executable], timeout_s=0)
