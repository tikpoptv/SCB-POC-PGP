"""Unit tests for the ConfigLoader and config.json validation rules (Task 2.1)."""

import json

import pytest

from harness.config import (
    BenchmarkConfig,
    ConfigError,
    ConfigLoader,
    DataCompressibility,
    FileSizeTier,
    KeyType,
    MemoryMode,
    OutputEncoding,
    RunMode,
)

VCPU = 8


@pytest.fixture
def valid_config_dict():
    """A complete, valid config covering RSA + ECC specs and several scenarios."""
    return {
        "rounds": 50,
        "warmupIterations": 5,
        "seed": 123456789,
        "samplingIntervalMs": 100,
        "resultDir": "./results",
        "corpusOnTmpfs": True,
        "stabilityThresholdCV": 0.05,
        "confidenceLevel": 0.95,
        "bestVariantCriterion": "p50_roundtrip",
        "cryptoProfiles": [
            {"id": "aes256-zlib", "pubAlg": "RSA-2048", "cipher": "AES-256",
             "compression": "ZLIB", "hash": "SHA-256"},
            {"id": "chacha20", "pubAlg": "RSA-2048", "cipher": "CHACHA20",
             "compression": "NONE", "hash": "SHA-256"},
        ],
        "keySpecs": [
            {"type": "RSA", "bits": 2048},
            {"type": "RSA", "bits": 4096},
            {"type": "ECC", "curve": "Curve25519"},
        ],
        "scenarios": [
            {
                "id": "small-files-rsa2048",
                "fileSizeTier": "small",
                "customSizeBytes": None,
                "keySpec": {"type": "RSA", "bits": 2048},
                "concurrency": 4,
                "memoryMode": "both",
                "cryptoProfileId": "aes256-zlib",
                "dataCompressibility": "both",
                "outputEncoding": "binary",
                "memoryQuotaMb": 2048,
            },
            {
                "id": "custom-ecc",
                "fileSizeTier": "custom",
                "customSizeBytes": 4096,
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
        "nullTest": {"enabled": True, "runner": "go"},
        "soakTest": {"enabled": False, "durationSec": 3600, "totalOperations": None,
                     "ramLeakThresholdMbPerHour": 50, "latencyDegradationThresholdPct": 10},
    }


@pytest.fixture
def loader():
    return ConfigLoader(vcpu=VCPU)


# Happy path
def test_loads_valid_config(loader, valid_config_dict):
    cfg = loader.load_dict(valid_config_dict)
    assert isinstance(cfg, BenchmarkConfig)
    assert cfg.rounds == 50
    assert cfg.warmup_iterations == 5
    assert cfg.sampling_interval_ms == 100
    assert cfg.vcpu == VCPU
    assert len(cfg.crypto_profiles) == 2
    assert cfg.crypto_profiles[0].profile.cipher == "AES-256"
    assert len(cfg.key_specs) == 3
    assert cfg.key_specs[0].type is KeyType.RSA and cfg.key_specs[0].bits == 2048
    assert cfg.key_specs[2].type is KeyType.ECC and cfg.key_specs[2].curve == "Curve25519"
    assert cfg.modes == (RunMode.COLD_START, RunMode.STEADY_STATE)

    s0, s1 = cfg.scenarios
    assert s0.file_size_tier is FileSizeTier.SMALL
    assert s0.output_encoding is OutputEncoding.BINARY
    assert s0.memory_mode is MemoryMode.BOTH
    assert s0.data_compressibility is DataCompressibility.BOTH
    assert s1.file_size_tier is FileSizeTier.CUSTOM
    assert s1.custom_size_bytes == 4096
    assert s1.output_encoding is OutputEncoding.ARMORED


def test_loads_from_text(loader, valid_config_dict):
    cfg = loader.load_text(json.dumps(valid_config_dict))
    assert cfg.rounds == 50


def test_loads_from_file(tmp_path, loader, valid_config_dict):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(valid_config_dict), encoding="utf-8")
    cfg = loader.load_file(p)
    assert cfg.rounds == 50


def test_effective_values_echoes_used_parameters(loader, valid_config_dict):
    cfg = loader.load_dict(valid_config_dict)
    eff = cfg.effective_values()
    assert eff["rounds"] == 50
    assert eff["warmupIterations"] == 5
    assert eff["samplingIntervalMs"] == 100
    assert eff["seed"] == 123456789
    assert eff["vCPU"] == VCPU
    assert eff["modes"] == ["cold_start", "steady_state"]
    # Round-trippable JSON so it can be written verbatim into the Result_Report.
    assert json.loads(json.dumps(eff))["scenarios"][1]["customSizeBytes"] == 4096


def test_optional_fields_get_defaults(loader, valid_config_dict):
    for key in ("resultDir", "corpusOnTmpfs", "stabilityThresholdCV",
                "confidenceLevel", "bestVariantCriterion", "nullTest", "soakTest"):
        valid_config_dict.pop(key, None)
    cfg = loader.load_dict(valid_config_dict)
    assert cfg.result_dir == "./results"
    assert cfg.corpus_on_tmpfs is True
    assert cfg.confidence_level == 0.95
    assert cfg.best_variant_criterion == "p50_roundtrip"
    assert cfg.null_test.enabled is False
    assert cfg.soak_test.enabled is False


# Range validation: rounds (8.2/8.3), warmup (8.6), samplingIntervalMs (11.1)
@pytest.mark.parametrize("rounds", [0, -1, 1001, 5000])
def test_rejects_rounds_out_of_range(loader, valid_config_dict, rounds):
    valid_config_dict["rounds"] = rounds
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "rounds"


@pytest.mark.parametrize("rounds", [1, 1000])
def test_accepts_rounds_boundaries(loader, valid_config_dict, rounds):
    valid_config_dict["rounds"] = rounds
    assert loader.load_dict(valid_config_dict).rounds == rounds


def test_rejects_non_integer_rounds(loader, valid_config_dict):
    valid_config_dict["rounds"] = 50.0
    with pytest.raises(ConfigError, match="rounds"):
        loader.load_dict(valid_config_dict)


def test_rejects_bool_rounds(loader, valid_config_dict):
    valid_config_dict["rounds"] = True
    with pytest.raises(ConfigError, match="rounds"):
        loader.load_dict(valid_config_dict)


@pytest.mark.parametrize("warmup", [-1, 101])
def test_rejects_warmup_out_of_range(loader, valid_config_dict, warmup):
    valid_config_dict["warmupIterations"] = warmup
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "warmupIterations"


@pytest.mark.parametrize("warmup", [0, 100])
def test_accepts_warmup_boundaries(loader, valid_config_dict, warmup):
    valid_config_dict["warmupIterations"] = warmup
    assert loader.load_dict(valid_config_dict).warmup_iterations == warmup


@pytest.mark.parametrize("interval", [9, 1001, 0])
def test_rejects_sampling_interval_out_of_range(loader, valid_config_dict, interval):
    valid_config_dict["samplingIntervalMs"] = interval
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "samplingIntervalMs"


@pytest.mark.parametrize("interval", [10, 1000])
def test_accepts_sampling_interval_boundaries(loader, valid_config_dict, interval):
    valid_config_dict["samplingIntervalMs"] = interval
    assert loader.load_dict(valid_config_dict).sampling_interval_ms == interval


@pytest.mark.parametrize("concurrency", [0, -1, VCPU + 1, 100])
def test_rejects_concurrency_out_of_range(loader, valid_config_dict, concurrency):
    valid_config_dict["scenarios"][0]["concurrency"] = concurrency
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "scenarios[0].concurrency"


@pytest.mark.parametrize("concurrency", [1, VCPU])
def test_accepts_concurrency_boundaries(loader, valid_config_dict, concurrency):
    valid_config_dict["scenarios"][0]["concurrency"] = concurrency
    cfg = loader.load_dict(valid_config_dict)
    assert cfg.scenarios[0].concurrency == concurrency


@pytest.mark.parametrize("size", [0, -1, -4096])
def test_rejects_nonpositive_custom_size(loader, valid_config_dict, size):
    valid_config_dict["scenarios"][1]["customSizeBytes"] = size
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "scenarios[1].customSizeBytes"


def test_rejects_missing_custom_size_when_tier_custom(loader, valid_config_dict):
    valid_config_dict["scenarios"][1]["customSizeBytes"] = None
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "scenarios[1].customSizeBytes"


# Closed enums: outputEncoding (4.7), dataCompressibility (30.4), fileSizeTier
def test_rejects_invalid_output_encoding(loader, valid_config_dict):
    valid_config_dict["scenarios"][0]["outputEncoding"] = "base64"
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "scenarios[0].outputEncoding"


def test_rejects_invalid_data_compressibility(loader, valid_config_dict):
    valid_config_dict["scenarios"][0]["dataCompressibility"] = "maybe"
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "scenarios[0].dataCompressibility"


def test_rejects_invalid_file_size_tier(loader, valid_config_dict):
    valid_config_dict["scenarios"][0]["fileSizeTier"] = "humongous"
    with pytest.raises(ConfigError, match="fileSizeTier"):
        loader.load_dict(valid_config_dict)


def test_rejects_invalid_mode(loader, valid_config_dict):
    valid_config_dict["modes"] = ["cold_start", "turbo"]
    with pytest.raises(ConfigError, match=r"modes\[1\]"):
        loader.load_dict(valid_config_dict)


def test_rejects_incomplete_crypto_profile(loader, valid_config_dict):
    del valid_config_dict["cryptoProfiles"][0]["cipher"]
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "cryptoProfiles[0].cipher"


def test_rejects_blank_crypto_profile_field(loader, valid_config_dict):
    valid_config_dict["cryptoProfiles"][0]["hash"] = "  "
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "cryptoProfiles[0].hash"


def test_rejects_rsa_keyspec_without_bits(loader, valid_config_dict):
    valid_config_dict["keySpecs"][0] = {"type": "RSA"}
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "keySpecs[0].bits"


def test_rejects_ecc_keyspec_without_curve(loader, valid_config_dict):
    valid_config_dict["keySpecs"][2] = {"type": "ECC"}
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "keySpecs[2].curve"


def test_rejects_unknown_key_type(loader, valid_config_dict):
    valid_config_dict["keySpecs"][0] = {"type": "DSA", "bits": 2048}
    with pytest.raises(ConfigError, match="keySpecs"):
        loader.load_dict(valid_config_dict)


@pytest.mark.parametrize(
    "field", ["rounds", "warmupIterations", "seed", "samplingIntervalMs",
              "cryptoProfiles", "keySpecs", "scenarios", "modes"],
)
def test_rejects_missing_required_top_level_field(loader, valid_config_dict, field):
    del valid_config_dict[field]
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert field in exc.value.parameter


def test_rejects_scenario_referencing_unknown_profile(loader, valid_config_dict):
    valid_config_dict["scenarios"][0]["cryptoProfileId"] = "does-not-exist"
    with pytest.raises(ConfigError) as exc:
        loader.load_dict(valid_config_dict)
    assert exc.value.parameter == "scenarios[0].cryptoProfileId"


def test_rejects_empty_scenarios(loader, valid_config_dict):
    valid_config_dict["scenarios"] = []
    with pytest.raises(ConfigError, match="scenarios"):
        loader.load_dict(valid_config_dict)


def test_rejects_duplicate_profile_ids(loader, valid_config_dict):
    valid_config_dict["cryptoProfiles"][1]["id"] = "aes256-zlib"
    with pytest.raises(ConfigError, match="id"):
        loader.load_dict(valid_config_dict)


def test_rejects_non_object_top_level(loader):
    with pytest.raises(ConfigError, match="config.json"):
        loader.load_dict([1, 2, 3])


def test_rejects_invalid_json_text(loader):
    with pytest.raises(ConfigError, match="invalid JSON"):
        loader.load_text("{not json")


def test_invalid_config_file_does_not_create_result_dir(tmp_path):
    """A bad config raises before any run; the loader never touches resultDir."""
    result_dir = tmp_path / "results"
    bad = {"rounds": 99999}  # out of range + incomplete
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({**bad, "resultDir": str(result_dir)}), encoding="utf-8")

    with pytest.raises(ConfigError):
        ConfigLoader(vcpu=VCPU).load_file(cfg_path)

    assert not result_dir.exists()


def test_loader_rejects_invalid_vcpu():
    with pytest.raises(ConfigError, match="vCPU"):
        ConfigLoader(vcpu=0)
