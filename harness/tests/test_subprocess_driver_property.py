"""Property-based test for the single-Runner-per-VM invariant."""

import os
import sys
import threading

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness.contract import Command
from harness.subprocess_driver import (
    SubprocessDriver,
    active_runner_count,
    peak_runner_count,
    reset_peak_runner_count,
)

_FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "_fake_runner.py")
_CHECKSUM = "sha256:" + "ab" * 32


def _make_command(key_path: str, corpus_path: str) -> Command:
    return Command.from_dict(
        {
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
            "outputDir": corpus_path + "-out",
            "operation": "roundtrip",
        }
    )


def _driver(sleep_s: float) -> SubprocessDriver:
    """A driver whose fake Runner sleeps ``sleep_s`` while holding the gate."""
    env = {**os.environ, "FAKE_SLEEP": f"{sleep_s:.4f}"}
    return SubprocessDriver([sys.executable, _FAKE_RUNNER], env=env)


# Feature: pgp-encryption-benchmark-go-java, Property 22: scheduler รัน Runner ได้สูงสุด 1 ตัวต่อ VM
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    # An arbitrary number of concurrent Runners in [2, 8].
    n=st.integers(min_value=2, max_value=8),
    # Varied small sleeps (ms) so the gate-holding windows overlap in time.
    sleeps_ms=st.lists(
        st.integers(min_value=0, max_value=12),
        min_size=2,
        max_size=8,
    ),
    data=st.data(),
)
def test_peak_runner_count_never_exceeds_one(n, sleeps_ms, data, tmp_path_factory):
    # Reset the observed peak before each example so it reflects only this run.
    reset_peak_runner_count()

    # Shared, readable Key_Set / Test_Corpus for the Command input validation.
    base = tmp_path_factory.mktemp("io")
    key_dir = base / "keys"
    key_dir.mkdir()
    (key_dir / "rsa2048-public.asc").write_text("KEY")
    corpus_dir = base / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "doc.txt").write_text("hello")
    command = _make_command(str(key_dir), str(corpus_dir))

    # One sleep per thread; reuse/extend the generated list to length n.
    while len(sleeps_ms) < n:
        sleeps_ms.append(data.draw(st.integers(min_value=0, max_value=12)))
    sleeps = [ms / 1000.0 for ms in sleeps_ms[:n]]

    errors: list[BaseException] = []
    start_gate = threading.Barrier(n)

    def worker(sleep_s: float) -> None:
        driver = _driver(sleep_s)
        try:
            # Release all threads together to maximise contention on the gate.
            start_gate.wait()
            result = driver.run(command)
            assert result.success is True
        except BaseException as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(s,)) for s in sleeps]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No worker may fail, and the gate must never have allowed two Runners to be
    assert errors == [], f"workers raised: {errors!r}"
    assert peak_runner_count() == 1
    # The active count must settle back to zero once every Runner has exited.
    assert active_runner_count() == 0
