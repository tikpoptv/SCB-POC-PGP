"""Deterministic Test_Corpus generator keyed by seed and plan."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "Compressibility",
    "SizeTier",
    "Classification",
    "SUPPORTED_EXTENSIONS",
    "SKIP_EXTENSIONS",
    "INMEM_CAP_BYTES",
    "DEFAULT_CHUNK_BYTES",
    "SMALL_MAX_BYTES",
    "MEDIUM_MAX_BYTES",
    "MANY_SMALL_MAX_BYTES",
    "MANY_SMALL_MIN_FILES",
    "file_extension",
    "classify_file",
    "output_name",
    "classify_size_tier",
    "should_stream",
    "default_compressibility",
    "FileSpec",
    "CorpusFile",
    "CorpusManifest",
    "generate_corpus",
    "build_plan",
]


#: Real file types the benchmark encrypts.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".xlsx", ".xls", ".csv", ".pdf", ".zip", ".7z", ".dat", ".gz"}
)

#: File types that must be skipped (never encrypted).
SKIP_EXTENSIONS: frozenset[str] = frozenset({".ctrl", ".ctl"})

#: Size-tier boundaries in bytes.
SMALL_MAX_BYTES: int = 1 * 1024 * 1024  # 1 MiB
MEDIUM_MAX_BYTES: int = 100 * 1024 * 1024  # 100 MiB
MANY_SMALL_MAX_BYTES: int = 1 * 1024 * 1024  # each many-small file <= 1 MiB
MANY_SMALL_MIN_FILES: int = 1000

#: Advisory in-memory cap (~256 MiB); files larger than this should be streamed.
INMEM_CAP_BYTES: int = 256 * 1024 * 1024

#: Fixed write/hash chunk size; keeps generator peak memory bounded.
DEFAULT_CHUNK_BYTES: int = 1 * 1024 * 1024  # 1 MiB

# Magic-byte prefixes so binary container types look like the real thing. They
# count toward the requested size and never change the deterministic tail.
_MAGIC: dict[str, bytes] = {
    ".pdf": b"%PDF-1.7\n",
    ".zip": b"PK\x03\x04",
    ".xlsx": b"PK\x03\x04",  # xlsx is a zip container
    ".gz": b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03",
    ".7z": b"7z\xbc\xaf\x27\x1c",
    ".xls": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # OLE2 compound document
}

# Compressed/container formats are incompressible by nature; text-ish formats
# compress well. Used only as defaults by :func:`build_plan`; a FileSpec may
# override compressibility explicitly.
_INCOMPRESSIBLE_DEFAULT: frozenset[str] = frozenset({".zip", ".gz", ".7z", ".xlsx", ".dat"})

# Small fixed vocabulary -> highly compressible repetitive text.
_VOCAB: tuple[str, ...] = (
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
    "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
)


class Compressibility(str, Enum):
    """Whether file content is intended to compress well."""

    COMPRESSIBLE = "compressible"
    INCOMPRESSIBLE = "incompressible"


class SizeTier(str, Enum):
    """File size tiers reported separately in the Result_Report."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    MANY_SMALL = "many_small"


class Classification(str, Enum):
    """How a file name maps onto the file-type rules."""

    SUPPORTED = "supported"
    SKIP = "skip"
    UNSUPPORTED = "unsupported"


def file_extension(name: str) -> str:
    """Return the lower-cased extension of ``name`` including the dot."""
    suffix = Path(name).suffix
    return suffix.lower()


def classify_file(name: str) -> Classification:
    """Classify ``name`` as supported, skip (``.ctrl``/``.ctl``), or unsupported."""
    ext = file_extension(name)
    if ext in SKIP_EXTENSIONS:
        return Classification.SKIP
    if ext in SUPPORTED_EXTENSIONS:
        return Classification.SUPPORTED
    return Classification.UNSUPPORTED


def output_name(name: str) -> str:
    """Return the encrypted output name for a supported file.

    The original extension is preserved and ``.pgp`` is appended. Raises
    ``ValueError`` for files that are not supported.
    """
    if classify_file(name) is not Classification.SUPPORTED:
        raise ValueError(f"{name!r} is not a supported file type; it has no encrypted output")
    return name + ".pgp"


def classify_size_tier(size_bytes: int) -> SizeTier:
    """Map a byte size to its size tier.

    ``MANY_SMALL`` is a grouping rather than a size band, so it is not returned
    here; callers that build a many-small group label those files explicitly.
    """
    if size_bytes <= SMALL_MAX_BYTES:
        return SizeTier.SMALL
    if size_bytes <= MEDIUM_MAX_BYTES:
        return SizeTier.MEDIUM
    return SizeTier.LARGE


