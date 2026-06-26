"""Detect and validate toolchain/library versions against recorded values."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

__all__ = [
    "SemVer",
    "ComponentVersion",
    "VersionReport",
    "VersionResolver",
    "COMPONENT_KEYS",
    "version_matches",
    "parse_go_version",
    "parse_java_version",
    "parse_gpg_version",
    "parse_native_image_version",
    "parse_maven_property",
    "parse_pom_dependency_version",
    "parse_spring_boot_version",
    "parse_go_mod_dependency",
]

# Component keys, in the order they appear in the Result_Report schema.
COMPONENT_KEYS: tuple[str, ...] = (
    "go",
    "goCryptoLib",
    "jdk",
    "springBoot",
    "bouncyCastle",
    "graalvm",
    "gpg",
)

_GO_CRYPTO_MODULE = "github.com/ProtonMail/go-crypto"
_SEMVER_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_WILDCARD = {"x", "X", "*", ""}


@dataclass(frozen=True)
class SemVer:
    """A coarse ``major.minor.patch`` view of a version string."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str | None) -> "SemVer | None":
        """Extract the first ``major[.minor[.patch]]`` run from ``text``."""
        if not text:
            return None
        match = _SEMVER_RE.search(text)
        if not match:
            return None
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) is not None else 0
        patch = int(match.group(3)) if match.group(3) is not None else 0
        return cls(major, minor, patch)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.major}.{self.minor}.{self.patch}"


def version_matches(detected: str | None, expected: str | None) -> bool:
    """Return whether ``detected`` satisfies the ``expected`` version."""
    if expected is None:
        return True
    if detected is None:
        return False

    det = SemVer.parse(detected)
    if det is None:
        return False

    det_segments = (det.major, det.minor, det.patch)
    exp_segments = expected.strip().split(".")
    for index in range(min(len(exp_segments), 3)):
        segment = exp_segments[index].strip()
        if segment in _WILDCARD:
            continue
        digits = re.match(r"\d+", segment)
        if not digits:
            # Non-numeric, non-wildcard segment: treat as wildcard rather than
            # failing on suffixes such as "1.78.1-beta".
            continue
        if int(digits.group()) != det_segments[index]:
            return False
    return True


# Pure parsers (testable against captured output / file contents)
def parse_go_version(text: str | None) -> str | None:
    """Parse ``go version go1.25.1 darwin/arm64`` -> ``"1.25.1"``."""
    if not text:
        return None
    match = re.search(r"go(\d+\.\d+(?:\.\d+)?)", text)
    return match.group(1) if match else None


def parse_java_version(text: str | None) -> str | None:
    """Parse ``java -version`` output -> normalized version string."""
    if not text:
        return None
    match = re.search(r'version\s+"([^"]+)"', text)
    if not match:
        return None
    raw = match.group(1)
    # Legacy "1.8.0_402" -> drop the build suffix after '_'.
    raw = raw.split("_", 1)[0]
    sem = SemVer.parse(raw)
    return str(sem) if sem else None


def parse_gpg_version(text: str | None) -> str | None:
    """Parse ``gpg (GnuPG) 2.4.5`` -> ``"2.4.5"``."""
    if not text:
        return None
    match = re.search(r"gpg\s+\([^)]*\)\s+(\d+\.\d+(?:\.\d+)?)", text)
    if match:
        return match.group(1)
    # Fallback: first version-looking token on the first line.
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    sem = SemVer.parse(first_line)
    return str(sem) if sem else None


def parse_native_image_version(text: str | None) -> str | None:
    """Parse ``native-image --version`` output -> GraalVM version string."""
    if not text:
        return None
    match = re.search(r"native-image\s+(\d+\.\d+(?:\.\d+)?)", text)
    if match:
        return match.group(1)
    match = re.search(r"GraalVM\s+Version\s+(\d+\.\d+(?:\.\d+)?)", text)
    if match:
        return match.group(1)
    sem = SemVer.parse(text)
    return str(sem) if sem else None


