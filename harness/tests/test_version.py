"""Unit tests for the VersionResolver."""

import pytest

from harness.version import (
    COMPONENT_KEYS,
    ComponentVersion,
    SemVer,
    VersionResolver,
    parse_go_mod_dependency,
    parse_go_version,
    parse_gpg_version,
    parse_java_version,
    parse_maven_property,
    parse_native_image_version,
    parse_pom_dependency_version,
    parse_spring_boot_version,
    version_matches,
)

GO_VERSION_OUTPUT = "go version go1.25.1 darwin/arm64\n"
JAVA_VERSION_OUTPUT = (
    'openjdk version "25.0.1" 2025-10-21\n'
    "OpenJDK Runtime Environment (build 25.0.1+9)\n"
    "OpenJDK 64-Bit Server VM (build 25.0.1+9, mixed mode)\n"
)
JAVA_LEGACY_OUTPUT = 'java version "1.8.0_402"\n'
GPG_VERSION_OUTPUT = "gpg (GnuPG) 2.4.5\nlibgcrypt 1.10.3\n"
NATIVE_IMAGE_OUTPUT = (
    "native-image 21.0.2 2024-01-16\n"
    "GraalVM Runtime Environment Oracle GraalVM 21.0.2+13.1\n"
)

POM_XML = """<?xml version="1.0"?>
<project>
  <properties>
    <bouncycastle.version>1.78.1</bouncycastle.version>
    <spring-boot.version>4.0.0</spring-boot.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.bouncycastle</groupId>
      <artifactId>bcpg-jdk18on</artifactId>
      <version>${bouncycastle.version}</version>
    </dependency>
  </dependencies>
</project>
"""

GO_MOD = (
    "module github.com/poc-encryption/pgp-benchmark/go-runner\n\n"
    "go 1.24\n\n"
    "require (\n"
    "\tgithub.com/ProtonMail/go-crypto v1.1.6\n"
    ")\n"
)


# SemVer
@pytest.mark.parametrize(
    "text,expected",
    [
        ("1.25.1", (1, 25, 1)),
        ("25", (25, 0, 0)),
        ("2.4", (2, 4, 0)),
        ("go1.25.1 darwin", (1, 25, 1)),
    ],
)
def test_semver_parse(text, expected):
    sem = SemVer.parse(text)
    assert (sem.major, sem.minor, sem.patch) == expected


def test_semver_parse_none_when_no_digits():
    assert SemVer.parse("no version here") is None
    assert SemVer.parse(None) is None
    assert SemVer.parse("") is None


def test_parse_go_version():
    assert parse_go_version(GO_VERSION_OUTPUT) == "1.25.1"
    assert parse_go_version("go version go1.24 linux/amd64") == "1.24"
    assert parse_go_version("garbage") is None


def test_parse_java_version_modern_and_legacy():
    assert parse_java_version(JAVA_VERSION_OUTPUT) == "25.0.1"
    assert parse_java_version(JAVA_LEGACY_OUTPUT) == "1.8.0"
    assert parse_java_version('openjdk version "21"') == "21.0.0"
    assert parse_java_version("no version") is None


def test_parse_gpg_version():
    assert parse_gpg_version(GPG_VERSION_OUTPUT) == "2.4.5"
    assert parse_gpg_version("gpg (GnuPG) 2.2") == "2.2"


def test_parse_native_image_version():
    assert parse_native_image_version(NATIVE_IMAGE_OUTPUT) == "21.0.2"
    assert parse_native_image_version("GraalVM Version 22.3.0 (Java Version 17.0.5)") == "22.3.0"
    assert parse_native_image_version(None) is None


def test_parse_maven_property():
    assert parse_maven_property(POM_XML, "bouncycastle.version") == "1.78.1"
    assert parse_maven_property(POM_XML, "missing.prop") is None