def should_stream(size_bytes: int, cap_bytes: int = INMEM_CAP_BYTES) -> bool:
    """Return True when a file exceeds the in-memory cap and needs streaming."""
    return size_bytes > cap_bytes


def default_compressibility(name: str) -> Compressibility:
    """Default compressibility for a file type; overridable per file."""
    ext = file_extension(name)
    if ext in _INCOMPRESSIBLE_DEFAULT:
        return Compressibility.INCOMPRESSIBLE
    return Compressibility.COMPRESSIBLE


@dataclass(frozen=True)
class FileSpec:
    """A single planned corpus file.

    ``name`` is a path relative to the corpus root and may contain
    subdirectories. ``size_bytes`` is the exact output size. ``tier`` defaults
    to the size-derived tier; pass it explicitly to label a many-small group.
    """

    name: str
    size_bytes: int
    compressibility: Compressibility
    tier: SizeTier | None = None

    def resolved_tier(self) -> SizeTier:
        return self.tier if self.tier is not None else classify_size_tier(self.size_bytes)


@dataclass(frozen=True)
class CorpusFile:
    """One file as written, with its recorded checksum."""

    relative_path: str
    file_type: str
    size_bytes: int
    tier: SizeTier
    compressibility: Compressibility
    sha256: str
    classification: Classification
    skipped: bool
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "relativePath": self.relative_path,
            "fileType": self.file_type,
            "sizeBytes": self.size_bytes,
            "tier": self.tier.value,
            "compressibility": self.compressibility.value,
            "sha256": self.sha256,
            "classification": self.classification.value,
            "skipped": self.skipped,
            "skipReason": self.skip_reason,
        }


@dataclass(frozen=True)
class CorpusManifest:
    """Manifest describing a generated corpus and its checksums."""

    seed: int
    root: str
    files: tuple[CorpusFile, ...]
    corpus_checksum: str  # "sha256:<hex>" aggregate over all files

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "root": self.root,
            "corpusChecksum": self.corpus_checksum,
            "files": [f.to_dict() for f in self.files],
        }


def _seed_int(seed: int, name: str) -> int:
    """Derive a stable per-file PRNG seed from the corpus seed and file name."""
    digest = hashlib.sha256(f"{seed}\x00{name}".encode("utf-8")).digest()
    return int.from_bytes(digest, "big")


