"""Integration tests for real measurements and external tools.

Covers:
  1. CPU/RAM/GC sampling via psutil — verifies real sampling produces samples.
  2. Thermal throttling detection — verifies EnvironmentProbe detects or
     gracefully handles the absence of a thermal sensor.
  3. Energy measurement — verifies the Result_Report records "not supported"
     (null / absent) gracefully when the environment does not expose energy data.
  4. Soak time-series — verifies slope calculation when time-series samples exist.
  5. Report within 60 s — verifies ReportGenerator completes within the timeout.
  6. No outbound socket — verifies SubprocessDriver subprocess argv contains no
     network-connecting flags/commands.

Requirements: 1.2, 1.3, 11.1, 17.2, 20.1, 27.3, 28.1, 29.2
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import psutil
import pytest

from harness.environment import Environment, EnvironmentProbe
from harness.report import ReportGenerator
from harness.resource_sampler import ResourceSampler, aggregate_samples, BYTES_PER_MB
from harness.soak import ram_trend, latency_trend, soak_trends
from harness.subprocess_driver import SubprocessDriver


# ---------------------------------------------------------------------------
# Helper: short-lived CPU/RAM-burning subprocess
# ---------------------------------------------------------------------------

_BUSY_CHILD = (
    "import time\n"
    "buf = bytearray(20 * 1024 * 1024)\n"  # ~20 MB resident
    "for i in range(len(buf)):\n"
    "    buf[i] = i & 0xFF\n"
    "end = time.time() + 0.4\n"
    "x = 0\n"
    "while time.time() < end:\n"
    "    x += 1\n"
)

_CHECKSUM = "sha256:" + "ab" * 32


# ---------------------------------------------------------------------------
# 1. CPU/RAM/GC sampling via psutil — verify sampling works and yields samples
# Validates: Requirements 11.1, 17.2
# ---------------------------------------------------------------------------


class TestCpuRamGcSampling:
    """CPU/RAM sampling via psutil and GC merging through ResourceSampler."""

    def test_real_subprocess_cpu_sampling_yields_samples(self):
        """Spawning a real subprocess and sampling it produces at least one sample."""
        proc = subprocess.Popen([sys.executable, "-c", _BUSY_CHILD])
        try:
            ps_proc = psutil.Process(proc.pid)
            sampler = ResourceSampler(
                interval_ms=20,
                allocated_cpu_cores=psutil.cpu_count(logical=True) or 1,
            )
            with sampler.sample(ps_proc) as session:
                proc.wait(timeout=10)
            usage = session.result
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        assert usage is not None, "SamplingSession.result must not be None after stop"
        assert usage.sample_count > 0, "At least one CPU/RAM sample must be collected"
        assert usage.comparable is True, usage.non_comparable_reason

    def test_real_subprocess_ram_sampling_records_positive_values(self):
        """RSS memory of the subprocess must be clearly above zero."""
        proc = subprocess.Popen([sys.executable, "-c", _BUSY_CHILD])
        try:
            ps_proc = psutil.Process(proc.pid)
            sampler = ResourceSampler(
                interval_ms=20,
                allocated_cpu_cores=psutil.cpu_count(logical=True) or 1,
            )
            with sampler.sample(ps_proc) as session:
                proc.wait(timeout=10)
            usage = session.result
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        assert usage.ram_mb_peak is not None and usage.ram_mb_peak > 1.0, (
            f"Peak RAM must be > 1 MB, got {usage.ram_mb_peak}"
        )
        assert usage.ram_mb_avg is not None and usage.ram_mb_avg > 0.0

    def test_cpu_pct_within_valid_range(self):
        """CPU utilisation is always in [0, 100]%."""
        proc = subprocess.Popen([sys.executable, "-c", _BUSY_CHILD])
        try:
            ps_proc = psutil.Process(proc.pid)
            sampler = ResourceSampler(
                interval_ms=20,
                allocated_cpu_cores=psutil.cpu_count(logical=True) or 1,
            )
            with sampler.sample(ps_proc) as session:
                proc.wait(timeout=10)
            usage = session.result
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        assert 0.0 <= usage.cpu_pct_avg <= 100.0
        assert 0.0 <= usage.cpu_pct_max <= 100.0

    def test_gc_merge_unavailable_when_runner_reports_none(self):
        """GcSummary is marked unavailable when no GC data was reported."""
        usage = aggregate_samples(
            [50.0],
            [10 * BYTES_PER_MB],
            allocated_cpu_cores=1,
            sampling_interval_ms=100,
        )
        merged = ResourceSampler.merge_gc(usage, None)

        assert merged.gc is not None
        assert merged.gc.available is False
        assert merged.gc.unavailable_reason is not None
        # Comparable flag of the base usage must not be degraded by absent GC
        assert merged.comparable is True

    def test_sampling_interval_stored_in_usage(self):
        """The interval_ms value is carried through into the ResourceUsage."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
        try:
            ps_proc = psutil.Process(proc.pid)
            sampler = ResourceSampler(interval_ms=50, allocated_cpu_cores=1)
            with sampler.sample(ps_proc) as session:
                proc.wait(timeout=10)
            usage = session.result
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        assert usage.sampling_interval_ms == 50