def parse_maven_property(pom_xml: str | None, property_name: str) -> str | None:
    """Return the text of ``<property_name>...</property_name>`` from a POM."""
    if not pom_xml:
        return None
    match = re.search(
        rf"<{re.escape(property_name)}>\s*([^<\s]+)\s*</{re.escape(property_name)}>",
        pom_xml,
    )
    return match.group(1) if match else None


def parse_pom_dependency_version(
    pom_xml: str | None, group_id: str, artifact_id: str
) -> str | None:
    """Return the resolved ``<version>`` for a ``groupId``/``artifactId`` dep.

    A ``${property}`` placeholder version is resolved against the POM's
    ``<properties>`` block when possible.
    """
    if not pom_xml:
        return None
    for dep in re.findall(r"<dependency>(.*?)</dependency>", pom_xml, re.DOTALL):
        if (
            re.search(rf"<groupId>\s*{re.escape(group_id)}\s*</groupId>", dep)
            and re.search(rf"<artifactId>\s*{re.escape(artifact_id)}\s*</artifactId>", dep)
        ):
            version_match = re.search(r"<version>\s*([^<]+?)\s*</version>", dep)
            if not version_match:
                return None
            value = version_match.group(1).strip()
            prop = re.fullmatch(r"\$\{([^}]+)\}", value)
            if prop:
                return parse_maven_property(pom_xml, prop.group(1))
            return value
    return None


def parse_spring_boot_version(pom_xml: str | None) -> str | None:
    """Best-effort detection of the Spring Boot version from a POM."""
    if not pom_xml:
        return None

    prop = parse_maven_property(pom_xml, "spring-boot.version")
    if prop:
        return prop

    parent_match = re.search(r"<parent>(.*?)</parent>", pom_xml, re.DOTALL)
    if parent_match:
        parent = parent_match.group(1)
        if re.search(r"<artifactId>\s*spring-boot-starter-parent\s*</artifactId>", parent):
            version_match = re.search(r"<version>\s*([^<]+?)\s*</version>", parent)
            if version_match:
                value = version_match.group(1).strip()
                prop = re.fullmatch(r"\$\{([^}]+)\}", value)
                if prop:
                    return parse_maven_property(pom_xml, prop.group(1))
                return value

    for dep in re.findall(r"<dependency>(.*?)</dependency>", pom_xml, re.DOTALL):
        if re.search(r"<groupId>\s*org\.springframework\.boot\s*</groupId>", dep):
            version_match = re.search(r"<version>\s*([^<]+?)\s*</version>", dep)
            if version_match:
                value = version_match.group(1).strip()
                prop = re.fullmatch(r"\$\{([^}]+)\}", value)
                if prop:
                    return parse_maven_property(pom_xml, prop.group(1))
                return value
    return None


def parse_go_mod_dependency(go_mod: str | None, module_path: str) -> str | None:
    """Return the version of ``module_path`` from a ``go.mod`` (without ``v``)."""
    if not go_mod:
        return None
    pattern = re.compile(
        rf"^\s*(?:require\s+)?{re.escape(module_path)}\s+v(\d+\.\d+(?:\.\d+)?)",
        re.MULTILINE,
    )
    match = pattern.search(go_mod)
    return match.group(1) if match else None


@dataclass(frozen=True)
class ComponentVersion:
    """Detection + validation outcome for one component."""

    name: str
    detected: str | None
    expected: str | None
    match: bool
    detail: str | None = None

    @property
    def available(self) -> bool:
        return self.detected is not None