def test_parse_pom_dependency_version_resolves_property():
    assert (
        parse_pom_dependency_version(POM_XML, "org.bouncycastle", "bcpg-jdk18on")
        == "1.78.1"
    )
    assert parse_pom_dependency_version(POM_XML, "org.bouncycastle", "missing") is None


def test_parse_spring_boot_version_from_property():
    assert parse_spring_boot_version(POM_XML) == "4.0.0"


def test_parse_spring_boot_version_from_parent():
    pom = """<project>
      <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.2</version>
      </parent>
    </project>"""
    assert parse_spring_boot_version(pom) == "3.3.2"


def test_parse_spring_boot_version_absent():
    assert parse_spring_boot_version("<project></project>") is None


def test_parse_go_mod_dependency_block_and_single_line():
    assert parse_go_mod_dependency(GO_MOD, "github.com/ProtonMail/go-crypto") == "1.1.6"
    single = "require github.com/ProtonMail/go-crypto v1.2.0\n"
    assert parse_go_mod_dependency(single, "github.com/ProtonMail/go-crypto") == "1.2.0"
    assert parse_go_mod_dependency(GO_MOD, "github.com/missing/mod") is None


def test_version_matches_exact():
    assert version_matches("1.25.1", "1.25.1")
    assert not version_matches("1.25.1", "1.25.2")
    assert not version_matches("1.25.1", "1.24.1")


def test_version_matches_wildcard_patch():
    assert version_matches("1.25.7", "1.25.x")
    assert version_matches("1.25.0", "1.25.*")
    assert not version_matches("1.26.0", "1.25.x")


def test_version_matches_no_expected_is_match():
    # Nothing recorded -> nothing to invalidate.
    assert version_matches("1.25.1", None)
    assert version_matches(None, None)


def test_version_matches_recorded_but_undetected_is_mismatch():
    # Recorded a version but could not detect it -> cannot confirm -> mismatch.
    assert not version_matches(None, "1.25.1")


def test_version_matches_partial_expected():
    # Expected gives only major.minor -> patch unconstrained.
    assert version_matches("25.0.5", "25.0")
    assert not version_matches("25.1.0", "25.0")


def _write_inputs(tmp_path):
    pom = tmp_path / "pom.xml"
    pom.write_text(POM_XML, encoding="utf-8")
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(GO_MOD, encoding="utf-8")
    return pom, go_mod


def _fake_runner(mapping):
    def run(args):
        key = tuple(args)
        return mapping.get(key)

    return run


def _full_runner():
    return _fake_runner(
        {
            ("go", "version"): GO_VERSION_OUTPUT,
            ("java", "-version"): JAVA_VERSION_OUTPUT,
            ("gpg", "--version"): GPG_VERSION_OUTPUT,
            ("native-image", "--version"): NATIVE_IMAGE_OUTPUT,
        }
    )


def test_resolver_detect_all(tmp_path):
    pom, go_mod = _write_inputs(tmp_path)
    resolver = VersionResolver(pom_path=pom, go_mod_path=go_mod, command_runner=_full_runner())
    detected = resolver.detect_all()
    assert detected == {
        "go": "1.25.1",
        "goCryptoLib": "1.1.6",
        "jdk": "25.0.1",
        "springBoot": "4.0.0",
        "bouncyCastle": "1.78.1",
        "graalvm": "21.0.2",
        "gpg": "2.4.5",
    }


def test_resolver_all_keys_present_in_to_dict(tmp_path):
    pom, go_mod = _write_inputs(tmp_path)
    resolver = VersionResolver(pom_path=pom, go_mod_path=go_mod, command_runner=_full_runner())
    data = resolver.resolve().to_dict()
    for key in COMPONENT_KEYS:
        assert key in data
    assert "versionMatch" in data