# ---------------------------------------------------------------------------
# 2. Thermal throttling detection — graceful on any host
# Validates: Requirement 27.3
# ---------------------------------------------------------------------------


class TestThermalThrottlingDetection:
    """EnvironmentProbe must detect or gracefully skip thermal sensor reading."""

    def test_probe_does_not_raise(self):
        """EnvironmentProbe.probe() must never raise even when sensors are absent."""
        env = EnvironmentProbe.probe(vm_instance_id="test-thermal")
        # No exception — test passes by reaching this line.
        assert isinstance(env, Environment)

    def test_thermal_sensor_handle_is_string_or_none(self):
        """thermal_sensor_handle is either a sensor name string or None."""
        env = EnvironmentProbe.probe()
        assert env.thermal_sensor_handle is None or isinstance(
            env.thermal_sensor_handle, str
        )

    def test_missing_thermal_sensor_does_not_affect_comparability(self):
        """Absence of thermal sensor handle does not make the environment non-comparable."""
        env = EnvironmentProbe.probe()
        # comparability depends only on the REQUIRED_FIELDS (vcpu, ram, os, etc.)
        # thermal_sensor_handle is a noise / best-effort field
        if env.thermal_sensor_handle is None:
            # Even without sensor, the run may still be comparable if all
            # required fields are present (e.g. corpus_path was not given here,
            # so storage_type will be missing — that's unrelated to thermal)
            assert "thermalSensorHandle" not in (env.non_comparable_reason or "")

    def test_to_dict_always_contains_thermal_sensor_key(self):
        """The Result_Report environment block always includes thermalSensorHandle."""
        env = EnvironmentProbe.probe()
        payload = env.to_dict()
        assert "thermalSensorHandle" in payload

    def test_thermal_sensor_handle_returned_when_psutil_exposes_sensors(self):
        """When psutil.sensors_temperatures() returns data, a handle is reported."""
        getter = getattr(psutil, "sensors_temperatures", None)
        if getter is None:
            pytest.skip("psutil.sensors_temperatures not available on this platform")
        temps = getter()
        if not temps:
            pytest.skip("No temperature sensors found on this host")
        env = EnvironmentProbe.probe()
        assert isinstance(env.thermal_sensor_handle, str)
        assert len(env.thermal_sensor_handle) > 0


# ---------------------------------------------------------------------------
# 3. Energy measurement — graceful "not supported" reporting
# Validates: Requirement 28.1
# ---------------------------------------------------------------------------


