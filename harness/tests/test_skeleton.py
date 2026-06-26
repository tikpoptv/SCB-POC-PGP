"""Smoke test confirming the harness package and its core dependencies import."""


def test_package_imports():
    import harness

    assert harness.__version__ == "0.1.0"


def test_core_dependencies_available():
    import numpy  # noqa: F401
    import scipy  # noqa: F401
    import psutil  # noqa: F401
