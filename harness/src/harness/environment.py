"""EnvironmentProbe — record the VM environment for each Benchmark_Run."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass

__all__ = ["Environment", "EnvironmentProbe", "REQUIRED_FIELDS"]


# (attribute name, Result_Report schema key) for the fields required for a run
# to be comparable. Order is the reporting order.
REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("vcpu", "vcpu"),
    ("ram_mb", "ramMb"),
    ("os", "os"),
    ("os_version", "osVersion"),
    ("cpu_arch", "cpuArch"),
    ("storage_type", "storageType"),
)

_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Environment:
    """A captured VM environment snapshot.

    Comparability-critical fields are ``None`` when they could not be recorded;
    :attr:`comparable` is then ``False`` and :attr:`non_comparable_reason` names
    what is missing.
    """

    # Comparability-critical
    vcpu: int | None = None
    ram_mb: int | None = None
    os: str | None = None
    os_version: str | None = None
    cpu_arch: str | None = None
    storage_type: str | None = None
    # Noise-control / capability (best effort)
    turbo_boost: str | None = None  # "on" | "off" | None(unknown)
    cpu_governor: str | None = None
    aes_ni: bool | None = None  # CPU supports AES-NI / ARM AES crypto extension
    thermal_sensor_handle: str | None = None
    vm_instance_id: str | None = None

    def missing_fields(self) -> tuple[str, ...]:
        """Schema keys of comparability-critical fields that were not recorded."""
        return tuple(
            schema_key
            for attr, schema_key in REQUIRED_FIELDS
            if getattr(self, attr) is None
        )

    @property
    def comparable(self) -> bool:
        """True when every comparability-critical field is present."""
        return not self.missing_fields()

    @property
    def non_comparable_reason(self) -> str | None:
        """Human-readable reason naming the missing data, or ``None`` if complete."""
        missing = self.missing_fields()
        if not missing:
            return None
        return "environment incomplete: missing " + ", ".join(missing)

    def to_dict(self) -> dict[str, object]:
        """Render the Result_Report ``environment`` block.

        Comparability-critical fields are emitted as ``null`` when missing.
        Best-effort noise fields degrade to ``"unavailable"`` (turbo/governor)
        or ``null`` (aesNi/thermalSensorHandle) when unknown.
        """
        return {
            "vmInstanceId": self.vm_instance_id,
            "vcpu": self.vcpu,
            "ramMb": self.ram_mb,
            "os": self.os,
            "osVersion": self.os_version,
            "cpuArch": self.cpu_arch,
            "storageType": self.storage_type,
            "turboBoost": self.turbo_boost if self.turbo_boost is not None else _UNAVAILABLE,
            "cpuGovernor": self.cpu_governor if self.cpu_governor is not None else _UNAVAILABLE,
            "aesNi": self.aes_ni,
            "thermalSensorHandle": self.thermal_sensor_handle,
            "comparable": self.comparable,
            "nonComparableReason": self.non_comparable_reason,
        }

    @classmethod
    def probe(
        cls,
        *,
        corpus_path: str | None = None,
        vm_instance_id: str | None = None,
    ) -> "Environment":
        """Capture the current VM environment (best effort, never raises).

        ``corpus_path`` is used to detect the storage type of the filesystem
        that holds the Test_Corpus; when omitted, storage type is left
        unrecorded and the run becomes non-comparable.
        """
        return cls(
            vcpu=_probe_vcpu(),
            ram_mb=_probe_ram_mb(),
            os=_probe_os_name(),
            os_version=_probe_os_version(),
            cpu_arch=_probe_cpu_arch(),
            storage_type=_probe_storage_type(corpus_path),
            turbo_boost=_probe_turbo_boost(),
            cpu_governor=_probe_cpu_governor(),
            aes_ni=_probe_aes_ni(),
            thermal_sensor_handle=_probe_thermal_sensor_handle(),
            vm_instance_id=vm_instance_id,
        )


# EnvironmentProbe is an alias: the design refers to the component by that name.
EnvironmentProbe = Environment


# Individual readings — each returns None on any failure (never raises).
def _probe_vcpu() -> int | None:
    try:
        import psutil

        n = psutil.cpu_count(logical=True)
        if n:
            return int(n)
    except Exception:
        pass
    try:
        n = os.cpu_count()
        return int(n) if n else None
    except Exception:
        return None


def _probe_ram_mb() -> int | None:
    try:
        import psutil

        return int(psutil.virtual_memory().total // (1024 * 1024))
    except Exception:
        return None


def _probe_os_name() -> str | None:
    try:
        return platform.system() or None
    except Exception:
        return None


def _probe_os_version() -> str | None:
    try:
        if platform.system() == "Linux" and hasattr(platform, "freedesktop_os_release"):
            try:
                info = platform.freedesktop_os_release()
                name = info.get("NAME")
                version = info.get("VERSION") or info.get("VERSION_ID")
                if name and version:
                    return f"{name} {version}"
            except Exception:
                pass
        return platform.release() or None
    except Exception:
        return None


def _probe_cpu_arch() -> str | None:
    try:
        return platform.machine() or None
    except Exception:
        return None


def _probe_storage_type(path: str | None) -> str | None:
    """Detect the filesystem type backing ``path`` (e.g. ``tmpfs``, ``apfs``)."""
    if not path:
        return None
    try:
        import psutil

        target = os.path.realpath(path)
        best = None
        for part in psutil.disk_partitions(all=True):
            mount = part.mountpoint
            if not mount:
                continue
            normalized = mount.rstrip("/") or "/"
            if target == mount or target == normalized or target.startswith(normalized + "/") or mount == "/":
                if best is None or len(part.mountpoint) > len(best.mountpoint):
                    best = part
        if best is not None and best.fstype:
            return best.fstype
    except Exception:
        return None
    return None


def _probe_turbo_boost() -> str | None:
    """Read CPU turbo-boost state from sysfs (Linux). None when unknown."""
    try:
        no_turbo = "/sys/devices/system/cpu/intel_pstate/no_turbo"
        if os.path.exists(no_turbo):
            with open(no_turbo, encoding="ascii") as fh:
                return "off" if fh.read().strip() == "1" else "on"
        boost = "/sys/devices/system/cpu/cpufreq/boost"
        if os.path.exists(boost):
            with open(boost, encoding="ascii") as fh:
                return "on" if fh.read().strip() == "1" else "off"
    except Exception:
        return None
    return None


def _probe_cpu_governor() -> str | None:
    try:
        governor = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        if os.path.exists(governor):
            with open(governor, encoding="ascii") as fh:
                return fh.read().strip() or None
    except Exception:
        return None
    return None


def _probe_aes_ni() -> bool | None:
    """Detect CPU AES-NI / ARM AES capability by reading CPU feature flags."""
    system = platform.system()
    try:
        if system == "Linux":
            with open("/proc/cpuinfo", encoding="ascii", errors="ignore") as fh:
                for line in fh:
                    lowered = line.lower()
                    if lowered.startswith("flags") or lowered.startswith("features"):
                        return "aes" in lowered.split()
            return None
        if system == "Darwin":
            intel = _sysctl("machdep.cpu.features")
            if intel is not None:
                if "AES" in intel.upper().split():
                    return True
                # An Intel Mac that reports features but no AES.
                arm = _sysctl("hw.optional.arm.FEAT_AES")
                return arm == "1" if arm is not None else False
            arm = _sysctl("hw.optional.arm.FEAT_AES")
            if arm is not None:
                return arm == "1"
            return None
    except Exception:
        return None
    return None


def _probe_thermal_sensor_handle() -> str | None:
    """Return a handle (sensor name) for the CPU thermal sensor, if exposed."""
    try:
        import psutil

        getter = getattr(psutil, "sensors_temperatures", None)
        if getter is None:
            return None
        temps = getter()
        if not temps:
            return None
        for preferred in ("coretemp", "cpu_thermal", "k10temp", "acpitz", "cpu-thermal"):
            if preferred in temps:
                return preferred
        return next(iter(temps.keys()))
    except Exception:
        return None


def _sysctl(name: str) -> str | None:
    """Run ``sysctl -n <name>`` (macOS); return stripped output or None."""
    try:
        result = subprocess.run(
            ["sysctl", "-n", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            out = result.stdout.strip()
            return out if out else None
    except Exception:
        return None
    return None
