"""Unit tests for the EnvironmentProbe."""

import platform

import pytest

from harness.environment import Environment, EnvironmentProbe, REQUIRED_FIELDS


def _complete_env(**overrides) -> Environment:
    base = dict(
        vcpu=8,
        ram_mb=8192,
        os="Linux",
        os_version="Ubuntu 24.04 LTS",
        cpu_arch="x86_64",
        storage_type="tmpfs",
        turbo_boost="off",
        cpu_governor="performance",
        aes_ni=True,
        thermal_sensor_handle="coretemp",
        vm_instance_id="vmid-122",
    )
    base.update(overrides)
    return Environment(**base)


def test_fully_recorded_environment_is_comparable():
    env = _complete_env()
    assert env.comparable is True
    assert env.missing_fields() == ()
    assert env.non_comparable_reason is None


@pytest.mark.parametrize("attr,schema_key", list(REQUIRED_FIELDS))
def test_missing_any_required_field_marks_non_comparable(attr, schema_key):
    env = _complete_env(**{attr: None})
    assert env.comparable is False
    assert schema_key in env.missing_fields()
    assert schema_key in env.non_comparable_reason


def test_multiple_missing_fields_all_named():
    env = _complete_env(vcpu=None, storage_type=None)
    missing = env.missing_fields()
    assert missing == ("vcpu", "storageType")
    reason = env.non_comparable_reason
    assert "vcpu" in reason and "storageType" in reason


def test_missing_noise_fields_do_not_break_comparability():
    env = _complete_env(
        turbo_boost=None,
        cpu_governor=None,
        aes_ni=None,
        thermal_sensor_handle=None,
    )
    assert env.comparable is True
    assert env.non_comparable_reason is None


# Serialisation (Result_Report environment block)
def test_to_dict_has_expected_keys_and_values():
    payload = _complete_env().to_dict()
    expected_keys = {
        "vmInstanceId",
        "vcpu",
        "ramMb",
        "os",
        "osVersion",
        "cpuArch",
        "storageType",
        "turboBoost",
        "cpuGovernor",
        "aesNi",
        "thermalSensorHandle",
        "comparable",
        "nonComparableReason",
    }
    assert set(payload) == expected_keys
    assert payload["vcpu"] == 8
    assert payload["storageType"] == "tmpfs"
    assert payload["aesNi"] is True
    assert payload["comparable"] is True
    assert payload["nonComparableReason"] is None


def test_to_dict_missing_required_is_null_and_flags_non_comparable():
    payload = _complete_env(ram_mb=None).to_dict()
    assert payload["ramMb"] is None
    assert payload["comparable"] is False
    assert "ramMb" in payload["nonComparableReason"]


def test_to_dict_unavailable_noise_fields():
    payload = _complete_env(
        turbo_boost=None,
        cpu_governor=None,
        aes_ni=None,
        thermal_sensor_handle=None,
    ).to_dict()
    assert payload["turboBoost"] == "unavailable"
    assert payload["cpuGovernor"] == "unavailable"
    assert payload["aesNi"] is None
    assert payload["thermalSensorHandle"] is None


# Live probe — must not raise and must read the always-available basics.
def test_probe_records_core_machine_fields():
    env = EnvironmentProbe.probe(vm_instance_id="test-vm")
    # vCPU, RAM, OS, version and CPU arch are available on any supported host.
    assert isinstance(env.vcpu, int) and env.vcpu >= 1
    assert isinstance(env.ram_mb, int) and env.ram_mb > 0
    assert env.os == platform.system()
    assert env.os_version is not None
    assert env.cpu_arch == platform.machine()
    assert env.vm_instance_id == "test-vm"
    # aes_ni is either a definite bool capability or None (undetectable).
    assert env.aes_ni in (True, False, None)


def test_probe_detects_storage_type_for_given_path(tmp_path):
    env = EnvironmentProbe.probe(corpus_path=str(tmp_path))
    # On this host the temp dir lives on a real filesystem we can name.
    assert env.storage_type is not None
    assert env.comparable is True


def test_probe_without_corpus_path_is_non_comparable_for_storage():
    env = EnvironmentProbe.probe()
    assert env.storage_type is None
    assert env.comparable is False
    assert "storageType" in env.non_comparable_reason
