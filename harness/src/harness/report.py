"""ReportGenerator: assemble and atomically write the machine-readable ``results.json``."""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "RESULTS_SCHEMA_KEYS",
    "ReportGenerator",
    "to_jsonable",
]

#: Top-level keys of the Result_Report document, in canonical report order.
RESULTS_SCHEMA_KEYS: tuple[str, ...] = (
    "pocStartDate",
    "startedAt",
    "finishedAt",
    "versions",
    "environment",
    "resourceQuota",
    "configUsed",
    "keySet",
    "keySetChecksum",
    "corpusChecksum",
    "noiseFloor",
    "interopChecks",
    "rounds",
    "scenarioResults",
    "softTrends",
    "costEnergy",
    "thermalThrottleEvents",
    "conclusion",
)


def to_jsonable(value: Any) -> Any:
    """Recursively convert ``value`` into JSON-serialisable primitives.

    Unwraps harness value objects: ``to_dict()`` objects are expanded, dataclass
    instances converted field-by-field, ``Enum`` members collapse to ``.value``,
    and mappings/iterables are converted element-wise. Anything else raises
    :class:`TypeError` so :meth:`ReportGenerator.write_atomic` fails before
    creating any file.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    # Enum -> its value (then normalise the value too).
    if isinstance(value, enum.Enum):
        return to_jsonable(value.value)

    # Prefer an explicit to_dict() contract (all harness value objects).
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_jsonable(to_dict())

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: to_jsonable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }

    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}

    # bytes are not valid JSON; surface as a clear error instead of guessing.
    if isinstance(value, (bytes, bytearray)):
        raise TypeError("bytes are not JSON-serialisable in a Result_Report")

    if isinstance(value, Iterable):
        return [to_jsonable(v) for v in value]

    raise TypeError(
        f"value of type {type(value).__name__!r} is not JSON-serialisable "
        "and exposes no to_dict()"
    )


def _section(value: Any, default: Any) -> Any:
    """Return ``default`` when ``value is None`` else the normalised ``value``."""
    if value is None:
        return default
    return to_jsonable(value)


def _list_section(value: Any) -> list[Any]:
    """Normalise an optional sequence section to a JSON list (default ``[]``)."""
    if value is None:
        return []
    normalised = to_jsonable(value)
    if isinstance(normalised, list):
        return normalised
    raise TypeError("expected a sequence section but got a non-list value")


class ReportGenerator:
    """Assemble the ``results.json`` document and write it atomically.

    The generator holds no benchmark state of its own; :meth:`build` is a pure
    function of its arguments. Construct it once and call :meth:`generate` (or
    :meth:`build` + :meth:`write_atomic`) per Benchmark_Run.
    """

    #: Suffix used while a results document is mid-write, before the atomic
    #: rename onto the final path.
    TEMP_SUFFIX = ".tmp"

    def build(
        self,
        *,
        poc_start_date: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        versions: Any = None,
        environment: Any = None,
        resource_quota: Any = None,
        config_used: Any = None,
        key_set: Any = None,
        key_set_checksum: str | None = None,
        corpus_checksum: str | None = None,
        noise_floor: Any = None,
        interop_checks: Any = None,
        rounds: Any = None,
        scenario_results: Any = None,
        soft_trends: Any = None,
        cost_energy: Any = None,
        thermal_throttle_events: Any = None,
        conclusion: Any = None,
    ) -> dict[str, Any]:
        """Compose the full Result_Report ``dict``.

        Every argument is optional. Inputs may be plain JSON values or harness
        value objects exposing ``to_dict()`` (see :func:`to_jsonable`). A few
        inputs accept convenience forms:

        * ``key_set`` — either a sequence of key records or a
          :class:`~harness.keys.KeySetManifest` (whose ``to_dict()`` carries the
          ``keySet`` array and ``keySetChecksum``; both are lifted to the top
          level so the caller need not pass ``key_set_checksum`` separately).
        * ``interop_checks`` — either the bare ``[{producer,consumer,result}]``
          list, or an :class:`~harness.interop.InteropSummary` whose
          ``to_dict()`` nests the array under ``interopChecks``.
        """
        key_set_array, lifted_checksum = self._normalise_key_set(key_set)
        report: dict[str, Any] = {
            "pocStartDate": poc_start_date,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "versions": _section(versions, {}),
            "environment": _section(environment, {}),
            "resourceQuota": _section(resource_quota, {}),
            "configUsed": _section(config_used, {}),
            "keySet": key_set_array,
            "keySetChecksum": key_set_checksum
            if key_set_checksum is not None
            else lifted_checksum,
            "corpusChecksum": corpus_checksum,
            "noiseFloor": _section(noise_floor, None),
            "interopChecks": self._normalise_interop(interop_checks),
            "rounds": _list_section(rounds),
            "scenarioResults": _list_section(scenario_results),
            "softTrends": _section(soft_trends, {}),
            "costEnergy": _section(cost_energy, {}),
            "thermalThrottleEvents": _list_section(thermal_throttle_events),
            "conclusion": _section(conclusion, None),
        }
        return report

    def generate(self, path: str | os.PathLike[str], **build_kwargs: Any) -> dict[str, Any]:
        """Build the report and write it atomically to ``path``.

        Returns the assembled ``dict`` so callers can reuse it without
        re-reading the file.
        """
        report = self.build(**build_kwargs)
        self.write_atomic(path, report)
        return report

    def write_atomic(
        self,
        path: str | os.PathLike[str],
        report: Mapping[str, Any],
        *,
        indent: int | None = 2,
    ) -> Path:
        """Serialise ``report`` and write it atomically to ``path``.

        The document is fully serialised first (a non-serialisable value raises
        before any file is touched), written to a uniquely-named temp file in
        the target's directory, flushed and ``fsync``-ed, then ``os.replace``-d
        onto the target. A crash can only leave the temp file behind (cleaned
        up), never a partial ``results.json``.
        """
        target = Path(path)

        # Serialise everything up front (may raise -> no file touched).
        payload = json.dumps(to_jsonable(report), indent=indent, ensure_ascii=False)

        target.parent.mkdir(parents=True, exist_ok=True)

        # Write to a temp file in the same directory.
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=self.TEMP_SUFFIX,
            dir=str(target.parent),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            # Atomic rename onto the target.
            os.replace(tmp_path, target)
        except BaseException:
            # Never leave a stray temp file behind on failure.
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise
        return target

    # Input normalisation helpers
    @staticmethod
    def _normalise_key_set(key_set: Any) -> tuple[list[Any], str | None]:
        """Return ``(keySet array, keySetChecksum|None)`` from flexible input."""
        if key_set is None:
            return [], None

        normalised = to_jsonable(key_set)
        if isinstance(normalised, Mapping):
            array = normalised.get("keySet", [])
            if not isinstance(array, list):
                raise TypeError("'keySet' inside a manifest must be a list")
            checksum = normalised.get("keySetChecksum")
            return list(array), checksum
        if isinstance(normalised, list):
            return normalised, None
        raise TypeError(
            "key_set must be a sequence of key records or a manifest mapping"
        )

    @staticmethod
    def _normalise_interop(interop_checks: Any) -> list[Any]:
        """Return the bare ``interopChecks`` array from flexible input."""
        if interop_checks is None:
            return []
        normalised = to_jsonable(interop_checks)
        if isinstance(normalised, Mapping):
            array = normalised.get("interopChecks", [])
            if not isinstance(array, list):
                raise TypeError("'interopChecks' must be a list")
            return list(array)
        if isinstance(normalised, list):
            return normalised
        raise TypeError(
            "interop_checks must be a list or an InteropSummary mapping"
        )