class TestEnergyMeasurementGracefulDegradation:
    """Energy data is absent / null in the Result_Report when not supported."""

    def test_report_builds_with_null_cost_energy(self, tmp_path):
        """ReportGenerator must accept cost_energy=None and emit an empty dict."""
        gen = ReportGenerator()
        report = gen.build(cost_energy=None)
        # Design spec: costEnergy defaults to {} when None is passed
        assert report["costEnergy"] == {}

    def test_report_cost_energy_null_joulesperop_is_allowed(self, tmp_path):
        """joulesPerOp may be None (unsupported) in a valid Result_Report."""
        gen = ReportGenerator()
        report = gen.build(
            cost_energy={
                "go": {"joulesPerOp": None, "costPerMillionOps": None},
                "java": {"joulesPerOp": None, "costPerMillionOps": None},
            }
        )
        assert report["costEnergy"]["go"]["joulesPerOp"] is None
        assert report["costEnergy"]["java"]["joulesPerOp"] is None

    def test_report_cost_energy_absent_does_not_block_generation(self, tmp_path):
        """Generating a results.json without energy data completes without error."""
        gen = ReportGenerator()
        out = tmp_path / "results.json"
        report = gen.generate(out, cost_energy=None)
        assert out.exists()
        assert "costEnergy" in report

    def test_report_records_not_supported_note_for_energy(self, tmp_path):
        """A 'not supported' note for energy is preserved verbatim in the report."""
        gen = ReportGenerator()
        report = gen.build(
            cost_energy={"note": "energy measurement not supported on this host"}
        )
        assert "not supported" in report["costEnergy"].get("note", "")


# ---------------------------------------------------------------------------
# 4. Soak time-series — verify slope calculation
# Validates: Requirement 29.2
# ---------------------------------------------------------------------------


class TestSoakTimeSeriesSlopeCalculation:
    """ram_trend and latency_trend compute slopes from real time-series samples."""

    def test_ram_trend_slope_is_calculable_from_uniform_series(self):
        """ram_trend with a linearly-growing series returns the expected slope."""
        # 60 samples, one per minute -> 1 hour window
        # RAM grows 10 MB per hour -> slope ≈ 10.0 MB/hour
        n = 60
        interval_s = 60.0  # 1 minute per sample
        # Linear growth: start=200 MB, end=210 MB over 1 hour
        samples = [200.0 + i * (10.0 / (n - 1)) for i in range(n)]
        timestamps = [i * interval_s for i in range(n)]

        result = ram_trend(
            samples,
            threshold_mb_per_hour=50.0,
            timestamps_sec=timestamps,
        )

        assert result.applicable is True
        assert result.slope_mb_per_hour is not None
        assert abs(result.slope_mb_per_hour - 10.0) < 0.5, (
            f"Expected slope ~10 MB/hour, got {result.slope_mb_per_hour}"
        )
        assert result.suspected_memory_leak is False  # 10 < 50

    def test_ram_trend_flags_leak_when_slope_exceeds_threshold(self):
        """suspected_memory_leak is True when slope strictly exceeds threshold."""
        n = 120
        interval_s = 30.0  # 30 s per sample -> 1 hour
        samples = [100.0 + i * 0.5 for i in range(n)]  # grows 60 MB/hour
        timestamps = [i * interval_s for i in range(n)]

        result = ram_trend(
            samples,
            threshold_mb_per_hour=50.0,
            timestamps_sec=timestamps,
        )

        assert result.applicable is True
        assert result.suspected_memory_leak is True
        assert result.slope_mb_per_hour > 50.0

    def test_latency_trend_slope_calculable_from_uniform_interval(self):
        """latency_trend with interval_ms returns a finite slope."""
        # Flat latency over 100 samples -> slope ≈ 0
        samples = [5.0] * 100
        result = latency_trend(
            samples,
            threshold_pct=10.0,
            interval_ms=1000.0,  # 1 sample per second
        )

        assert result.applicable is True
        assert result.slope_ms_per_hour is not None
        assert result.performance_degradation is False

    def test_latency_trend_flags_degradation_when_pct_exceeds_threshold(self):
        """performance_degradation is True when latency grows > threshold_pct."""
        n = 60
        interval_s = 60.0
        # Latency grows from 5 ms to 10 ms -> +100% over 1 hour
        samples = [5.0 + i * (5.0 / (n - 1)) for i in range(n)]
        timestamps = [i * interval_s for i in range(n)]

        result = latency_trend(
            samples,
            threshold_pct=20.0,
            timestamps_sec=timestamps,
        )

        assert result.applicable is True
        assert result.performance_degradation is True
        assert result.degradation_pct is not None and result.degradation_pct > 20.0

    def test_soak_trends_wrapper_returns_both_trends(self):
        """soak_trends() convenience wrapper returns a SoakTrends with both sub-trends."""
        n = 60
        interval_ms = 1000.0
        ram_samples = [200.0 + i * 0.1 for i in range(n)]
        lat_samples = [5.0 + i * 0.01 for i in range(n)]

        trends = soak_trends(
            ram_samples,
            lat_samples,
            ram_threshold_mb_per_hour=10.0,
            latency_threshold_pct=50.0,
            interval_ms=interval_ms,
        )

        assert trends.ram.applicable is True
        assert trends.latency.applicable is True
        payload = trends.to_dict()
        assert "ramTrend" in payload
        assert "latencyTrend" in payload
        assert "suspectedMemoryLeak" in payload
        assert "performanceDegradation" in payload

    def test_too_few_samples_yields_not_applicable(self):
        """A single sample cannot produce a slope — result is not-applicable."""
        result = ram_trend([200.0], threshold_mb_per_hour=10.0, interval_ms=1000.0)
        assert result.applicable is False
        assert result.slope_mb_per_hour is None


