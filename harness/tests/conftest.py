"""Shared fixtures providing valid example contract payloads."""

import pytest

_CHECKSUM = "sha256:" + "ab" * 32


@pytest.fixture
def valid_command_dict():
    return {
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
        "keySetPath": "/mnt/tmpfs/keys",
        "keySetChecksum": _CHECKSUM,
        "corpusPath": "/mnt/tmpfs/corpus/scenario-01",
        "corpusChecksum": _CHECKSUM,
        "outputDir": "/mnt/tmpfs/out/run-0007",
        "operation": "roundtrip",
    }


@pytest.fixture
def valid_runner_output_dict():
    return {
        "runnerId": "go",
        "variantId": "go-stream-parallel",
        "mode": "steady_state",
        "scenarioId": "small-files-rsa2048",
        "cryptoProfileId": "aes256-zlib",
        "concurrency": 4,
        "outputEncoding": "binary",
        "processStartupMs": None,
        "hardwareAccel": True,
        "keySetChecksumSeen": _CHECKSUM,
        "corpusChecksumSeen": _CHECKSUM,
        "gc": {
            "collections": 14,
            "totalPauseMs": 23.7,
            "gcType": "G1",
            "heapInitMb": 256,
            "heapMaxMb": 2048,
        },
        "operations": [
            {
                "fileName": "doc-0001.pdf",
                "fileType": ".pdf",
                "originalBytes": 845123,
                "ciphertextBytes": 612001,
                "skipped": False,
                "skipReason": None,
                "encryptMs": 1.83,
                "decryptMs": 2.04,
                "asymEncryptMs": 0.42,
                "asymDecryptMs": 0.55,
                "symEncryptMs": 1.41,
                "symDecryptMs": 1.49,
                "roundTripOk": True,
                "failureType": None,
                "outputFileName": "doc-0001.pdf.pgp",
            },
            {
                "fileName": "ignore.ctrl",
                "fileType": ".ctrl",
                "originalBytes": 10,
                "skipped": True,
                "skipReason": "control_file",
                "roundTripOk": True,
            },
        ],
        "resourceSamplesNote": "CPU/RAM sampled externally by the Harness",
    }
