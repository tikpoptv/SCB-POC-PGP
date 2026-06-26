"""Unit tests for the ResourceSampler."""

import subprocess
import sys
import time

import psutil
import pytest

from harness.contract.models import GcStats
from harness.resource_sampler import (
    BYTES_PER_MB,
    DEFAULT_SAMPLING_INTERVAL_MS,
    GcSummary,
    ResourceSampler,
    ResourceSamplerError,
    ResourceUsage,
    aggregate_samples,
)


def test_default_interval_is_100ms():
    assert ResourceSampler().interval_ms == DEFAULT_SAMPLING_INTERVAL_MS == 100


@pytest.mark.parametrize("interval", [10, 100, 250, 1000])
def test_interval_in_range_accepted(interval):
    assert ResourceSampler(interval_ms=interval).interval_ms == interval


@pytest.mark.parametrize("interval", [9, 0, -1, 1001, 5000])
def test_interval_out_of_range_rejected(interval):
    with pytest.raises(ResourceSamplerError):
        ResourceSampler(interval_ms=interval)


@pytest.mark.parametrize("interval", [True, 100.0, "100"])
def test_interval_non_integer_rejected(interval):
    with pytest.raises(ResourceSamplerError):
        ResourceSampler(interval_ms=interval)


def test_allocated_cpu_cores_must_be_positive_int():
    with pytest.raises(ResourceSamplerError):
        ResourceSampler(allocated_cpu_cores=0)
    with pytest.raises(ResourceSamplerError):
        ResourceSampler(allocated_cpu_cores=True)


def test_aggregate_cpu_normalised_to_percent_of_allocated():
    # 4 allocated cores; raw 400% == fully using all 4 cores == 100%.
    usage = aggregate_samples(
        [400.0, 200.0],
        [BYTES_PER_MB, BYTES_PER_MB],
        allocated_cpu_cores=4,
        sampling_interval_ms=100,
    )
    assert usage.cpu_pct_max == 100.0  # 400/4
    assert usage.cpu_pct_avg == 75.0  # (100 + 50) / 2
    assert usage.comparable is True
    assert usage.non_comparable_reason is None


def test_aggregate_cpu_clamped_to_100():
    usage = aggregate_samples(
        [900.0],
        [BYTES_PER_MB],
        allocated_cpu_cores=8,
        sampling_interval_ms=100,
    )
    assert usage.cpu_pct_max == 100.0
    assert usage.cpu_pct_avg == 100.0


def test_aggregate_ram_avg_and_peak_in_mb():
    usage = aggregate_samples(
        [10.0, 10.0],
        [100 * BYTES_PER_MB, 300 * BYTES_PER_MB],
        allocated_cpu_cores=2,
        sampling_interval_ms=100,
    )
    assert usage.ram_mb_avg == pytest.approx(200.0)
    assert usage.ram_mb_peak == pytest.approx(300.0)


def test_aggregate_no_samples_is_non_comparable():
    usage = aggregate_samples(
        [], [], allocated_cpu_cores=4, sampling_interval_ms=100
    )
    assert usage.comparable is False
    assert usage.sample_count == 0
    assert usage.cpu_pct_avg is None
    assert usage.ram_mb_peak is None
    assert "no resource samples" in usage.non_comparable_reason


def test_aggregate_error_reason_marks_non_comparable_but_keeps_count():
    usage = aggregate_samples(
        [50.0, 60.0],
        [BYTES_PER_MB, BYTES_PER_MB],
        allocated_cpu_cores=1,
        sampling_interval_ms=100,
        error_reason="resource sampling failed: boom",
    )
    assert usage.comparable is False
    assert usage.non_comparable_reason == "resource sampling failed: boom"
    assert usage.sample_count == 2


def test_aggregate_uses_paired_sample_count():
    # Mismatched lengths -> only the paired prefix is used.
    usage = aggregate_samples(
        [100.0, 100.0, 100.0],
        [BYTES_PER_MB],
        allocated_cpu_cores=1,
        sampling_interval_ms=100,
    )
    assert usage.sample_count == 1


def test_aggregate_rejects_bad_allocated_cores():
    with pytest.raises(ResourceSamplerError):
        aggregate_samples([1.0], [1], allocated_cpu_cores=0, sampling_interval_ms=100)


# A short-lived child that burns CPU and holds a chunk of memory for ~0.6s.
_BUSY_CHILD = (
    "import time\n"
    "buf = bytearray(40 * 1024 * 1024)\n"  # ~40 MB resident
    "for i in range(len(buf)):\n"
    "    buf[i] = i & 0xFF\n"
    "end = time.time() + 0.6\n"
    "x = 0\n"
    "while time.time() < end:\n"
    "    x += 1\n"
)