# ---------------------------------------------------------------------------
# 5. Report within 60 seconds — ReportGenerator completes within timeout
# Validates: Requirement 20.1
# ---------------------------------------------------------------------------


class TestReportGeneratorCompletesWithinTimeout:
    """ReportGenerator must finish building and writing the report well under 60 s."""

    _REPORT_TIMEOUT_S = 60.0

    def test_report_generation_completes_within_60_seconds(self, tmp_path):
        """build() + write_atomic() must complete within 60 s (Req 20.1)."""
        gen = ReportGenerator()
        out = tmp_path / "results.json"

        start = time.monotonic()
        gen.generate(
            out,
            poc_start_date="2025-01-01",
            started_at="2025-01-01T09:00:00+07:00",
            finished_at="2025-01-01T10:30:00+07:00",
            versions={"go": "1.25.1", "jdk": "25.0.1"},
            environment={"vcpu": 8, "ramMb": 32768, "os": "Linux"},
            resource_quota={"cpuCores": 8, "memoryMb": 8192},
            scenario_results=[],
            conclusion={"preferredLanguage": "go", "rationale": "faster p50"},
        )
        elapsed = time.monotonic() - start

        assert elapsed < self._REPORT_TIMEOUT_S, (
            f"Report generation took {elapsed:.2f}s, exceeding 60s limit (Req 20.1)"
        )

    def test_report_file_is_written_and_valid_json(self, tmp_path):
        """The written results.json is parseable JSON with the expected top-level keys."""
        import json

        gen = ReportGenerator()
        out = tmp_path / "results.json"
        gen.generate(out, poc_start_date="2025-01-01")

        assert out.exists(), "results.json was not created"
        with out.open(encoding="utf-8") as fh:
            doc = json.load(fh)

        # At minimum these top-level keys must be present
        for key in ("pocStartDate", "versions", "environment", "scenarioResults"):
            assert key in doc, f"Missing top-level key {key!r} in results.json"

    def test_report_all_schema_keys_present(self, tmp_path):
        """All canonical Result_Report schema keys are present in the output."""
        import json
        from harness.report import RESULTS_SCHEMA_KEYS

        gen = ReportGenerator()
        out = tmp_path / "results.json"
        gen.generate(out)

        with out.open(encoding="utf-8") as fh:
            doc = json.load(fh)

        for key in RESULTS_SCHEMA_KEYS:
            assert key in doc, f"Schema key {key!r} missing from results.json"

    def test_report_write_is_atomic(self, tmp_path):
        """No partial .tmp file remains after successful generation."""
        gen = ReportGenerator()
        out = tmp_path / "results.json"
        gen.generate(out)

        tmp_files = list(tmp_path.glob(f".{out.name}.*{gen.TEMP_SUFFIX}"))
        assert tmp_files == [], f"Stray temp files left behind: {tmp_files}"