def test_resolver_version_match_true_when_all_recorded_match(tmp_path):
    pom, go_mod = _write_inputs(tmp_path)
    resolver = VersionResolver(pom_path=pom, go_mod_path=go_mod, command_runner=_full_runner())
    expected = {
        "go": "1.25.1",
        "goCryptoLib": "1.1.6",
        "jdk": "25.0.1",
        "springBoot": "4.0.0",
        "bouncyCastle": "1.78.1",
        "graalvm": "21.0.2",
        "gpg": "2.4.5",
    }
    report = resolver.resolve(expected)
    assert report.version_match is True
    assert report.to_dict()["versionMatch"] is True
    assert report.mismatches() == []


def test_resolver_version_match_false_on_mismatch(tmp_path):
    pom, go_mod = _write_inputs(tmp_path)
    resolver = VersionResolver(pom_path=pom, go_mod_path=go_mod, command_runner=_full_runner())
    # Record a Go version that differs from what is detected.
    report = resolver.resolve({"go": "1.24.0"})
    assert report.version_match is False
    mismatches = report.mismatches()
    assert len(mismatches) == 1
    assert mismatches[0].name == "go"
    messages = report.mismatch_messages()
    assert any("go" in m and "1.24.0" in m and "1.25.1" in m for m in messages)


def test_resolver_wildcard_expected_matches(tmp_path):
    pom, go_mod = _write_inputs(tmp_path)
    resolver = VersionResolver(pom_path=pom, go_mod_path=go_mod, command_runner=_full_runner())
    report = resolver.resolve({"go": "1.25.x", "jdk": "25.x.x"})
    assert report.version_match is True


def test_resolver_unrecorded_components_do_not_invalidate(tmp_path):
    pom, go_mod = _write_inputs(tmp_path)
    resolver = VersionResolver(pom_path=pom, go_mod_path=go_mod, command_runner=_full_runner())
    # Only Go recorded; everything else unrecorded -> still valid overall.
    report = resolver.resolve({"go": "1.25.1"})
    assert report.version_match is True


def test_resolver_graceful_when_tools_missing(tmp_path):
    pom, go_mod = _write_inputs(tmp_path)
    # Runner returns None for every command (tool not installed).
    resolver = VersionResolver(
        pom_path=pom, go_mod_path=go_mod, command_runner=_fake_runner({})
    )
    detected = resolver.detect_all()
    assert detected["go"] is None
    assert detected["jdk"] is None
    assert detected["gpg"] is None
    assert detected["graalvm"] is None
    # File-based detections still work.
    assert detected["springBoot"] == "4.0.0"
    assert detected["bouncyCastle"] == "1.78.1"
    assert detected["goCryptoLib"] == "1.1.6"


def test_resolver_recorded_but_undetected_invalidates(tmp_path):
    pom, go_mod = _write_inputs(tmp_path)
    resolver = VersionResolver(
        pom_path=pom, go_mod_path=go_mod, command_runner=_fake_runner({})
    )
    # gpg recorded but not installed -> cannot verify -> invalid round.
    report = resolver.resolve({"gpg": "2.4.5"})
    assert report.version_match is False
    comp = report.components["gpg"]
    assert comp.detected is None
    assert comp.detail is not None


def test_resolver_missing_files_degrade_gracefully(tmp_path):
    missing_pom = tmp_path / "nope" / "pom.xml"
    missing_go_mod = tmp_path / "nope" / "go.mod"
    resolver = VersionResolver(
        pom_path=missing_pom, go_mod_path=missing_go_mod, command_runner=_full_runner()
    )
    detected = resolver.detect_all()
    assert detected["springBoot"] is None
    assert detected["bouncyCastle"] is None
    assert detected["goCryptoLib"] is None
    # Tool-based detections still succeed.
    assert detected["go"] == "1.25.1"


def test_component_version_available_flag(tmp_path):
    comp = ComponentVersion(name="go", detected="1.25.1", expected=None, match=True)
    assert comp.available is True
    comp_missing = ComponentVersion(name="gpg", detected=None, expected=None, match=True)
    assert comp_missing.available is False