@dataclass(frozen=True)
class VersionReport:
    """Aggregate version detection/validation result."""

    components: Mapping[str, ComponentVersion]
    version_match: bool

    def mismatches(self) -> list[ComponentVersion]:
        """Components that were recorded but do not match the detected value."""
        return [
            comp
            for comp in self.components.values()
            if comp.expected is not None and not comp.match
        ]

    def mismatch_messages(self) -> list[str]:
        """Human-readable messages for each mismatch."""
        messages: list[str] = []
        for comp in self.mismatches():
            detected = comp.detected if comp.detected is not None else "not detected"
            messages.append(
                f"version mismatch for {comp.name}: recorded {comp.expected!r} "
                f"but detected {detected!r}"
                + (f" ({comp.detail})" if comp.detail else "")
            )
        return messages

    def to_dict(self) -> dict[str, object]:
        """Serialize to the ``results.json['versions']`` shape."""
        data: dict[str, object] = {
            key: self.components[key].detected for key in COMPONENT_KEYS
        }
        data["versionMatch"] = self.version_match
        return data


CommandRunner = Callable[[Sequence[str]], "str | None"]


def _default_command_runner(args: Sequence[str]) -> str | None:
    """Run ``args`` and return combined stdout+stderr, or ``None`` if missing.

    Many tools (notably ``java -version``) print their version banner to
    stderr, so both streams are combined for parsing.
    """
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{proc.stdout}\n{proc.stderr}"


def _read_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _repo_root() -> Path:
    # version.py -> harness -> src -> harness(project) -> repo root
    return Path(__file__).resolve().parents[3]


class VersionResolver:
    """Detect actual component versions and validate against recorded values."""

    def __init__(
        self,
        pom_path: Path | str | None = None,
        go_mod_path: Path | str | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        root = _repo_root()
        self.pom_path = (
            Path(pom_path) if pom_path is not None else root / "runners" / "java" / "pom.xml"
        )
        self.go_mod_path = (
            Path(go_mod_path) if go_mod_path is not None else root / "runners" / "go" / "go.mod"
        )
        self._run = command_runner or _default_command_runner

    def detect_go(self) -> str | None:
        return parse_go_version(self._run(["go", "version"]))

    def detect_jdk(self) -> str | None:
        return parse_java_version(self._run(["java", "-version"]))

    def detect_gpg(self) -> str | None:
        return parse_gpg_version(self._run(["gpg", "--version"]))

    def detect_graalvm(self) -> str | None:
        return parse_native_image_version(self._run(["native-image", "--version"]))

    def detect_spring_boot(self) -> str | None:
        return parse_spring_boot_version(_read_text(self.pom_path))

    def detect_bouncy_castle(self) -> str | None:
        pom = _read_text(self.pom_path)
        # Prefer the explicit property, fall back to the bcpg dependency.
        return parse_maven_property(pom, "bouncycastle.version") or parse_pom_dependency_version(
            pom, "org.bouncycastle", "bcpg-jdk18on"
        )

    def detect_go_crypto(self) -> str | None:
        return parse_go_mod_dependency(_read_text(self.go_mod_path), _GO_CRYPTO_MODULE)

    def detect_all(self) -> dict[str, str | None]:
        """Detect every component; values are ``None`` when not detectable."""
        return {
            "go": self.detect_go(),
            "goCryptoLib": self.detect_go_crypto(),
            "jdk": self.detect_jdk(),
            "springBoot": self.detect_spring_boot(),
            "bouncyCastle": self.detect_bouncy_castle(),
            "graalvm": self.detect_graalvm(),
            "gpg": self.detect_gpg(),
        }

    def resolve(self, expected: Mapping[str, str | None] | None = None) -> VersionReport:
        """Detect all components and compare against ``expected``.

        Components absent from ``expected`` (or mapped to ``None``) impose no
        constraint. ``version_match`` is ``False`` when any recorded component
        does not match what was detected.
        """
        expected = dict(expected or {})
        detected = self.detect_all()

        components: dict[str, ComponentVersion] = {}
        overall_match = True
        for key in COMPONENT_KEYS:
            exp = expected.get(key)
            det = detected.get(key)
            matched = version_matches(det, exp)
            detail: str | None = None
            if exp is not None and det is None:
                detail = "tool/source not available for verification"
            if exp is not None and not matched:
                overall_match = False
            components[key] = ComponentVersion(
                name=key,
                detected=det,
                expected=exp,
                match=matched,
                detail=detail,
            )

        return VersionReport(components=components, version_match=overall_match)
