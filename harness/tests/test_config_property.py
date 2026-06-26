"""Property-based tests for ConfigLoader validation (Task 2.2).

# Feature: pgp-encryption-benchmark-go-java, Property 16: การ validate config ปฏิเสธค่าผิดและหยุดก่อนสร้าง Result_Report
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness.config import BenchmarkConfig, ConfigError, ConfigLoader

VCPU = 8

VALID_OUTPUT_ENCODINGS = ("binary", "armored")
VALID_DATA_COMPRESSIBILITY = ("compressible", "incompressible", "both")
VALID_MEMORY_MODES = ("in_memory", "streaming", "both")
VALID_TIERS = ("small", "medium", "large", "many_small")  # non-custom tiers


def _base_config(
    *,
    rounds: int,
    warmup: int,
    sampling: int,
    concurrency: int,
    custom_size: int,
    output_encoding: str,
    data_compressibility: str,
    memory_mode: str,
    tier: str,
) -> dict[str, Any]:
    """A complete, valid config parameterised by the values under test."""
    return {
        "rounds": rounds,
        "warmupIterations": warmup,
        "seed": 123456789,
        "samplingIntervalMs": sampling,
        "resultDir": "./results",
        "cryptoProfiles": [
            {"id": "aes256-zlib", "pubAlg": "RSA-2048", "cipher": "AES-256",
             "compression": "ZLIB", "hash": "SHA-256"},
            {"id": "chacha20", "pubAlg": "RSA-2048", "cipher": "CHACHA20",
             "compression": "NONE", "hash": "SHA-256"},
        ],
        "keySpecs": [
            {"type": "RSA", "bits": 2048},
            {"type": "ECC", "curve": "Curve25519"},
        ],
        "scenarios": [
            {
                "id": "scenario-0",
                "fileSizeTier": tier,
                "customSizeBytes": None,
                "keySpec": {"type": "RSA", "bits": 2048},
                "concurrency": concurrency,
                "memoryMode": memory_mode,
                "cryptoProfileId": "aes256-zlib",
                "dataCompressibility": data_compressibility,
                "outputEncoding": output_encoding,
                "memoryQuotaMb": 2048,
            },
            {
                "id": "scenario-1-custom",
                "fileSizeTier": "custom",
                "customSizeBytes": custom_size,
                "keySpec": {"type": "ECC", "curve": "Curve25519"},
                "concurrency": 1,
                "memoryMode": "streaming",
                "cryptoProfileId": "chacha20",
                "dataCompressibility": "incompressible",
                "outputEncoding": "armored",
                "memoryQuotaMb": 1024,
            },
        ],
        "modes": ["cold_start", "steady_state"],
    }


# Strategies for the legal domain of each field
_valid_rounds = st.integers(min_value=1, max_value=1000)
_valid_warmup = st.integers(min_value=0, max_value=100)
_valid_sampling = st.integers(min_value=10, max_value=1000)
_valid_concurrency = st.integers(min_value=1, max_value=VCPU)
_valid_custom_size = st.integers(min_value=1, max_value=10_000_000)


@st.composite
def valid_config(draw: st.DrawFn) -> dict[str, Any]:
    return _base_config(
        rounds=draw(_valid_rounds),
        warmup=draw(_valid_warmup),
        sampling=draw(_valid_sampling),
        concurrency=draw(_valid_concurrency),
        custom_size=draw(_valid_custom_size),
        output_encoding=draw(st.sampled_from(VALID_OUTPUT_ENCODINGS)),
        data_compressibility=draw(st.sampled_from(VALID_DATA_COMPRESSIBILITY)),
        memory_mode=draw(st.sampled_from(VALID_MEMORY_MODES)),
        tier=draw(st.sampled_from(VALID_TIERS)),
    )


def _fresh_valid(draw: st.DrawFn) -> dict[str, Any]:
    """A valid config built from in-range random values, ready to be mutated."""
    return draw(valid_config())


# Integers explicitly outside the closed range [low, high].
def _out_of_range(low: int, high: int) -> st.SearchStrategy[int]:
    below = st.integers(max_value=low - 1)
    above = st.integers(min_value=high + 1)
    return st.one_of(below, above)


# A string that is NOT one of the allowed enum members.
def _bad_enum(allowed: tuple[str, ...]) -> st.SearchStrategy[str]:
    return st.text(min_size=0, max_size=12).filter(lambda s: s not in allowed)


@st.composite
def invalid_config(draw: st.DrawFn) -> tuple[dict[str, Any], str]:
    """A valid config with exactly ONE field corrupted.

    Returns the corrupted config plus the parameter name the loader must flag.
    Because only a single field is invalid, the offending parameter is
    deterministic regardless of validation order.
    """
    cfg = _fresh_valid(draw)
    kind = draw(st.sampled_from([
        "rounds",
        "warmup",
        "sampling",
        "concurrency",
        "custom_size",
        "output_encoding",
        "data_compressibility",
        "missing_profile_field",
        "rsa_missing_bits",
        "ecc_missing_curve",
        "missing_top_level",
    ]))

    if kind == "rounds":
        cfg["rounds"] = draw(_out_of_range(1, 1000))
        return cfg, "rounds"
    if kind == "warmup":
        cfg["warmupIterations"] = draw(_out_of_range(0, 100))
        return cfg, "warmupIterations"
    if kind == "sampling":
        cfg["samplingIntervalMs"] = draw(_out_of_range(10, 1000))
        return cfg, "samplingIntervalMs"
    if kind == "concurrency":
        cfg["scenarios"][0]["concurrency"] = draw(_out_of_range(1, VCPU))
        return cfg, "scenarios[0].concurrency"
    if kind == "custom_size":
        cfg["scenarios"][1]["customSizeBytes"] = draw(st.integers(max_value=0))
        return cfg, "scenarios[1].customSizeBytes"
    if kind == "output_encoding":
        cfg["scenarios"][0]["outputEncoding"] = draw(_bad_enum(VALID_OUTPUT_ENCODINGS))
        return cfg, "scenarios[0].outputEncoding"
    if kind == "data_compressibility":
        cfg["scenarios"][0]["dataCompressibility"] = draw(_bad_enum(VALID_DATA_COMPRESSIBILITY))
        return cfg, "scenarios[0].dataCompressibility"
    if kind == "missing_profile_field":
        field = draw(st.sampled_from(["pubAlg", "cipher", "compression", "hash"]))
        del cfg["cryptoProfiles"][0][field]
        return cfg, f"cryptoProfiles[0].{field}"
    if kind == "rsa_missing_bits":
        cfg["keySpecs"][0] = {"type": "RSA"}
        return cfg, "keySpecs[0].bits"
    if kind == "ecc_missing_curve":
        cfg["keySpecs"][1] = {"type": "ECC"}
        return cfg, "keySpecs[1].curve"
    # missing_top_level
    field = draw(st.sampled_from([
        "rounds", "warmupIterations", "seed", "samplingIntervalMs",
        "cryptoProfiles", "keySpecs", "scenarios", "modes",
    ]))
    del cfg[field]
    return cfg, field


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(case=invalid_config())
def test_invalid_config_rejected_names_param_and_writes_no_report(case):
    cfg, expected_param = case
    loader = ConfigLoader(vcpu=VCPU)

    # Point resultDir at a path that does not exist yet, then load from a file so
    # any filesystem side effect (a created Result_Report) would be observable.
    with tempfile.TemporaryDirectory() as tmp:
        result_dir = Path(tmp) / "results"
        cfg["resultDir"] = str(result_dir)
        cfg_path = Path(tmp) / "config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

        with pytest.raises(ConfigError) as exc:
            loader.load_file(cfg_path)

        assert exc.value.parameter == expected_param
        assert not result_dir.exists()


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(cfg=valid_config())
def test_valid_config_passes_validation(cfg):
    loader = ConfigLoader(vcpu=VCPU)
    parsed = loader.load_dict(cfg)
    assert isinstance(parsed, BenchmarkConfig)
    assert 1 <= parsed.rounds <= 1000
    assert 0 <= parsed.warmup_iterations <= 100
    assert 10 <= parsed.sampling_interval_ms <= 1000
    for scenario in parsed.scenarios:
        assert 1 <= scenario.concurrency <= VCPU