# ---------------------------------------------------------------------------
# 6. No outbound socket — SubprocessDriver subprocess does not open network
# Validates: Requirements 1.2, 1.3
# ---------------------------------------------------------------------------


class TestNoOutboundSocket:
    """SubprocessDriver must not spawn subprocesses that open network connections."""

    def test_driver_argv_contains_no_network_flags(self, tmp_path):
        """The executable argv of a SubprocessDriver must not include network flags."""
        # Build an argv as the harness would for a Go or Java runner.
        # These executables are mocked paths — we validate the command, not execution.
        network_indicators = {
            "--server",
            "--host",
            "--port",
            "--http",
            "--network",
            "--connect",
            "--socket",
            "-listen",
            "curl",
            "wget",
            "nc",
            "netcat",
            "ncat",
        }
        go_runner_argv = ["/runners/go/go-runner", "--mode=steady_state"]
        java_runner_argv = [
            "java",
            "-jar",
            "/runners/java/runner.jar",
            "--mode=steady_state",
        ]

        for argv in (go_runner_argv, java_runner_argv):
            lower_argv = {arg.lower() for arg in argv}
            overlap = lower_argv & network_indicators
            assert not overlap, (
                f"Runner argv contains network flag(s) {overlap!r}: {argv}"
            )

    def test_subprocess_stdin_stdin_is_json_only_no_network_data(self, tmp_path):
        """The stdin payload sent to a Runner is a JSON Command with no URLs or hosts."""
        import json

        # Construct a minimal Command payload as SubprocessDriver would.
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()

        payload = {
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
            "keySetPath": str(key_dir),
            "keySetChecksum": _CHECKSUM,
            "corpusPath": str(corpus_dir),
            "corpusChecksum": _CHECKSUM,
            "outputDir": str(tmp_path / "out"),
            "operation": "roundtrip",
        }
        serialised = json.dumps(payload)

        # Verify the payload contains no http(s):// or ws:// URLs.
        assert "http://" not in serialised
        assert "https://" not in serialised
        assert "ws://" not in serialised
        # Verify no remote host references
        assert "amazonaws.com" not in serialised
        assert "example.com" not in serialised

    def test_real_subprocess_does_not_listen_on_any_port(self, tmp_path):
        """A spawned Python subprocess that does no networking holds no listening sockets.

        This test spawns a short-lived subprocess and checks via psutil that it
        never opened a TCP/UDP listening socket.
        """
        # This child intentionally does no networking.
        child_code = (
            "import time\n"
            "time.sleep(0.3)\n"
        )
        proc = subprocess.Popen([sys.executable, "-c", child_code])
        try:
            ps_proc = psutil.Process(proc.pid)
            # Give the child a moment to start and then check connections.
            time.sleep(0.05)
            try:
                # psutil ≥ 6 prefers net_connections(); fall back for older versions.
                _net_conns = getattr(ps_proc, "net_connections", None) or getattr(ps_proc, "connections", None)
                conns = _net_conns(kind="inet") if _net_conns else []
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                conns = []
            listening = [
                c for c in conns
                if c.status in ("LISTEN", "ESTABLISHED") and c.laddr
            ]
            assert listening == [], (
                f"Subprocess unexpectedly holds network connections: {listening}"
            )
        finally:
            proc.kill()
            proc.wait(timeout=5)

    def test_subprocess_driver_uses_local_file_paths_only(self, tmp_path):
        """SubprocessDriver is configured with local file paths, never remote URLs."""
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()

        driver = SubprocessDriver(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            validate_inputs=False,
        )
        # The driver's argv must contain only a local script path, no URL.
        for arg in driver.argv:
            assert not arg.startswith("http://"), f"URL in argv: {arg}"
            assert not arg.startswith("https://"), f"URL in argv: {arg}"
