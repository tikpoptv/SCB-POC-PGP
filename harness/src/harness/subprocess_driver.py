"""SubprocessDriver — spawn a Runner subprocess and exchange the CLI contract.

Spawns a Go/Java Runner, feeds it one Command JSON on stdin, reads one
RunnerOutput JSON on stdout, captures stderr and the exit code, and enforces the
timeout. Classifies the exit code, serializes Runners so at most one is active
per VM, and never returns a partial result on input/process failure.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from harness.contract import (
    Command,
    ContractError,
    ExitCode,
    RunnerOutput,
    classify_exit_code,
)

__all__ = [
    "SubprocessDriver",
    "RunnerResult",
    "SubprocessDriverError",
    "RunnerInputError",
    "RunnerSpawnError",
    "RunnerTimeoutError",
    "RunnerProtocolError",
    "active_runner_count",
    "peak_runner_count",
    "reset_peak_runner_count",
]

# Default wall-clock budget for a single Runner invocation (seconds).
DEFAULT_TIMEOUT_S = 300.0


class SubprocessDriverError(RuntimeError):
    """Base error for any failure to drive a Runner subprocess."""


class RunnerInputError(SubprocessDriverError):
    """A required input was missing or unreadable (raised before spawning)."""


class RunnerSpawnError(SubprocessDriverError):
    """The Runner process could not be started (e.g. executable not found)."""


class RunnerTimeoutError(SubprocessDriverError):
    """The Runner exceeded its timeout and was killed."""


class RunnerProtocolError(SubprocessDriverError):
    """The Runner exited 0 but its stdout was not a valid RunnerOutput object."""


@dataclass(frozen=True)
class RunnerResult:
    """Outcome of one Runner invocation.

    ``output`` is the parsed :class:`RunnerOutput` on success (exit code 0), and
    ``None`` for any non-zero exit (inspect ``classified`` instead).
    """

    exit_code: int
    classified: ExitCode
    stdout: str
    stderr: str
    duration_s: float
    output: RunnerOutput | None = None

    @property
    def success(self) -> bool:
        """True only when the Runner exited 0 and produced a valid RunnerOutput."""
        return self.classified is ExitCode.SUCCESS and self.output is not None


class _RunnerGate:
    """Serializes Runner execution so at most one is active per VM.

    Acts as a re-usable context manager. ``active`` and ``peak`` let tests
    observe that the concurrent count never exceeds 1.
    """

    def __init__(self) -> None:
        self._gate = threading.Lock()
        self._counter_lock = threading.Lock()
        self._active = 0
        self._peak = 0

    def __enter__(self) -> "_RunnerGate":
        self._gate.acquire()
        with self._counter_lock:
            self._active += 1
            if self._active > self._peak:
                self._peak = self._active
        return self

    def __exit__(self, *exc: object) -> None:
        with self._counter_lock:
            self._active -= 1
        self._gate.release()

    @property
    def active(self) -> int:
        with self._counter_lock:
            return self._active

    @property
    def peak(self) -> int:
        with self._counter_lock:
            return self._peak

    def reset_peak(self) -> None:
        with self._counter_lock:
            self._peak = self._active


#: Process-wide gate shared by every SubprocessDriver, enforcing <= 1 active
#: Runner per VM.
_VM_RUNNER_GATE = _RunnerGate()


def active_runner_count() -> int:
    """Number of Runners currently executing across this process."""
    return _VM_RUNNER_GATE.active


def peak_runner_count() -> int:
    """Highest number of Runners ever concurrently active (must stay 1)."""
    return _VM_RUNNER_GATE.peak


def reset_peak_runner_count() -> None:
    """Reset the observed peak to the current active count (test helper)."""
    _VM_RUNNER_GATE.reset_peak()


class SubprocessDriver:
    """Spawn a Runner, exchange the CLI contract, and capture its outcome."""

    def __init__(
        self,
        executable: Sequence[str],
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        validate_inputs: bool = True,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        if not executable:
            raise ValueError("executable argv must not be empty")
        if timeout_s <= 0:
            raise ValueError(f"timeout_s must be > 0, got {timeout_s!r}")
        self._argv: tuple[str, ...] = tuple(executable)
        self._timeout_s = float(timeout_s)
        self._validate_inputs = validate_inputs
        self._env = dict(env) if env is not None else None
        self._cwd = cwd

    @property
    def argv(self) -> tuple[str, ...]:
        return self._argv

    def run(self, command: Command, *, timeout_s: float | None = None) -> RunnerResult:
        """Run the Runner for one :class:`Command` and return its outcome.

        Blocks while another Runner is active. Raises on input/spawn/timeout
        failure without producing a partial result; a non-zero exit code is
        returned in the :class:`RunnerResult`, not raised.
        """
        if not isinstance(command, Command):
            raise TypeError(f"command must be a Command, got {type(command).__name__}")

        effective_timeout = self._timeout_s if timeout_s is None else float(timeout_s)
        if effective_timeout <= 0:
            raise ValueError(f"timeout_s must be > 0, got {effective_timeout!r}")

        if self._validate_inputs:
            self._check_inputs(command)

        payload = command.to_json()

        # Enforce <= 1 active Runner per VM: the gate serializes all drivers.
        with _VM_RUNNER_GATE:
            return self._spawn_and_collect(payload, effective_timeout)

    def _check_inputs(self, command: Command) -> None:
        """Verify the Key_Set and Test_Corpus are present/readable."""
        for label, path in (
            ("Key_Set", command.key_set_path),
            ("Test_Corpus", command.corpus_path),
        ):
            if not os.path.exists(path):
                raise RunnerInputError(
                    f"{label} input not found: {path!r} "
                    f"(Benchmark_Run aborted before producing any result)"
                )
            if not os.access(path, os.R_OK):
                raise RunnerInputError(
                    f"{label} input is not readable: {path!r} "
                    f"(Benchmark_Run aborted before producing any result)"
                )

    def _spawn_and_collect(self, payload: str, timeout_s: float) -> RunnerResult:
        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                self._argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._env,
                cwd=self._cwd,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise RunnerSpawnError(
                f"failed to spawn Runner {self._argv[0]!r}: {exc}"
            ) from exc

        try:
            stdout, stderr = proc.communicate(input=payload, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            # Reap the killed child so no zombie lingers; discard partial output.
            try:
                proc.communicate(timeout=timeout_s)
            except Exception:
                pass
            raise RunnerTimeoutError(
                f"Runner {self._argv[0]!r} exceeded timeout of {timeout_s:g}s "
                f"and was killed (no partial result recorded)"
            ) from exc

        duration = time.monotonic() - start
        exit_code = proc.returncode
        classified = classify_exit_code(exit_code)

        output: RunnerOutput | None = None
        if classified is ExitCode.SUCCESS:
            output = self._parse_output(stdout, stderr)

        return RunnerResult(
            exit_code=exit_code,
            classified=classified,
            stdout=stdout,
            stderr=stderr,
            duration_s=duration,
            output=output,
        )

    @staticmethod
    def _parse_output(stdout: str, stderr: str) -> RunnerOutput:
        """Parse the single RunnerOutput object from stdout."""
        text = stdout.strip()
        if not text:
            raise RunnerProtocolError(
                "Runner exited 0 but wrote no RunnerOutput to stdout"
                + (f"; stderr: {stderr.strip()}" if stderr.strip() else "")
            )
        try:
            return RunnerOutput.from_json(text)
        except ContractError as exc:
            raise RunnerProtocolError(
                f"Runner exited 0 but stdout was not a valid RunnerOutput: {exc}"
            ) from exc