def _compressible_block(rng: random.Random, length: int) -> bytes:
    """Build a deterministic, highly repetitive text block of ``length`` bytes."""
    if length <= 0:
        return b""
    words = [rng.choice(_VOCAB) for _ in range(64)]
    paragraph = (" ".join(words) + "\n").encode("ascii")
    # Tile the paragraph to fill the requested length exactly.
    reps = (length // len(paragraph)) + 1
    return (paragraph * reps)[:length]


def _iter_content(
    name: str,
    size_bytes: int,
    compressibility: Compressibility,
    seed: int,
    chunk_size: int,
) -> Iterable[bytes]:
    """Yield the deterministic byte content of a file in chunks.

    A type-specific magic prefix is emitted first (counting toward
    ``size_bytes``); the remainder is compressible text or pseudo-random bytes.
    """
    if size_bytes < 0:
        raise ValueError(f"size_bytes must be >= 0, got {size_bytes}")

    ext = file_extension(name)
    magic = _MAGIC.get(ext, b"")[:size_bytes]
    if magic:
        yield magic
    remaining = size_bytes - len(magic)
    if remaining <= 0:
        return

    rng = random.Random(_seed_int(seed, name))

    if compressibility is Compressibility.INCOMPRESSIBLE:
        while remaining > 0:
            take = min(chunk_size, remaining)
            yield rng.randbytes(take)
            remaining -= take
        return

    # Compressible: tile a deterministic repetitive block.
    block = _compressible_block(rng, min(chunk_size, max(remaining, 1)))
    if not block:  # pragma: no cover - block is non-empty when remaining > 0
        block = b"\x00"
    offset = 0
    while remaining > 0:
        if offset >= len(block):
            offset = 0
        end = min(offset + remaining, len(block))
        piece = block[offset:end]
        yield piece
        remaining -= len(piece)
        offset = end


def _write_file(
    path: Path,
    spec: FileSpec,
    seed: int,
    chunk_size: int,
) -> str:
    """Write one file deterministically in chunks; return its SHA-256 hex."""
    hasher = hashlib.sha256()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        for chunk in _iter_content(spec.name, spec.size_bytes, spec.compressibility, seed, chunk_size):
            fh.write(chunk)
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_corpus(
    specs: Sequence[FileSpec],
    dest_dir: str | Path,
    seed: int,
    *,
    chunk_size: int = DEFAULT_CHUNK_BYTES,
) -> CorpusManifest:
    """Generate a Test_Corpus deterministically and return its manifest.

    Files are written under ``dest_dir`` using each spec's ``name`` as a path
    relative to that directory. The same ``seed`` and ``specs`` always produce
    byte-identical files. A SHA-256 checksum is recorded per file plus one
    aggregate corpus checksum. ``.ctrl``/``.ctl`` files are still generated but
    are marked ``skipped`` in the manifest.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")

    root = Path(dest_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    # Reject duplicate names early — they would make the corpus ambiguous and
    # break the deterministic aggregate checksum.
    seen: set[str] = set()
    for spec in specs:
        if spec.name in seen:
            raise ValueError(f"duplicate file name in corpus plan: {spec.name!r}")
        seen.add(spec.name)

    files: list[CorpusFile] = []
    for spec in specs:
        if spec.size_bytes < 0:
            raise ValueError(f"{spec.name!r}: size_bytes must be >= 0, got {spec.size_bytes}")

        target = root / spec.name
        digest = _write_file(target, spec, seed, chunk_size)

        classification = classify_file(spec.name)
        skipped = classification is not Classification.SUPPORTED
        skip_reason: str | None = None
        if classification is Classification.SKIP:
            skip_reason = "control_file"
        elif classification is Classification.UNSUPPORTED:
            skip_reason = "unsupported"

        files.append(
            CorpusFile(
                relative_path=spec.name,
                file_type=file_extension(spec.name),
                size_bytes=spec.size_bytes,
                tier=spec.resolved_tier(),
                compressibility=spec.compressibility,
                sha256=digest,
                classification=classification,
                skipped=skipped,
                skip_reason=skip_reason,
            )
        )

    corpus_checksum = _aggregate_checksum(files)
    return CorpusManifest(
        seed=seed,
        root=str(root),
        files=tuple(files),
        corpus_checksum=corpus_checksum,
    )


def _aggregate_checksum(files: Iterable[CorpusFile]) -> str:
    """Compute a single deterministic checksum over every file.

    The aggregate hashes ``relativePath\\0sha256\\n`` lines in sorted path order
    so it is independent of generation order and changes if any file changes.
    """
    hasher = hashlib.sha256()
    for f in sorted(files, key=lambda x: x.relative_path):
        hasher.update(f.relative_path.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(f.sha256.encode("ascii"))
        hasher.update(b"\n")
    return "sha256:" + hasher.hexdigest()


def build_plan(
    seed: int,
    *,
    small_types: Sequence[str] = (".txt", ".csv", ".pdf", ".dat"),
    medium_types: Sequence[str] = (".txt", ".zip"),
    large_types: Sequence[str] = (".dat",),
    small_size: int = 64 * 1024,
    medium_size: int = 8 * 1024 * 1024,
    large_size: int = 128 * 1024 * 1024,
    many_small_count: int = MANY_SMALL_MIN_FILES,
    many_small_size: int = 4 * 1024,
    many_small_type: str = ".txt",
    include_skip_files: bool = True,
) -> list[FileSpec]:
    """Build a representative, 8 GB-friendly corpus plan deterministically.

    Sizes default to modest values so the whole corpus fits comfortably on a
    tmpfs of ~2 GB. Callers can scale individual tiers up. Every tier includes
    both compressible and incompressible coverage via the chosen type mix. The
    plan is a pure function of its arguments.
    """
    specs: list[FileSpec] = []

    for i, ext in enumerate(small_types):
        name = f"small/small-{i:02d}{ext}"
        specs.append(
            FileSpec(name, small_size, default_compressibility(name), SizeTier.SMALL)
        )

    for i, ext in enumerate(medium_types):
        name = f"medium/medium-{i:02d}{ext}"
        specs.append(
            FileSpec(name, medium_size, default_compressibility(name), SizeTier.MEDIUM)
        )

    for i, ext in enumerate(large_types):
        name = f"large/large-{i:02d}{ext}"
        specs.append(
            FileSpec(name, large_size, default_compressibility(name), SizeTier.LARGE)
        )

    if many_small_size > MANY_SMALL_MAX_BYTES:
        raise ValueError(
            f"many_small_size {many_small_size} exceeds the {MANY_SMALL_MAX_BYTES}-byte cap"
        )
    for i in range(many_small_count):
        name = f"many-small/file-{i:05d}{many_small_type}"
        specs.append(
            FileSpec(
                name,
                many_small_size,
                default_compressibility(name),
                SizeTier.MANY_SMALL,
            )
        )

    if include_skip_files:
        # One skip file of each skip extension so Runners can prove they skip.
        for ext in sorted(SKIP_EXTENSIONS):
            name = f"skip/control{ext}"
            specs.append(FileSpec(name, small_size, Compressibility.COMPRESSIBLE, SizeTier.SMALL))

    return specs
