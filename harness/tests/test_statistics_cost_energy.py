"""Unit tests for StatisticsEngine cost / energy calc (task 8.18)."""

import pytest

from harness.statistics_engine import (
    ENERGY_UNSUPPORTED_REASON,
    MS_PER_HOUR,
    OPS_PER_MILLION,
    CostEnergyRecord,
    cost_energy_record,
    cost_per_million_ops,
)


# Constants
def test_unit_constants():
    assert MS_PER_HOUR == 3_600_000
    assert OPS_PER_MILLION == 1_000_000


def test_cost_reference_value():
    # 3.6 ms/op = 1e-6 vCPU·hours/op. At $0.04 per vCPU·hour, one million ops
    # cost 1e-6 * 0.04 * 1_000_000 = 0.04.
    assert cost_per_million_ops(3.6, 0.04) == pytest.approx(0.04)


def test_cost_scales_with_vcpus():
    one = cost_per_million_ops(3.6, 0.04, vcpus=1)
    four = cost_per_million_ops(3.6, 0.04, vcpus=4)
    assert four == pytest.approx(4 * one)


def test_cost_is_deterministic():
    # Same inputs -> identical output every call (no hidden state / randomness).
    a = cost_per_million_ops(12.5, 0.083, vcpus=2)
    b = cost_per_million_ops(12.5, 0.083, vcpus=2)
    assert a == b


def test_cost_proportional_to_mean_time():
    base = cost_per_million_ops(5.0, 0.05)
    doubled = cost_per_million_ops(10.0, 0.05)
    assert doubled == pytest.approx(2 * base)


def test_cost_proportional_to_rate():
    base = cost_per_million_ops(5.0, 0.05)
    doubled = cost_per_million_ops(5.0, 0.10)
    assert doubled == pytest.approx(2 * base)


def test_cost_zero_when_time_zero():
    assert cost_per_million_ops(0.0, 0.04) == 0.0


def test_cost_zero_when_rate_zero():
    assert cost_per_million_ops(3.6, 0.0) == 0.0


def test_cost_always_non_negative():
    assert cost_per_million_ops(1.0, 0.01) >= 0.0


def test_cost_rejects_negative_mean_time():
    with pytest.raises(ValueError):
        cost_per_million_ops(-1.0, 0.04)


def test_cost_rejects_negative_rate():
    with pytest.raises(ValueError):
        cost_per_million_ops(3.6, -0.04)


def test_cost_rejects_negative_vcpus():
    with pytest.raises(ValueError):
        cost_per_million_ops(3.6, 0.04, vcpus=-1)


def test_record_energy_unsupported_records_null_with_reason():
    rec = cost_energy_record(3.6, 0.04, binary_size_mb=12.0, idle_ram_mb=48.0)
    assert isinstance(rec, CostEnergyRecord)
    assert rec.joules_per_op is None
    assert rec.energy_supported is False
    assert rec.energy_reason == ENERGY_UNSUPPORTED_REASON
    assert rec.cost_per_million_ops == pytest.approx(0.04)
    assert rec.binary_size_mb == 12.0
    assert rec.idle_ram_mb == 48.0


def test_record_energy_supported_keeps_joules_and_clears_reason():
    rec = cost_energy_record(
        3.6, 0.04, joules_per_op=0.012, binary_size_mb=12.0, idle_ram_mb=48.0
    )
    assert rec.joules_per_op == 0.012
    assert rec.energy_supported is True
    assert rec.energy_reason is None


def test_record_custom_unsupported_reason_preserved():
    rec = cost_energy_record(3.6, 0.04, energy_reason="no RAPL access in VM")
    assert rec.joules_per_op is None
    assert rec.energy_reason == "no RAPL access in VM"


def test_record_missing_sizes_are_none():
    rec = cost_energy_record(3.6, 0.04)
    assert rec.binary_size_mb is None
    assert rec.idle_ram_mb is None


def test_record_rejects_negative_joules():
    with pytest.raises(ValueError):
        cost_energy_record(3.6, 0.04, joules_per_op=-0.1)


def test_record_to_dict_shape():
    rec = cost_energy_record(
        3.6, 0.04, joules_per_op=0.5, binary_size_mb=12.0, idle_ram_mb=48.0
    )
    d = rec.to_dict()
    assert d == {
        "joulesPerOp": 0.5,
        "costPerMillionOps": pytest.approx(0.04),
        "binarySizeMb": 12.0,
        "idleRamMb": 48.0,
        "energyReason": None,
    }


def test_record_to_dict_unsupported_energy():
    rec = cost_energy_record(3.6, 0.04)
    d = rec.to_dict()
    assert d["joulesPerOp"] is None
    assert d["energyReason"] == ENERGY_UNSUPPORTED_REASON
    assert d["costPerMillionOps"] == pytest.approx(0.04)