def test_samples_real_subprocess_end_to_end():
    proc = subprocess.Popen([sys.executable, "-c", _BUSY_CHILD])
    try:
        ps_proc = psutil.Process(proc.pid)
        sampler = ResourceSampler(interval_ms=20, allocated_cpu_cores=psutil.cpu_count() or 1)
        with sampler.sample(ps_proc) as session:
            proc.wait(timeout=10)
        usage = session.result
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    assert usage is not None
    assert usage.comparable is True, usage.non_comparable_reason
    assert usage.sample_count > 0
    assert 0.0 <= usage.cpu_pct_avg <= 100.0
    assert 0.0 <= usage.cpu_pct_max <= 100.0
    # The child held ~40 MB resident, so peak RAM must be clearly positive.
    assert usage.ram_mb_peak is not None and usage.ram_mb_peak > 1.0
    assert usage.ram_mb_avg is not None and usage.ram_mb_avg > 0.0
    assert usage.sampling_interval_ms == 20


def test_session_stop_is_idempotent():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
    try:
        ps_proc = psutil.Process(proc.pid)
        session = ResourceSampler(interval_ms=10).start(ps_proc)
        proc.wait(timeout=10)
        first = session.stop()
        second = session.stop()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
    assert first.sample_count == second.sample_count


class _RaisingProcess:
    """Fake psutil.Process whose reads raise AccessDenied immediately."""

    def cpu_percent(self, interval=None):
        raise psutil.AccessDenied(pid=1234)

    def memory_info(self):
        raise psutil.AccessDenied(pid=1234)


class _VanishedProcess:
    """Fake psutil.Process that has already exited (NoSuchProcess)."""

    def cpu_percent(self, interval=None):
        raise psutil.NoSuchProcess(pid=4321)

    def memory_info(self):
        raise psutil.NoSuchProcess(pid=4321)


def test_sampling_failure_marks_non_comparable_with_reason():
    sampler = ResourceSampler(interval_ms=10, allocated_cpu_cores=4)
    with sampler.sample(_RaisingProcess()) as session:
        time.sleep(0.05)
    usage = session.result
    assert usage.comparable is False
    assert usage.sample_count == 0
    assert "resource sampling failed" in usage.non_comparable_reason


def test_vanished_process_yields_no_samples_non_comparable():
    sampler = ResourceSampler(interval_ms=10, allocated_cpu_cores=4)
    with sampler.sample(_VanishedProcess()) as session:
        time.sleep(0.05)
    usage = session.result
    assert usage.comparable is False
    assert usage.sample_count == 0
    assert "no resource samples" in usage.non_comparable_reason


def _ok_usage() -> ResourceUsage:
    return aggregate_samples(
        [100.0], [BYTES_PER_MB], allocated_cpu_cores=1, sampling_interval_ms=100
    )


def test_merge_gc_available_from_runner_output():
    gc = GcStats(
        collections=14,
        total_pause_ms=23.7,
        gc_type="G1",
        heap_init_mb=256,
        heap_max_mb=2048,
    )
    usage = ResourceSampler.merge_gc(_ok_usage(), gc)
    assert usage.gc is not None
    assert usage.gc.available is True
    assert usage.gc.collections == 14
    assert usage.gc.gc_type == "G1"
    payload = usage.to_dict()["gc"]
    assert payload["available"] is True
    assert payload["totalPauseMs"] == 23.7
    assert payload["heapMaxMb"] == 2048


def test_merge_gc_unavailable_when_runner_reports_none():
    usage = ResourceSampler.merge_gc(_ok_usage(), None)
    assert usage.gc is not None
    assert usage.gc.available is False
    assert usage.gc.unavailable_reason is not None
    payload = usage.to_dict()["gc"]
    assert payload["available"] is False
    assert payload["reason"]
    assert usage.comparable is True


def test_gc_summary_from_none_is_unavailable():
    summary = GcSummary.from_runner_gc(None)
    assert summary.available is False
    assert summary.to_dict() == {"available": False, "reason": summary.unavailable_reason}


# Result_Report serialisation shape (design.md cpuPct/ramMb blocks)
def test_to_dict_shape_matches_report_schema():
    usage = aggregate_samples(
        [100.0, 200.0],
        [100 * BYTES_PER_MB, 200 * BYTES_PER_MB],
        allocated_cpu_cores=2,
        sampling_interval_ms=100,
    ).with_gc(None)
    payload = usage.to_dict()
    assert set(payload) == {
        "cpuPct",
        "ramMb",
        "sampleCount",
        "samplingIntervalMs",
        "allocatedCpuCores",
        "comparable",
        "nonComparableReason",
        "gc",
    }
    assert set(payload["cpuPct"]) == {"avg", "max"}
    assert set(payload["ramMb"]) == {"avg", "peak"}
